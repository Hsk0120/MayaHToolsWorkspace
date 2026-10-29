"""skinClusterのinfluenceと、先頭Meshの頂点ウェイトを照会・編集する。

"""

import json
import math
from collections.abc import Mapping
from decimal import Decimal, localcontext, ROUND_FLOOR

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

from ..core.fastWrite import require_range, require_writable, set_attr
from ..core.object import Object
from ..decorator import _edit_context, _require_bool, preservedSelection, undoChunk
from ..maths import easing
from ..util import _world_space
from .dagNode import DagNode
from .joint import Joint
from .node import Node, Nodes


class SkinCluster(Node):
    """skinClusterを参照し、influenceと先頭出力Meshの頂点ウェイトを照会・編集する。

    構築時の先頭geometry名・DAGパスと、自身のMFnSkinClusterを保持する。
    頂点操作はそのgeometryがMeshであることを前提とし、複数geometryの一括編集は行わない。
    influenceObjects()の物理順と、weights[]への書込みに使う論理番号を区別する。
    """

    _LAYER_TOKENS = ("ngskin", "ngst", "ngskintools", "skinlayer", "skinninglayer", "layerdata")
    _MIRROR_PLANES = ("XY", "YZ", "XZ")
    _SURFACE_ASSOCIATIONS = ("closestPoint", "rayCast", "closestComponent")
    _INFLUENCE_ASSOCIATIONS = ("closestJoint", "closestBone", "label", "name", "oneToOne")

    def __init__(self, skinCluster):
        """skinCluster 名または Maya オブジェクトからラッパーを初期化する。

        取得専用で、新規バインドは :meth:`bind` を使う。先頭 geometry のみを保持する。
        頂点ウェイト操作ではその geometry が mesh であることを前提とする。

        Args:
            skinCluster (str | om2.MObject | om2.MDagPath): skinCluster の名前または API オブジェクト。

        Returns:
            None: 値を返さない。

        Raises:
            IndexError: 対象 geometry がない場合。
            RuntimeError: geometry を解決できない場合。
        """
        super().__init__(skinCluster)
        self.mesh = self._first_geometry_name()
        self.mesh_path = self._geometry_dag_path(self.mesh)
        # 内部の照会で使い回す。公開の取得口は毎回新しく作る mfn()。
        self._skin_fn = oma2.MFnSkinCluster(self.mnode())

    @classmethod
    @undoChunk("mlibSkinClusterBind")
    def bind(cls, mesh, influences, maxInfluences=4):
        """未スキニングの形状を指定influenceへバインドする。

        Args:
            mesh (str | Node): Mayaがバインド可能な形状またはtransform。
            influences (Sequence[str | Node]): バインドする骨等のtransform。
            maxInfluences (int): 1頂点に割り当てる最大数。正の整数。

        Returns:
            SkinCluster: 作成したskinCluster。
        """
        mesh = Node(mesh)
        influences = [Node(n) for n in Nodes._resolve_inputs(influences)]
        if not influences or type(maxInfluences) is not int or maxInfluences < 1:
            raise ValueError("Expected influences and a positive maximum influence count")
        if SkinCluster._geometry_skin_uuids(mesh):
            raise ValueError("Geometry already has a skinCluster")
        return cls(cmds.skinCluster([n.getFullName() for n in influences], mesh.getFullName(),
                                   toSelectedBones=True, maximumInfluences=maxInfluences,
                                   normalizeWeights=1)[0])

    def mfn(self):
        """このskinClusterのMFnSkinClusterを、呼び出すたびに新しく作って返す。

        ``oma2.MFnSkinCluster`` は ``om2.MFnDependencyNode`` の派生で、:meth:`Node.mfn` の契約どおり
        内部で使い回す function set とは共有しない。

        Returns:
            oma2.MFnSkinCluster: このskinClusterの function set。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        # 破棄済みノードへ function set を作るとMayaが異常終了するため、先に確かめる。
        self._alive_fn()
        return oma2.MFnSkinCluster(self.mnode())

    def deforms(self, geometry):
        """指定形状を自身が変形するか照会する。

        :meth:`mlib.nodes.DagNode.getSkinClusters` と同じく、Shapeは自身、Transformは直下の
        非中間Shapeの上流から、出力geometryがその形状であるskinClusterを探す。
        Jointは形状を持たないためFalseで、influenceとしての登録は :meth:`hasInfluence` で調べる。

        Args:
            geometry (str | Node): 調べる形状またはtransform。

        Returns:
            bool: 自身が対象形状を変形する場合True。DAGノード以外もFalse。

        Raises:
            RuntimeError: 名前が存在しない場合、またはMayaの検索が失敗した場合。
        """
        return self.getUuid() in self._geometry_skin_uuids(Node(geometry))

    @undoChunk("mlibSkinClusterCopyWeightsTo")
    def copyWeightsTo(self, target):
        """別skinClusterへ最近傍でウェイトを転送する。

        転送先にはskinClusterのほか、形状(Shape)またはその親Transformも指定できる。形状を変形する
        skinClusterがあればそれへ転送し、無ければ自身の全influence・同じmaxInfluencesで
        :meth:`bind` してから転送する。バインドと転送は1回のUndoで戻る。fast引数は持たない
        (OpenMayaにバインド・コピーのAPIが無いため)。

        Args:
            target (str | Node): 転送先のskinCluster、または形状・その親Transform。

        Returns:
            SkinCluster: ウェイトを書き込んだ転送先。新しくバインドした場合はそのskinCluster。

        Raises:
            TypeError: 転送先がskinClusterでも形状でもない場合(Joint・形状の無いTransform・DGノード等)。
            ValueError: 転送先が自身(または自身が変形する形状)の場合、または形状を複数のskinClusterが変形している場合。
            RuntimeError: 転送先の名前が存在しない場合、またはMayaがバインド・転送を拒否した場合。

        Note:
            closestPoint、name/closestJointによる近似転送で正規化する。
            異なる基準姿勢の補正やメッシュ削減は行わない。
        """
        destination = self._copy_destination(target)
        if destination.getUuid() == self.getUuid():
            raise ValueError("Source and destination skinClusters must differ")
        cmds.copySkinWeights(sourceSkin=self.getFullName(), destinationSkin=destination.getFullName(),
                             noMirror=True, surfaceAssociation="closestPoint",
                             influenceAssociation=["name", "closestJoint"], normalize=True)
        return destination

    @undoChunk("mlibSkinClusterMirrorWeights")
    def mirrorWeights(self, axis="YZ", positiveToNegative=True, surfaceAssociation="closestPoint",
                      influenceAssociation=("closestJoint",), normalize=True):
        """自身の形状の片側のウェイトを、鏡映面の反対側へ写す。

        ``cmds.copySkinWeights(sourceSkin=自身, destinationSkin=自身, mirrorMode=axis, ...)`` を
        1回のUndoにまとめて実行する。fast引数は持たない(OpenMayaにミラーのAPIが無いため)。

        Args:
            axis (str): 鏡映面。``"XY"``・``"YZ"``・``"XZ"`` のいずれか。既定の ``"YZ"`` はX軸方向の左右反転。
            positiveToNegative (bool): Trueは面の正側(YZならX>0)から負側へ写す。Falseは負側から正側へ
                (``mirrorInverse=True``)。
            surfaceAssociation (str): 頂点の対応。``"closestPoint"``・``"rayCast"``・``"closestComponent"``。
            influenceAssociation (str | Sequence[str]): influenceの対応を1〜3個、優先順に指定する。
                ``"closestJoint"``・``"closestBone"``・``"label"``・``"name"``・``"oneToOne"`` から選ぶ。
                ジョイントのラベル(side/type)を設定済みなら ``("label", "closestJoint")`` が確実。
            normalize (bool): Trueは写した後の各頂点を正規化する(copySkinWeightsのnormalize)。

        Returns:
            SkinCluster: 自身。

        Raises:
            TypeError: 引数の型が不正な場合。
            ValueError: 面・対応方法の名前が不正、またはinfluenceの対応が0個・4個以上・重複の場合。
            RuntimeError: Mayaがミラーを拒否した場合。
        """
        axis = self._require_choice(axis, "axis", self._MIRROR_PLANES)
        _require_bool(positiveToNegative, "positiveToNegative")
        surfaceAssociation = self._require_choice(surfaceAssociation, "surfaceAssociation",
                                                  self._SURFACE_ASSOCIATIONS)
        if isinstance(influenceAssociation, str):
            influenceAssociation = (influenceAssociation,)
        try:
            influence_association = list(influenceAssociation)
        except TypeError:
            raise TypeError("influenceAssociation must be a str or a sequence of str") from None
        if not 1 <= len(influence_association) <= 3 or len(set(influence_association)) != len(influence_association):
            raise ValueError("influenceAssociation must name 1 to 3 different association methods")
        for method in influence_association:
            self._require_choice(method, "influenceAssociation", self._INFLUENCE_ASSOCIATIONS)
        _require_bool(normalize, "normalize")
        name = self.getFullName()
        cmds.copySkinWeights(sourceSkin=name, destinationSkin=name, mirrorMode=axis,
                             mirrorInverse=not positiveToNegative, surfaceAssociation=surfaceAssociation,
                             influenceAssociation=influence_association, normalize=normalize)
        return self

    def pruneWeights(self, threshold, normalize=True):
        """先頭Meshの各頂点で、閾値未満の小さなウェイトを0にする。

        ``cmds.skinPercent(skin, mesh, pruneWeights=threshold)`` と同じく、値が ``0 < w < threshold``
        のinfluenceを0にし(閾値と等しい値は残す)、ロック以外の全てが閾値未満になる頂点は刈り込みも正規化もしない。
        lockInfluenceWeightsが有効なinfluenceは0にせず、正規化でも値を保つ。値が変わった頂点・列だけを
        cmds.setAttrで書き、1回のUndoで戻る。fast引数は持たない(Maya標準の刈り込みに合わせた
        編集の補助で、OpenMayaの一括APIは未指定列を再配分するため)。

        Args:
            threshold (float): 0以上の有限な閾値。boolは不可。
            normalize (bool): Trueは上記の頂点を除く全頂点(刈り込みの無い頂点を含む)を、ロックされていないinfluenceの
                比率を保ったまま合計1(ロック分を除いた残り)へ戻す。ロック以外が全て0の頂点は変えない。
                ロックが無ければskinPercentの刈り込みと同じ値になる。Falseは0にするだけで、他の値は変えない。

        Returns:
            SkinCluster: 自身。

        Raises:
            TypeError: thresholdが数値でない、またはnormalizeがbool以外の場合。
            ValueError: thresholdが負・非有限、または刈り込む頂点に負値・非有限値・合計1を超えるロック値がある場合。
            RuntimeError: ウェイトがロック・入力接続されている、またはMayaが書込みを拒否した場合。
        """
        with undoChunk("mlibSkinClusterPruneWeights"):
            if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
                raise TypeError(f"threshold must be a number, got {type(threshold).__name__}")
            threshold = float(threshold)
            if not math.isfinite(threshold) or threshold < 0.0:
                raise ValueError(f"threshold must be a finite non-negative number, got {threshold}")
            _require_bool(normalize, "normalize")
            paths = self._skin_fn.influenceObjects()
            locked = {i for i, path in enumerate(paths) if self._influence_locked(path)}
            free = [i for i in range(len(paths)) if i not in locked]
            _, num_vertices = self._all_vertices()
            vertex_indices = list(range(num_vertices))
            rows = self._read_rows(vertex_indices, range(len(paths)))
            edited_vertices, edited_rows, changed = [], [], set()
            for vertex, row in zip(vertex_indices, rows):
                pruned = [i for i in free if 0.0 < row[i] < threshold]
                if pruned and all(row[i] == 0.0 or i in pruned for i in free):
                    # skinPercentと同じく、全てを刈り込む頂点は刈り込みも正規化もしない。
                    continue
                new = list(row)
                for i in pruned:
                    new[i] = 0.0
                if normalize and any(new[i] > 0.0 for i in free):
                    # skinPercentと同じく、刈り込みの無い頂点も正規化する。ロック以外が全て0の頂点は変更しない。
                    self._normalize_row(new, vertex, (), free, locked)
                # 既に正規化済みの頂点を丸め誤差だけで書き直さない。
                columns = [i for i in range(len(paths)) if abs(new[i] - row[i]) > 1e-12]
                if columns:
                    changed.update(columns)
                    edited_vertices.append(vertex)
                    edited_rows.append(new)
            if edited_vertices:
                columns = sorted(changed)
                values = [row[i] for row in edited_rows for i in columns]
                logical = [self._skin_fn.indexForInfluenceObject(paths[i]) for i in columns]
                self._set_weight_values_cmds(values, len(columns), edited_vertices, logical)
            return self

    def getInfluences(self):
        """登録influenceをAPIの物理順で参照する。

        Returns:
            list[Node]: influenceObjects()のDAGパスから作る新しいラッパーのリスト。
                登録型に応じJoint以外も返す。リスト位置はweights[]の論理番号とは限らず、ノードは複製しない。
        """
        # influenceObjects()が返したばかりの有効なパスなので、入力の再解決を省いてラッパーにする。
        return [Node._wrap_dag_path(path) for path in self._skin_fn.influenceObjects()]

    @undoChunk("mlibSkinClusterAddInfluences")
    def addInfluences(self, joints):
        """ジョイントをウェイト0で登録する。既存influence・重複指定は無視する。

        Args:
            joints (Joint | str | Iterable[Joint | str]): 追加するジョイント。空は何もしない。

        Returns:
            SkinCluster: 自身。

        Raises:
            ValueError: Joint以外を指定した場合。全対象を編集前に検査する。
            RuntimeError: 対象が無効、またはMayaが追加を拒否した場合。

        Note:
            既存ウェイトの再配分や正規化は行わず、既存のロック設定も変更しない。
        """

        existing = {om2.MFnDependencyNode(path.node()).uuid().asString() for path in self._skin_fn.influenceObjects()}
        names = []
        for name in Object._input_names(joints):
            node = Node(name)
            if not node.isType("joint"):
                raise ValueError(f"Expected a joint: {name}")
            if node.getUuid() not in existing:
                existing.add(node.getUuid())
                names.append(node.getFullName())
        if names:
            cmds.skinCluster(self.getFullName(), edit=True, addInfluence=names, weight=0.0)
        return self

    def getBindPose(self):
        """bindPoseアトリビュートに接続された保存ポーズを取得する。

        Returns:
            DagPose | None: 接続されたポーズ。未接続ならNone。

        Raises:
            RuntimeError: skinClusterが無効、または接続先がdagPoseでない場合。
        """
        from .dagPose import DagPose

        return DagPose.fromSkinCluster(self)

    def restoreBindPose(self, worldSpace=True):
        """接続されたポーズの全メンバーを保存姿勢へ復元する。

        ポーズを共有する別のskinClusterや、influence以外のメンバーにも影響する。
        ロックや入力接続は解除しない。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。

        Returns:
            SkinCluster: 自身。

        Raises:
            RuntimeError: ポーズが未接続、ノードが無効、またはMayaが復元を拒否した場合。
        """
        with undoChunk("mlibSkinClusterRestoreBindPose"):
            ws = _world_space(worldSpace)
            pose = self.getBindPose()
            if pose is None:
                raise RuntimeError(f"No bind pose connected to {self.getFullName()}")
            pose.restore(worldSpace=ws)
            return self

    def getUnusedInfluences(self):
        """ウェイトを持たないinfluenceを検索する。シーンは変更しない。

        Returns:
            list[Node]: influence順のノードラッパー。微小値も使用中として扱い、
                閾値による切り捨てはしない。全geometryをMFnSkinClusterで判定する。

        Raises:
            RuntimeError: skinClusterが無効、または照会に失敗した場合。
        """
        result = []
        for path in self._skin_fn.influenceObjects():
            selection, _ = self._skin_fn.getPointsAffectedByInfluence(path)
            if not selection.length():
                result.append(Node._wrap_dag_path(path))
        return result

    def removeUnusedInfluences(self, *, force=False):
        """未使用influenceの登録を外し、ノード自体は残す。

        force時は不正ウェイトを修復してから未使用を検索する。Undo有効時は一つのチャンクへ記録する。
        fast引数は持たない。先行した修復・解除は自動で戻さない。

        Args:
            force (bool): 修復後に未使用を調べる。正規化やロック解除は行わない。

        Returns:
            list[Node]: influence順の、登録を外したノード参照。対象がなければ空リスト。

        Raises:
            TypeError: forceがbool以外の場合。
            ValueError: 解除すると登録が空になる場合。
            RuntimeError: レイヤー・ロック・接続、またはMayaの編集失敗。
        """
        with undoChunk("mlibSkinClusterRemoveUnusedInfluences"):
            _require_bool(force, "force")
            if force:
                _, used = self._weight_cleanup_plan()
                if not used:
                    raise ValueError("Cannot remove every influence from a skinCluster")
                self.removeInvalidWeights()
            unused = self.getUnusedInfluences()
            if unused and len(unused) == len(self.getInfluences()):
                raise ValueError("Cannot remove every influence from a skinCluster")
            for node in unused:
                self.removeInfluence(node.getFullName(), transferToParent=False)
            return unused

    def removeInvalidWeights(self, *, fast=False):
        """負値・非有限値・未登録influence番号のウェイト要素を除去する。

        生のweightListにある既存要素だけを対象とする。有効な非負の有限値は
        1を超えていても保持し、正規化・合計0の補填・influenceの削除は行わない。
        除去した登録済みinfluenceのウェイトは既定値0になる。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            SkinCluster: 自身。不正要素がなければ何もしない。

        Raises:
            TypeError: fastがbool以外の場合。
            RuntimeError: レイヤー・influenceやウェイトのロック・接続、または編集失敗。

        Note:
            全要素を変更前に検証する。実行途中のMayaエラーは自動では戻さない。
        """
        with _edit_context("mlibSkinClusterRemoveInvalidWeights", fast):
            elements, _ = self._weight_cleanup_plan()
            if fast:
                modifier = om2.MDGModifier()
                for plug in elements:
                    modifier.removeMultiInstance(plug, False)
                if elements:
                    modifier.doIt()
            else:
                names = [plug.name() for plug in elements]
                for name in names:
                    cmds.removeMultiInstance(name, b=False)
            return self

    def hasInfluence(self, joint):
        """指定したjointがinfluenceに含まれるか判定する。

        Args:
            joint (str): 判定するjoint名。

        Returns:
            bool: influenceに含まれる場合は ``True``。
        """
        uuid = self._uuid_or_none(joint)
        if not uuid:
            return False
        return any(
            self._path_uuid(path) == uuid
            for path in self._skin_fn.influenceObjects()
        )

    def getWeights(self, joints, *, vertices=None):
        """指定influenceの頂点ウェイトを、先頭Meshから取得する。

        APIにはinfluenceObjects()内の物理番号を渡し、疎なweights[]の論理番号は渡さない。
        influenceは :meth:`setWeights` と同じく、空・未登録・重複を変更前に拒否する。

        Args:
            joints (str | Node | Iterable): 登録済みinfluence。複数は名前と参照を混在させない。
                頂点(Vertex・"mesh.vtx[0]"等)はinfluenceではないためTypeError。
            vertices (Vertex | Vertices | int | str | Iterable | None): 取得する頂点。Noneは全頂点。
                Vertex/Verticesは先頭Mesh所属に限り、文字列は ``"mesh.vtx[0:3]"`` のような頂点名。
                指定した順に返し、重複はValueError。

        Returns:
            om2.MDoubleArray: 頂点順(Noneは番号順)・各頂点内はjoints順の、頂点数×指定数の平坦な値配列。
                無次元の独立した値で、配列の変更はシーンへ反映されない。

        Raises:
            TypeError: jointsに頂点・アトリビュートを渡した、または頂点の入力型が不正な場合。
            ValueError: influenceが空・未登録(例: ``'arm_R_JNT' is not an influence of skinCluster1``)・重複、
                または頂点が重複・別の形状の場合。
            IndexError: 頂点番号が範囲外の場合。
        """
        physical_indices = self._require_influences(joints)
        vertex_indices = self._vertex_indices(vertices)
        if vertex_indices is None:
            component, _ = self._all_vertices()
            return self._skin_fn.getWeights(self.mesh_path, component, om2.MIntArray(physical_indices))
        rows = self._read_rows(vertex_indices, physical_indices)
        return om2.MDoubleArray([value for row in rows for value in row])

    def setWeights(self, joints, weights, *, vertices=None, normalize=False, broadcast=False, fast=False):
        """指定influenceの頂点ウェイトを設定する。既定では正規化せず生の値として書く。

        共通検証後、通常はcmds.setAttrで頂点・指定列の順に書く。指定順で連続する論理番号は
        範囲指定の1回のsetAttrにまとめるが、失敗時の部分更新とエラーは要素ごとの書込みと同じ。fastは全対象Plugの
        ロック・入力接続・書込み可否とアトリビュート範囲を先に検査し、MPlug.setDoubleで順に書く。
        どちらもMFnSkinCluster.setWeightsによる未指定列の再配分は使わない。

        ``normalize=True`` は書込み対象の各頂点を、``cmds.skinPercent(transformValue=..., normalize=True)``
        に倣って合計1へ正規化する。指定influenceには指定値を書き、lockInfluenceWeightsが有効な未指定
        influenceは値を保ち、残りの未指定influenceを比率を保ったまま ``1 - 指定値の合計 - ロック値の合計``
        へ拡大縮小する。指定値の合計がこの残りを超える場合と、拡大縮小できる未指定influenceが無い
        (値がすべて0)場合は、指定値を比率を保ったまま ``1 - ロック値の合計`` へ縮小・拡大し、未指定(ロック以外)を0にする。
        値が変わった未指定influenceの列も書き込む。後者の場合、skinPercentの結果はMayaの版で異なる
        (2022は指定値をそのまま書く)ため、mlibは版によらずこの規則で合計1にする。

        Args:
            joints (str | Node | Iterable): 空でない登録済みinfluence。名前またはNodeを同じ形式で指定する。
                同一influenceの重複指定は拒否する。頂点(Vertex・"mesh.vtx[0]"等)はTypeError。
            weights (Iterable[float]): 対象頂点数V・指定列数Kに対しV*K個(頂点順で、各頂点内はjoints順)。
                ``broadcast=True`` の場合は全対象頂点に共通のK個。値はfloatへ変換できる有限値。
            vertices (Vertex | Vertices | int | str | Iterable | None): 書き込む頂点。Noneは全頂点。
                Vertex/Verticesは先頭Mesh所属に限り、文字列は ``"mesh.vtx[0:3]"`` のような頂点名。
                weightsはこの指定順に対応する。重複はValueError、空は何もしない。
            normalize (bool): Trueは書き込んだ頂点を上記の規則で合計1へ正規化する。既定False。
                対象頂点に負値・非有限値があればValueError。
            broadcast (bool): TrueはK個の値を全対象頂点へ同じく適用する。既定False。
                5.0.0から、V>1の頂点へK個だけを渡す場合はこの指定が必要。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。通常setterのself返却とは異なる既存仕様。

        Raises:
            TypeError: 数値に変換できない型、頂点・influenceの入力型が不正、またはbool引数がbool以外の場合。
            ValueError: influenceが空・未登録・重複、件数不一致(K個をbroadcast=Trueなしで複数頂点へ渡した場合を含む)、
                非有限値、数値文字列が不正、頂点が重複・別の形状、または正規化できない頂点がある場合。
            IndexError: 頂点番号が範囲外の場合。
            RuntimeError: Plugが編集不可、またはMayaが設定を拒否した場合。

        Note:
            ``normalize=False`` では未指定列とinfluenceのロック設定は変更しないが、lockInfluenceWeightsを
            保護条件として拒否する処理も、レイヤー検出も行わない。非負・合計1を独自には検査しない。
            normalizeWeights/maintainMaxInfluences設定に合わせた再正規化もしない。
            通常経路はUndoが有効なら同じチャンクへ記録する。後半の失敗時に完了済み変更は
            自動で戻さず、fastの事前検査も書込み中の失敗に対する原子性は保証しない。
        """
        with _edit_context("mlibSkinClusterSetWeights", fast):
            _require_bool(normalize, "normalize")
            _require_bool(broadcast, "broadcast")
            values, width, vertex_indices, physical_indices = self._prepare_weight_values(
                joints, weights, vertices, broadcast)
            if normalize:
                values, physical_indices = self._normalized_write(values, width, vertex_indices, physical_indices)
                width = len(physical_indices)
            influences = self._skin_fn.influenceObjects()
            # 削除済み influence によるマルチアトリビュートの穴を考慮し、物理番号をアトリビュートの論理番号へ変換する。
            logical_indices = [self._skin_fn.indexForInfluenceObject(influences[i]) for i in physical_indices]
            if fast:
                self._set_weight_values_fast(values, width, vertex_indices, logical_indices)
            else:
                self._set_weight_values_cmds(values, width, vertex_indices, logical_indices)

    def getVertexWeights(self, vertex, *, nonzero=False):
        """先頭Meshの1頂点について、全influenceのウェイトを辞書で取得する。

        Args:
            vertex (Vertex | int | str): 先頭Meshの頂点。Vertex、頂点番号、または ``"mesh.vtx[3]"``。
            nonzero (bool): Trueは値が0でないinfluenceだけを返す。既定False。

        Returns:
            dict[Node, float]: influenceのラッパー(:meth:`getInfluences` と同じ型)からウェイトへの辞書。
                influenceObjects()の物理順に並ぶ。そのまま :meth:`setVertexWeights` へ渡せる。
                値は独立したコピーで、辞書の変更はシーンへ反映されない。

        Raises:
            TypeError: 頂点の入力型が不正、またはnonzeroがbool以外の場合。
            ValueError: 頂点が1つでない、または別の形状の頂点の場合。
            IndexError: 頂点番号が範囲外の場合。
        """
        _require_bool(nonzero, "nonzero")
        index = self._single_vertex_index(vertex)
        paths = self._skin_fn.influenceObjects()
        row = self._read_rows([index], range(len(paths)))[0]
        return {Node._wrap_dag_path(path): value for path, value in zip(paths, row) if not nonzero or value != 0.0}

    def setVertexWeights(self, vertex, weights, normalize=True, *, fast=False):
        """先頭Meshの1頂点に、influenceごとのウェイトを設定する。

        ``setWeights(list(weights), list(weights.values()), vertices=[vertex], normalize=normalize)`` と同じ。
        既定の ``normalize=True`` では、指定influenceに指定値を書き、指定しなかったinfluenceを
        :meth:`setWeights` の正規化規則で拡大縮小(または0に)して合計1にする。
        ``normalize=False`` では指定influenceだけを生の値で書き、他は変更しない。

        Args:
            vertex (Vertex | int | str): 先頭Meshの頂点。Vertex、頂点番号、または ``"mesh.vtx[3]"``。
            weights (Mapping[str | Node, float]): 空でない、登録済みinfluenceからウェイトへの辞書。
                キーは名前またはNodeのどちらかに揃える(:meth:`getVertexWeights` の戻り値はNode)。
            normalize (bool): Trueは書いた頂点を合計1へ正規化する。既定True。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            SkinCluster: 自身。

        Raises:
            TypeError: weightsが辞書でない、頂点・値の型が不正、またはbool引数がbool以外の場合。
            ValueError: weightsが空、influenceが未登録・重複、値が非有限、頂点が1つでない・別の形状、
                または正規化できない場合。
            IndexError: 頂点番号が範囲外の場合。
            RuntimeError: Plugが編集不可、またはMayaが設定を拒否した場合。
        """
        with _edit_context("mlibSkinClusterSetVertexWeights", fast):
            if not isinstance(weights, Mapping):
                raise TypeError(f"weights must be a mapping of influence to weight, got {type(weights).__name__}")
            if not weights:
                raise ValueError("weights must contain at least one influence")
            index = self._single_vertex_index(vertex)
            self.setWeights(list(weights.keys()), list(weights.values()), vertices=[index],
                            normalize=normalize, fast=fast)
            return self

    def dumpWeights(self, path):
        """全 influence の頂点ウェイトを JSON ファイルへ書き出す。

        シーン間でのバックアップ・復元・転送を想定した単純な JSON 形式で書き出す。
        influence の並びは getInfluences() と一致する。

        Args:
            path (str): 書き出し先のファイルパス。

        Returns:
            None: 値を返さない。
        """
        influences = [node.getName() for node in self.getInfluences()]
        _, num_vertices = self._all_vertices()
        payload = {
            "influences": influences,
            "numVertices": num_vertices,
            "weights": list(self.getWeights(influences)),
        }
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file)

    def loadWeights(self, path, *, fast=False):
        """dumpWeights() が書き出した JSON ファイルからウェイトを読み込み設定する。

        ファイルに記録された influence がすべてこの skinCluster に存在し、
        頂点数が現在の mesh と一致することを要求する。一致しない場合は
        ウェイトを変更せず例外を送出する。

        Args:
            path (str): 読み込むファイルパス。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 頂点数が現在の mesh と一致しない、またはファイルに
                記録された influence の一部がこの skinCluster に存在しない場合。

        Note:
            ``fast=True`` はOpenMaya直接更新(Undoなし)。既定の ``False`` は通常処理。
            fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        with _edit_context("mlibSkinClusterLoadWeights", fast):
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            _, num_vertices = self._all_vertices()
            if payload["numVertices"] != num_vertices:
                raise ValueError(
                    f"Stored vertex count ({payload['numVertices']}) does not match "
                    f"the current mesh vertex count ({num_vertices})"
                )
            influences = payload["influences"]
            current_influences = {node.getName() for node in self.getInfluences()}
            missing = [name for name in influences if name not in current_influences]
            if missing:
                raise ValueError(f"Influences missing from this skinCluster: {missing}")
            self.setWeights(influences, payload["weights"], fast=fast)

    def redistributeWeights(self, vertices, method="cubic", *, fast=False):
        """先頭Meshの頂点ウェイトを正規化し、イージングをかけて再正規化する。

        頂点番号はint()で変換し、重複を除いて昇順に処理する。各頂点で読取り・計算・書込みを行い、
        全頂点の書込み可否は先に検査しない。0のinfluenceは0のまま。linearでも合計1へ正規化する。

        Args:
            vertices (Vertex | Vertices | Iterable[int | Vertex]): 頂点または番号列。
                Vertex/Verticesは先頭Mesh所属に限る。空列は変更しない。
            method (str): mlib.maths.easing.CURVESの曲線名。既定cubic。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。途中失敗で先行する頂点・列の変更は自動で戻さない。

        Raises:
            TypeError: methodが文字列でない、fastがbool以外、または頂点入力を変換できない型の場合。
            ValueError: 曲線名・所属・頂点番号の変換が不正、ウェイト合計が0以下、またはイージング計算が成立しない場合。
            IndexError: 頂点番号が現在の範囲外の場合。
            RuntimeError: Mayaが読取り・書込みを拒否した場合。
        """
        with _edit_context("mlibSkinClusterRedistributeWeights", fast):
            if not isinstance(method, str):
                raise TypeError(f"Easing method must be a str, got {type(method).__name__}")
            curve = method
            if curve not in easing.CURVES:
                raise ValueError(f"Unsupported easing method: {method}")
            num_vertices = om2.MFnMesh(self.mesh_path).numVertices
            from ..components.vertex import Vertex, Vertices

            if isinstance(vertices, Vertices):
                if vertices.shape.mnode() != self.mesh_path.node():
                    raise ValueError("Vertices must belong to this skinCluster's first mesh")
                vertices = vertices.indices
            elif isinstance(vertices, Vertex):
                vertices = [vertices]
            vertex_indices = set()
            for vertex in vertices:
                if isinstance(vertex, Vertex):
                    if vertex.shape.mnode() != self.mesh_path.node():
                        raise ValueError("Vertex must belong to this skinCluster's first mesh")
                    vertex = vertex.index
                # 既存番号入力のint変換を維持し、新しい頂点参照だけを所有者検証する。
                vertex_indices.add(int(vertex))
            vertex_indices = sorted(vertex_indices)
            for vertex in vertex_indices:
                if not (0 <= vertex < num_vertices):
                    raise IndexError(f"Vertex index out of range: {vertex}")
            if not vertex_indices:
                return
            influence_paths = self._skin_fn.influenceObjects()
            all_indices = om2.MIntArray(range(len(influence_paths)))
            logical_indices = [self._skin_fn.indexForInfluenceObject(path) for path in influence_paths]
            name = self.getFullName()
            for vertex in vertex_indices:
                component_fn = om2.MFnSingleIndexedComponent()
                component = component_fn.create(om2.MFn.kMeshVertComponent)
                component_fn.addElement(vertex)
                row = list(self._skin_fn.getWeights(self.mesh_path, component, all_indices))
                total = sum(row)
                if total <= 0.0:
                    raise ValueError(f"Vertex {vertex} has no weight to redistribute")
                normalized = [value / total for value in row]
                eased = [easing.ease(value, curve) for value in normalized]
                eased_total = sum(eased)
                if eased_total <= 0.0:
                    raise ValueError(f"Vertex {vertex} produced a zero-sum weight distribution")
                final = [value / eased_total for value in eased]
                for logical_index, value in zip(logical_indices, final):
                    set_attr(f"{name}.weightList[{vertex}].weights[{logical_index}]", value, fast=fast)

    def transferWeights(self, sourceTargetPairs, *, fast=False):
        """指定順のsource/target組で、sourceの影響頂点からtargetへウェイトを移す。

        全組の参照と登録を検証してから処理し、同じinfluence同士は省く。
        targetへ加算せずsource値で置換し、sourceを0にする。source=0の頂点は変更しない。
        通常はskinPercentとnormalizeWeights設定に従い、preservedSelectionで選択復元を試みる。
        fastは単一geometryと編集条件を検査し、interactive正規化を再現する。完了済み変更は戻さない。

        Args:
            sourceTargetPairs (Iterable[tuple[Node | str, Node | str]]): 登録済みinfluenceの組。
                Maya APIのノード参照も受理する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: ペアを反復できない、未対応の参照型、またはfastがbool以外の場合。
            ValueError: ペアが2要素でない、または未登録influenceの場合。
            RuntimeError: レイヤー・ロック等の編集制限、またはMayaの処理失敗。
            NotImplementedError: fastでgeometryが1個でない場合。
        """
        with _edit_context("mlibSkinClusterTransferWeights", fast):
            self._raise_if_layers()

            pairs = []
            for pair in sourceTargetPairs:
                if isinstance(pair, (str, bytes)):
                    raise ValueError("Expected a source/target pair, not a string")
                pair = tuple(pair)
                if len(pair) != 2:
                    raise ValueError("Expected exactly two influences per pair")
                source, target = (Node._resolve_input(value) for value in pair)
                if any(not node.isValid() or not self.hasInfluence(node.getFullName()) for node in (source, target)):
                    raise ValueError("Both nodes must be influences of this skinCluster")
                if source.getUuid() != target.getUuid():
                    pairs.append((source.getFullName(), target.getFullName()))
            if fast:
                from ..core.skinEdit import transfer_weights
                transfer_weights(self, pairs)
            else:
                with preservedSelection():
                    for source_joint, target_joint in pairs:
                        self._transfer_pair(source_joint, target_joint)

    def removeInfluence(self, joint, transferToParent=True, *, force=False):
        """祖先influenceへ加算してから登録を外す。ノード自体は削除しない。

        移送先は同じskinClusterの最も近い祖先influence。生ウェイトを加算してsourceを0にし、登録を外す。
        登録の解除と残りの再配分は ``cmds.skinCluster(edit=True, removeInfluence=...)`` に任せる。
        最後の登録は外せない。Undo有効時は一つのチャンクへ記録する。fast引数は持たない。
        修復・移送・解除は順次行い、後続失敗で完了済み変更は戻さない。

        Args:
            joint (Joint | str): 解除対象のinfluence。
            transferToParent (bool): 祖先へ移送するか。False、または祖先がなければ標準の再配分。
            force (bool): 不正ウェイトを修復してから処理する。修復自体は正規化・ロック解除・レイヤー回避を行わない。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: transferToParent・forceがbool以外の場合。
            ValueError: 未登録、または最後のinfluenceの場合。
            RuntimeError: レイヤー・ロック・接続、またはMayaの編集失敗。
        """
        with undoChunk("mlibSkinClusterRemoveInfluence"):
            source, target = self._influence_removal_target(joint, transferToParent, force=force)
            if force:
                self.removeInvalidWeights()
            if target is not None:
                # skinPercentの移送は正規化設定に依存するため、保存値を明示的に加算する。
                weights = list(self.getWeights([source.getFullName(), target]))
                summed = []
                for i in range(0, len(weights), 2):
                    summed.extend((0.0, weights[i] + weights[i + 1]))
                self.setWeights([source.getFullName(), target], summed)
            cmds.skinCluster(self.getName(), edit=True, removeInfluence=source.getFullName())

    def normalizeWeights(self, decimals=None, *, fast=False):
        """先頭Meshの各頂点について、全登録influenceのウェイトを合計1へ正規化する。

        全頂点を計算・検証してからsetWeightsへ渡す。負値・非有限値・合計ゼロ、
        influenceのlockInfluenceWeights、既存ウェイトのロック/入力接続、
        レイヤーと推定される接続があれば拒否する。normalizeWeights設定自体は変えない。

        Args:
            decimals (int | None): 0〜15の小数桁数。boolは不可。Noneは桁丸めなし。
                桁指定時は最大剰余法で十進の合計1を保ち、同率はinfluenceObjects()の物理順を優先する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            SkinCluster: 自身。influence登録数とnormalizeWeights設定は変更しない。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 桁数が不正、influenceがない、負値・非有限値・合計ゼロの頂点がある場合。
            RuntimeError: ロック・入力接続・レイヤー推定、またはMayaの編集失敗。

        Note:
            レイヤー判定は接続相手の名前/型の固定トークン照合で、実レイヤーデータの検査ではない。
            保存時はfloatへ戻すため、二進浮動小数点での厳密な合計1は保証しない。
            書込み途中の失敗時に完了済み変更を自動ロールバックしない。
        """
        with _edit_context("mlibSkinClusterNormalizeWeights", fast):
            names, values = self._normalized_weights(decimals)
            self.setWeights(names, values, fast=fast)
            return self

    def getMaxInfluences(self):
        """skinClusterのmaxInfluences設定値。実際の非ゼロ数ではない。

        Returns:
            int: skinClusterのmaxInfluences設定値。実際の非ゼロ数ではない。
        """
        return self.getPlug("maxInfluences").get()

    def setMaxInfluences(self, count, maintain=True, prune=False, *, fast=False):
        """最大influenceの設定を変更し、任意で先頭Meshの非ゼロ列数を制限する。

        maxInfluencesとmaintainMaxInfluencesをPlugで設定し、skinCluster編集コマンドの
        再バインドは使わない。prune=Falseは設定2Plugだけを検査し、全ウェイトやレイヤーは調べない。
        prune=Trueは全ウェイトの編集可否と正規化結果を先に確認する。

        Args:
            count (int): 1〜2147483647。bool不可。登録influence数より大きい値も受け付ける。
            maintain (bool): maintainMaxInfluencesへ設定する値。
            prune (bool): Trueは各頂点の大きいcount列だけを残し、他列を0にして正規化する。
                同率は物理順を優先する。influenceの登録は削除しない。Falseは既存値を変更しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            SkinCluster: 自身。通常経路はUndoが有効なら同じチャンクへ記録する。

        Raises:
            TypeError: maintain・prune・fastがbool以外の場合。
            ValueError: countが不正、またはprune時にウェイトを正規化できない場合。
            RuntimeError: 設定がロック/入力接続されている、pruneの編集制限、またはMayaの設定失敗。

        Note:
            maxInfluences、maintainMaxInfluences、prune済み値の順に適用する。
            後続の書込みに失敗した場合、先に変更した設定や値を自動で戻す処理は持たない。
        """
        with _edit_context("mlibSkinClusterSetMaxInfluences", fast):
            if type(count) is not int or not 1 <= count <= 2147483647:
                raise ValueError("count must be a positive 32-bit integer")
            _require_bool(maintain, "maintain")
            _require_bool(prune, "prune")
            settings = [self.getPlug(attr) for attr in ("maxInfluences", "maintainMaxInfluences")]
            for plug in settings:
                if plug.mplug().isFreeToChange() != om2.MPlug.kFreeToChange:
                    attr = plug.getLongName()
                    raise RuntimeError(f"Setting is locked or connected: {attr}")
            computed = self._normalized_weights(limit=count) if prune else None
            settings[0].set(count, fast=fast)
            settings[1].set(maintain, fast=fast)
            if computed:
                self.setWeights(*computed, fast=fast)
            return self

    @staticmethod
    def _geometry_skin_uuids(node):
        """形状を変形するskinClusterのUUIDを、DagNode.getSkinClustersの規則で集める。

        Jointの同名メソッドはinfluence接続の照会なので、DagNodeの実装を直接呼ぶ。

        Args:
            node (Node): 調べるノード。DAGノード以外は空。

        Returns:
            list[str]: skinClusterのUUID文字列。getSkinClustersと同じ順。
        """
        if not isinstance(node, DagNode):
            return []
        return [skin.getUuid() for skin in DagNode.getSkinClusters(node)]

    def _uuid_or_none(self, node):
        """ノード名から Maya UUID を取得する。

        Args:
            node (str): UUID を問い合わせるノード名。

        Returns:
            str | None: 対応する UUID。ノードが存在しない場合は None。
        """
        # 存在しない名前でNode()がエラー通知を出さないよう、先に存在だけを確かめる。
        if isinstance(node, str) and not cmds.objExists(node):
            return None
        try:
            return Node(node).getUuid()
        except RuntimeError:
            return None

    @staticmethod
    def _path_uuid(path):
        """influenceのDAGパスから、名前を経由せずにMaya UUIDを取得する。

        ``_uuid_or_none(path.fullPathName())`` と同じ値を、名前の再解決なしで求める。

        Args:
            path (om2.MDagPath): influenceObjects()のパス。

        Returns:
            str | None: 対応するUUID。パスまたはノードが無効ならNone。
        """
        if not path.isValid():
            return None
        node = path.node()
        if not om2.MObjectHandle(node).isValid():
            return None
        return om2.MFnDependencyNode(node).uuid().asString()

    def _geometry_dag_path(self, name):
        """geometry 名から shape まで展開した MDagPath を取得する。

        Args:
            name (str): geometry のノード名。

        Returns:
            om2.MDagPath: Transform なら shape へ展開した DAG パス。
        """
        # 名前とインスタンスパスの解決は既存Node/DagNodeの経路を共有する。
        path = Node(name).mpath()
        if path.node().hasFn(om2.MFn.kTransform):
            path.extendToShape()
        return path

    def _first_geometry_name(self):
        """skinCluster が変形する先頭 geometry 名を取得する。

        Returns:
            str: skinCluster に登録された先頭 geometry 名(フルパス)。

        Raises:
            IndexError: geometry がない場合。
        """
        geometries = oma2.MFnGeometryFilter(self.mnode()).getOutputGeometry()
        if not geometries:
            raise IndexError("This skinCluster has no output geometry")
        return om2.MFnDagNode(geometries[0]).fullPathName()

    def _influence_index(self, joint):
        """登録influenceの名前/UUIDを照合し、対応する物理番号を取得する。

        Args:
            joint (str): 検索するinfluence名。

        Returns:
            int | None: influenceObjects()のリスト位置。一致するUUIDまたはpartial名の候補のうち
                最初の物理番号を選び、weights[]の論理番号は返さない。未登録はNone。
        """
        return self._influence_indices((joint,), self._skin_fn.influenceObjects())[0]

    def _all_vertices(self):
        """mesh の全頂点 component と頂点数を生成する。

        Returns:
            tuple[om2.MObject, int]: 全頂点を含む component と頂点数。
        """
        num_vertices = om2.MFnMesh(self.mesh_path).numVertices
        component_fn = om2.MFnSingleIndexedComponent()
        vertices = component_fn.create(om2.MFn.kMeshVertComponent)
        component_fn.addElements(range(num_vertices))
        return vertices, num_vertices

    def _require_influences(self, joints):
        """influence指定を検証し、指定順の物理番号へ変換する。シーンは変更しない。

        Args:
            joints (str | Node | Iterable): 指定順のinfluence参照。

        Returns:
            list[int]: influenceObjects()内の物理番号。weights[]の論理番号ではない。

        Raises:
            TypeError: 頂点・コンポーネントやアトリビュートを渡した場合、または入力型が不正な場合。
            ValueError: 空・未登録・重複の場合。
        """
        # componentsはnodesを読み込むため、循環importを避けて使う時点で読み込む。
        from ..components.component import Component, Components
        hint = "pass vertices with vertices=, or use getVertexWeights()/setVertexWeights()"
        items = joints if isinstance(joints, (list, tuple, set)) else (joints,)
        for item in items:
            if isinstance(item, (Component, Components)):
                raise TypeError(f"Expected influences, got a component ({type(item).__name__}); {hint}")
        names = Object._input_names(joints)
        if not names:
            raise ValueError("Expected at least one influence")
        for name in names:
            if "." in name:
                raise TypeError(f"Expected an influence, got a component or attribute name '{name}'; {hint}")
        physical_indices = self._influence_indices(names, self._skin_fn.influenceObjects())
        seen = set()
        for name, index in zip(names, physical_indices):
            if index is None:
                raise ValueError(f"'{name}' is not an influence of {self.getName()}")
            if index in seen:
                raise ValueError(f"Influence specified more than once: '{name}'")
            seen.add(index)
        return physical_indices

    def _vertex_indices(self, vertices):
        """頂点指定を、先頭Meshの頂点番号のリストへ変換する。シーンは変更しない。

        Args:
            vertices (Vertex | Vertices | int | str | Iterable | None): 頂点参照・番号・頂点名
                (``"mesh.vtx[0:3]"`` の範囲も可)、またはそれらの反復可能オブジェクト。

        Returns:
            list[int] | None: 指定順の頂点番号。Noneを渡した場合はNone(全頂点)。

        Raises:
            TypeError: 入力型が頂点以外(bool・float・エッジ等)の場合。
            ValueError: 先頭Mesh以外の頂点、または同じ頂点の重複の場合。
            IndexError: 頂点番号が範囲外の場合。
        """
        if vertices is None:
            return None
        # componentsはnodesを読み込むため、循環importを避けて使う時点で読み込む。
        from ..components.component import Component, Components
        from ..components.vertex import Vertex, Vertices
        mesh = self.mesh_path.node()
        num_vertices = om2.MFnMesh(self.mesh_path).numVertices
        result = []

        def collect(value):
            """単数・範囲・入れ子の頂点指定を番号へ展開してresultへ追加する。"""
            if isinstance(value, Vertices):
                if value.shape.mnode() != mesh:
                    raise ValueError("Vertices must belong to this skinCluster's first mesh")
                result.extend(value.indices)
            elif isinstance(value, Vertex):
                if value.shape.mnode() != mesh:
                    raise ValueError("Vertex must belong to this skinCluster's first mesh")
                result.append(value.index)
            elif isinstance(value, (Component, Components)):
                raise TypeError(f"Expected mesh vertices, got {type(value).__name__}")
            elif isinstance(value, bool) or isinstance(value, float):
                raise TypeError(f"Expected a vertex index, got {type(value).__name__}")
            elif isinstance(value, int):
                result.append(value)
            elif isinstance(value, str):
                result.extend(self._vertex_name_indices(value, mesh, num_vertices))
            else:
                try:
                    iterator = iter(value)
                except TypeError:
                    raise TypeError(f"Expected vertices, got {type(value).__name__}") from None
                for item in iterator:
                    collect(item)

        collect(vertices)
        seen = set()
        for index in result:
            if not 0 <= index < num_vertices:
                raise IndexError(f"Vertex index out of range: {index}")
            if index in seen:
                raise ValueError(f"Vertex specified more than once: {index}")
            seen.add(index)
        return result

    @staticmethod
    def _vertex_name_indices(name, mesh, num_vertices):
        """``"mesh.vtx[0:3]"`` のような頂点名を、先頭Meshの頂点番号へ展開する。

        Args:
            name (str): 頂点の名前。範囲・``[*]`` を含んでよい。
            mesh (om2.MObject): 先頭MeshのShape。
            num_vertices (int): 先頭Meshの頂点数。complete指定の展開に使う。

        Returns:
            list[int]: Mayaが返す順の頂点番号。

        Raises:
            TypeError: 頂点以外のコンポーネント、またはノード名だけの場合。
            ValueError: 空文字、または先頭Mesh以外の頂点の場合。
            RuntimeError: 名前を解決できない場合。
        """
        if not name:
            raise ValueError("Expected a non-empty vertex name")
        selection = om2.MSelectionList()
        selection.add(name)
        indices = []
        for item in range(selection.length()):
            path, component = selection.getComponent(item)
            if component.isNull() or component.apiType() != om2.MFn.kMeshVertComponent:
                raise TypeError(f"Expected mesh vertex names such as 'mesh.vtx[0]', got '{name}'")
            if path.node().hasFn(om2.MFn.kTransform):
                path.extendToShape()
            if path.node() != mesh:
                raise ValueError(f"Vertex must belong to this skinCluster's first mesh: '{name}'")
            component_fn = om2.MFnSingleIndexedComponent(component)
            indices.extend(range(num_vertices) if component_fn.isComplete else component_fn.getElements())
        return indices

    def _single_vertex_index(self, vertex):
        """1頂点の指定を頂点番号へ変換する。

        Args:
            vertex (Vertex | int | str): 先頭Meshの1頂点。

        Returns:
            int: 頂点番号。

        Raises:
            TypeError: Noneや頂点以外の型の場合。
            ValueError: 1頂点でない、または先頭Mesh以外の頂点の場合。
            IndexError: 頂点番号が範囲外の場合。
        """
        if vertex is None:
            raise TypeError("Expected a vertex, got None")
        indices = self._vertex_indices(vertex)
        if len(indices) != 1:
            raise ValueError(f"Expected exactly one vertex, got {len(indices)}")
        return indices[0]

    def _read_rows(self, vertex_indices, physical_indices):
        """指定頂点・指定influenceのウェイトを、頂点ごとの行として読み取る。

        MFnSkinCluster.getWeightsはcomponentの番号を昇順で返すため、昇順で読んでから指定順へ並べ直す。

        Args:
            vertex_indices (Sequence[int]): 検証済みの頂点番号。重複なし。
            physical_indices (Iterable[int]): influenceObjects()内の物理番号。

        Returns:
            list[list[float]]: vertex_indicesの順の行。各行はphysical_indicesの順。
        """
        physical_indices = list(physical_indices)
        if not vertex_indices or not physical_indices:
            return [[] for _ in vertex_indices]
        ordered = sorted(vertex_indices)
        component_fn = om2.MFnSingleIndexedComponent()
        component = component_fn.create(om2.MFn.kMeshVertComponent)
        component_fn.addElements(ordered)
        flat = list(self._skin_fn.getWeights(self.mesh_path, component, om2.MIntArray(physical_indices)))
        width = len(physical_indices)
        position = {vertex: i for i, vertex in enumerate(ordered)}
        return [flat[position[vertex] * width:(position[vertex] + 1) * width] for vertex in vertex_indices]

    @staticmethod
    def _influence_locked(path):
        """influenceのlockInfluenceWeightsが有効か調べる。アトリビュートが無い型はFalse。

        Args:
            path (om2.MDagPath): influenceObjects()のパス。

        Returns:
            bool: ロックされている場合True。
        """
        fn = om2.MFnDependencyNode(path.node())
        if not fn.hasAttribute("lockInfluenceWeights"):
            return False
        return fn.findPlug("lockInfluenceWeights", False).asBool()

    @staticmethod
    def _normalize_row(row, vertex, specified, free, locked):
        """1頂点の全influence行を、指定列を優先して合計1へ正規化する(rowをその場で書き換える)。

        ロック列は保ち、空き(``1 - ロック合計``)から指定列の合計を引いた残りへ自由列を比率で合わせる。
        指定列の合計が空きを超えるか自由列がすべて0なら、指定列を空きへ比率で合わせ、自由列を0にする。

        Args:
            row (list[float]): 物理順の全influenceの値。
            vertex (int): エラー表示用の頂点番号。
            specified (Iterable[int]): 値を指定した物理番号。
            free (Iterable[int]): 指定もロックもされていない物理番号。
            locked (Iterable[int]): 値を保つ、ロックされた未指定の物理番号。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 負値・非有限値がある、ロック値の合計が1を超える、または合計0で正規化できない場合。
        """
        if not all(math.isfinite(value) and value >= 0.0 for value in row):
            raise ValueError(f"Cannot normalize negative or non-finite weights at vertex {vertex}")
        specified, free = list(specified), list(free)
        budget = 1.0 - sum(row[i] for i in locked)
        if budget < -1e-9:
            raise ValueError(f"Locked influence weights exceed 1.0 at vertex {vertex}")
        budget = max(budget, 0.0)
        specified_total = sum(row[i] for i in specified)
        free_total = sum(row[i] for i in free)
        if free_total > 0.0 and specified_total <= budget:
            scale = (budget - specified_total) / free_total
            for i in free:
                row[i] *= scale
        elif specified_total > 0.0:
            scale = budget / specified_total
            for i in specified:
                row[i] *= scale
            for i in free:
                row[i] = 0.0
        elif budget > 1e-9:
            raise ValueError(f"Cannot normalize zero-total weights at vertex {vertex}")

    def _normalized_write(self, values, width, vertex_indices, physical_indices):
        """setWeights(normalize=True)の書込み値を、対象頂点の現在値から計算する。シーンは変更しない。

        Args:
            values (list[float]): 検証済みのV*K値または共通K値。
            width (int): 指定列数K。
            vertex_indices (Sequence[int]): 書き込む頂点番号。
            physical_indices (list[int]): 指定influenceの物理番号。

        Returns:
            tuple[list[float], list[int]]: 頂点順の平坦な値と、その列の物理番号。
                指定列の後に、値が変わった未指定列を物理順で続ける。
        """
        paths = self._skin_fn.influenceObjects()
        specified = set(physical_indices)
        others = [i for i in range(len(paths)) if i not in specified]
        locked = [i for i in others if self._influence_locked(paths[i])]
        free = [i for i in others if i not in set(locked)]
        rows = self._read_rows(vertex_indices, range(len(paths)))
        shared = len(values) == width
        results, changed = [], set()
        for position, (vertex, row) in enumerate(zip(vertex_indices, rows)):
            offset = 0 if shared else position * width
            new = list(row)
            for column, index in enumerate(physical_indices):
                new[index] = values[offset + column]
            self._normalize_row(new, vertex, physical_indices, free, locked)
            changed.update(i for i in others if new[i] != row[i])
            results.append(new)
        columns = list(physical_indices) + [i for i in others if i in changed]
        return [row[i] for row in results for i in columns], columns

    def _copy_destination(self, target):
        """copyWeightsToの転送先を、既存またはバインドしたSkinClusterへ解決する。

        Args:
            target (str | Node): skinCluster、または形状・その親Transform。

        Returns:
            SkinCluster: 転送先。形状にskinClusterが無ければ自身のinfluenceでバインドする。

        Raises:
            TypeError: skinClusterでも形状でもない場合。
            ValueError: 形状を複数のskinClusterが変形している場合。
            RuntimeError: 名前が存在しない、またはMayaがバインドを拒否した場合。
        """
        node = target if isinstance(target, Node) else Node(target)
        if isinstance(node, SkinCluster):
            return node
        description = f"{node.getType()} '{node.getName()}'"
        if not isinstance(node, DagNode) or node.isType("joint"):
            raise TypeError(f"copyWeightsTo requires a skinCluster or a geometry, got {description}")
        skins = DagNode.getSkinClusters(node)
        if len(skins) > 1:
            raise ValueError(f"Geometry is deformed by more than one skinCluster: {description}")
        if skins:
            return skins[0]
        if not self._has_geometry(node.mpath()):
            raise TypeError(f"copyWeightsTo requires a skinCluster or a geometry, got {description} without a shape")
        return SkinCluster.bind(node, self.getInfluences(), maxInfluences=self.getMaxInfluences())

    @staticmethod
    def _has_geometry(path):
        """DAGパスが形状、または直下に中間でない形状を持つTransformか調べる。

        Args:
            path (om2.MDagPath): 調べるパス。

        Returns:
            bool: 形状を持つ場合True。
        """
        if path.node().hasFn(om2.MFn.kShape):
            return True
        for index in range(path.childCount()):
            child = path.child(index)
            if child.hasFn(om2.MFn.kShape) and not om2.MFnDagNode(child).isIntermediateObject:
                return True
        return False

    @staticmethod
    def _require_choice(value, name, choices):
        """文字列の選択肢を検証する。

        Args:
            value (str): 検証する値。
            name (str): エラー表示用の引数名。
            choices (Sequence[str]): 受け付ける値。

        Returns:
            str: 検証済みの値。

        Raises:
            TypeError: 文字列でない場合。
            ValueError: 選択肢にない場合。
        """
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a str, got {type(value).__name__}")
        if value not in choices:
            raise ValueError(f"{name} must be one of {', '.join(choices)}, got '{value}'")
        return value

    def _prepare_weight_values(self, joints, weights, vertices=None, broadcast=False):
        """指定influence・頂点と平坦なウェイト入力を検証する。

        値の数・有限性と、対象が空でなく登録済み/重複なしであることを検証する。
        非負・合計1・レイヤー・lockInfluenceWeightsは検査しない。シーンには書き込まない。

        Args:
            joints (Iterable): 指定順のinfluence参照。
            weights (Iterable): 頂点順のV*K値、またはbroadcast時の共通K値。
            vertices (object): :meth:`_vertex_indices` が受け付ける頂点指定。Noneは全頂点。
            broadcast (bool): TrueはK個の値を全対象頂点へ適用する。

        Returns:
            tuple: float値リスト、指定列数K、対象頂点番号の列、指定順の物理番号リスト。

        Raises:
            ValueError: 件数不一致。K個をbroadcastなしで複数頂点へ渡した場合は、broadcast=True・vertices=の
                指定を促す。
        """
        physical_indices = self._require_influences(joints)
        if isinstance(weights, (str, bytes)):
            raise TypeError("weights must be an iterable of numbers, not a string")
        values = [float(value) for value in weights]
        vertex_indices = self._vertex_indices(vertices)
        if vertex_indices is None:
            vertex_indices = range(om2.MFnMesh(self.mesh_path).numVertices)
        count, width = len(vertex_indices), len(physical_indices)
        if broadcast:
            if len(values) != width:
                raise ValueError(f"broadcast=True requires exactly {width} weights (one per influence), "
                                 f"got {len(values)}")
        elif len(values) != count * width:
            if len(values) == width:
                raise ValueError(f"Got {width} weights for {count} vertices x {width} influences; "
                                 "pass broadcast=True to apply them to every vertex, "
                                 "or vertices= to choose the vertices")
            raise ValueError(f"Weight count must be vertex count times influence count "
                             f"({count} x {width} = {count * width}), got {len(values)}")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Weights must be finite")
        return values, width, vertex_indices, physical_indices

    def _set_weight_values_fast(self, values, width, vertex_indices, logical_indices):
        """全対象ウェイトPlugを検査し、頂点・指定列の順にOpenMayaで生値を書き込む。

        writable/check_rangeを全件に適用してからsetDoubleを始める。MFnSkinCluster.setWeightsは
        未指定列を再配分し得るため使わない。liwや正規化設定も変更しない。
        事前検査後のAPI書込み失敗は自動で戻さず、Undo設定を変更しない。

        Args:
            values (list[float]): 検証済みのV*K値または共通K値。
            width (int): 指定列数K。
            vertex_indices (Sequence[int]): 書き込む頂点番号。valuesの行の順。
            logical_indices (list[int]): weights[]の論理番号。指定influence順。

        Returns:
            None: 値を返さない。
        """
        weights_plug = self._dependency_fn().findPlug("weightList", False)
        # 全要素が同じweightsアトリビュートなので、書込み可否と範囲の定義を読むfunction setは
        # 1つを共有する。ロック・入力接続は要素ごと、親側(weightList[v].weights より上)は
        # 頂点ごとに毎回調べる。拒否する要素ではrequire_writable()を呼び、従来と同じ例外を送出する。
        attribute_fn = range_fn = None
        attribute_writable = has_limits = True
        edits = []
        for position, vertex in enumerate(vertex_indices):
            row = weights_plug.elementByLogicalIndex(vertex).child(0)
            row_blocked = self._plug_chain_blocked(row)
            offset = 0 if len(values) == width else position * width
            for column, index in enumerate(logical_indices):
                plug = row.elementByLogicalIndex(index)
                if attribute_fn is None:
                    attribute = plug.attribute()
                    attribute_fn = om2.MFnAttribute(attribute)
                    attribute_writable = attribute_fn.writable
                    if attribute.hasFn(om2.MFn.kNumericAttribute):
                        range_fn = om2.MFnNumericAttribute(attribute)
                        has_limits = range_fn.hasMin() or range_fn.hasMax()
                if row_blocked or plug.isLocked or plug.isDestination or not attribute_writable:
                    require_writable(plug, attribute_fn)
                if has_limits:
                    require_range(plug, values[offset + column], range_fn)
                edits.append((plug, values[offset + column]))
        # MFnSkinCluster.setWeightsはliw等の設定によって未指定値を再配分する。
        # 通常モードと同じ生値を維持するため、MPlugに直接書き込む。
        for plug, value in edits:
            plug.setDouble(value)

    @staticmethod
    def _plug_chain_blocked(plug):
        """Plugと、その親・マルチアトリビュート側の全段にロックまたは入力接続があるか調べる。

        :func:`mlib.core.fastWrite.writable` が要素から辿る親側の判定を、同じ頂点の要素で
        共有するために使う。例外は送出せず、書込み不能アトリビュートの判定も行わない。

        Args:
            plug (om2.MPlug): 調べる起点。weightList[v].weights のようなマルチアトリビュートのPlug。

        Returns:
            bool: いずれかの段がロックされているか、入力接続を持つ場合True。
        """
        current = plug
        while True:
            if current.isLocked or current.isDestination:
                return True
            if current.isChild:
                current = current.parent()
            elif current.isElement:
                current = current.array()
            else:
                return False

    def _set_weight_values_cmds(self, values, width, vertex_indices, logical_indices):
        """頂点・指定influence列の順に、cmdsで生のウェイト値を書き込む。

        weights[]には疎な論理番号を使う。指定順で論理番号が1ずつ増える列は
        ``weights[a:b]`` の範囲指定で1回のsetAttrにまとめ、番号の穴や順序の入れ替わりで区切る。
        全Plugの事前検査はせず、途中で拒否された場合も先行する書込みを自動で戻さない。
        Undoチャンクは呼出し側が管理する。

        範囲指定のsetAttrはロック・入力接続などで拒否されると範囲内のどの要素も更新しない。
        その場合だけ同じ範囲を要素ごとのsetAttrで書き直し、従来の要素ごとの書込みと同じく
        拒否された要素の手前まで更新して、その要素のMayaのエラーを送出する。

        Args:
            values (list[float]): 検証済みのV*K値または共通K値。
            width (int): 指定列数K。
            vertex_indices (Sequence[int]): 書き込む頂点番号。valuesの行の順。
            logical_indices (list[int]): weights[]の論理番号。指定influence順。

        Returns:
            None: 値を返さない。
        """
        name = self.getFullName()
        runs = self._consecutive_runs(logical_indices)
        shared = len(values) == width
        for position, vertex in enumerate(vertex_indices):
            offset = 0 if shared else position * width
            prefix = f"{name}.weightList[{vertex}].weights"
            for column, first, count in runs:
                start = offset + column
                if count == 1:
                    set_attr(f"{prefix}[{first}]", values[start])
                    continue
                row = values[start:start + count]
                try:
                    set_attr(f"{prefix}[{first}:{first + count - 1}]", *row)
                except RuntimeError:
                    # 範囲指定は失敗時に何も書かないため、要素ごとに書き直して
                    # 拒否された要素までの部分更新とエラーを従来と揃える。
                    for position, value in enumerate(row):
                        set_attr(f"{prefix}[{first + position}]", value)

    @staticmethod
    def _consecutive_runs(logical_indices):
        """指定順の論理番号を、1ずつ増える連続した区間へ分ける。

        Args:
            logical_indices (Sequence[int]): weights[]の論理番号。指定influence順。

        Returns:
            list[tuple[int, int, int]]: 区間ごとの、指定列での開始位置・先頭の論理番号・要素数。
                例えば[0, 1, 3, 2]は[(0, 0, 2), (2, 3, 1), (3, 2, 1)]。
        """
        runs = []
        for column, index in enumerate(logical_indices):
            if runs:
                start, first, count = runs[-1]
                if index == first + count:
                    runs[-1] = (start, first, count + 1)
                    continue
            runs.append((column, index, 1))
        return runs

    def _influence_indices(self, joints, influences):
        """一回の操作内でUUIDと名前の検索表を共有する。

        Args:
            joints (Iterable[str]): 入力順のinfluence名。
            influences (om2.MDagPathArray): 操作開始時のinfluence配列。

        Returns:
            list[int | None]: 入力順の物理番号。未登録はNone。
                同じUUIDの複数パスは従来の逐次検索と同じ先頭を選ぶ。
        """
        joints = list(joints)
        if not joints:
            return []
        if len(joints) == 1:
            # 単数指定では検索表全体を構築せず、一致した時点で終了する。
            joint = joints[0]
            uuid = self._uuid_or_none(joint)
            for index, path in enumerate(influences):
                if ((uuid and self._path_uuid(path) == uuid)
                        or path.partialPathName() == joint):
                    return [index]
            return [None]
        by_uuid, by_name = {}, {}
        for index, path in enumerate(influences):
            uuid = self._path_uuid(path)
            if uuid:
                by_uuid.setdefault(uuid, index)
            by_name.setdefault(path.partialPathName(), index)
        result = []
        for joint in joints:
            candidates = (by_uuid.get(self._uuid_or_none(joint)), by_name.get(joint))
            result.append(min((i for i in candidates if i is not None), default=None))
        return result

    def _transfer_pair(self, source_joint, target_joint):
        """選択された source influence 頂点のウェイトを target へ移す。

        元 influence に影響される頂点を選択し、skinPercent の transformMoveWeights を実行する。選択状態の復元は呼び出し側が行う。

        Args:
            source_joint (str): 移送元の influence 名。
            target_joint (str): 移送先の influence 名。

        Returns:
            None: 値を返さない。
        """
        cmds.skinCluster(self.getName(), edit=True, selectInfluenceVerts=source_joint)
        if om2.MGlobal.getActiveSelectionList().length():
            cmds.skinPercent(self.getName(), transformMoveWeights=[source_joint, target_joint])

    def _influence_removal_target(self, joint, transfer_to_parent=True, *, force=False):
        """削除可否と祖先移送先を変更前に確認する。

        Args:
            joint: 処理対象のジョイント。
            transfer_to_parent: 削除前にウェイトを親インフルエンスへ移すか。
            force: 不正ウェイトの除去を許可するか。検証中は変更しない。
        """
        _require_bool(transfer_to_parent, "transferToParent")
        _require_bool(force, "force")
        self._raise_if_layers()
        source = joint if isinstance(joint, Node) else Node(joint)
        if not source.isValid() or not self.hasInfluence(source.getFullName()):
            raise ValueError("Joint is not an influence of this skinCluster")
        if len(self.getInfluences()) <= 1:
            raise ValueError("Cannot remove the last influence")
        target = source.getTransferTarget(self) if transfer_to_parent and isinstance(source, Joint) else None
        if force:
            if target is not None:
                # 既存の祖先移送は先頭mesh専用。未対応形状の拒否を修復より前に行う。
                om2.MFnMesh(self.mesh_path)
            self._weight_cleanup_plan()
        elif target is not None:
            self._editable_weights()
        return source, target

    def _editable_weights(self):
        """先頭meshの全influence値を取得し、ロック・接続・レイヤーを拒否する。"""
        names, _ = self._editable_weight_list()
        weights = list(self.getWeights(names))
        if any(not math.isfinite(v) or v < 0 for v in weights):
            raise ValueError("Weights must be finite and non-negative")
        return names, weights

    def _editable_weight_list(self):
        """正規化・整理用に全ウェイトの編集条件を検査し、名前列とweightList参照を返す。

        登録influenceが空、lockInfluenceWeightsが有効、既存weightList配下にロック/入力接続、
        またはレイヤー推定の接続があれば拒否する。値の有限性や符号はここでは検査しない。
        この厳密な編集条件は、setWeightsの直接書込みには適用しない。

        Returns:
            tuple[list[str], om2.MPlug]: 物理順のinfluence名と、シーン内weightListへの参照。
                Plugはコピーした値ではない。ロックの一時解除や設定変更は行わない。
        """
        self._raise_if_layers()
        influences = self.getInfluences()
        names = [node.getName() for node in influences]
        if not names:
            raise ValueError("No influences")
        for node in influences:
            if node.hasAttr("lockInfluenceWeights") and node.getPlug("lockInfluenceWeights").get():
                raise RuntimeError(f"Influence is locked: {node.getName()}")
        path = self.getFullName() + ".weightList"
        weight_list = self.getPlug("weightList").mplug()
        if weight_list.isLocked or weight_list.isDestination:
            raise RuntimeError("Weights are locked or connected")
        self._validate_weight_locks(weight_list)
        return names, weight_list

    def _weight_cleanup_plan(self):
        """既存の疎な要素から不正ウェイトの除去計画を作る。シーンは変更しない。

        Returns:
            tuple[list[om2.MPlug], set[int]]: 除去対象と、修復後も正値を持つ
                登録済みinfluenceの論理番号。存在しない要素は作成しない。

        Raises:
            RuntimeError: ウェイトが編集不可、または除去対象に出力接続がある場合。
        """
        _, weight_list = self._editable_weight_list()
        registered = {self._skin_fn.indexForInfluenceObject(path) for path in self._skin_fn.influenceObjects()}
        elements, used = [], set()
        for vertex in weight_list.getExistingArrayAttributeIndices():
            row = weight_list.elementByLogicalIndex(vertex).child(0)
            for index in row.getExistingArrayAttributeIndices():
                plug = row.elementByLogicalIndex(index)
                value = plug.asDouble()
                if index not in registered or not math.isfinite(value) or value < 0:
                    if plug.isConnected:
                        raise RuntimeError(f"Invalid weight is connected: {plug.name()}")
                    elements.append(plug)
                elif value > 0:
                    used.add(index)
        return elements, used

    @staticmethod
    def _validate_weight_locks(plug):
        """既存の疎なウェイト要素だけを辿りロックを検証する。

        Args:
            plug (om2.MPlug): weightListとその子。未存在要素は作成しない。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 要素または親のアトリビュートがロックされている場合。
        """
        if plug.isLocked or plug.isDestination:
            raise RuntimeError(f"Weight multi element is locked or connected: {plug.name()}")
        if plug.isArray:
            for index in plug.getExistingArrayAttributeIndices():
                SkinCluster._validate_weight_locks(plug.elementByLogicalIndex(index))
        elif plug.isCompound:
            for index in range(plug.numChildren()):
                SkinCluster._validate_weight_locks(plug.child(index))

    def _normalized_weights(self, decimals=None, limit=None):
        """全頂点ウェイトの正規化・任意の列削減・十進丸めをメモリ上で計算する。

        編集可否と非負/有限値を検証し、各頂点の合計がゼロなら拒否する。
        limit指定時は大きい列を残して他列を0にし、桁指定時は最大剰余法で配分する。
        同率は物理順を優先する。結果はfloatへ戻し、シーンには書き込まない。

        Args:
            decimals (int | None): 0〜15の小数桁数。Noneは桁丸めなし。bool不可。
            limit (int | None): 呼出し側で検証した残列数の上限。Noneは列削減なし。

        Returns:
            tuple[list[str], list[float]]: 物理順のinfluence名と、頂点順×influence順の平坦な値。
        """
        if decimals is not None and (type(decimals) is not int or not 0 <= decimals <= 15):
            raise ValueError("decimals must be an integer between 0 and 15")
        names, weights = self._editable_weights()
        width, result = len(names), []
        with localcontext() as context:
            context.prec = 64
            for start in range(0, len(weights), width):
                row = [Decimal(str(v)) for v in weights[start:start + width]]
                if limit is not None:
                    keep = set(sorted(range(width), key=lambda i: (-row[i], i))[:limit])
                    row = [v if i in keep else Decimal(0) for i, v in enumerate(row)]
                total = sum(row)
                if not total:
                    raise ValueError(f"Cannot normalize zero-total weights at vertex {start // width}")
                row = [v / total for v in row]
                if decimals is not None:
                    scale = 10 ** decimals
                    scaled = [v * scale for v in row]
                    ticks = [int(v.to_integral_value(rounding=ROUND_FLOOR)) for v in scaled]
                    remaining = scale - sum(ticks)
                    order = sorted(range(width), key=lambda i: (-(scaled[i] - ticks[i]), i))
                    for i in order[:remaining]:
                        ticks[i] += 1
                    row = [Decimal(v) / scale for v in ticks]
                result.extend(float(v) for v in row)
        return names, result

    def _has_layer_plugs(self):
        """スキニングレイヤー関連ノードが接続されているか判定する。

        Returns:
            bool: 接続ノードの名前または型名にレイヤー判定用トークンが含まれる場合は True。実際のレイヤーデータの有無は調べない。
        """
        # ノード名・型だけが必要。genericアトリビュートを含む接続のPlug生成は避ける。
        fn = self._dependency_fn()
        connected = {om2.MObjectHandle(other.node()).hashCode(): other.node()
                     for plug in fn.getConnections() for other in plug.connectedTo(True, True)}
        for obj in connected.values():
            other_fn = om2.MFnDependencyNode(obj)
            node_name = other_fn.name().lower()
            node_type = other_fn.typeName.lower()
            if any(token in node_name or token in node_type for token in self._LAYER_TOKENS):
                return True
        return False

    def _raise_if_layers(self):
        """スキニングレイヤー検出時に安全のため処理を中断する。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: _has_layer_plugs() が True の場合。
        """
        if self._has_layer_plugs():
            raise RuntimeError("Cannot run while skinning layers exist")


class SkinClusters(Nodes):
    """重複を除き、保持順にSkinClusterを保持するコレクション。"""

    item_class = SkinCluster
