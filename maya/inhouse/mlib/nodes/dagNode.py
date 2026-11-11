"""TransformとShapeに共通するDAG階層へのアクセスを提供する。"""

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

from ..core.fastWrite import require_writable, set_plug
from ..core.registry import _inherited_node_types, _real_node_type
from ..decorator import _edit_context, _pick_alias, _require_bool, undoChunk, undoTransaction
from ..maths import Vector
from ..util import _UNSET, _color_value, _world_space
from .node import Node

#: GUIのないMayaで使う、Maya標準のカラーインデックスのRGB。
_DEFAULT_COLOR_PALETTE = (
    (0.4699999988079071, 0.4699999988079071, 0.4699999988079071),
    (0.0, 0.0, 0.0),
    (0.25, 0.25, 0.25),
    (0.6000000238418579, 0.6000000238418579, 0.6000000238418579),
    (0.6079999804496765, 0.0, 0.15700000524520874),
    (0.0, 0.01600000075995922, 0.37599998712539673),
    (0.0, 0.0, 1.0),
    (0.0, 0.2750000059604645, 0.09799999743700027),
    (0.14900000393390656, 0.0, 0.2630000114440918),
    (0.7839999794960022, 0.0, 0.7839999794960022),
    (0.5410000085830688, 0.28200000524520874, 0.20000000298023224),
    (0.24699999392032623, 0.13699999451637268, 0.12200000137090683),
    (0.6000000238418579, 0.14900000393390656, 0.0),
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.2549999952316284, 0.6000000238418579),
    (1.0, 1.0, 1.0),
    (1.0, 1.0, 0.0),
    (0.3919999897480011, 0.8629999756813049, 1.0),
    (0.2630000114440918, 1.0, 0.6389999985694885),
    (1.0, 0.6899999976158142, 0.6899999976158142),
    (0.8939999938011169, 0.675000011920929, 0.4749999940395355),
    (1.0, 1.0, 0.3880000114440918),
    (0.0, 0.6000000238418579, 0.32899999618530273),
    (0.8549000024795532, 0.5686299800872803, 0.4274500012397766),
    (0.8784300088882446, 0.784309983253479, 0.30588001012802124),
    (0.6352900266647339, 0.8117600083351135, 0.2784300148487091),
    (0.2313700020313263, 0.7568600177764893, 0.5803899765014648),
    (0.2549000084400177, 0.8196099996566772, 0.7254899740219116),
    (0.22744999825954437, 0.6156899929046631, 0.8078399896621704),
    (0.6117600202560425, 0.41960999369621277, 0.8078399896621704),
    (0.8078399896621704, 0.34902000427246094, 0.6549000144004822),
)

#: overrideDisplayType の値(番号順)と、setDisplayType で指定する名前。
_DISPLAY_TYPES = ("normal", "template", "reference")


def _type_filter(value):
    """getChildren(type=) の指定を型名のtupleへ正規化する。

    Args:
        value (str | Iterable[str] | None): ノード型名、その列、またはNone。

    Returns:
        tuple[str, ...]: 型名。Noneは空。

    Raises:
        TypeError: 文字列・文字列の列・None以外の場合。
        ValueError: 空文字列を含む場合。
    """
    if value is None:
        return ()
    names = (value,) if isinstance(value, str) else tuple(value) if isinstance(value, (list, tuple)) else None
    if names is None or not all(isinstance(name, str) for name in names):
        raise TypeError("type must be a node type name, a sequence of names, or None")
    if not all(names):
        raise ValueError("type must not contain an empty node type name")
    return names


