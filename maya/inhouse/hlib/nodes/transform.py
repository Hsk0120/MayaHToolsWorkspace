"""変換行列を介して Transform ノードを操作する。"""

import math
import numbers

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace

from .._core.collection import bulk_api
from .._core.fastWrite import set_attr, set_plug
from .._core.flags import flag_aliases
from .._core.registry import node_wrapper
from .._core.registry import collection_export
from .._core.space import world_space
from ..decorators._fast import fast_edit, is_fast
from ..decorators.undo import undoChunk
from ..maths import EulerRotation, Matrix, Quaternion, Scale, Shear, Translation, Vector, Transformation
from ..maths.vector import _vector_of
from ..plugs.plug import Plug
from .dagNode import DagNode, DagNodes
from .node import Node

#: 拘束元の transform の値(位置・回転など)を使うコンストレイント。拘束元は Transform に限る。
_TRANSFORM_SOURCE_CONSTRAINTS = frozenset((
    "parentConstraint", "pointConstraint", "orientConstraint", "scaleConstraint",
    "aimConstraint", "poleVectorConstraint",
))


_TRANSFORM_ATTRIBUTES = {}


def _transform_attribute(name):
    """transform ノード型のアトリビュートの MObject を取得する(初回だけ問い合わせて保持する)。

    joint など transform の派生型も同じアトリビュートの MObject を共有するため、
    ``om2.MPlug(node, attribute)`` で名前の検索なしに MPlug を作れる。

    Args:
        name (str): アトリビュートのロング名(``matrix`` / ``worldMatrix`` など)。

    Returns:
        om2.MObject: transform ノード型のアトリビュート。
    """
    attribute = _TRANSFORM_ATTRIBUTES.get(name)
    if attribute is None:
        attribute = om2.MNodeClass("transform").attribute(name)
        _TRANSFORM_ATTRIBUTES[name] = attribute
    return attribute


def _match_scale_signs(quaternion, scale, shear, references):
    """分解したスケールの符号の組み合わせを、基準のスケールの符号へ揃える。

    2軸のスケールの符号を同時に反転し、残りの軸まわりの 180 度回転で補償しても
    行列は変わらない(D を2軸が -1 の対角行列として S·Sh·R = (S·D)·(D·Sh·D)·(D·R))。
    行列式の符号は変えられないため、references を先頭から順に調べ、反転が必要な軸が
    0 個または 2 個(行列式の符号と合う)の最初の基準に揃える。どの基準とも合わない
    (奇数個の軸が違う)場合は入力(om2 の規約)のまま返す。

    Args:
        quaternion (om2.MQuaternion): 分解した回転。
        scale (Iterable[float]): 分解したスケール。
        shear (Iterable[float]): 分解したシアー(XY、XZ、YZ)。
        references (Iterable[Iterable[float]]): 符号を合わせる基準のスケールの候補。
            優先する順に並べる(setScaling で要求した値、現在の scale チャンネル値など)。

    Returns:
        tuple: (quaternion, scale, shear)。scale と shear は3要素の tuple。
    """
    scale = tuple(scale)
    shear = tuple(shear)
    for reference in references:
        flips = tuple((value < 0.0) != (base < 0.0) for value, base in zip(scale, reference))
        count = sum(flips)
        if count == 0:
            return quaternion, scale, shear
        if count == 2:
            break
    else:
        return quaternion, scale, shear
    signs = tuple(-1.0 if flip else 1.0 for flip in flips)
    axis = [0.0, 0.0, 0.0]
    axis[flips.index(False)] = 1.0
    # om2 の四元数の積は左を先に適用する。D(残りの軸まわりの 180 度)の後に元の回転。
    half_turn = om2.MQuaternion(axis[0], axis[1], axis[2], 0.0)
    return (
        om2.MQuaternion.__mul__(half_turn, quaternion),
        (scale[0] * signs[0], scale[1] * signs[1], scale[2] * signs[2]),
        (shear[0] * signs[0] * signs[1], shear[1] * signs[0] * signs[2], shear[2] * signs[1] * signs[2]),
    )


def _closest_euler(quaternion, reference):
    """回転を reference の回転順序で表し、reference に最も近い等価な解を返す。

    Args:
        quaternion (om2.MQuaternion): 変換する回転。
        reference (om2.MEulerRotation): 基準の回転(回転順序と解の選択に使う)。

    Returns:
        om2.MEulerRotation: reference と同じ回転順序の、reference に最も近い解
        (``MEulerRotation.closestSolution``。360 度の周期と、中間軸を反転した別解を考慮する)。
    """
    rotation = quaternion.asEulerRotation()
    rotation.reorderIt(reference.order)
    return rotation.closestSolution(reference)


