"""変換行列を介して Transform ノードを操作する。"""

from .._core.flags import flag_aliases
from ..decorators._fast import fast_edit
from .._core.fast_write import set_attr

import math

import maya.cmds as cmds
import maya.api.OpenMaya as om2

from ..decorators.undo import undo_chunk
from .._core.registry import node_wrapper
from ..maths import EulerRotation, Matrix, Quaternion, Scale, Shear, Translation, Vector
from ..maths.vector import _vector_of
from .node import Node

#: 拘束元の transform の値(位置・回転など)を使うコンストレイント。拘束元は Transform に限る。
_TRANSFORM_SOURCE_CONSTRAINTS = frozenset((
    "parentConstraint", "pointConstraint", "orientConstraint", "scaleConstraint",
    "aimConstraint", "poleVectorConstraint",
))


_TRANSFORM_ATTRIBUTES = {}


def _transform_attribute(name):
    """transform ノード型の属性の MObject を取得する(初回だけ問い合わせて保持する)。

    joint など transform の派生型も同じ属性の MObject を共有するため、
    ``om2.MPlug(node, attribute)`` で名前の検索なしに MPlug を作れる。

    Args:
        name (str): 属性のロング名(``matrix`` / ``worldMatrix`` など)。

    Returns:
        om2.MObject: transform ノード型の属性。
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
            優先する順に並べる(set_scale で要求した値、現在の scale チャンネル値など)。

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
class Transform(Node):
    """Maya transform ノードを matrix-first API で扱うラッパー。

    評価済み値を取得する ``get_*`` 系メソッドは cymel の ``getMatrix(ws=...)`` に
    倣い、``ws=False`` （既定）でローカル空間、``ws=True`` でワールド空間の値を返す。
    """

    @flag_aliases(typ="type", mo="maintainOffset")
    @undo_chunk("hlibTransformAddConstraint")
    def add_constraint(self, sources, type="parent", maintainOffset=False):
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
            DeletedAttributeError: 拘束元に、属性が削除済みの Plug / MPlug を渡した場合
                (ValueError と RuntimeError の両方の派生)。

        PoleVector は RP IK ハンドル、Geometry/Normal/PointOnPoly は適切な形状、
        Tangent は NURBS カーブが必要。選択状態による対象補完は行わない。
        typeはtyp、maintainOffsetはmoでも指定可能。同時指定はTypeError。
        maintainOffsetはparent/point/orient/scale/aim以外では使用しない。
        """
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
        if not self.is_valid():
            raise RuntimeError("Cannot constrain an invalid transform")
        from .._core.coerce import to_node
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
        for source in sources:
            if source is None or (isinstance(source, str) and not source):
                raise TypeError("Constraint sources must be non-empty names or Node objects")
            # 文字列も含めて所有ノードへ解決する。Plug・MPlug・"node.attribute" は所有ノード、
            # Component・"pCube1.vtx[0]" は所有シェイプを拘束元にする(maya.cmds へ
            # プラグ名・コンポーネント名をそのまま渡すと拘束元として扱われないため)。
            source = to_node(source)
            if not source.is_valid():
                raise RuntimeError("Constraint target is invalid")
            if requires_transform and not source.mobject().hasFn(om2.MFn.kTransform):
                raise TypeError(
                    f"{command_name} の拘束元には Transform(joint・IkHandle を含む)を指定してください"
                    f"(シェイプ・Component・DG ノードは不可): {source.__class__.__name__} {source.name()!r}"
                )
            names.append(source.full_name())
        if not names:
            raise ValueError("At least one constraint source is required")
        command_kwargs = {}
        if command_name in {
            "parentConstraint",
            "pointConstraint",
            "orientConstraint",
            "scaleConstraint",
            "aimConstraint",
        }:
            command_kwargs["maintainOffset"] = maintainOffset
        result = getattr(cmds, command_name)(*names, self.full_name(), **command_kwargs)
        return Node(result[0])

    @undo_chunk("hlibTransformDeleteConstraints")
    def delete_constraints(self):
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
        if not self.is_valid():
            raise RuntimeError("Cannot edit an invalid transform")
        owner = self.full_name()
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

    def dag_path(self):
        """Transform の MDagPath を取得する。

        Returns:
            om2.MDagPath | None: 有効な DAG パス。取得できない場合は ``None``。
                保持していたインスタンスのパスが削除された場合は、残っている最初の
                インスタンスのパスを返す。
        """
        return self._current_dag_path()

    def dag_node(self):
        """Transform 用の MFnDagNode を取得する。

        Returns:
            om2.MFnDagNode: この Transform の function set。
        """
        return om2.MFnDagNode(self.dag_path())

    def transform_fn(self):
        """Transform 用の MFnTransform を取得する。

        Returns:
            om2.MFnTransform: この Transform の function set。
        """
        return om2.MFnTransform(self.dag_path())

    def pivot(self, ws=False):
        """回転ピボットを取得する。

        スケールピボットは set_pivot() で常に同じ位置に揃えて設定するため、
        別途取得するメソッドは提供しない。

        Args:
            ws (bool): True はワールド空間、False はオブジェクト空間(ローカル)。

        Returns:
            Translation: ピボット位置。Maya API の内部距離単位。
        """
        space = om2.MSpace.kWorld if ws else om2.MSpace.kTransform
        return _vector_of(Translation, self.transform_fn().rotatePivot(space))

    @undo_chunk("hlibTransformSetPivot")
    def set_pivot(self, value, ws=False):
        """回転ピボットとスケールピボットを同じ位置にまとめて設定する。

        Args:
            value (Iterable[float]): 新しいピボット位置。Maya API の内部距離単位。
            ws (bool): True はワールド空間、False はオブジェクト空間(ローカル)。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: ノードが無効、または Maya が設定を拒否した場合。
        """
        point = om2.MPoint(*value)
        coordinates = [om2.MDistance(v).asUnits(om2.MDistance.uiUnit()) for v in (point.x, point.y, point.z)]
        cmds.xform(self.full_name(), pivots=coordinates, worldSpace=ws, objectSpace=not ws, preserve=False)
        return self

    @undo_chunk("hlibTransformCenterPivot")
    def center_pivot(self):
        """Maya標準のバウンディングボックス中心へ両ピボットを移動する。

        xformのcenterPivotsと同じ対象範囲を使用する。preserve=Trueで
        オブジェクトの変換結果を維持し、回転・スケールピボットを変更する。
        コンポーネントの選択状態は使用しない。

        Returns:
            Transform: 自身。一回のUndoで戻せる。

        Raises:
            RuntimeError: 無効なノードやロックなどでMayaが変更を拒否した場合。
        """
        cmds.xform(self.full_name(), centerPivots=True, preserve=True)
        return self

    def bounding_box(self, ws=False):
        """直下の Shape 階層を含むバウンディングボックスを取得する。

        MFnDagNode.boundingBox は自身の translate/rotate/scale は含むが、
        親から継承した変換は含まない（``cmds.xform(-boundingBox)`` と同じ）。
        ``ws=True`` はそこへ親のワールド行列をさらに適用し、真のワールド空間の
        バウンディングボックスを返す。

        Args:
            ws (bool): True はワールド空間、False は自身の変換のみを含む空間
                （親の変換は含まない）。

        Returns:
            om2.MBoundingBox: 軸並行境界ボックス。Maya API の内部距離単位。
                子 Shape が無い場合は原点のみを含む空に近いボックスになる。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.is_valid():
            raise RuntimeError("Cannot compute the bounding box of an invalid transform")
        box = self.dag_node().boundingBox
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

    def parent_path(self):
        """親ノードの DAG パスを取得する。

        Returns:
            om2.MDagPath | None: 親のパス。親がない場合は ``None``。
        """
        if not self.is_valid() or self.dag_path().length() <= 1:
            return None
        parent_path = om2.MDagPath(self.dag_path())
        parent_path.pop()
        return parent_path

    def parent_node(self):
        """親ノードを汎用 Node として取得する。

        Returns:
            Node | None: 親ノード。親がない場合は ``None``。
        """
        parent_path = self.parent_path()
        return Node(parent_path) if parent_path is not None else None

    def root(self):
        """DAG 階層の最上位祖先を取得する。

        DAG 上の親は常に Transform であるため、祖先も常に Transform になる。

        Returns:
            Transform: ワールド直下の祖先ノード。自身がワールド直下ならその自身を返す。
        """
        node = self
        parent = node.parent_node()
        while parent is not None:
            node = parent
            parent = node.parent_node()
        return node

    def child_nodes(self):
        """直接の子ノードを汎用 Node のリストとして取得する。

        Returns:
            list[Node]: 直接の子ノード。
        """
        if not self.is_valid():
            return []
        dag_path = self.dag_path()
        dag_fn = self.dag_node()
        children = []
        for index in range(dag_fn.childCount()):
            child_path = om2.MDagPath(dag_path)
            child_path.push(dag_fn.child(index))
            children.append(Node(child_path))
        return children

    def child_transforms(self):
        """直接の子 Transform のみを取得する（Shape 子は含まない）。

        Returns:
            list[Transform]: 直接の子 Transform。
        """
        return [child for child in self.child_nodes() if isinstance(child, Transform)]

    def leaves(self):
        """Transform 階層下の葉ノード（子 Transform を持たないもの）をすべて取得する。

        Shape の有無は判定に関与しない。

        Returns:
            list[Transform]: 葉ノードのリスト。子 Transform が無い場合は自身のみを含む。
        """
        children = self.child_transforms()
        if not children:
            return [self]
        result = []
        for child in children:
            result.extend(child.leaves())
        return result

    def siblings(self):
        """親を同じくする兄弟 Transform を取得する（自身は含まない）。

        自身がワールド直下の場合は、他のワールド直下 Transform を対象にする。

        Returns:
            list[Transform]: 兄弟 Transform のリスト。
        """
        if not self.is_valid():
            return []
        parent = self.parent_node()
        if parent is not None:
            candidates = parent.child_transforms()
        else:
            candidates = self._world_assemblies()
        self_uuid = self.uuid()
        return [
            candidate for candidate in candidates
            if isinstance(candidate, Transform) and candidate.uuid() != self_uuid
        ]

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

    def shapes(self, intermediates=False):
        """このTransform直下のShapeを取得する。

        Args:
            intermediates (bool): ``True`` の場合は中間Shapeも含める。

        Returns:
            list[Shape]: 条件に一致するShapeのリスト。
        """
        from .shape import Shape

        if not self.is_valid():
            return []
        shapes = []
        dag_path = self.dag_path()
        dag_fn = self.dag_node()
        for index in range(dag_fn.childCount()):
            child = dag_fn.child(index)
            if not child.hasFn(om2.MFn.kShape):
                continue
            child_fn = om2.MFnDagNode(child)
            if not intermediates and child_fn.isIntermediateObject:
                continue
            child_path = om2.MDagPath(dag_path)
            child_path.push(child)
            shapes.append(Shape(child_path))
        return shapes

    @fast_edit
    def mirror(self, axis="x", ws=False, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False):
        """直下のすべてのShapeのジオメトリをミラーする。

        直下の各Shape（Mesh、NurbsCurveなど mirror を実装するもの）へ同じ引数で
        処理を委譲する。indices は Shape ごとの要素番号（Mesh は頂点、NurbsCurve は
        CV）として解釈される。Transform自身の行列やShapeの構造は変更しない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            axis (str): 反転する座標軸。x、y、z、xy、xz、yz、xyz。大文字も可。
                x は pivot.x を通る YZ 平面で反転する。複数軸は同時に反転する。
            ws (bool): True はワールド軸、False はオブジェクト空間の軸。既定は False。
            pivot (Iterable[float]): 指定空間での反転中心。既定はその空間の原点。
                単位は Maya の現在の距離単位。Transform のピボットとは独立する。
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
        for shape in self.shapes():
            shape.mirror(axis=axis, ws=ws, pivot=pivot, indices=indices)
        return self

    def shape(self, index=0, intermediates=False):
        """指定位置のShapeを取得する。

        Args:
            index (int): Shapeのインデックス。
            intermediates (bool): ``True`` の場合は中間Shapeも含める。

        Returns:
            Shape: 指定位置のShape。

        Raises:
            IndexError: 指定したインデックスにShapeがない場合。
        """
        shapes = self.shapes(intermediates=intermediates)
        try:
            return shapes[index]
        except IndexError as original_error:
            raise IndexError(f"Shape index out of range: {index}") from original_error

    def transform(self):
        """Transform自身を返す。

        Returns:
            Transform: 自身。
        """
        return self

    @undo_chunk("hlibTransformSetParent")
    def set_parent(self, parent=None, relative=False, add=False):
        """Transformの親を変更する。

        Args:
            parent (Node | str | om2.MObject | om2.MDagPath | None): 新しい親。None はワールド直下。
                ``Node(parent)`` で解決できる型(Plug・Component は所有ノード)を受け付ける。
            relative (bool): True は親変更前のローカル変換を保持する。False は Maya の既定動作。
            add (bool): True は既存の親を維持して追加の親を設定する。parent が None の場合は渡されない。

        Returns:
            Transform: 自身。
        """
        if not self.is_valid():
            raise RuntimeError("Cannot parent an invalid transform")
        if parent is None:
            if self.parent_path() is None and not self.dag_path().isInstanced():
                return self
            cmds.parent(self.name(), world=True, relative=relative)
        else:
            target = parent if isinstance(parent, Node) else Node(parent)
            parent_name = target.full_name()
            # 古いMayaでは同じ親への再parentがエラーになる。
            # add=Trueはインスタンス操作なのでMayaの判定に委ねる。
            current = self.parent_path()
            if (not add and not self.dag_path().isInstanced() and current is not None
                    and current.fullPathName() == parent_name):
                return self
            cmds.parent(self.name(), parent_name, relative=relative, add=add)
        return self

    @undo_chunk("hlibTransformMatch")
    def match_transform(self, target, position=True, rotation=True, scale=True, pivots=False):
        """自身の変換を指定Transformへ合わせる。選択状態は使用しない。

        Args:
            target (Transform | str | om2.MObject | om2.MDagPath): 合わせ先のTransformまたはjoint。
                hlib._core.coerce.to_node が受け付ける型(Plug は所有ノード)を指定できる。
            position (bool): 位置を合わせる。
            rotation (bool): 回転を合わせる。
            scale (bool): スケールを合わせる。
            pivots (bool): 回転・スケールピボットも合わせる。

        Returns:
            Transform: 自身。全フラグFalseなら何も変更しない。

        Raises:
            TypeError: targetがTransformではない場合。
            RuntimeError: ノードが無効、またはMayaが変更を拒否した場合。
            DeletedAttributeError: targetに、属性が削除済みの Plug / MPlug を渡した場合
                (ValueError と RuntimeError の両方の派生)。

        maya.cmds.matchTransformと同じ空間・joint・ピボット処理を使用する。
        shearの一致や行列全体のコピーは保証しない。
        """
        from .._core.coerce import to_node

        target = to_node(target)
        if not isinstance(target, Transform):
            raise TypeError("Target must be a transform or joint")
        if any((position, rotation, scale, pivots)):
            cmds.matchTransform(self.full_name(), target.full_name(), position=position,
                                rotation=rotation, scale=scale, pivots=pivots)
        return self

    def get_matrix(self, ws=False):
        """変換行列を取得する。

        Maya が評価・キャッシュ済みの ``matrix`` / ``worldMatrix`` 属性値をそのまま
        使うため、``jnt.plug("matrix")`` / ``jnt.plug("worldMatrix")`` の対応する要素と
        常に一致する。hlib の Plug ラッパーを介さず OpenMaya の MPlug から直接読み取る。

        Args:
            ws (bool): ``True`` でワールド空間（``worldMatrix``）、``False`` （既定）で
                ローカル空間（``matrix``）の値を取得する。ワールド空間では、
                :meth:`dag_path` が示す DAG インスタンスの要素
                (``worldMatrix[<インスタンス番号>]``)を使う。

        Returns:
            Matrix: 指定空間の評価済み行列の複製(om2.MMatrix の派生)。

        Raises:
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        if not self.is_valid():
            raise RuntimeError("無効なノードの行列は取得できません")
        # 名前による findPlug より速い、属性の MObject からの MPlug 生成を使う。
        plug = om2.MPlug(self.mobject(), _transform_attribute("worldMatrix" if ws else "matrix"))
        if ws:
            plug = plug.elementByLogicalIndex(self.dag_path().instanceNumber())
        return Matrix._wrap(om2.MFnMatrixData(plug.asMObject()).matrix())

    def get_translate(self, ws=False):
        """Translation を取得する。

        Args:
            ws (bool): ``True`` でワールド空間、``False`` （既定）でローカル空間の値を取得する。

        Returns:
            Translation: 評価済みの位置。
        """
        return self.get_matrix(ws=ws).translate

    def get_rotate(self, ws=False):
        """Euler 回転値を、ノードの rotateOrder で取得する。

        ``cmds.xform(query=True, rotation=True)`` と同じく、値はノードの rotateOrder で
        表す(戻り値の order もノードの回転順序)。行列を分解した回転の等価な解のうち、
        transform では現在の rotate チャンネル値に最も近いものを返すため、ローカル空間の
        transform(rotateAxis が 0)ではチャンネル値と一致する(浮動小数点の誤差を除く)。
        joint の値は jointOrient と rotateAxis を含む行列全体の回転で、解は 0 回転に
        最も近いものを選ぶ。スケールの符号の扱いは :meth:`get_scale` と同じ。

        Args:
            ws (bool): ``True`` でワールド空間、``False`` （既定）でローカル空間の値を取得する。

        Returns:
            EulerRotation: 評価済みの回転値（radian、ノードの回転順序）。

        Raises:
            ValueError: 行列を分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        _, quaternion, _, _, reference = self._decompose_like_channels(self.get_matrix(ws=ws))
        return EulerRotation._wrap(_closest_euler(quaternion, self._rotate_reference(reference)))

    def get_scale(self, ws=False):
        """Scale を取得する。

        行列を om2.MTransformationMatrix と同じ規約で分解してから、スケールの符号の
        組み合わせを現在の scale チャンネル値へ揃える(2軸の符号の反転を、残りの軸まわりの
        180 度回転で補償する)。例えば scale が (-1, 1, 1) のノードは (-1, 1, 1) を返す。
        行列式の符号と合わない組み合わせ(ワールド空間で親が奇数個の負スケールを持つ
        場合など)は om2 の規約(行列式が負なら Z が負)のまま返す。
        :class:`~hlib.maths.matrix.Matrix` の ``scale`` は常に om2 の規約。

        Args:
            ws (bool): ``True`` でワールド空間、``False`` （既定）でローカル空間の値を取得する。

        Returns:
            Scale: 評価済みのスケール値。

        Raises:
            ValueError: 行列を分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        _, _, scale, _, _ = self._decompose_like_channels(self.get_matrix(ws=ws))
        return Scale(*scale)

    def get_shear(self, ws=False):
        """Shear を取得する。

        スケールの符号の扱いは :meth:`get_scale` と同じ(符号を揃えた軸に合わせて
        シアーの符号も変わる)。

        Args:
            ws (bool): ``True`` でワールド空間、``False`` （既定）でローカル空間の値を取得する。

        Returns:
            Shear: 評価済みの shear 値。

        Raises:
            ValueError: 行列を分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        _, _, _, shear, _ = self._decompose_like_channels(self.get_matrix(ws=ws))
        return Shear(*shear)

    def get_quaternion(self, ws=False):
        """Quaternion を取得する。

        スケールの符号の扱いは :meth:`get_scale` と同じ。

        Args:
            ws (bool): ``True`` でワールド空間、``False`` （既定）でローカル空間の値を取得する。

        Returns:
            Quaternion: 評価済みの回転値。

        Raises:
            ValueError: 行列を分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        _, quaternion, _, _, _ = self._decompose_like_channels(self.get_matrix(ws=ws))
        return Quaternion._wrap(quaternion)

    def get_euler(self, ws=False):
        """回転を XYZ 順序の EulerRotation として取得する。

        :meth:`get_quaternion` と同じ回転を ``om2.MQuaternion.asEulerRotation()`` の解
        (XYZ 順序)で返す。ノードの rotateOrder で表した値は :meth:`get_rotate` を使う。

        Args:
            ws (bool): ``True`` でワールド空間、``False`` （既定）でローカル空間の値を取得する。

        Returns:
            EulerRotation: 評価済みの回転値（radian、XYZ 順序）。

        Raises:
            ValueError: 行列を分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        _, quaternion, _, _, _ = self._decompose_like_channels(self.get_matrix(ws=ws))
        return EulerRotation._wrap(quaternion.asEulerRotation())

    def decompose(self, ws=True):
        """指定空間の変換行列を取得する互換メソッド。

        Args:
            ws (bool): ``True`` （既定）でワールド空間、``False`` でローカル空間の値を取得する。

        Returns:
            Matrix: get_matrix(ws=ws) の結果。成分辞書は返さない。
        """
        return self.get_matrix(ws=ws)

    def _parent_world_matrix(self):
        """親Transformのワールド行列を取得する。

        Returns:
            Matrix: 親のワールド行列。親がない、または親に get_matrix がなければ単位行列。
        """
        parent = self.parent_node()
        if parent is None or not hasattr(parent, "get_matrix"):
            return Matrix()
        return parent.get_matrix(ws=True)

    def _rotate_order(self):
        """ノードの rotateOrder を om2 の回転順序の番号として取得する。

        Returns:
            int: 0(xyz)〜5(zyx)。om2.MEulerRotation.kXYZ〜kZYX と同じ番号。
        """
        return om2.MFnTransform(self.mobject()).rotation(om2.MSpace.kTransform).order

    def _channel_state(self):
        """現在の scale チャンネル値と rotate チャンネル値を内部単位で取得する。

        分解の解を現在のチャンネル値に近づけるための基準に使う。

        Returns:
            tuple: (scale の3成分の tuple, rotate の om2.MEulerRotation)。rotate は
            ラジアンで、順序はノードの rotateOrder。ノードが無効なら
            ((1.0, 1.0, 1.0), XYZ 順序の 0 回転)。
        """
        if not self.is_valid():
            return (1.0, 1.0, 1.0), om2.MEulerRotation()
        # MFnTransform の scale() / rotation() は scale・rotate 属性そのもの(joint でも
        # jointOrient を含まない)を返す。名前による findPlug より大幅に速い。
        fn = om2.MFnTransform(self.mobject())
        return tuple(fn.scale()), fn.rotation(om2.MSpace.kTransform)

    def _decompose_like_channels(self, matrix, scale_reference=None):
        """行列を分解し、スケールの符号の組み合わせを基準のスケールへ揃える。

        om2.MTransformationMatrix の規約(行列式が負なら Z が負)で分解してから、
        :func:`_match_scale_signs` で符号を揃える。基準は scale_reference (指定時)、
        次に現在の scale チャンネル値の順に、行列式の符号と合う最初のもの。これにより
        scale が (-1, 1, 1) のようなミラーのノードでも、取得・設定の往復でチャンネル値の
        符号と回転が保たれ、``set_scale`` では要求した符号がそのまま入る。

        Args:
            matrix (Matrix): 分解する行列。
            scale_reference (Iterable[float] | None): 最優先で符号を合わせるスケール
                (``set_scale`` で要求した値)。None なら現在の scale チャンネル値だけ。

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
        """:meth:`get_rotate` が Euler の解を選ぶ基準を返す。

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

        transform では行列の回転をそのまま rotate とみなす(rotateAxis は未対応)。

        Args:
            quaternion (om2.MQuaternion): ローカル行列の回転。
            reference (om2.MEulerRotation): 現在の rotate チャンネル値。

        Returns:
            om2.MEulerRotation: ノードの rotateOrder で表した、reference に最も近い解。
        """
        return _closest_euler(quaternion, reference)

    def _apply_local_matrix(self, matrix, scale_reference=None):
        """ローカル行列の各成分をMaya属性へ適用する。

        行列を1回だけ分解し、平行移動・回転・スケール・シアーを順に書き込む。
        分解は om2.MTransformationMatrix の規約に、次の2点の選択を加えたもの。

        * スケールの符号の組み合わせは、行列式の符号が許す限り scale_reference
          (``set_scale`` で要求した値)、次に現在の scale チャンネルに揃える
          (:meth:`_decompose_like_channels`)。
        * 回転はノードの rotateOrder で表し、等価な解のうち現在の rotate チャンネル値に
          最も近いものを選ぶ(``om2.MEulerRotation.closestSolution``)。

        このため ``set_matrix(get_matrix())`` や ``set_translate`` はチャンネル値を
        (浮動小数点の誤差を除いて)変えない。回転は現在のMaya角度単位へ変換して書き込む。
        ピボットや rotateAxis の補正は行わない
        (非ゼロの場合は未対応)。

        Args:
            matrix (Matrix): ローカル空間の変換行列。
            scale_reference (Iterable[float] | None): 最優先で符号を合わせるスケール。
                None なら現在の scale チャンネル値に合わせる。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 行列を分解できない場合。
            RuntimeError: Maya が属性の書き込みを拒否した場合。
        """
        translate, quaternion, scale, shear, reference = self._decompose_like_channels(matrix, scale_reference)
        rotation = self._channel_rotation(quaternion, reference)
        name = self.full_name()
        set_attr(f"{name}.translate", *translate)
        set_attr(f"{name}.rotate", *(om2.MAngle(component).asUnits(om2.MAngle.uiUnit()) for component in rotation))
        set_attr(f"{name}.scale", *scale)
        set_attr(f"{name}.shear", *shear)

    @fast_edit
    @undo_chunk("hlibTransformSetMatrix")
    def set_matrix(self, matrix, ws=False, *, fast=False):
        """行列をローカルまたはワールド空間で設定する。

        行列を分解して translate・rotate・scale・shear に書き込む。スケールの符号と
        Euler の解は、同じ行列になる候補のうち現在のチャンネル値に近いものを選ぶ
        (詳細は ``_apply_local_matrix``)。そのため ``cmds.xform(matrix=...)``
        (常に om2 の規約で書く)とは、負スケールのノードや Euler の別解でチャンネル値が
        異なることがあるが、結果の行列は同じ。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            matrix (Matrix | sequence): 適用する変換行列。
            ws (bool): ``True`` でワールド空間、``False`` でローカル空間に設定する。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: 無効なノード、または Maya が属性設定を拒否した場合。
            ValueError: 入力行列が不正、分解不能、またはワールド指定時の親行列が逆行列を持たない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        return self._set_matrix(matrix, ws)

    def _set_matrix(self, matrix, ws=False, scale_reference=None):
        """:meth:`set_matrix` の本体。Undo チャンクと fast の扱いは呼び出し元に任せる。

        Args:
            matrix (Matrix | sequence): 適用する変換行列。
            ws (bool): ``True`` でワールド空間、``False`` でローカル空間に設定する。
            scale_reference (Iterable[float] | None): 分解したスケールの符号を最優先で
                合わせる値(:meth:`set_scale` で要求した値)。None なら現在の scale
                チャンネル値に合わせる。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: 無効なノード、または Maya が属性設定を拒否した場合。
            ValueError: 入力行列が不正、分解不能、またはワールド指定時の親行列が逆行列を持たない場合。
        """
        if not isinstance(matrix, Matrix):
            matrix = Matrix(matrix)
        if not self.is_valid():
            raise RuntimeError("Cannot set an invalid transform")
        local_matrix = matrix if not ws else matrix * self._parent_world_matrix().inverse()
        self._apply_local_matrix(local_matrix, scale_reference)
        return self

    @fast_edit
    @undo_chunk("hlibTransformSetTranslate")
    def set_translate(self, value, ws=False, *, fast=False):
        """平行移動をローカルまたはワールド空間で設定する。

        rotate・scale・shear のチャンネル値は(浮動小数点の誤差を除いて)変えない
        (transform の rotateAxis は 0 を前提とする。joint は jointOrient / rotateAxis を保つ)。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Translation | sequence): 新しい平行移動値。
            ws (bool): ``True`` でワールド空間に設定する。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: 現在の行列を分解できない、または必要な親行列を反転できない場合。
            RuntimeError: ノードが無効、または属性を書き込めない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        matrix = self.get_matrix(ws=ws)
        matrix.translate = value
        return self.set_matrix(matrix, ws=ws)

    @fast_edit
    @undo_chunk("hlibTransformSetRotate")
    def set_rotate(self, value, unit="rad", ws=False, *, fast=False):
        """Euler回転を設定する。

        3成分の値は ``cmds.xform(rotation=...)`` と同じくノードの rotateOrder の値として
        解釈する(:meth:`get_rotate` や ``plug("rotate").get()`` の値をそのまま渡せる)。
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
            ws (bool): True はワールド、False はローカル空間。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: unit が rad/deg 以外、deg を EulerRotation / Quaternion と指定、
                値が3成分でない、行列が分解不能、または必要な親行列が反転不能の場合。
            RuntimeError: ノードが無効、または属性を書き込めない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if unit not in ("rad", "deg"):
            raise ValueError("unit must be 'rad' or 'deg'")
        if isinstance(value, (om2.MEulerRotation, om2.MQuaternion)):
            if unit == "deg":
                raise ValueError("unit='deg' is only supported for three plain components")
        else:
            if not self.is_valid():
                raise RuntimeError("Cannot set an invalid transform")
            x, y, z = value
            if unit == "deg":
                x, y, z = math.radians(x), math.radians(y), math.radians(z)
            # cmds.xform と同じく、3成分はノードの rotateOrder の値として解釈する。
            value = EulerRotation(x, y, z, self._rotate_order())
        matrix = self._replace_components(self.get_matrix(ws=ws), rotate=value)
        return self.set_matrix(matrix, ws=ws)

    @fast_edit
    @undo_chunk("hlibTransformSetScale")
    def set_scale(self, value, ws=False, *, fast=False):
        """スケールをローカルまたはワールド空間で設定する。

        回転・シアー・平行移動は保つ(回転とシアーは :meth:`get_scale` と同じ規約で
        分解した値)。書き込むスケールの符号は、行列式の符号が許す限り value の符号の
        とおりにする(ローカル空間の transform では常にそのまま入る)。例えば rotate が
        (10, 20, 30)、scale が (1, 1, 1) の transform へ (-1, 1, 1) を設定すると scale は
        (-1, 1, 1)、rotate は (10, 20, 30) のまま(``cmds.setAttr`` で scale だけを書いた
        場合と同じ)。ワールド空間で親の行列式が負の場合など、value の符号の組み合わせを
        取れないときは現在の scale チャンネル値、それも合わなければ om2 の規約(Z が負)に
        揃える。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Scale | sequence): 新しいスケール値。
            ws (bool): ``True`` でワールド空間に設定する。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: 現在の行列を分解できない、または必要な親行列を反転できない場合。
            RuntimeError: ノードが無効、または属性を書き込めない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        value = tuple(value)
        matrix = self._replace_components(self.get_matrix(ws=ws), scale=value)
        return self._set_matrix(matrix, ws, scale_reference=value)

    @fast_edit
    @undo_chunk("hlibTransformSetShear")
    def set_shear(self, value, ws=False, *, fast=False):
        """Shearをローカルまたはワールド空間で設定する。

        値は :meth:`get_shear` と同じ規約で解釈し、回転・スケール・平行移動は保つ。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Shear | sequence): 新しいShear値。
            ws (bool): ``True`` でワールド空間に設定する。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: 現在の行列を分解できない、または必要な親行列を反転できない場合。
            RuntimeError: ノードが無効、または属性を書き込めない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        matrix = self._replace_components(self.get_matrix(ws=ws), shear=value)
        return self.set_matrix(matrix, ws=ws)


    @fast_edit
    @undo_chunk("hlibTransformShow")
    def show(self, *, fast=False):
        """visibility を True に設定する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Transform: 自身。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        self.plug("visibility").set(True)
        return self

    @fast_edit
    @undo_chunk("hlibTransformHide")
    def hide(self, *, fast=False):
        """visibility を False に設定する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Transform: 自身。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        self.plug("visibility").set(False)
        return self

    @undo_chunk("hlibTransformMakeIdentity")
    def make_identity(self, **kwargs):
        """cmds.makeIdentity のシンプルなラッパー。

        Args:
            kwargs: cmds.makeIdentity にそのまま渡す追加のフラグ
                (apply、translate、rotate、scale、normal など)。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: ノードが無効、または Maya が拒否した場合。
        """
        if not self.is_valid():
            raise RuntimeError("Cannot freeze transform of an invalid transform")
        cmds.makeIdentity(self.full_name(), **kwargs)
        return self

    @undo_chunk("hlibTransformReleaseSRT")
    def unlock_and_disconnect_transform_channels(self):
        """translate/rotate/scale/shear とその子チャンネルを一括でアンロック・切断する。

        各チャンネルとその X/Y/Z 子の両方についてロック解除と接続解除を行う。
        既にアンロック・未接続のチャンネルは変化しない。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.is_valid():
            raise RuntimeError("Cannot release SRT channels of an invalid transform")
        for channel in ("translate", "rotate", "scale", "shear"):
            plug = self.plug(channel)
            plug.set_locked(False)
            plug.disconnect()
            for child in plug.children():
                child.set_locked(False)
                child.disconnect()
        return self

    def closest_axis_to_vector(self, ref_vector, include_negative=True):
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
        if not self.is_valid():
            raise RuntimeError("Cannot evaluate axes of an invalid transform")
        if not isinstance(ref_vector, Vector):
            ref_vector = Vector(*ref_vector)
        ref_vector = ref_vector.normalized()
        matrix = self.get_matrix(ws=True)
        axes = {"x": Vector(1.0, 0.0, 0.0), "y": Vector(0.0, 1.0, 0.0), "z": Vector(0.0, 0.0, 1.0)}
        if include_negative:
            axes.update({f"-{name}": axis * -1.0 for name, axis in axes.items()})
        best_axis = None
        best_dot = None
        for name, axis in axes.items():
            world_axis = matrix.transform_vector(axis).normalized()
            dot = world_axis.dot(ref_vector)
            if best_dot is None or dot > best_dot:
                best_dot = dot
                best_axis = name
        return best_axis

    @undo_chunk("hlibTransformCreateOffsetGroups")
    def create_offset_groups(self, *names):
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
        if not self.is_valid():
            raise RuntimeError("Cannot create offset groups for an invalid transform")
        if not names:
            names = (f"{self.name()}_offset",)
        matrix = self.get_matrix(ws=True)
        parent = self.parent_node()
        groups = []
        for name in names:
            kwargs = {}
            if parent is not None:
                kwargs["parent"] = parent.full_name()
            group = Transform(cmds.group(empty=True, name=name, **kwargs))
            group.set_matrix(matrix, ws=True)
            groups.append(group)
            parent = group
        self.set_parent(groups[-1])
        return groups