class DagNode(Node):
    """Transform・ShapeのDAGパスを保持し、階層を照会する。

    getParent/getChildrenは保持パス基準。全インスタンスの参照はgetInstancesで取得する。

    各メソッドの「保持するDAGパスが無効」には、保持インスタンスだけが外れた場合に加え、
    ノードごと削除された場合(Undoの記録に残っている間も含む)を含む。その間もMDagPathは
    古いパスを返すため、パスを使う照会は空文字列・削除前の名前を返さずRuntimeErrorにする。
    """

    def getSkinClusters(self):
        """自身のジオメトリを変形するSkinClusterを取得する。

        Shapeは自身、Transformは直下の非中間Shapeを対象にする。
        子Transform以下は検索しない。上流を探索した後、デフォーマの出力Shapeが
        対象と一致するものだけを返すため、別形状の履歴を混入させない。
        Mesh・NURBS等の形状に共通で使用でき、シーンやUndo履歴は変更しない。
        Jointの同名メソッドは従来のinfluence接続照会を維持する。

        Returns:
            list[SkinCluster]: Shape順、各Shapeの上流幅優先順。重複なし。
                対象なしは空リスト。

        Raises:
            RuntimeError: 無効なDAGパス、またはMayaの検索が失敗した場合。
        """
        path = self.mpath()
        obj = path.node()
        if obj.hasFn(om2.MFn.kTransform):
            fn = om2.MFnDagNode(path)
            shapes = [fn.child(i) for i in range(fn.childCount())
                      if fn.child(i).hasFn(om2.MFn.kShape)
                      and not om2.MFnDagNode(fn.child(i)).isIntermediateObject]
        else:
            shapes = [obj] if obj.hasFn(om2.MFn.kShape) else []
        result, seen = [], set()
        for shape in shapes:
            iterator = om2.MItDependencyGraph(
                shape, om2.MFn.kSkinClusterFilter,
                om2.MItDependencyGraph.kUpstream,
                om2.MItDependencyGraph.kBreadthFirst,
                om2.MItDependencyGraph.kNodeLevel,
            )
            iterator.pruningOnFilter = False
            while not iterator.isDone():
                skin = iterator.currentNode()
                key = om2.MFnDependencyNode(skin).uuid().asString()
                if key not in seen and any(
                        output == shape for output in oma2.MFnGeometryFilter(skin).getOutputGeometry()):
                    seen.add(key)
                    result.append(Node(skin))
                iterator.next()
        return result

    def getBindPoses(self):
        """getSkinClusters()で得たSkinClusterのバインドポーズを取得する。

        Shape/Transformは変形対象、Jointは既存のinfluence接続照会を使用する。
        SkinClusterの順を保ち、共有ポーズの重複と未接続を除く。

        Returns:
            list[DagPose]: 接続されたポーズ。対象なしは空リスト。

        Raises:
            RuntimeError: 無効な対象、または不正なバインドポーズ接続。
        """
        result, seen = [], set()
        for skin in self.getSkinClusters():
            pose = skin.getBindPose()
            if pose is not None:
                key = pose.getUuid()
                if key not in seen:
                    seen.add(key)
                    result.append(pose)
        return result

    def mpath(self):
        """保持する可変MDagPathを借用する。コピーは返さない。

        push/pop等で編集する前に ``om2.MDagPath(node.mpath())`` でコピーする。

        Returns:
            om2.MDagPath: 内部で保持するインスタンスのパスと同一のオブジェクト。

        Raises:
            RuntimeError: 保持パスが無効な場合。別インスタンスへ切り替えない。
        """
        dag_path = self._current_dag_path()
        # DagNode は初期化時に必ず DAG パスを解決して保持する(None は非DAGの Node だけ)。
        assert dag_path is not None
        return dag_path

    def mfn(self):
        """保持する DAG パスに対応する function set を、呼び出すたびに新しく作って返す。

        Transform・Mesh 等の派生クラスはさらに具体的な function set へ上書きする。

        Returns:
            om2.MFnDagNode: このインスタンスの function set。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        return om2.MFnDagNode(self.mpath())

    def getRoot(self):
        """保持するパスの最上位(ワールド直下)の祖先を取得する。

        DAG 上の親は常に Transform なので、Shape から呼んでも戻り値は Transform。
        自身がワールド直下ならその自身を返す。

        Returns:
            Transform: ワールド直下の祖先、または自身(ワールド直下に置けるのは Transform 系だけ)。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        node = self
        parent = node.getParent()
        while parent is not None:
            node = parent
            parent = node.getParent()
        return node

    def getCommonAncestor(self, other):
        """保持パスどうしで、自身とotherに共通する最も近い祖先を取得する。

        一方が他方の祖先(または同じパス)なら、その祖先自身を返す。インスタンスは保持パスだけで比べ、
        別のパスでの共通の祖先は探さない。

        Args:
            other (DagNode | str | om2.MObject | om2.MDagPath): 比べるDAGノード。

        Returns:
            DagNode | None: 共通の祖先。自身が該当すれば自身、otherが該当すればotherの参照、
                それ以外は新しいラッパー。ワールド直下の別々の階層にあればNone。

        Raises:
            TypeError: otherがDAGノードでない、または未対応の型の場合。
            RuntimeError: 自身またはotherのノード・保持するDAGパスが無効な場合。

        Examples:
            >>> hand.getCommonAncestor(foot)    # 腰など、両方を含む最も近い親
        """
        other_node = Node._resolve_input(other)
        if not isinstance(other_node, DagNode):
            raise TypeError(f"other must be a DAG node: {other_node.getFullName()}")
        self._require_valid("find the common ancestor of")
        other_node._require_valid("find the common ancestor of")
        self_path = self.mpath().fullPathName()
        other_path = other_node.mpath().fullPathName()
        other_ancestors = {other_path}
        path = om2.MDagPath(other_node.mpath())
        while path.length() > 1:
            path.pop()
            other_ancestors.add(path.fullPathName())
        if self_path in other_ancestors:
            return self
        path = om2.MDagPath(self.mpath())
        while path.length() > 1:
            path.pop()
            name = path.fullPathName()
            if name == other_path:
                return other_node
            if name in other_ancestors:
                # 有効な保持パスを遡ったパスなので、Node(path) の入力解決を省いて同じ型で包む。
                return Node._wrap_dag_path(path)
        return None

    def getSiblings(self):
        """同じ親の下にある同じ種類の兄弟を取得する(自身と自身の別インスタンスは含まない)。

        Transform は親直下の他の Transform、Shape は親直下の他の非中間 Shape を DAG の子順で返す。
        自身がワールド直下の Transform なら、他のワールド直下 Transform を対象にする。

        Returns:
            list[DagNode]: 兄弟の参照。無効なノードや兄弟なしは空リスト。

        Raises:
            RuntimeError: ノードは有効だが保持する DAG パスが無効な場合。
        """
        if not self.isValid():
            return []
        is_shape = self._require_mnode().hasFn(om2.MFn.kShape)
        parent = self.getParent()
        if parent is not None:
            candidates = parent._direct_children(is_shape, False, shapes_only=is_shape)
        elif is_shape:
            candidates = []
        else:
            candidates = DagNode._world_assemblies()
        self_uuid = self.getUuid()
        return [candidate for candidate in candidates if candidate.getUuid() != self_uuid]

    def getBoundingBox(self, worldSpace=_UNSET, *, ws=_UNSET):
        """バウンディングボックスを取得する。

        ``MFnDagNode.boundingBox`` は自身の translate/rotate/scale(Transform の場合)は含むが、
        親から継承した変換は含まない(``cmds.xform(-boundingBox)`` と同じ)。
        ``worldSpace=True`` はそこへ保持パスの ``exclusiveMatrix`` (親までのワールドマトリクス)を
        適用し、ワールド空間のボックスを返す。Shape では自身のローカル形状から計算する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseは親の変換を含まない空間。既定False。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            om2.MBoundingBox: 軸並行境界ボックス。Maya API の内部距離単位。
                子 Shape が無い Transform では原点のみを含む空に近いボックスになる。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: worldSpaceが bool でない場合。
            RuntimeError: ノードが無効、または保持する DAG パスが無効な場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        world = _world_space(worldSpace)
        self._require_valid("compute the bounding box of")
        path = self.mpath()
        box = om2.MFnDagNode(path).boundingBox
        if not world:
            return box
        parent_matrix = path.exclusiveMatrix()
        world_box = om2.MBoundingBox()
        for x in (box.min.x, box.max.x):
            for y in (box.min.y, box.max.y):
                for z in (box.min.z, box.max.z):
                    world_box.expand(om2.MPoint(x, y, z) * parent_matrix)
        return world_box

    def getBoundingBoxCorners(self, worldSpace=_UNSET, *, ws=_UNSET):
        """:meth:`getBoundingBox` の軸並行ボックスの8つの隅の点を取得する。

        ワールド指定でもワールドの軸に沿ったボックス(``getBoundingBox(worldSpace=True)``)の隅を返す。
        向きを持つボックスの隅ではない。

        Args:
            worldSpace (bool): Trueはワールド空間、既定Falseは親の変換を含まない空間(:meth:`getBoundingBox` と同じ)。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[Vector]: cm単位の8点。X・Y・Zの順に最小・最大を組み合わせた順
                ((minX, minY, minZ), (minX, minY, maxZ), (minX, maxY, minZ), ..., (maxX, maxY, maxZ))。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            RuntimeError: ノードが無効、または保持する DAG パスが無効な場合。

        Examples:
            >>> corners = node.getBoundingBoxCorners(ws=True)
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        box = self.getBoundingBox(worldSpace=worldSpace)
        return [Vector(x, y, z) for x in (box.min.x, box.max.x)
                for y in (box.min.y, box.max.y) for z in (box.min.z, box.max.z)]

    def isIntermediateObject(self):
        """中間オブジェクト(履歴用の非表示 Shape)か判定する。Transform では常に False。

        Returns:
            bool: 中間オブジェクトの場合は True。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        return self.mfn().isIntermediateObject

    def getInstances(self, noSelf=False):
        """同じDAGノードの全インスタンスを、複製せず参照する。

        Args:
            noSelf (bool): Trueなら保持するパスを除外する。既定False。

        Returns:
            list[DagNode]: 間接インスタンスも含むAPI列挙順の参照。
                保持パスは自身、それ以外は新しいラッパー。インスタンスは追加しない。

        Raises:
            RuntimeError: 保持するDAGパスが無効な場合。
        """
        original = self.mpath().fullPathName()
        # APIが列挙した有効なパスの複製なので、Node(...) の入力解決を省いて同じ型で包む。
        return [self if path.fullPathName() == original else Node._wrap_dag_path(om2.MDagPath(path))
                for path in om2.MDagPath.getAllPathsTo(self.mnode())
                if not noSelf or path.fullPathName() != original]

    def isInstanced(self):
        """複数のDAGパスを持つ(インスタンス化されている)か判定する。

        親のインスタンス化による間接的なインスタンスも含める(``len(getInstances()) > 1`` と同じ)。

        Returns:
            bool: パスが2つ以上ならTrue。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        return self.mfn().isInstanced(True)

    def getInstanceIndex(self):
        """保持パスのインスタンス番号を取得する(``MDagPath.instanceNumber``)。

        インスタンス化されていないノードは0。:meth:`getInstances` の何番目かとは限らない。

        Returns:
            int: 0以上のインスタンス番号。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        return self.mpath().instanceNumber()

    def getParents(self, indirect=False):
        """直接の親をノード単位またはパス単位で取得する。祖先全体ではない。

        Args:
            indirect (bool): FalseはAPIの親ノード順。保持パスの親にはそのパスを使い、
                他の親はAPIで得た一つのパスを使う。
                TrueはgetInstances順に各パスの親を返し、親のインスタンス化による別パスも含む。

        Returns:
            list[Transform]: 重複統合しない親の参照。DAG の親は Transform 系(Joint 等)。
                保持パスがワールド直下なら空リスト。

        Raises:
            RuntimeError: 保持するDAGパスが無効な場合。
        """
        parent = self.getParent()
        if parent is None:
            return []
        if indirect:
            return [instance.getParent() for instance in self.getInstances() if instance.getParent() is not None]
        fn = self.mfn()
        return [parent if fn.parent(index) == parent.mnode()
                else Node._wrap_dag_path(om2.MDagPath.getAPathTo(fn.parent(index)))
                for index in range(fn.parentCount())
                if not fn.parent(index).hasFn(om2.MFn.kWorld)]

    def getParent(self, step=1):
        """保持パスを指定階層だけ遡る。

        Args:
            step (int): 遡る階層数。0以下、またはワールドまで遡る場合はNone。

        Returns:
            Transform | None: 遡ったパスの新しいラッパー。DAG の親は Transform 系(Joint 等)。
                親がない場合はNone。

        Raises:
            RuntimeError: 正のstepで取得する際、保持するDAGパスが無効な場合。
        """
        if step <= 0:
            return None
        path = om2.MDagPath(self.mpath())
        if step >= path.length():
            return None
        path.pop(step)
        # 有効な保持パスの複製を遡ったパスなので、Node(path) の入力解決を省いて同じ型で包む。
        return Node._wrap_dag_path(path)

    def getChildren(self, shapes=False, intermediates=False, *, allDescendents=False,
                    order="depthFirst", leaves=False, includeSelf=False, underWorld=False, type=None):
        """保持パスに沿って子・子孫を列挙する。同じノードの別パスも残す。

        子パスを継ぎ足して探索し、名前から再解決しない。

        Args:
            type (str | Iterable[str] | None): Mayaのノード型で結果を絞る(``cmds.listRelatives(type=)``
                と同じく派生型を含む。:meth:`~mlib.nodes.node.Node.isType` で判定)。探索自体は絞らないため、
                ``allDescendents=True`` では型の違う子の下も探す。Shapeの型(``"mesh"`` 等)を指定した場合は
                shapes=Falseでも Shape を含めて探す。``multDoubleLinear``/``multDL`` のような版の互換名も使える。
            shapes (bool): Shapeも含める。既定はTransformのみ。
            intermediates (bool): 中間オブジェクトを含める。除外した子の下は探索しない。
            allDescendents (bool): Trueは子孫全体、Falseは直接の子だけ。
            order (str): depthFirstまたはbreadthFirst。兄弟間はDAGの子順。
            leaves (bool): 探索対象の子TransformがないTransformを再帰取得する。Shapeの有無は問わない。
                shapes=Trueとは併用不可。
            includeSelf (bool): 自身もshapes/leaves条件で判定し、該当すれば同じラッパーを返す。
            underWorld (bool): Shape下のアンダーワールドも探索する。

        Returns:
            list[DagNode]: 探索順の参照。対象なし、またはノード自体が無効なら空リスト。

        Raises:
            TypeError: allDescendents・leaves・includeSelf・underWorldがboolでない、またはtypeが
                文字列・文字列の列・None以外の場合。
            ValueError: 探索順が不正、leavesとshapesを併用した、またはtypeが空文字列の場合。
            RuntimeError: ノードは有効だが保持するDAGパスが無効な場合。
        """
        for value, name in ((allDescendents, "allDescendents"), (leaves, "leaves"),
                            (includeSelf, "includeSelf"), (underWorld, "underWorld")):
            _require_bool(value, name)
        if order not in ("depthFirst", "breadthFirst"):
            raise ValueError("order must be 'depthFirst' or 'breadthFirst'")
        if leaves and shapes:
            raise ValueError("leaves selects transforms and cannot be combined with shapes")
        types = _type_filter(type)
        if types and not leaves and not shapes:
            # Shapeの型で絞る場合は、既定のTransformだけの探索では必ず空になるためShapeも探す。
            shapes = any("shape" in _inherited_node_types(_real_node_type(name)) for name in types)
        if not self.isValid():
            return []
        result = self._collect_children(shapes, intermediates, allDescendents, order, leaves, includeSelf, underWorld)
        if types:
            result = [node for node in result if any(node.isType(name) for name in types)]
        return result

    def getShape(self, index=0, intermediates=False):
        """保持パスに対応する Shape を取得する。

        契約: 自身が Shape なら ``index``・``intermediates`` を無視して自身を返す。Transform は
        派生クラス(Transform.getShape)が直下の Shape を ``index`` 番目(0 始まり。範囲外は None)で返す。
        それ以外の DAG ノードは None。無効な index で IndexError にはしない。

        Args:
            index (int): Transform で選ぶ Shape の番号。Shape では無視する。既定 0。
            intermediates (bool): Transform で中間オブジェクトも候補に含める。Shape では無視する。

        Returns:
            DagNode | None: Shape なら自身、Transform は選んだ Shape、該当なしは None。

        Raises:
            RuntimeError: ノードが破棄されている場合。
        """
        return self if self._require_mnode().hasFn(om2.MFn.kShape) else None

    def isVisible(self):
        """親階層を含むDAGの表示状態。

        Returns:
            bool: 親階層を含むDAGの表示状態。

        Raises:
            RuntimeError: 保持するDAGパスが無効な場合(削除済みのノードを含む)。
        """
        return self.mpath().isVisible()

    def show(self, *, fast=False):
        """visibility を有効にして自身を返す。``setVisibility(True, fast=fast)`` と同じ。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DagNode: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
        """
        return self.setVisibility(True, fast=fast)

    def hide(self, *, fast=False):
        """visibility を無効にして自身を返す。``setVisibility(False, fast=fast)`` と同じ。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DagNode: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
        """
        return self.setVisibility(False, fast=fast)

    def getOverrideColor(self, *, shape=False):
        """描画のオーバーライドの表示色を取得する。

        既定ではTransformでも直下のShapeは読まず、自身のアトリビュートを読む。

        Args:
            shape (bool): Trueは直下の最初の中間でないShapeを読む(Shapeが無ければ自身)。既定Falseは自身。

        Returns:
            int | tuple[float, float, float] | None: ``overrideEnabled`` が無効ならNone。
                ``overrideRGBColors`` が有効なら (r, g, b)、それ以外はカラーインデックス(0は既定色)。

        Raises:
            TypeError: shapeがbool以外の場合。
            RuntimeError: ノードが無効な場合。
        """
        _require_bool(shape, "shape")
        fn = self._color_targets(shape)[0]._dependency_fn()
        if not fn.findPlug("overrideEnabled", False).asBool():
            return None
        if fn.findPlug("overrideRGBColors", False).asBool():
            plug = fn.findPlug("overrideColorRGB", False)
            return tuple(plug.child(index).asFloat() for index in range(3))
        return fn.findPlug("overrideColor", False).asInt()

    def setOverrideColor(self, color, *, shape=False, fast=False):
        """描画のオーバーライドで表示色を設定し、自身を返す。

        ``overrideEnabled`` を有効にし、インデックス指定は ``overrideRGBColors`` を無効にして
        ``overrideColor``、RGB指定は ``overrideRGBColors`` を有効にして ``overrideColorRGB`` を設定する。
        ``None`` は ``overrideEnabled`` を無効にする(表示タイプ等のほかのオーバーライドも効かなくなる)。
        TransformやJointでも直下のShapeではなく自身へ設定する(Mayaの描画のオーバーライドと同じく、Transformの
        設定は子の階層全体へ及ぶ)。``shape=True`` は直下の中間でないShape全てへ設定する(Shapeが無ければ自身)。
        通常は ``cmds.setAttr`` で1回のUndoにまとめ、途中で失敗した場合は巻き戻す。``fast=True`` は全対象アトリビュートの書込み可否を先に調べてから
        OpenMayaで書き込み、Undoに記録しない。

        Args:
            color (int | Sequence[float] | None): カラーインデックス(0〜31。0は既定色)、
                0〜1の有限な数値3個の (r, g, b)、または無効にするNone。RGBは表示色の値で、色空間の変換は行わない。
            shape (bool): Trueは直下の中間でないShapeへ設定する(Shapeが無ければ自身)。既定Falseは自身。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DagNode: 自身。

        Raises:
            TypeError: colorがint・3個の数値の列・None以外(boolを含む)、またはshape・fastがbool以外の場合。
            ValueError: インデックスが0〜31の範囲外、またはRGBの成分数が3でない・0〜1の範囲外の場合。
            RuntimeError: ノードが無効、またはロック・入力接続でMayaが設定を拒否した場合。
        """
        _require_bool(shape, "shape")
        _require_bool(fast, "fast")
        index, rgb = _color_value(color)
        if index is None and rgb is None:
            values = [("overrideEnabled", False)]
        elif rgb is None:
            values = [("overrideEnabled", True), ("overrideRGBColors", False), ("overrideColor", index)]
        else:
            values = [("overrideEnabled", True), ("overrideRGBColors", True), ("overrideColorRGB", rgb)]
        self._set_display_values(values, "mlibDagNodeSetOverrideColor", fast, shape)
        return self

    def getOutlinerColor(self, *, shape=False):
        """アウトライナーの文字色を取得する。

        Args:
            shape (bool): Trueは直下の最初の中間でないShapeを読む(Shapeが無ければ自身)。既定Falseは自身。

        Returns:
            tuple[float, float, float] | None: (r, g, b)。``useOutlinerColor`` が無効ならNone。

        Raises:
            TypeError: shapeがbool以外の場合。
            RuntimeError: ノードが無効な場合。
        """
        _require_bool(shape, "shape")
        fn = self._color_targets(shape)[0]._dependency_fn()
        if not fn.findPlug("useOutlinerColor", False).asBool():
            return None
        plug = fn.findPlug("outlinerColor", False)
        return tuple(plug.child(index).asFloat() for index in range(3))

    def setOutlinerColor(self, color, *, shape=False, fast=False):
        """アウトライナーの文字色を設定し、自身を返す。

        ``useOutlinerColor`` を有効にして ``outlinerColor`` を設定する。``None`` は ``useOutlinerColor`` を
        無効にする。既定ではTransformやJointでも直下のShapeではなく自身へ設定する。
        カラーインデックスは指定した時点のRGBへ変換して保持する(``outlinerColor`` はRGBだけを持つため)。
        GUIのないMayaでは現在のパレットを読めないため、Maya標準のパレットを使う。

        Args:
            color (int | Sequence[float] | None): カラーインデックス(0〜31)、0〜1の有限な数値3個の (r, g, b)、
                または無効にするNone。
            shape (bool): Trueは直下の中間でないShapeへ設定する(Shapeが無ければ自身)。既定Falseは自身。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DagNode: 自身。

        Raises:
            TypeError: colorがint・3個の数値の列・None以外(boolを含む)、またはshape・fastがbool以外の場合。
            ValueError: インデックスが0〜31の範囲外、またはRGBの成分数が3でない・0〜1の範囲外の場合。
            RuntimeError: ノードが無効、またはロック・入力接続でMayaが設定を拒否した場合。
        """
        _require_bool(shape, "shape")
        _require_bool(fast, "fast")
        index, rgb = _color_value(color)
        if index is not None:
            rgb = _palette_color(index)
        values = [("useOutlinerColor", False)] if rgb is None else [("useOutlinerColor", True), ("outlinerColor", rgb)]
        self._set_display_values(values, "mlibDagNodeSetOutlinerColor", fast, shape)
        return self

    def getVisibility(self):
        """自身のvisibilityアトリビュート値。親や表示レイヤーを含む最終可視性ではない。

        Returns:
            bool: 自身のvisibilityアトリビュート値。親や表示レイヤーを含む最終可視性ではない。
        """
        return bool(self.getPlug("visibility").get())

    def setVisibility(self, state, *, fast=False):
        """visibility を指定した状態に設定する。親やレイヤーの可視性は変更しない。

        Args:
            state (bool): visibilityへ設定する値。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DagNode: 自身。

        Raises:
            TypeError: state・fastがbool以外の場合。
            RuntimeError: ノードが無効、またはvisibilityがロック・入力接続されていて書き込めない場合。

        Note:
            ``fast=True`` はOpenMaya直接更新(Undoなし)。既定の ``False`` は通常処理。
            完了済みの直接更新は自動で戻さない。
        """
        with _edit_context("mlibDagNodeSetVisibility", fast):
            _require_bool(state, "state")
            self.getPlug("visibility").set(state, fast=fast)
            return self

    def getOutlinerVisibility(self):
        """アウトライナーでの表示を許可する設定値を取得する。

        Returns:
            bool: hiddenInOutlinerがFalseならTrue。実際の画面上の可視性ではない。

        Raises:
            RuntimeError: ノードが無効な場合。

        Note:
            エディターのフィルター・親の折り畳み・非表示ノード表示設定は判定しない。
        """
        return not bool(self.getPlug("hiddenInOutliner").get())

    def setOutlinerVisibility(self, state, *, fast=False):
        """ノードのアウトライナー表示を切り替える。

        Args:
            state (bool): Trueで表示、Falseで非表示(hiddenInOutlinerを反転設定)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DagNode: 自身。DagNodes・Transforms・Jointsからの一括操作にも対応する。

        Raises:
            TypeError: stateまたはfastがbool以外の場合。
            AttributeError: 対応アトリビュートがない場合。
            RuntimeError: ロック・入力接続などで更新できない場合。

        Note:
            ビューポートのvisibilityは変更しない。表示の最終結果は各Outlinerの
            フィルターや非表示ノード表示設定にも依存する。
        """
        with _edit_context("mlibDagNodeSetOutlinerVisibility", fast):
            _require_bool(state, "state")
            self.getPlug("hiddenInOutliner").set(not state, fast=fast)
            return self

    def getDisplayType(self):
        """描画のオーバーライドの表示の種類を取得する。

        自身の ``overrideEnabled``・``overrideDisplayType`` を読む(Transformでも直下のShapeは読まない。
        :meth:`setDisplayType` と同じ対象)。表示レイヤーの設定は含めない。

        Returns:
            str: ``"normal"``・``"template"``・``"reference"``。``overrideEnabled`` が無効なら ``"normal"``。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        self._require_valid("get the display type of")
        fn = self._dependency_fn()
        if not fn.findPlug("overrideEnabled", False).asBool():
            return "normal"
        return _DISPLAY_TYPES[fn.findPlug("overrideDisplayType", False).asInt()]

    def setDisplayType(self, kind, *, fast=False):
        """描画のオーバーライドで表示の種類(通常・テンプレート・リファレンス)を設定し、自身を返す。

        ``"template"``・``"reference"`` は ``overrideEnabled`` を有効にして ``overrideDisplayType`` を設定する。
        ``"normal"`` は ``overrideDisplayType`` を0へ戻すだけで、``overrideEnabled`` は変えない(表示色等の
        ほかのオーバーライドを保つため)。Transformでも直下のShapeではなく自身へ
        設定する(Mayaの描画のオーバーライドと同じく、Transformの設定は子の階層全体へ及ぶ)。
        通常は ``cmds.setAttr`` で1回のUndoにまとめ、途中で失敗した場合は巻き戻す。``fast=True`` は
        全対象アトリビュートの書込み可否を先に調べてからOpenMayaで書き込み、Undoに記録しない。

        Args:
            kind (str): ``"normal"``・``"template"``・``"reference"``。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DagNode: 自身。

        Raises:
            TypeError: kindが文字列以外、またはfastがbool以外の場合。
            ValueError: kindが未対応の名前の場合。
            RuntimeError: ノードが無効、またはロック・入力接続でMayaが設定を拒否した場合。
        """
        _require_bool(fast, "fast")
        if not isinstance(kind, str):
            raise TypeError("kind must be 'normal', 'template' or 'reference'")
        if kind not in _DISPLAY_TYPES:
            raise ValueError(f"kind must be one of {', '.join(map(repr, _DISPLAY_TYPES))}, got {kind!r}")
        index = _DISPLAY_TYPES.index(kind)
        values = [("overrideDisplayType", index)] if index == 0 else [
            ("overrideEnabled", True), ("overrideDisplayType", index)]
        self._set_display_values(values, "mlibDagNodeSetDisplayType", fast)
        return self

    def isShadingOverridden(self):
        """描画のオーバーライドでシェーディングを切り、ワイヤーフレーム表示にしているかを返す。

        Mayaの ``overrideShading`` は「Trueでシェーディングあり(既定)、Falseでワイヤーフレーム」の意味で、
        このメソッドはその逆向き(シェーディングを上書きして消しているか)を返す。自身のアトリビュートを読む
        (:meth:`setShadingOverride` と同じ対象)。

        Returns:
            bool: ``overrideEnabled`` が有効で ``overrideShading`` がFalseならTrue。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        self._require_valid("get the shading override of")
        fn = self._dependency_fn()
        return fn.findPlug("overrideEnabled", False).asBool() and not fn.findPlug("overrideShading", False).asBool()

    def setShadingOverride(self, enabled, *, fast=False):
        """描画のオーバーライドでシェーディングを切ってワイヤーフレーム表示にするかを設定し、自身を返す。

        ``enabled=True`` は ``overrideEnabled`` を有効にして ``overrideShading`` をFalse(ワイヤーフレーム)、
        ``enabled=False`` は ``overrideShading`` をTrue(Mayaの既定のシェーディングあり)へ戻すだけで、
        ``overrideEnabled`` は変えない。boolの向きはMayaの ``overrideShading`` と逆で、
        :meth:`isShadingOverridden` の戻り値と同じ向き。対象・Undo・fastは :meth:`setDisplayType` と同じ。

        Args:
            enabled (bool): Trueでシェーディングを切る(ワイヤーフレーム表示)、Falseで戻す。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DagNode: 自身。

        Raises:
            TypeError: enabledまたはfastがbool以外の場合。
            RuntimeError: ノードが無効、またはロック・入力接続でMayaが設定を拒否した場合。
        """
        _require_bool(fast, "fast")
        _require_bool(enabled, "enabled")
        values = [("overrideEnabled", True), ("overrideShading", False)] if enabled else [
            ("overrideShading", True)]
        self._set_display_values(values, "mlibDagNodeSetShadingOverride", fast)
        return self

    def deleteHistory(self, keepDeformers=True):
        """構築履歴を削除し、自身を返す。

        ``keepDeformers=True`` は ``cmds.bakePartialHistory(prePostDeformers=True)`` で、デフォーマー
        (skinCluster・blendShape・cluster等)を残し、それ以外の履歴(polySmooth等のモデリングの履歴)だけを
        形状へ焼き込んで消す。``False`` は ``cmds.delete(constructionHistory=True)`` で、デフォーマーを含む
        すべての履歴を消す(現在の変形結果の形状が残る)。Mayaのコマンドと同じく、Transformに呼ぶと直下の
        Shapeの履歴が対象になる。Shapeを持たないTransform(グループ等)で ``keepDeformers=True`` の場合は
        消す履歴が無いため何もしない。fast引数は持たない(OpenMayaに同等機能が無い)。Undo有効時は1回で戻せる。

        Args:
            keepDeformers (bool): Trueはデフォーマーを残す。既定True。

        Returns:
            DagNode: 自身。

        Raises:
            TypeError: keepDeformersがbool以外の場合。
            RuntimeError: ノードが無効、またはMayaが削除を拒否した場合。
        """
        _require_bool(keepDeformers, "keepDeformers")
        self._require_valid("delete the history of")
        name = self.getFullName()
        if keepDeformers and not self._require_mnode().hasFn(om2.MFn.kShape):
            # bakePartialHistory は Shape の無い Transform を「Shapeを選択」のエラーにするため、Shapeを渡す。
            targets = [shape.getFullName() for shape in self.getChildren(shapes=True)
                       if shape.mnode().hasFn(om2.MFn.kShape)]
            if not targets:
                return self
        else:
            targets = [name]
        with undoChunk("mlibDagNodeDeleteHistory"):
            if keepDeformers:
                cmds.bakePartialHistory(targets, prePostDeformers=True)
            else:
                cmds.delete(targets, constructionHistory=True)
        return self

    def _collect_children(self, shapes, intermediates, all_descendents, order, leaves, include_self, under_world):
        """検証済みの条件で子・子孫を探索する(:meth:`getChildren` の本体)。

        Args:
            shapes (bool): Shapeも含める。
            intermediates (bool): 中間オブジェクトを含める。
            all_descendents (bool): 子孫全体を探す。
            order (str): depthFirstまたはbreadthFirst。
            leaves (bool): 子Transformを持たないTransformだけを返す。
            include_self (bool): 自身も判定する。
            under_world (bool): アンダーワールドも探す。

        Returns:
            list[DagNode]: 探索順の参照。
        """
        recursive = all_descendents or leaves
        from collections import deque
        pending = deque([(self, 0)])
        result = []
        while pending:
            node, depth = pending.popleft() if order == "breadthFirst" else pending.pop()
            is_shape = node._require_mnode().hasFn(om2.MFn.kShape)
            children = node._traversal_children(shapes, intermediates, under_world) if recursive or depth == 0 else []
            selected = (include_self or depth > 0) and (shapes or not is_shape)
            if selected and (not leaves or not any(
                    child.mnode().hasFn(om2.MFn.kTransform) for child in children)):
                result.append(node)
            if recursive or depth == 0:
                rows = [(child, depth + 1) for child in children]
                pending.extend(rows if order == "breadthFirst" else reversed(rows))
        return result

    def _set_display_values(self, values, chunk, fast, shape=False):
        """表示のアトリビュートへ値を書き込む(:meth:`setOverrideColor`・:meth:`setDisplayType` 等の本体)。

        fastは一部のアトリビュートだけ変わるのを避けるため、全アトリビュート(コンパウンドアトリビュートは
        子も)の書込み可否を先に調べてから書き込む。

        Args:
            values (list[tuple[str, object]]): アトリビュート名と値を書き込む順に並べたもの。
            chunk (str): 通常経路のUndoチャンク名。
            fast (bool): 検証済みのfast。TrueはUndoなしのOpenMaya更新。
            shape (bool): 検証済みのshape。Trueは直下のShapeへ書き込む。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: ノードが無効、またはロック・入力接続で書き込めない場合。
        """
        targets = self._color_targets(shape)
        if fast:
            writes = []
            for target in targets:
                # Plugラッパーを作らず、組み込みアトリビュートのMPlugを直接取る。
                fn = target._dependency_fn()
                writes += [(fn.findPlug(attribute, False), value) for attribute, value in values]
            for plug, _ in writes:
                require_writable(plug)
                for child in range(plug.numChildren() if plug.isCompound else 0):
                    require_writable(plug.child(child))
            for plug, value in writes:
                set_plug(plug, value, _writable_checked=True)
            return
        names = [target.getFullName() for target in targets]
        with undoTransaction(chunk):
            for name in names:
                for attribute, value in values:
                    if isinstance(value, tuple):
                        cmds.setAttr(name + "." + attribute, *value)
                    else:
                        cmds.setAttr(name + "." + attribute, value)

    def _color_targets(self, shape):
        """表示色を読み書きするノードを返す。DagNodeは ``shape`` によらず自身。

        Args:
            shape (bool): 検証済みのshape。

        Returns:
            list[DagNode]: 対象のノード。
        """
        self._require_valid("access the display attributes of")
        return [self]

    def _require_mnode(self):
        """保持する MObject を返す。:meth:`mnode` と同じ値で、None にならないことを確かめる。

        初期化でノードを解決できなければ例外になるため、生成済みのラッパーは常に MObject を保持する。

        Returns:
            om2.MObject: 保持している MObject(複製ではない)。
        """
        mobject = self.mnode()
        assert mobject is not None
        return mobject

    @staticmethod
    def _world_assemblies():
        """ワールド直下の Transform をすべて取得する。

        Returns:
            list[DagNode]: ワールド直下(DAG パスの長さが 1)の Transform ラッパー。
        """
        iterator = om2.MItDag(om2.MItDag.kBreadthFirst, om2.MFn.kTransform)
        assemblies = []
        while not iterator.isDone():
            path = iterator.getPath()
            if path.length() == 1:
                # MItDag が返した有効なパスなので、Node(path) の入力解決を省いて同じ型で包む。
                assemblies.append(Node._wrap_dag_path(path))
            iterator.next()
        return assemblies

    def _direct_children(self, shapes, intermediates, shapes_only=False):
        """直接の子をAPIで列挙し、インスタンスの親パスを維持する。

        Args:
            shapes (bool): Shapeも列挙するか。
            intermediates (bool): 中間オブジェクトも含めるか。
            shapes_only (bool): TrueならShapeだけを列挙する(Transform等はラッパーを作らずに除く)。

        Returns:
            list[DagNode]: 条件に合う直接の子。非Transformでは空リスト。
        """
        path = self.mpath()
        if not path.node().hasFn(om2.MFn.kTransform):
            return []
        # 子の数と子は保持パスから直接読む(MFnDagNode(path) と同じ子の順。関数セットの作成を省く)。
        result = []
        for index in range(path.childCount()):
            obj = path.child(index)
            if not shapes and not obj.hasFn(om2.MFn.kTransform):
                continue
            if shapes_only and not obj.hasFn(om2.MFn.kShape):
                continue
            if not intermediates and om2.MFnDagNode(obj).isIntermediateObject:
                continue
            child = om2.MDagPath(path)
            child.push(obj)
            # 直前に延長した有効なパスなので、Node(child)の入力解決を省いて同じ型で包む。
            result.append(Node._wrap_dag_path(child))
        return result

    def _traversal_children(self, shapes, intermediates, under_world):
        """指定条件で探索を続ける子パスを取得する。

        Args:
            shapes: TrueはShapeも取得対象へ含める。
            intermediates: Trueは中間オブジェクトも含める。
            under_world: TrueはShape下のアンダーワールドも探索する。
        """
        result = []
        is_shape = self._require_mnode().hasFn(om2.MFn.kShape)
        if under_world and (is_shape or not shapes):
            shape = self if is_shape else self.getShape()
            if shape is not None:
                iterator = om2.MItDag()
                iterator.reset(shape.mpath())
                iterator.traverseUnderWorld = True
                iterator.next()
                if not iterator.isDone():
                    root = iterator.getPath()
                    # アンダーワールドの非表示ルート自体は公開せず、その子を探索する。
                    if not om2.MFnDagNode(root).inModel:
                        for index in range(root.childCount()):
                            path = om2.MDagPath(root)
                            path.push(root.child(index))
                            if intermediates or not om2.MFnDagNode(path).isIntermediateObject:
                                result.append(Node._wrap_dag_path(path))
        result.extend(self._direct_children(shapes, intermediates))
        return result


def _palette_color(index):
    """カラーインデックスのRGBを返す。

    Args:
        index (int): 0〜31のカラーインデックス。

    Returns:
        tuple[float, float, float]: RGB。
    """
    # 0は既定色で照会できず、GUIのないMayaはcolorIndexがNoneを返すため標準のパレットを使う。
    if index == 0 or cmds.about(batch=True):
        return _DEFAULT_COLOR_PALETTE[index]
    return tuple(cmds.colorIndex(index, query=True))