@node_wrapper("transform")
class Transform(DagNode):
    """Maya transform ノードを matrix-first API で扱うラッパー。

    評価済み値を取得するメソッドは、``ws=False`` （既定）でローカル空間、``ws=True`` でワールド空間の値を返す。
    """

    @flag_aliases(typ="type", mo="maintainOffset")
    @undoChunk("hlibTransformAddConstraint")
    def addConstraint(self, sources, type="parent", maintainOffset=False, **kwargs):
        """自身を拘束するコンストレイントを作成する。

        Args:
            sources (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug | Iterable):
                拘束元の単一ノードまたはノード列。Plug・MPlug・``"node.attribute"`` は
                所有ノード、Component・Components・``"pCube1.vtx[0]"`` は所有シェイプとして扱う。
                parent/point/orient/scale/aim/poleVector では、拘束元が Transform
                (joint・IkHandle を含む)に解決される必要がある(シェイプ・Component・
                DG ノードは TypeError)。
            type (str): parent、point、orient、scale、aim、poleVector、
                geometry、normal、tangent、pointOnPoly。または Constraint 接尾辞付きの型名。
            maintainOffset (bool): True の場合は現在の相対位置・回転を維持する。
                False の場合は Maya の既定動作で拘束する。
            **kwargs: aimVector・worldUpObject等の作成フラグ。短名も使用可能。

        Returns:
            Constraint: 対応する具象ラッパー。同じ種類が既存なら Maya の規則で
                ターゲットが追加される場合がある。

        Raises:
            ValueError: 未対応の型または空のソースの場合。
            TypeError: 型名やターゲットの入力型が不正な場合。parent/point/orient/scale/aim/
                poleVector の拘束元が Transform に解決されない場合(シェイプの Plug、
                Component、``"pCube1.vtx[0]"`` など。maya.cmds はシェイプを拘束元にしても
                ターゲットの無い拘束を黙って作るため)。
            RuntimeError: ノードが無効、拘束元の名前を解決できない(存在しない、または
                複数のノードに一致する)場合、または Maya が作成を拒否した場合。
            DeletedAttributeError: 拘束元に、アトリビュートが削除済みの Plug / MPlug を渡した場合
                (ValueError と RuntimeError の両方の派生)。

        PoleVector は RP IK ハンドル、Geometry/Normal/PointOnPoly は適切な形状、
        Tangent は NURBS カーブが必要。選択状態による対象補完は行わない。
        typeはtyp、maintainOffsetはmoでも指定可能。同時指定はTypeError。
        maintainOffsetはparent/point/orient/scale/aim以外では使用しない。
        """
        from ..nodes.node import Node as _InputNode
        from ..nodes.node import Nodes as _InputNodes
        from .constraint import Constraint

        if not isinstance(type, str):
            raise TypeError("type must be a string")
        command_name = type if type.endswith("Constraint") else type + "Constraint"
        # 型登録を重複管理せず、登録メタデータを持つ具象クラスから対象を判定する。
        supported = {
            cls.__dict__["__hlib_node_type__"]
            for cls in Constraint.__subclasses__()
            if "__hlib_node_type__" in cls.__dict__
        }
        if command_name not in supported:
            raise ValueError(f"Unsupported constraint type: {type}")
        if not self.isValid():
            raise RuntimeError("Cannot constrain an invalid transform")
        from ..components.component import Component, Components
        from ..plugs.plug import Plug

        # Components は要素へ展開せず、所有シェイプ1つの拘束元として扱う。
        if isinstance(sources, (Node, str, Plug, Component, Components,
                                om2.MObject, om2.MDagPath, om2.MPlug)):
            sources = [sources]
        # 拘束元の transform の値を使う型。シェイプを拘束元にすると maya.cmds はターゲットの
        # 無い(追従しない)拘束を黙って作るため、Transform 以外は TypeError にする。
        requires_transform = command_name in _TRANSFORM_SOURCE_CONSTRAINTS
        names = []
        for source in _InputNodes._resolve_inputs(sources):
            if source is None or (isinstance(source, str) and not source):
                raise TypeError("Constraint sources must be non-empty names or Node objects")
            # 文字列も含めて所有ノードへ解決する。Plug・MPlug・"node.attribute" は所有ノード、
            # Component・"pCube1.vtx[0]" は所有シェイプを拘束元にする(maya.cmds へ
            # プラグ名・コンポーネント名をそのまま渡すと拘束元として扱われないため)。
            source = _InputNode._resolve_input(source)
            if not source.isValid():
                raise RuntimeError("Constraint target is invalid")
            if requires_transform and not source.mnode().hasFn(om2.MFn.kTransform):
                raise TypeError(
                    f"{command_name} の拘束元には Transform(joint・IkHandle を含む)を指定してください"
                    f"(シェイプ・Component・DG ノードは不可): {source.__class__.__name__} {source.getName()!r}"
                )
            names.append(source.getFullName())
        if not names:
            raise ValueError("At least one constraint source is required")
        from .._core.flags import normalize_flags
        from .._core.commandResult import CommandResult

        command_kwargs = normalize_flags(command_name, kwargs)
        if command_kwargs.get("query") or command_kwargs.get("edit"):
            raise ValueError("addConstraint supports creation only; use hlib.addConstraint for query/edit")
        command_kwargs = CommandResult.node_flags(command_kwargs, ("worldUpObject",))
        if command_name in {
            "parentConstraint",
            "pointConstraint",
            "orientConstraint",
            "scaleConstraint",
            "aimConstraint",
        }:
            command_kwargs["maintainOffset"] = maintainOffset
        result = getattr(cmds, command_name)(*names, self.getFullName(), **command_kwargs)
        return Node(result[0])

    @undoChunk("hlibTransformDeleteConstraints")
    def deleteConstraints(self):
        """自身を拘束するconstraintと、経由するpairBlendを削除する。

        入力接続をpairBlend・unitConversionに限って上流へ辿る。
        constraintに到達した経路のpairBlendだけを削除し、拘束元の
        TransformやanimCurve、無関係なpairBlendは残す。
        削除ノードの出力が対象外ノードにも使われる場合は編集前に拒否する。
        現在姿勢の維持・ベイク・アニメーション入力の再接続は行わない。
        全体を一回のUndoで戻せる。

        Returns:
            list[str]: 削除前のノード名。該当がなければ空リスト。

        Raises:
            RuntimeError: 無効なTransform、共有出力、参照・ロックされた削除対象、
                またはMayaによる削除失敗。
        """
        if not self.isValid():
            raise RuntimeError("Cannot edit an invalid transform")
        owner = self.getFullName()
        deleting, bridges = set(), set()

        def upstream(node, path):
            if node in path:
                return False
            kind = cmds.nodeType(node)
            if "constraint" in (cmds.nodeType(node, inherited=True) or []):
                deleting.add(node)
                return True
            if kind not in ("pairBlend", "unitConversion"):
                return False
            found = False
            for source in inputs(node):
                found = upstream(source, path | {node}) or found
            if found:
                if kind == "pairBlend":
                    deleting.add(node)
                else:
                    bridges.add(node)
            return found

        def inputs(node):
            sources = cmds.listConnections(node, source=True, destination=False, plugs=True) or []
            return {cmds.ls(plug.split(".", 1)[0], long=True)[0] for plug in sources
                    if cmds.getAttr(plug, type=True) != "message"}

        for source in inputs(owner):
            upstream(source, {owner})
        allowed = deleting | bridges | {owner}
        for node in deleting | bridges:
            for destination in cmds.listConnections(node, source=False, destination=True, plugs=True) or []:
                if cmds.getAttr(destination, type=True) == "message":
                    continue
                target = cmds.ls(destination.split(".", 1)[0], long=True)[0]
                if target not in allowed:
                    raise RuntimeError("Constraint path has shared outputs: " + node)
        for node in deleting:
            if cmds.referenceQuery(node, isNodeReferenced=True) or cmds.lockNode(node, query=True, lock=True)[0]:
                raise RuntimeError("Cannot delete referenced or locked node: " + node)
        names = sorted(deleting)
        if names:
            cmds.delete(names)
        return names

    def transformFn(self):
        """Transform 用の MFnTransform を取得する。

        Returns:
            om2.MFnTransform: この Transform の function set。
        """
        return om2.MFnTransform(self.mpath())

    @flag_aliases(attrs="attributes")
    @fast_edit
    @undoChunk("hlibTransformReset")
    def reset(self, attributes=None, *, fast=False):
        """指定アトリビュートを定義上の既定値へ戻す。

        Args:
            attributes (str | Iterable[str] | None): tx/translateX/translateなど。
                省略時はtranslate・rotate・scale・shear。独自数値アトリビュートも可。 別名 ``attrs`` も使用可能。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: 名前が文字列でない、または既定値を扱えない型の場合。
            AttributeError: 指定アトリビュートが存在しない場合。
            RuntimeError: ロックや入力接続などで変更できない場合。

        フリーズではなく値を戻す操作なので姿勢は変わる。jointOrient・ピボット・
        offsetParentMatrixは明示指定しない限り変更しない。ロック解除・接続切断は
        行わない。途中の失敗は例外とし、完了済みの変更は通常Undoで戻せる。
        """
        if attributes is None:
            attributes = ("translate", "rotate", "scale", "shear")
        elif isinstance(attributes, str):
            attributes = (attributes,)
        attributes = tuple(attributes)
        if not all(isinstance(name, str) and name for name in attributes):
            raise TypeError("attributes must contain non-empty attribute names")
        plugs = [self.getPlug(name) for name in attributes]
        for plug in plugs:
            plug.reset()
        return self

    @flag_aliases(ws="worldSpace")
    @undoChunk("hlibTransformResetPivot")
    def resetPivot(self, worldSpace=True, *, kind="both"):
        """現在の姿勢を保ち、ピボットだけを指定空間の原点へ移動する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            kind (str): bothは両方、rotateは回転、scaleはスケールピボット。

        Returns:
            Transform: 自身。一回のUndoで元へ戻せる。

        Raises:
            TypeError: 対象がJointの場合。
            ValueError: worldSpaceがboolでない、またはkindが不正な場合。
            RuntimeError: Mayaが更新を拒否した場合。

        ピボット補償値を調整して行列を維持する。translateのリセットではない。
        """
        ws = world_space(worldSpace)
        if not isinstance(ws, bool):
            raise TypeError("ws must be a bool")
        return self.setPivot((0, 0, 0), ws=ws, kind=kind, preserve=True)

    @flag_aliases(ws="worldSpace")
    @fast_edit
    @undoChunk("hlibTransformScaleGeometry")
    def scaleGeometry(self, scale, worldSpace=False, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False):
        """直下の全Shapeの頂点・CVを拡縮する。Transformの行列は変更しない。

        Args:
            scale (float | Iterable[float]): 一様倍率、またはXYZの倍率。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            pivot (Iterable[float]): 指定空間の拡縮中心。内部距離単位cm。
            indices (Iterable[int | tuple[int, int]] | None): 各Shapeの対象番号。
                Noneは全要素。サーフェスは(U, V)の組。
            fast (bool): Trueは履歴なしメッシュ・非周期カーブをom2で直接更新し、Undoなし。

        Returns:
            Transform: 自身。通常モードは一回のUndoで戻せる。

        Raises:
            ValueError: 引数が不正な場合。
            NotImplementedError: 対応していないShapeの場合。
            RuntimeError: Mayaが変更を拒否した場合。

        中間Shapeは対象外。インスタンスは共有形状全体に影響する。
        途中で失敗した場合は停止し、完了済みの変更は自動で戻さない。
        """
        ws = world_space(worldSpace)
        indices = None if indices is None else tuple(indices)
        scale = scale if isinstance(scale, numbers.Real) else tuple(scale)
        pivot = tuple(pivot)
        for shape in self.getShapes():
            shape.scaleGeometry(scale, ws=ws, pivot=pivot, indices=indices)
        return self

    @flag_aliases(ws="worldSpace")
    def getPivot(self, worldSpace=False, *, kind="rotate"):
        """指定した種類のピボットを取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            kind (str): rotateは回転、scaleはスケールピボット。

        Returns:
            Translation: ピボット位置。Maya API の内部距離単位。

        Raises:
            ValueError: kindがrotate/scaleでない場合。
        """
        ws = world_space(worldSpace)
        if kind not in ("rotate", "scale"):
            raise ValueError("kind must be 'rotate' or 'scale'")
        # 設定と同じxform空間を使う。MFnTransformのkTransformとxformの
        # objectSpaceでは、スケールを持つノードのピボットの解釈が一致しない。
        flag = "rotatePivot" if kind == "rotate" else "scalePivot"
        values = cmds.xform(self.getFullName(), query=True, worldSpace=ws,
                            objectSpace=not ws, **{flag: True})
        return Translation(*(om2.MDistance(v, om2.MDistance.uiUnit()).asCentimeters() for v in values))

    @flag_aliases(ws="worldSpace")
    @undoChunk("hlibTransformSetPivot")
    def setPivot(self, value, worldSpace=False, *, kind="rotate", preserve=True):
        """指定した種類のピボットを変更する。既定ではノードの姿勢を保つ。

        Args:
            value (Iterable[float]): 新しいピボット位置。Maya API の内部距離単位。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            kind (str): rotate/scale/both。bothは両方を同じ位置へ設定する。
            preserve (bool): Trueはピボット補償値を調整して変換行列を保つ。
                Falseは補償せず、姿勢が変わる場合がある。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: kind、座標の要素数・有限値が不正な場合。
            TypeError: preserveがboolでない、または対象がJointの場合。
            RuntimeError: ノードが無効、または Maya が設定を拒否した場合。

        Jointは独立したピボットの変更をサポートしないため、更新前に拒否する。
        """
        ws = world_space(worldSpace)
        if kind not in ("rotate", "scale", "both"):
            raise ValueError("kind must be 'rotate', 'scale' or 'both'")
        if not isinstance(preserve, bool):
            raise TypeError("preserve must be a bool")
        if self.isType("joint"):
            raise TypeError("Joint does not support independent rotate/scale pivots")
        values = tuple(value)
        if len(values) != 3 or not all(math.isfinite(v) for v in values):
            raise ValueError("Expected three finite pivot coordinates")
        coordinates = [om2.MDistance(v).asUnits(om2.MDistance.uiUnit()) for v in values]
        flag = {"rotate": "rotatePivot", "scale": "scalePivot", "both": "pivots"}[kind]
        cmds.xform(self.getFullName(), worldSpace=ws, objectSpace=not ws,
                   preserve=preserve, **{flag: coordinates})
        return self

    @undoChunk("hlibTransformCenterPivot")
    def centerPivot(self):
        """Maya標準のバウンディングボックス中心へ両ピボットを移動する。

        xformのcenterPivotsと同じ対象範囲を使用する。preserve=Trueで
        オブジェクトの変換結果を維持し、回転・スケールピボットを変更する。
        コンポーネントの選択状態は使用しない。

        Returns:
            Transform: 自身。一回のUndoで戻せる。

        Raises:
            RuntimeError: 無効なノードやロックなどでMayaが変更を拒否した場合。
        """
        cmds.xform(self.getFullName(), centerPivots=True, preserve=True)
        return self

    @flag_aliases(ws="worldSpace")
    def getBoundingBox(self, worldSpace=False):
        """直下の Shape 階層を含むバウンディングボックスを取得する。

        MFnDagNode.boundingBox は自身の translate/rotate/scale は含むが、
        親から継承した変換は含まない（``cmds.xform(-boundingBox)`` と同じ）。
        ``ws=True`` はそこへ親のワールド行列をさらに適用し、真のワールド空間の
        バウンディングボックスを返す。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
                （親の変換は含まない）。

        Returns:
            om2.MBoundingBox: 軸並行境界ボックス。Maya API の内部距離単位。
                子 Shape が無い場合は原点のみを含む空に近いボックスになる。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        ws = world_space(worldSpace)
        if not self.isValid():
            raise RuntimeError("Cannot compute the bounding box of an invalid transform")
        box = self.dagFn().boundingBox
        if not ws:
            return box
        parent_matrix = self._parent_world_matrix()
        world_box = om2.MBoundingBox()
        for x in (box.min.x, box.max.x):
            for y in (box.min.y, box.max.y):
                for z in (box.min.z, box.max.z):
                    # Matrix は om2.MMatrix の派生なので、MPoint との積をそのまま使える。
                    world_box.expand(om2.MPoint(x, y, z) * parent_matrix)
        return world_box

    def getRoot(self):
        """DAG 階層の最上位祖先を取得する。

        DAG 上の親は常に Transform であるため、祖先も常に Transform になる。

        Returns:
            Transform: ワールド直下の祖先ノード。自身がワールド直下ならその自身を返す。
        """
        node = self
        parent = node.getParent()
        while parent is not None:
            node = parent
            parent = node.getParent()
        return node

    def getChildNodes(self):
        """直接の子ノードを登録された型の Node のリストとして取得する。

        Returns:
            list[Node]: 直接の子ノード。
        """
        if not self.isValid():
            return []
        dagPath = self.mpath()
        dagFn = self.dagFn()
        children = []
        for index in range(dagFn.childCount()):
            child_path = om2.MDagPath(dagPath)
            child_path.push(dagFn.child(index))
            children.append(Node(child_path))
        return children

    def getChildren(self, shapes=False, intermediates=False):
        """指定条件に合う直接の子ノードを取得する。

        Args:
            shapes (bool): TrueはShapeも含める。既定FalseはTransformのみ。
            intermediates (bool): Trueは中間オブジェクトも含める。

        Returns:
            list[DagNode]: DAGの子順に並んだノード。該当なしは空リスト。
        """
        return [child for child in self.getChildNodes()
                if (shapes or isinstance(child, Transform))
                and (intermediates or not child.dagFn().isIntermediateObject)]

    def getLeaves(self):
        """Transform 階層下の葉ノード（子 Transform を持たないもの）をすべて取得する。

        Shape の有無は判定に関与しない。

        Returns:
            list[Transform]: 葉ノードのリスト。子 Transform が無い場合は自身のみを含む。
        """
        children = self.getChildren()
        if not children:
            return [self]
        result = []
        for child in children:
            result.extend(child.getLeaves())
        return result

    def getSiblings(self):
        """親を同じくする兄弟 Transform を取得する（自身は含まない）。

        自身がワールド直下の場合は、他のワールド直下 Transform を対象にする。

        Returns:
            list[Transform]: 兄弟 Transform のリスト。
        """
        if not self.isValid():
            return []
        parent = self.getParent()
        if parent is not None:
            candidates = parent.getChildren()
        else:
            candidates = self._world_assemblies()
        self_uuid = self.getUuid()
        return [
            candidate for candidate in candidates
            if isinstance(candidate, Transform) and candidate.getUuid() != self_uuid
        ]

    def getShapes(self, intermediates=False):
        """このTransform直下のShapeを取得する。

        Args:
            intermediates (bool): ``True`` の場合は中間Shapeも含める。

        Returns:
            list[Shape]: 条件に一致するShapeのリスト。
        """
        from .shape import Shape

        if not self.isValid():
            return []
        shapes = []
        dagPath = self.mpath()
        dagFn = self.dagFn()
        for index in range(dagFn.childCount()):
            child = dagFn.child(index)
            if not child.hasFn(om2.MFn.kShape):
                continue
            child_fn = om2.MFnDagNode(child)
            if not intermediates and child_fn.isIntermediateObject:
                continue
            child_path = om2.MDagPath(dagPath)
            child_path.push(child)
            shapes.append(Shape(child_path))
        return shapes

    @flag_aliases(ws="worldSpace")
    @fast_edit
    @undoChunk("hlibTransformMirrorGeometry")
    def mirrorGeometry(self, axis="x", worldSpace=False, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False):
        """直下のすべてのShapeのジオメトリをミラーする。

        直下の各Shape（Mesh、NurbsCurveなど mirror を実装するもの）へ同じ引数で
        処理を委譲する。indices は Shape ごとの要素番号（Mesh は頂点、NurbsCurve は
        CV）として解釈される。Transform自身の行列やShapeの構造は変更しない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            axis (str): 反転する座標軸。x、y、z、xy、xz、yz、xyz。大文字も可。
                x は pivot.x を通る YZ 平面で反転する。複数軸は同時に反転する。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            pivot (Iterable[float]): 指定空間での反転中心。既定はその空間の原点。
                単位は 内部距離単位cm。Transform のピボットとは独立する。
            indices (Iterable[int] | None): 各Shapeへそのまま渡す要素番号。
                None は全要素、空列は変更なし。

        Returns:
            Transform: 編集した自身。

        Raises:
            ValueError: 軸・空間・中心が不正、またはワールド変換が数値的にほぼ特異な場合。
            TypeError: 要素番号が整数でない場合、または直下のShapeが mirror を実装しない場合。
            IndexError: 要素番号が範囲外の場合。
            RuntimeError: Maya が形状の取得・編集を拒否した場合。

        複数のShapeを持つ場合、途中のShapeで失敗すると以降のShapeは処理されない
        （それまでに成功した分はロールバックしない）。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        ws = world_space(worldSpace)
        for shape in self.getShapes():
            shape.mirror(axis=axis, ws=ws, pivot=pivot, indices=indices)
        return self

    @flag_aliases(index="idx")
    def getShape(self, idx=0, intermediates=False):
        """指定位置のShapeを取得する。

        Args:
            idx (int): Shapeのインデックス。 別名 ``index`` も使用可能。
            intermediates (bool): ``True`` の場合は中間Shapeも含める。

        Returns:
            Shape | None: 指定位置のShape。範囲外ではNone。
        """
        shapes = self.getShapes(intermediates=intermediates)
        try:
            return shapes[idx]
        except IndexError:
            return None

    def getTransform(self):
        """Transform自身を返す。

        Returns:
            Transform: 自身。
        """
        return self

    @undoChunk("hlibTransformSetParent")
    def setParent(self, parent=None, relative=False, add=False):
        """Transformの親を変更する。

        Args:
            parent (Node | str | om2.MObject | om2.MDagPath | None): 新しい親。None はワールド直下。
                ``Node(parent)`` で解決できる型(Plug・Component は所有ノード)を受け付ける。
            relative (bool): True は親変更前のローカル変換を保持する。False は Maya の既定動作。
            add (bool): True は既存の親を維持して追加の親を設定する。parent が None の場合は渡されない。

        Returns:
            Transform: 自身。
        """
        if not self.isValid():
            raise RuntimeError("Cannot parent an invalid transform")
        if parent is None:
            if self.getParentPath() is None and not self.mpath().isInstanced():
                return self
            cmds.parent(self.getName(), world=True, relative=relative)
        else:
            target = parent if isinstance(parent, Node) else Node(parent)
            parent_name = target.getFullName()
            # 古いMayaでは同じ親への再parentがエラーになる。
            # add=Trueはインスタンス操作なのでMayaの判定に委ねる。
            current = self.getParentPath()
            if (not add and not self.mpath().isInstanced() and current is not None
                    and current.fullPathName() == parent_name):
                return self
            cmds.parent(self.getName(), parent_name, relative=relative, add=add)
        return self

    @undoChunk("hlibTransformMatch")
    def matchTransform(self, target, position=True, rotation=True, scale=True, pivots=False):
        """自身の変換を指定Transformへ合わせる。選択状態は使用しない。

        Args:
            target (Transform | str | om2.MObject | om2.MDagPath): 合わせ先のTransformまたはjoint。
                hlib.nodes.Node._resolve_input が受け付ける型(Plug は所有ノード)を指定できる。
            position (bool): 位置を合わせる。
            rotation (bool): 回転を合わせる。
            scale (bool): スケールを合わせる。
            pivots (bool): 回転・スケールピボットも合わせる。

        Returns:
            Transform: 自身。全フラグFalseなら何も変更しない。

        Raises:
            TypeError: targetがTransformではない場合。
            RuntimeError: ノードが無効、またはMayaが変更を拒否した場合。
            DeletedAttributeError: targetに、アトリビュートが削除済みの Plug / MPlug を渡した場合
                (ValueError と RuntimeError の両方の派生)。

        maya.cmds.matchTransformと同じ空間・joint・ピボット処理を使用する。
        shearの一致や行列全体のコピーは保証しない。
        """
        from ..nodes.node import Node as _InputNode

        target = _InputNode._resolve_input(target)
        if not isinstance(target, Transform):
            raise TypeError("Target must be a transform or joint")
        if any((position, rotation, scale, pivots)):
            cmds.matchTransform(self.getFullName(), target.getFullName(), position=position,
                                rotation=rotation, scale=scale, pivots=pivots)
        return self

    @flag_aliases(ws="worldSpace")
    @fast_edit
    @undoChunk("hlibTransformMirrorTransform")
    def mirrorTransform(self, axis="x", worldSpace=False, pivot=(0.0, 0.0, 0.0), *, fast=False):
        """位置と向きを指定空間でビヘイビアミラーする。

        Matrix.mirrorと同じ回転規約で、負スケールによる形状反転ではない。
        Shapeの頂点・CVは編集しない。子孫は通常の親変換として追従する。
        指定空間のスケール・シアーを保つが、親に非一様スケールがある場合は
        ローカルのスケール・シアーが変わる場合がある。

        Args:
            axis (str | int): x/y/z/xy/xz/yz/xyz、または0/1/2。xはYZ平面。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            pivot (Iterable[float]): 指定空間の中心。内部距離単位cm。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。

        Returns:
            Transform: 自身。Transforms/Jointsからの一括呼出も可能。

        Raises:
            TypeError: fast が bool でない場合。
            ValueError: 入力不正、特異な親行列、未対応のピボット/rotateAxisの場合。
            RuntimeError: ロックや入力接続で更新できない場合。

        setMatrix() と同じ制約があり、非ゼロのピボット・
        TransformのrotateAxisは更新前に拒否する。
        """
        ws = world_space(worldSpace)
        from ..utils.mirror import mirrorArguments
        if not isinstance(ws, bool):
            raise TypeError("ws must be a bool")
        _, center = mirrorArguments(axis, pivot)
        name = self.getFullName()
        parent_node = self.getParent()
        parent = Matrix()
        if parent_node is not None and self.getPlug("inheritsTransform").get():
            # 親のチャンネル変更直後も評価済み値を取得する。
            parent = parent_node.getPlug("worldMatrix")[parent_node.mpath().instanceNumber()].get()
        offset = self.getPlug("offsetParentMatrix").get()
        effective_parent = offset * parent
        magnitude = max(1.0, *(sum(abs(effective_parent[row, col]) for col in range(3))
                               for row in range(3)))
        if abs(effective_parent.det4x4()) <= 1e-12 * magnitude ** 3:
            raise ValueError("Cannot mirror with a singular parent or offsetParentMatrix")
        attributes = ["rotatePivot", "scalePivot", "rotatePivotTranslate", "scalePivotTranslate"]
        if not self.mnode().hasFn(om2.MFn.kJoint):
            attributes.append("rotateAxis")
        if any(any(self.getPlug(attr).get()) for attr in attributes):
            raise ValueError("mirrorTransform does not support nonzero pivots or transform rotateAxis")
        world = self.getMatrix(ws=True)
        source = world if ws else world * parent.inverse()
        target = source.mirror(axis, center)
        target_world = target if ws else target * parent
        local = target_world * effective_parent.inverse()
        self.setMatrix(local, fast=fast)
        return self

    def getShadingEngines(self):
        """直下の非中間Shapeで使用中のセット。インスタンス経路を保持。

        Returns:
            list[ShadingEngine]: 直下の非中間Shapeで使用中のセット。インスタンス経路を保持。
        """
        return list(dict.fromkeys(group for shape in self.getShapes() for group in shape.getShadingEngines()))

    def getOffsetParentMatrix(self):
        """offsetParentMatrixの現在値を取得する。

        Returns:
            Matrix: アトリビュート値の複製。ワールド行列やローカル行列との合成はしない。

        Raises:
            RuntimeError: ノードやアトリビュートが無効の場合。
        """
        return self.getPlug("offsetParentMatrix").get()

    @fast_edit
    @undoChunk("hlibTransformSetOffsetParentMatrix")
    def setOffsetParentMatrix(self, value, *, fast=False):
        """offsetParentMatrixへ行列値を設定する。

        Args:
            value (Matrix | Iterable[float]): 別Transform.getMatrix()の戻り値などの4x4行列。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Transform: 自身。Transformsでは各対象へ同じ値を設定する。

        Raises:
            TypeError: fastがboolでない場合。
            ValueError: 行列値が不正な場合。
            RuntimeError: 無効な対象・ロック・入力接続などで更新できない場合。

        TRSチャンネル値は変更しない。指定行列は既存ローカル行列と親行列に合成される。
        ワールド姿勢の自動一致・入力接続の切断・ロック解除は行わない。
        """
        self.getPlug("offsetParentMatrix").set(value)
        return self

    @flag_aliases(ws="worldSpace")
    def getTransformation(self, worldSpace=False):
        """チャンネルと補助成分を独立した値として取得する。

        Args:
            worldSpace (bool): ワールド空間へ変換する。短縮名ws。
        Returns:
            Transformation: Euler回転順序・ピボット・補助回転・SSCを含む値。
                offsetParentMatrixと親行列はワールド指定時の合成に含める。
        """
        ws = world_space(worldSpace)
        values = {name: self.getPlug(name).get() for name in (
            "translate", "rotate", "scale", "shear", "rotateOrder", "rotateAxis",
            "rotatePivot", "rotatePivotTranslate", "scalePivot", "scalePivotTranslate")}
        values["rotate"] = EulerRotation(values["rotate"], order=values["rotateOrder"])
        values["rotateAxis"] = EulerRotation(values["rotateAxis"])
        if self.mnode().hasFn(om2.MFn.kJoint):
            values.update(jointOrient=EulerRotation(self.getPlug("jointOrient").get()),
                          inverseScale=self.getPlug("inverseScale").get(),
                          segmentScaleCompensate=bool(self.getPlug("segmentScaleCompensate").get()))
            # Mayaのjoint行列はピボットを使わない。
            for key in ("rotatePivot", "rotatePivotTranslate", "scalePivot", "scalePivotTranslate"):
                values[key] = (0, 0, 0)
        else:
            values["segmentScaleCompensate"] = False
        result = Transformation(**values)
        if ws:
            result *= Matrix(self.mpath().exclusiveMatrix())
            if result.ssc and tuple(result.inverseScale) != (1, 1, 1):
                matrix = result.matrix
                result.inverseScale = (1, 1, 1)
                result.matrix = matrix
            else:
                result.inverseScale = (1, 1, 1)
        return result

    @flag_aliases(ws="worldSpace")
    @undoChunk("hlibTransformSetTransformation")
    def setTransformation(self, value, worldSpace=False, safe=False, get=False):
        """補助成分を含む変換を適用する。入力の値は変更しない。

        Args:
            value (Transformation): 適用する変換情報。
            worldSpace (bool): ワールド空間として適用する。短縮名ws。
            safe (bool): 書けない成分を残して、書ける成分で行列を合わせる。
            get (bool): シーンを更新せず、対象ノード用に補正した値を返す。
        Returns:
            Transform | Transformation: 通常は自身。get=Trueは設定予定値。
        Note:
            inverseScaleの接続は保持する。jointとtransformを相互コピーする場合は
            対象で使えない補助成分を除き、行列を維持するようにTRSを補正する。
        """
        if not isinstance(value, Transformation):
            raise TypeError("value must be a Transformation")
        ws = world_space(worldSpace)
        if ws:
            parent = Matrix(self.mpath().exclusiveMatrix())
            magnitude = max(1.0, *(sum(abs(parent[row, col]) for col in range(3)) for row in range(3)))
            if abs(parent.det4x4()) <= 1e-12 * magnitude ** 3:
                raise ValueError("Cannot apply a world transformation with a singular parent matrix")
            fitted = value * parent.inverse()
        else:
            fitted = value.copy()
        matrix = fitted.matrix
        is_joint = self.mnode().hasFn(om2.MFn.kJoint)
        if is_joint:
            for name in ("rotatePivot", "rotatePivotTranslate", "scalePivot", "scalePivotTranslate"):
                setattr(fitted, name, (0, 0, 0))
            fitted.inverseScale = self.getPlug("inverseScale").get()
        else:
            fitted.jointOrient = Quaternion()
            fitted.segmentScaleCompensate = False
            fitted.inverseScale = (1, 1, 1)
        if not fitted.matrix.isEquivalent(matrix):
            fitted.matrix = matrix
        if get:
            return fitted
        modifiers = ["rotateOrder", "rotateAxis"]
        if is_joint:
            modifiers += ["jointOrient", "segmentScaleCompensate"]
        else:
            modifiers += ["rotatePivot", "rotatePivotTranslate", "scalePivot", "scalePivotTranslate"]
        for name in modifiers:
            current = getattr(fitted, name)
            if name in ("rotateAxis", "jointOrient"):
                # 等価なクォータニオンでもチャンネルの数値を不用意に反転しない。
                reference = EulerRotation(self.getPlug(name).get())
                current = current.asEulerRotation().closestSolution(reference)
            if name in ("rotateOrder", "segmentScaleCompensate"):
                self.getPlug(name).set(current, safe=safe)
            else:
                self._set_channel_value(name, current, safe=safe)
        if safe:
            # 書込みできなかった補助成分を実際の状態へ戻してからTRSを計算する。
            actual = self.getTransformation()
            reference = EulerRotation(fitted.rotate)
            reference.reorderIt(actual.rotateOrder)
            actual.rotate = reference
            actual.scale = fitted.scale
            actual.matrix = matrix
            fitted = actual
        for name in ("translate", "rotate", "scale", "shear"):
            self._set_channel_value(name, getattr(fitted, name), safe=safe)
        return self

    @flag_aliases(ws="worldSpace")
    def getMatrix(self, worldSpace=False, p=False, inv=False):
        """変換行列を取得する。

        ワールド空間は保持する DAG パスの inclusiveMatrix から取得する。
        ローカル空間は評価済みの ``matrix`` アトリビュートを直接読み取る。
        どちらも行列値を保持し続けず、呼出し時点の Maya の評価結果を返す。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
                ローカル空間（``matrix``）の値を取得する。ワールド空間では、
                :meth:`dagPath` が示す DAG インスタンスの要素
                (``worldMatrix[<インスタンス番号>]``)を使う。

            p (bool): 親行列を取得する。
            inv (bool): 逆行列を返す。

        Returns:
            Matrix: 指定空間の評価済み行列の複製(om2.MMatrix の派生)。

        Raises:
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        ws = world_space(worldSpace)
        if not self.isValid():
            raise RuntimeError("無効なノードの行列は取得できません")
        path = self.mpath()
        if ws:
            matrix = path.exclusiveMatrix() if p else path.inclusiveMatrix()
        elif p:
            parent = om2.MDagPath(path).pop()
            matrix = parent.inclusiveMatrix() * parent.exclusiveMatrixInverse()
        else:
            plug = om2.MPlug(self.mnode(), _transform_attribute("matrix"))
            matrix = om2.MFnMatrixData(plug.asMObject()).matrix()
        return Matrix._wrap(matrix.inverse() if inv else matrix)

    @flag_aliases(ws="worldSpace")
    @fast_edit
    @undoChunk("hlibTransformSetMatrix")
    def setMatrix(self, matrix, worldSpace=False, safe=False, get=False, *, fast=False):
        """行列をローカルまたはワールド空間で設定する。

        行列を分解して translate・rotate・scale・shear に書き込む。スケールの符号と
        Euler の解は、同じ行列になる候補のうち現在のチャンネル値に近いものを選ぶ
        (詳細は ``_apply_local_matrix``)。そのため ``cmds.xform(matrix=...)``
        (常に om2 の規約で書く)とは、負スケールのノードや Euler の別解でチャンネル値が
        異なることがあるが、結果の行列は同じ。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            matrix (Matrix | sequence): 適用する変換行列。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。

            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずtranslate/rotate/scale/shearの辞書を返す。

        Returns:
            Transform | dict: 通常は自身、get=Trueは内部単位の設定値。

        Raises:
            RuntimeError: 無効なノード、または Maya がアトリビュート設定を拒否した場合。
            ValueError: 入力行列が不正、分解不能、またはワールド指定時の親行列が逆行列を持たない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        ws = world_space(worldSpace)
        if safe or get:
            matrix = Matrix(matrix)
            if ws:
                matrix *= Matrix._wrap(self.mpath().exclusiveMatrixInverse())
            values = self._matrix_channel_values(matrix)
            if get:
                return values
            for name, value in values.items():
                self._set_channel_value(name, value, safe=True)
            return self
        return self._set_matrix(matrix, ws)

    @flag_aliases(ws="worldSpace")
    def getTranslation(self, worldSpace=False, at=2):
        """基準位置を取得する。既定は回転ピボット位置。

        Args:
            worldSpace (bool): ワールド指定。短縮名ws。
            at (int): 0=親原点、1=translate、2=回転ピボット、3=スケールピボット、4以上=行列原点。
        Returns:
            Translation: cm単位の位置。
        """
        ws = world_space(worldSpace)
        if at >= 3:
            matrix = self.getMatrix(ws=ws)
            if at >= 4:
                return matrix.translate
            point = om2.MPoint(tuple(self.getPlug("scalePivot").get())) * matrix
        elif at < 1:
            point = om2.MPoint()
            if ws:
                point *= self.mpath().exclusiveMatrix()
        else:
            value = om2.MVector(tuple(self.getPlug("translate").get()))
            if at >= 2:
                offset = om2.MVector(tuple(self.getPlug("rotatePivot").get()))
                offset += om2.MVector(tuple(self.getPlug("rotatePivotTranslate").get()))
                inv_scale = self._inverse_scale_values()
                value += om2.MVector(*(offset[i] / inv_scale[i] for i in range(3)))
            point = om2.MPoint(value)
            if ws:
                point *= self.mpath().exclusiveMatrix()
        return Translation(point.x, point.y, point.z)

    @flag_aliases(ws="worldSpace")
    @fast_edit
    @undoChunk("hlibTransformSetTranslate")
    def setTranslation(self, value, worldSpace=False, at=2, safe=False, get=False, *, fast=False):
        """指定基準の位置へ移動する。ピボットや回転は変更しない。

        Args:
            value (Iterable[float]): cm単位の位置。
            worldSpace (bool): ワールド指定。短縮名ws。
            at (int): getTranslationと同じ基準。既定2。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずtranslateの計算値だけを返す。
            fast (bool): Undoなしの直接更新。
        Returns:
            Transform | list[float]: 自身。get=Trueはtranslateの計算値。
        """
        ws = world_space(worldSpace)
        point = om2.MPoint(tuple(value))
        if ws:
            point *= self.mpath().exclusiveMatrixInverse()
        current = om2.MVector(tuple(self.getPlug("translate").get()))
        if at < 1:
            result = om2.MVector(point) - current
        else:
            result = current + (om2.MVector(point) - om2.MVector(tuple(self.getTranslation(at=at))))
        if get:
            return list(result)
        self._set_channel_value("translate", result, safe=safe)
        return self

    @flag_aliases(ws="worldSpace")
    def getRotation(self, worldSpace=False):
        """Euler 回転値を、ノードの rotateOrder で取得する。

        ``cmds.xform(query=True, rotation=True)`` と同じく、値はノードの rotateOrder で
        表す(戻り値の order もノードの回転順序)。行列を分解した回転の等価な解のうち、
        transform では現在の rotate チャンネル値に最も近いものを返すため、ローカル空間の
        transform(rotateAxis が 0)ではチャンネル値と一致する(浮動小数点の誤差を除く)。
        joint の値は jointOrient と rotateAxis を含む行列全体の回転で、解は 0 回転に
        最も近いものを選ぶ。スケールの符号は現在のチャンネルを基準とする。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。

        Returns:
            EulerRotation: 評価済みの回転値（radian、ノードの回転順序）。

        Raises:
            ValueError: 行列を分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        ws = world_space(worldSpace)
        _, quaternion, _, _, reference = self._decompose_like_channels(self.getMatrix(ws=ws))
        return EulerRotation._wrap(_closest_euler(quaternion, self._rotate_reference(reference)))

    @flag_aliases(ws="worldSpace")
    @fast_edit
    @undoChunk("hlibTransformSetRotate")
    def setRotation(self, value, worldSpace=False, safe=False, get=False, *, unit="rad", fast=False):
        """Euler回転を設定する。

        3成分の値は ``cmds.xform(rotation=...)`` と同じくノードの rotateOrder の値として
        解釈する(:meth:`getRotation` や ``getPlug("rotate").get()`` の値をそのまま渡せる)。
        書き込む rotate は、同じ回転を表す解のうち現在のチャンネル値に最も近いもの。
        ローカル空間の transform では通常は渡した値がそのまま入る(浮動小数点の誤差を
        除く。現在値が 0 のノードへ 370 度を渡すと 10 度になるなど、等価な解に
        置き換わることはある)。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Iterable[float] | EulerRotation | Quaternion): 回転値。3成分はノードの
                rotateOrder の値として解釈する。EulerRotation(om2.MEulerRotation)は
                その回転順序を反映する。unit が rad の場合は Quaternion も受け入れる。
                ノードへは rotateOrder に並べ替えて書き込む。
            unit (str): rad はラジアン、deg は度の3成分。既定は rad。deg は3成分の
                値にだけ使える。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。

            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずrotateチャンネル値を返す。

        Returns:
            Transform | list[float]: 通常は自身、get=Trueはrad単位の計算値。

        Raises:
            ValueError: unit が rad/deg 以外、deg を EulerRotation / Quaternion と指定、
                値が3成分でない、行列が分解不能、または必要な親行列が反転不能の場合。
            RuntimeError: ノードが無効、またはアトリビュートを書き込めない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        ws = world_space(worldSpace)
        if unit not in ("rad", "deg"):
            raise ValueError("unit must be 'rad' or 'deg'")
        if isinstance(value, (om2.MEulerRotation, om2.MQuaternion)):
            if unit == "deg":
                raise ValueError("unit='deg' is only supported for three plain components")
        else:
            if not self.isValid():
                raise RuntimeError("Cannot set an invalid transform")
            x, y, z = value
            if unit == "deg":
                x, y, z = math.radians(x), math.radians(y), math.radians(z)
            # cmds.xform と同じく、3成分はノードの rotateOrder の値として解釈する。
            value = EulerRotation(x, y, z, self._rotate_order())
        matrix = self._replace_components(self.getMatrix(ws=ws), rotate=value)
        result = self.setMatrix(matrix, ws=ws, safe=safe, get=get)
        return list(result["rotate"]) if get else self

    @flag_aliases(ws="worldSpace")
    def getScaling(self, worldSpace=False):
        """指定空間のスケール値を取得する。

        Args:
            worldSpace (bool): ワールド指定。短縮名ws。Falseはscaleチャンネル。
        Returns:
            Scale: ローカルではSSCを除く値、ワールドではAPI規約の分解値。
        """
        if world_space(worldSpace):
            return Scale(*om2.MTransformationMatrix(self.getMatrix(ws=True)).scale(MSpace.kTransform))
        return self.getPlug("scale").get()

    @flag_aliases(ws="worldSpace")
    @fast_edit
    def setScaling(self, value, worldSpace=False, safe=False, get=False, *, fast=False):
        """scaleチャンネルだけを設定する。

        Args:
            value (Iterable[float]): スケール3成分。
            worldSpace (bool): ワールド指定。短縮名ws。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずチャンネル値を返す。
            fast (bool): Undoなしの直接更新。
        Returns:
            Transform | list[float]: 自身。get=Trueは計算値。
        """
        values = self._scaling_channel_value(value, world_space(worldSpace))
        if get:
            return values
        self._set_channel_value("scale", values, safe=safe)
        return self

    @flag_aliases(ws="worldSpace")
    def getShearing(self, worldSpace=False):
        """指定空間のシアー値を取得する。

        Args:
            worldSpace (bool): ワールド指定。短縮名ws。Falseはshearチャンネル。
        Returns:
            Shear: 指定空間のシアー。
        """
        if world_space(worldSpace):
            return Shear(*om2.MTransformationMatrix(self.getMatrix(ws=True)).shear(MSpace.kTransform))
        return self.getPlug("shear").get()

    @flag_aliases(ws="worldSpace")
    @fast_edit
    def setShearing(self, value, worldSpace=False, safe=False, get=False, *, fast=False):
        """shearチャンネルだけを設定する。

        Args:
            value (Iterable[float]): シアー3成分。
            worldSpace (bool): ワールド指定。短縮名ws。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずチャンネル値を返す。
            fast (bool): Undoなしの直接更新。
        Returns:
            Transform | list[float]: 自身。get=Trueは計算値。
        """
        values = self._scaling_channel_value(value, world_space(worldSpace), shear=True)
        if get:
            return values
        self._set_channel_value("shear", values, safe=safe)
        return self

    @flag_aliases(ws="worldSpace")
    def getQuaternion(self, worldSpace=False, ra=False, r=True, jo=True):
        """回転成分を選んで取得する。既定ではrotateAxisを含めない。

        Args:
            worldSpace (bool): ワールド指定。短縮名ws。
            ra (bool): rotateAxisを含める。
            r (bool): rotateを含める。
            jo (bool): jointOrientを含める。
        Returns:
            Quaternion: 指定成分の合成回転。
        Raises:
            ValueError: 回転成分と空間指定が未対応の組合せの場合。
        """
        ws = world_space(worldSpace)
        joint = self.mnode().hasFn(om2.MFn.kJoint)
        if ws:
            if (ra and not (r and jo)) or (not ra and r and not jo):
                raise ValueError("Unsupported rotation component combination")
            matrix = self.getMatrix(ws=True, p=not (ra or r or (jo and joint)))
            q = om2.MQuaternion().setValue(om2.MMatrix(matrix).homogenize())
            if not ra and (r or (jo and joint)):
                q = self._component_quaternion("rotateAxis").inverse() * q
                if not r:
                    q = self._component_quaternion("rotate").inverse() * q
        else:
            if ra and not r and jo:
                raise ValueError("Unsupported rotation component combination")
            q = om2.MQuaternion()
            for enabled, name in ((ra, "rotateAxis"), (r, "rotate"), (jo and joint, "jointOrient")):
                if enabled:
                    q *= self._component_quaternion(name)
        return Quaternion._wrap(q)

    @flag_aliases(ws="worldSpace")
    @fast_edit
    @undoChunk("hlibTransformSetQuaternion")
    def setQuaternion(self, value, worldSpace=False, ra=False, r=True, jo=True,
                      safe=False, get=False, *, fast=False):
        """回転成分の指定に従いrotate・jointOrient・rotateAxisを設定する。

        Args:
            value (Quaternion | om2.MQuaternion | Iterable[float]): xyzwの回転。
            worldSpace (bool): ワールド指定。短縮名ws。
            ra (bool): 入力にrotateAxisを含む。
            r (bool): rotateを更新する。FalseはjointOrientまたはrotateAxis。
            jo (bool): jointOrientを含む。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まず計算したEuler成分を返す。
            fast (bool): Undoなしの直接更新。
        Returns:
            Transform | list[float]: 自身。get=Trueはrad単位の計算値。
        """
        ws = world_space(worldSpace)
        q = om2.MQuaternion(value) if isinstance(value, om2.MQuaternion) else om2.MQuaternion(*value)
        joint = self.mnode().hasFn(om2.MFn.kJoint)
        undo_ra = undo_r = None
        if ws:
            if not jo or (not r and (ra or not joint)):
                raise ValueError("Unsupported rotation component combination")
            jo = joint
            matrix = None
            if self.mpath().length() > 1:
                if not r:
                    undo_r = self._component_quaternion("rotate")
                    q = undo_r * q
                if not ra:
                    undo_ra = self._component_quaternion("rotateAxis")
                    q = undo_ra * q
                matrix = q.asMatrix() * self.mpath().exclusiveMatrixInverse()
            inv_scale = self._inverse_scale_values()
            if jo and inv_scale != (1.0, 1.0, 1.0):
                matrix = (q.asMatrix() if matrix is None else matrix) * Matrix(scale=inv_scale)
            if matrix is not None:
                q = om2.MQuaternion().setValue(om2.MMatrix(matrix).homogenize())
        else:
            jo = jo and joint
            if ra and not r and jo:
                raise ValueError("Unsupported rotation component combination")
        if undo_ra is not None:
            q = undo_ra.inverse() * q
        if undo_r is not None:
            q = undo_r.inverse() * q
        if r:
            if ra:
                q = self._component_quaternion("rotateAxis").inverse() * q
            if jo:
                q *= self._component_quaternion("jointOrient").inverse()
            name = "rotate"
            rotation = q.asEulerRotation().reorder(self._rotate_order())
        else:
            name = "jointOrient" if jo else "rotateAxis"
            rotation = q.asEulerRotation()
        if get:
            return list(rotation)
        self._set_channel_value(name, rotation, safe=safe)
        return self

    @flag_aliases(ws="worldSpace")
    def getEuler(self, worldSpace=False):
        """回転を XYZ 順序の EulerRotation として取得する。

        行列から分解した回転をXYZ順序で返す。getQuaternionのra/r/joによる
        合成対象の選択は行わない。ノードのrotateOrderで表す場合はgetRotationを使う。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。

        Returns:
            EulerRotation: 評価済みの回転値（radian、XYZ 順序）。

        Raises:
            ValueError: 行列を分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        ws = world_space(worldSpace)
        _, quaternion, _, _, _ = self._decompose_like_channels(self.getMatrix(ws=ws))
        return EulerRotation._wrap(quaternion.asEulerRotation())

    @flag_aliases("makeIdentity")
    @undoChunk("hlibTransformFreeze")
    def freeze(self, **kwargs):
        """MayaのmakeIdentity(apply=True)で形状の位置を保ってフリーズする。

        Args:
            **kwargs (object): translate(t)、rotate(r)、scale(s)、normal(n)、
                preserveNormals(pn)、jointOrient(jo)等のMaya標準フラグ。
                成分の省略時の扱いもMayaに従う。applyはTrueのみ許可する。

        Returns:
            Transform: 自身。Transformsからも一括呼出でき、Undo可能。

        Raises:
            ValueError: apply=Falseを指定した場合。
            TypeError: 長短フラグを重複指定した場合。
            RuntimeError: Mayaがフリーズを拒否した場合。

        子階層への適用、Jointの移動保持、スキニング済み対象や接続への制約も
        Maya標準に従う。resetやJoint.freezeRotationの姿勢移送とは異なる。
        """
        if kwargs.pop("apply", True) is not True:
            raise ValueError("freeze requires apply=True")
        return self.makeIdentity(apply=True, **kwargs)

    @undoChunk("hlibTransformMakeIdentity")
    def makeIdentity(self, **kwargs):
        """cmds.makeIdentity のシンプルなラッパー。

        Args:
            kwargs: cmds.makeIdentity にそのまま渡す追加のフラグ
                (apply、translate、rotate、scale、normal など)。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: ノードが無効、または Maya が拒否した場合。
        """
        if not self.isValid():
            raise RuntimeError("Cannot freeze transform of an invalid transform")
        cmds.makeIdentity(self.getFullName(), **kwargs)
        return self

    @undoChunk("hlibTransformReleaseSRT")
    def unlockAndDisconnectTransformChannels(self):
        """translate/rotate/scale/shear とその子チャンネルを一括でアンロック・切断する。

        各チャンネルとその X/Y/Z 子の両方についてロック解除と接続解除を行う。
        既にアンロック・未接続のチャンネルは変化しない。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.isValid():
            raise RuntimeError("Cannot release SRT channels of an invalid transform")
        for channel in ("translate", "rotate", "scale", "shear"):
            plug = self.getPlug(channel)
            plug.setFlags(locked=False)
            plug.disconnectAll()
            for child in plug.getChildren():
                child.setFlags(locked=False)
                child.disconnectAll()
        return self

    def getClosestAxisToVector(self, ref_vector, include_negative=True):
        """自身のローカル軸のうち、ワールド空間の方向ベクトルに最も近いものを求める。

        各ローカル軸をワールド行列（回転・スケールのみ、平行移動は無視）で変換し、
        正規化した上で ref_vector との内積が最大のものを選ぶ。

        Args:
            ref_vector (Vector | Iterable[float]): 比較対象のワールド空間方向ベクトル。
            include_negative (bool): True の場合、負方向の軸（-x/-y/-z）も候補に含める。

        Returns:
            str: 最も近い軸名("x"、"y"、"z"。include_negative が True なら
                "-x"、"-y"、"-z" も返り得る)。

        Raises:
            RuntimeError: ノードが無効な場合。
            ValueError: ref_vector またはいずれかのローカル軸がワールド変換後にゼロベクトルになる場合。
        """
        if not self.isValid():
            raise RuntimeError("Cannot evaluate axes of an invalid transform")
        if not isinstance(ref_vector, Vector):
            ref_vector = Vector(*ref_vector)
        ref_vector = ref_vector.unit()
        matrix = self.getMatrix(ws=True)
        axes = {"x": Vector(1.0, 0.0, 0.0), "y": Vector(0.0, 1.0, 0.0), "z": Vector(0.0, 0.0, 1.0)}
        if include_negative:
            axes.update({f"-{name}": axis * -1.0 for name, axis in axes.items()})
        best_axis = None
        best_dot = None
        for name, axis in axes.items():
            world_axis = matrix.transformVector(axis).unit()
            dot = world_axis.dot(ref_vector)
            if best_dot is None or dot > best_dot:
                best_dot = dot
                best_axis = name
        return best_axis

    @undoChunk("hlibTransformCreateOffsetGroups")
    def createOffsetGroups(self, *names):
        """自身を現在のワールド行列に一致させたオフセット(ゼロ)グループで包む。

        names の並びは外側から内側の順(例: ``"zero", "offset"`` なら zero が
        元の親の直下、offset が自身の直上の親になる)。各グループは作成時点の
        自身のワールド行列にそのまま一致するため、自身をそこへ付け替えても
        ワールド位置は変化しない。

        Args:
            names (str): 作成するグループ名。外側から内側の順。省略時は
                ``"<自身の名前>_offset"`` という1個のグループを作成する。

        Returns:
            list[Transform]: 作成したグループ。names と同じ並び(外側から内側)。

        Raises:
            RuntimeError: ノードが無効、または Maya がグループ作成・親変更を拒否した場合。
        """
        if not self.isValid():
            raise RuntimeError("Cannot create offset groups for an invalid transform")
        if not names:
            names = (f"{self.getName()}_offset",)
        matrix = self.getMatrix(ws=True)
        parent = self.getParent()
        groups = []
        for name in names:
            kwargs = {}
            if parent is not None:
                kwargs["parent"] = parent.getFullName()
            group = Transform(cmds.group(empty=True, name=name, **kwargs))
            group.setMatrix(matrix, ws=True)
            groups.append(group)
            parent = group
        self.setParent(groups[-1])
        return groups

    # 公開APIの短縮メソッド。旧hlib名の互換入口ではない。
    @flag_aliases(worldSpace="ws")
    def getJointOrientQuaternion(self, ws=False):
        """jointOrientまでのクォータニオンを取得する。

        Args:
            ws (bool): ワールド空間を使う。 別名 ``worldSpace`` も使用可能。
        Returns:
            Quaternion: rotateを除いた姿勢。
        """
        return self.getQuaternion(ws=ws, r=False)

    def _inverse_scale_values(self):
        """jointの有効なinverseScaleを返す。それ以外は単位スケール。"""
        if self.mnode().hasFn(om2.MFn.kJoint) and self.getPlug("segmentScaleCompensate").get():
            return tuple(self.getPlug("inverseScale").get())
        return (1.0, 1.0, 1.0)

    def _scaling_channel_value(self, value, ws, shear=False):
        """ワールドのscale/shear要求を、SSCを除いたチャンネル値へ変換する。

        Args:
            value: 変換・設定する入力値。
            ws: Trueはワールド空間、Falseはローカル空間。
            shear: XY/XZ/YZのシアー成分。
        """
        values = tuple(value)
        if len(values) != 3 or not all(math.isfinite(v) for v in values):
            raise ValueError("Expected three finite components")
        if ws:
            transform = om2.MTransformationMatrix(self.getMatrix(ws=True))
            if shear:
                transform.setShear(values, MSpace.kTransform)
            else:
                transform.setScale(values, MSpace.kTransform)
            matrix = transform.asMatrix() * self.mpath().exclusiveMatrixInverse()
            matrix *= Matrix(scale=self._inverse_scale_values())
            transform = om2.MTransformationMatrix(matrix)
            values = transform.shear(MSpace.kTransform) if shear else transform.scale(MSpace.kTransform)
        return list(values)

    def _component_quaternion(self, name):
        """回転アトリビュートを自身の回転順序でQuaternionへ変換する。

        Args:
            name: 参照・作成・照会する対象の名前。
        """
        value = self.getPlug(name).get()
        order = self._rotate_order() if name == "rotate" else om2.MEulerRotation.kXYZ
        return om2.MEulerRotation(*tuple(value), order).asQuaternion()

    @staticmethod
    def _world_assemblies():
        """ワールド直下の Transform をすべて取得する。

        Returns:
            list[Node]: ワールド直下(DAGパスの長さが1)の Transform ラッパー。
        """
        iterator = om2.MItDag(om2.MItDag.kBreadthFirst, om2.MFn.kTransform)
        assemblies = []
        while not iterator.isDone():
            path = iterator.getPath()
            if path.length() == 1:
                assemblies.append(Node(path))
            iterator.next()
        return assemblies

    def _parent_world_matrix(self):
        """親Transformのワールド行列を取得する。

        Returns:
            Matrix: 親のワールド行列。親がない、または親に getMatrix がなければ単位行列。
        """
        parent = self.getParent()
        if parent is None or not hasattr(parent, "getMatrix"):
            return Matrix()
        return parent.getMatrix(ws=True)

    def _rotate_order(self):
        """ノードの rotateOrder を om2 の回転順序の番号として取得する。

        Returns:
            int: 0(xyz)〜5(zyx)。om2.MEulerRotation.kXYZ〜kZYX と同じ番号。
        """
        return om2.MFnTransform(self.mnode()).rotation(om2.MSpace.kTransform).order

    def _channel_state(self):
        """現在の scale チャンネル値と rotate チャンネル値を内部単位で取得する。

        分解の解を現在のチャンネル値に近づけるための基準に使う。

        Returns:
            tuple: (scale の3成分の tuple, rotate の om2.MEulerRotation)。rotate は
            ラジアンで、順序はノードの rotateOrder。ノードが無効なら
            ((1.0, 1.0, 1.0), XYZ 順序の 0 回転)。
        """
        if not self.isValid():
            return (1.0, 1.0, 1.0), om2.MEulerRotation()
        # MFnTransform の scale() / rotation() は scale・rotate アトリビュートそのもの(joint でも
        # jointOrient を含まない)を返す。名前による findPlug より大幅に速い。
        fn = om2.MFnTransform(self.mnode())
        return tuple(fn.scale()), fn.rotation(om2.MSpace.kTransform)

    def _decompose_like_channels(self, matrix, scale_reference=None):
        """行列を分解し、スケールの符号の組み合わせを基準のスケールへ揃える。

        om2.MTransformationMatrix の規約(行列式が負なら Z が負)で分解してから、
        :func:`_match_scale_signs` で符号を揃える。基準は scale_reference (指定時)、
        次に現在の scale チャンネル値の順に、行列式の符号と合う最初のもの。これにより
        scale が (-1, 1, 1) のようなミラーのノードでも、取得・設定の往復でチャンネル値の
        符号と回転が保たれ、``setScaling`` では要求した符号がそのまま入る。

        Args:
            matrix (Matrix): 分解する行列。
            scale_reference (Iterable[float] | None): 最優先で符号を合わせるスケール
                (``setScaling`` で要求した値)。None なら現在の scale チャンネル値だけ。

        Returns:
            tuple: (translate(Translation), quaternion(om2.MQuaternion),
            scale(tuple), shear(tuple), reference(om2.MEulerRotation))。reference は
            現在の rotate チャンネル値で、Euler の解を選ぶ基準に使う。

        Raises:
            ValueError: 行列を分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        # Matrix.decompose() と同じ検査・分解だが、使わない Euler などの生成を省く。
        transformation = matrix._checked_transformation()
        reference_scale, reference_rotate = self._channel_state()
        if scale_reference is None:
            references = (reference_scale,)
        else:
            references = (tuple(scale_reference), reference_scale)
        quaternion, scale, shear = _match_scale_signs(
            transformation.rotation(asQuaternion=True),
            transformation.scale(om2.MSpace.kTransform),
            transformation.shear(om2.MSpace.kTransform),
            references,
        )
        return matrix.translate, quaternion, scale, shear, reference_rotate

    def _replace_components(self, matrix, rotate=None, scale=None, shear=None):
        """行列の回転・スケール・シアーの一部を置き換えた新しい行列を返す。

        置き換えない成分は :meth:`_decompose_like_channels` の分解値(スケールの符号を
        現在のチャンネルへ揃えた値)を使う。平行移動は行列の値をそのまま保つ。

        Args:
            matrix (Matrix): 元の行列。
            rotate (Iterable[float] | EulerRotation | Quaternion | None): 新しい回転。
                3成分は XYZ 順序のラジアン。None は現在の値。
            scale (Iterable[float] | None): 新しいスケール。None は現在の値。
            shear (Iterable[float] | None): 新しいシアー。None は現在の値。

        Returns:
            Matrix: 合成し直した新しい行列。

        Raises:
            ValueError: 元の行列を分解できない場合、または入力が不正な場合。
        """
        translate, quaternion, old_scale, old_shear, _ = self._decompose_like_channels(matrix)
        return Matrix(
            translate=translate,
            rotate=quaternion if rotate is None else rotate,
            scale=old_scale if scale is None else scale,
            shear=old_shear if shear is None else shear,
        )

    def _rotate_reference(self, reference):
        """:meth:`getRotation` が Euler の解を選ぶ基準を返す。

        transform では行列の回転と rotate チャンネルが同じ回転(rotateAxis が 0 の場合)
        なので、現在の rotate チャンネル値をそのまま基準にする。

        Args:
            reference (om2.MEulerRotation): 現在の rotate チャンネル値。

        Returns:
            om2.MEulerRotation: 基準の回転(順序はノードの rotateOrder)。
        """
        return reference

    def _channel_rotation(self, quaternion, reference):
        """ローカル行列の回転を、rotate チャンネルへ書き込む値へ変換する。

        transformではrotateAxisを除いてrotateチャンネルの回転を求める。

        Args:
            quaternion (om2.MQuaternion): ローカル行列の回転。
            reference (om2.MEulerRotation): 現在の rotate チャンネル値。

        Returns:
            om2.MEulerRotation: ノードの rotateOrder で表した、reference に最も近い解。
        """
        return _closest_euler(self._component_quaternion("rotateAxis").inverse() * quaternion, reference)

    def _apply_local_matrix(self, matrix, scale_reference=None):
        """ローカル行列の各成分をMayaアトリビュートへ適用する。

        行列を1回だけ分解し、平行移動・回転・スケール・シアーを順に書き込む。
        分解は om2.MTransformationMatrix の規約に、次の2点の選択を加えたもの。

        * スケールの符号の組み合わせは、行列式の符号が許す限り scale_reference
          (``setScaling`` で要求した値)、次に現在の scale チャンネルに揃える
          (:meth:`_decompose_like_channels`)。
        * 回転はノードの rotateOrder で表し、等価な解のうち現在の rotate チャンネル値に
          最も近いものを選ぶ(``om2.MEulerRotation.closestSolution``)。

        このため ``setMatrix(getMatrix())`` や ``setTranslation`` はチャンネル値を
        (浮動小数点の誤差を除いて)変えない。回転は現在のMaya角度単位へ変換して書き込む。
        ピボット・rotateAxis・jointOrient・SSCの補正を含める。

        Args:
            matrix (Matrix): ローカル空間の変換行列。
            scale_reference (Iterable[float] | None): 最優先で符号を合わせるスケール。
                None なら現在の scale チャンネル値に合わせる。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 行列を分解できない場合。
            RuntimeError: Maya がアトリビュートの書き込みを拒否した場合。
        """
        values = self._matrix_channel_values(matrix, scale_reference)
        for name, value in values.items():
            self._set_channel_value(name, value)

    def _set_channel_value(self, name, value, safe=False):
        """変換チャンネルを内部単位で設定する。通常更新はMayaのアニメーション編集に従う。

        数値がすでにノードの回転順序なので、Double3の回転変換や接続の事前拒否を
        再実行しない。fastでは共通バックエンドが入力接続への直接書込みを拒否する。

        Args:
            name: 参照・作成・照会する対象の名前。
            value: 変換・設定する入力値。
            safe: 書込みできない成分を飛ばして処理するか。
        """
        return Plug.set(self.getPlug(name), tuple(value), safe=safe)

    def _matrix_channel_values(self, matrix, scale_reference=None):
        """行列からtranslate/rotate/scale/shearの設定値を計算する。シーンは更新しない。

        Args:
            matrix: 変換または数値計算に使う行列。
            scale_reference: スケール補正の基準となるノードまたは値。
        """
        source = Matrix(matrix)
        inv_scale = self._inverse_scale_values()
        corrected = source * Matrix(scale=inv_scale)
        corrected.translate = source.translate
        _, q, scale, shear, reference = self._decompose_like_channels(corrected, scale_reference)
        rotation = self._channel_rotation(q, reference)
        sp = tuple(self.getPlug("scalePivot").get())
        rp = tuple(self.getPlug("rotatePivot").get())
        spt = tuple(self.getPlug("scalePivotTranslate").get())
        rpt = tuple(self.getPlug("rotatePivotTranslate").get())
        orient = self._component_quaternion("rotateAxis") * rotation.asQuaternion()
        if self.mnode().hasFn(om2.MFn.kJoint):
            orient *= self._component_quaternion("jointOrient")
        base = (Matrix(translate=tuple(-v for v in sp)) * Matrix(scale=scale, shear=shear)
                * Matrix(translate=sp) * Matrix(translate=spt)
                * Matrix(translate=tuple(-v for v in rp)) * Matrix(rotate=orient)
                * Matrix(translate=rp) * Matrix(translate=rpt)
                * Matrix(scale=tuple(1.0 / v for v in inv_scale)))
        translate = source.translate - base.translate
        return {"translate": Translation(*translate), "rotate": EulerRotation._wrap(rotation),
                "scale": Scale(*scale), "shear": Shear(*shear)}

    def _set_matrix(self, matrix, ws=False, scale_reference=None):
        """:meth:`setMatrix` の本体。Undo チャンクと fast の扱いは呼び出し元に任せる。

        Args:
            matrix (Matrix | sequence): 適用する変換行列。
            ws (bool): ``True`` でワールド空間、``False`` でローカル空間に設定する。
            scale_reference (Iterable[float] | None): 分解したスケールの符号を最優先で
                合わせる値(:meth:`setScaling` で要求した値)。None なら現在の scale
                チャンネル値に合わせる。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: 無効なノード、または Maya がアトリビュート設定を拒否した場合。
            ValueError: 入力行列が不正、分解不能、またはワールド指定時の親行列が逆行列を持たない場合。
        """
        if not isinstance(matrix, Matrix):
            matrix = Matrix(matrix)
        if not self.isValid():
            raise RuntimeError("Cannot set an invalid transform")
        local_matrix = matrix if not ws else matrix * Matrix._wrap(self.mpath().exclusiveMatrixInverse())
        self._apply_local_matrix(local_matrix, scale_reference)
        return self


@collection_export()
@bulk_api(
    Transform,
    reads=('addConstraint', 'deleteConstraints', 'transformFn', 'getPivot', 'getBoundingBox', 'getRoot', 'getChildNodes', 'getChildren', 'getLeaves', 'getSiblings', 'getShapes', 'getShape', 'getShadingEngines', 'getOffsetParentMatrix', 'getMatrix', 'getJointOrientQuaternion', 'getTransformation', 'getTranslation', 'getRotation', 'getScaling', 'getShearing', 'getQuaternion', 'getEuler', 'getClosestAxisToVector', 'createOffsetGroups'),
    writes=('freeze', 'resetPivot', 'reset', 'scaleGeometry', 'setPivot', 'centerPivot', 'mirrorGeometry', 'getTransform', 'setParent', 'matchTransform', 'mirrorTransform', 'setOffsetParentMatrix', 'setMatrix', 'setTransformation', 'setTranslation', 'setRotation', 'setScaling', 'setShearing', 'setQuaternion', 'makeIdentity', 'unlockAndDisconnectTransformChannels'),
)
class Transforms(DagNodes):
    """Joint等の派生型を含むTransform参照のコレクション。

    型検証・色設定・参照のコピーはNodesに従う。座標・行列操作は各対象へ転送する。
    """

    item_class = Transform
