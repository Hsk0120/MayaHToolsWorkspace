"""変換行列を介して Transform ノードを操作する。"""
from maya.api.OpenMaya import MSpace
from .._core.space import world_space

from .._core.flags import flag_aliases
from ..decorators._fast import fast_edit, is_fast
from .._core.fastWrite import set_attr, set_plug

import math

import maya.cmds as cmds
import maya.api.OpenMaya as om2

from ..decorators.undo import undo_chunk
from .._core.registry import node_wrapper
from ..maths import EulerRotation, Matrix, Quaternion, Scale, Shear, Translation, Vector
from ..maths.vector import _vector_of
from .node import Node
from .dagNode import DagNode, DagNodes
from .._core.collection import bulk_api
from .._core.registry import collection_export

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
            優先する順に並べる(setScale で要求した値、現在の scale チャンネル値など)。

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

    評価済み値を取得する ``get_*`` 系メソッドは cymel の ``getMatrix(ws=...)`` に
    倣い、``ws=False`` （既定）でローカル空間、``ws=True`` でワールド空間の値を返す。
    """

    @flag_aliases(typ="type", mo="maintainOffset")
    @undo_chunk("hlibTransformAddConstraint")
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
        from hlib.nodes.node import Node as _InputNode
        from hlib.nodes.node import Nodes as _InputNodes
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
            if requires_transform and not source.mobject().hasFn(om2.MFn.kTransform):
                raise TypeError(
                    f"{command_name} の拘束元には Transform(joint・IkHandle を含む)を指定してください"
                    f"(シェイプ・Component・DG ノードは不可): {source.__class__.__name__} {source.name()!r}"
                )
            names.append(source.fullName())
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
        result = getattr(cmds, command_name)(*names, self.fullName(), **command_kwargs)
        return Node(result[0])

    @undo_chunk("hlibTransformDeleteConstraints")
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
        owner = self.fullName()
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
        return om2.MFnTransform(self.dagPath())

    @fast_edit
    @undo_chunk("hlibTransformReset")
    def reset(self, attributes=None, *, fast=False):
        """指定アトリビュートを定義上の既定値へ戻す。

        Args:
            attributes (str | Iterable[str] | None): tx/translateX/translateなど。
                省略時はtranslate・rotate・scale・shear。独自数値アトリビュートも可。
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
        plugs = [self.plug(name) for name in attributes]
        for plug in plugs:
            plug.reset()
        return self

    @undo_chunk("hlibTransformResetPivot")
    def resetPivot(self, space=MSpace.kWorld, *, kind="both"):
        """現在の姿勢を保ち、ピボットだけを指定空間の原点へ移動する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            kind (str): bothは両方、rotateは回転、scaleはスケールピボット。

        Returns:
            Transform: 自身。一回のUndoで元へ戻せる。

        Raises:
            TypeError: spaceが対応するMSpace定数でない、または対象がJointの場合。
            ValueError: kindが不正な場合。
            RuntimeError: Mayaが更新を拒否した場合。

        ピボット補償値を調整して行列を維持する。translateのリセットではない。
        """
        ws = world_space(space)
        if not isinstance(ws, bool):
            raise TypeError("ws must be a bool")
        return self.setPivot((0, 0, 0), space=MSpace.kWorld if ws else MSpace.kObject, kind=kind, preserve=True)

    @fast_edit
    @undo_chunk("hlibTransformScaleGeometry")
    def scaleGeometry(self, scale, space=MSpace.kObject, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False):
        """直下の全Shapeの頂点・CVを拡縮する。Transformの行列は変更しない。

        Args:
            scale (float | Iterable[float]): 一様倍率、またはXYZの倍率。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
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
        ws = world_space(space)
        indices = None if indices is None else tuple(indices)
        for shape in self.shapes():
            shape.scaleGeometry(scale, space=MSpace.kWorld if ws else MSpace.kObject, pivot=pivot, indices=indices)
        return self

    def getPivot(self, space=MSpace.kObject, *, kind="rotate"):
        """指定した種類のピボットを取得する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            kind (str): rotateは回転、scaleはスケールピボット。

        Returns:
            Translation: ピボット位置。Maya API の内部距離単位。

        Raises:
            ValueError: kindがrotate/scaleでない場合。
        """
        ws = world_space(space)
        if kind not in ("rotate", "scale"):
            raise ValueError("kind must be 'rotate' or 'scale'")
        # 設定と同じxform空間を使う。MFnTransformのkTransformとxformの
        # objectSpaceでは、スケールを持つノードのピボットの解釈が一致しない。
        flag = "rotatePivot" if kind == "rotate" else "scalePivot"
        values = cmds.xform(self.fullName(), query=True, worldSpace=ws,
                            objectSpace=not ws, **{flag: True})
        return Translation(*(om2.MDistance(v, om2.MDistance.uiUnit()).asCentimeters() for v in values))

    @undo_chunk("hlibTransformSetPivot")
    def setPivot(self, value, space=MSpace.kObject, *, kind="rotate", preserve=True):
        """指定した種類のピボットを変更する。既定ではノードの姿勢を保つ。

        Args:
            value (Iterable[float]): 新しいピボット位置。Maya API の内部距離単位。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
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
        ws = world_space(space)
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
        cmds.xform(self.fullName(), worldSpace=ws, objectSpace=not ws,
                   preserve=preserve, **{flag: coordinates})
        return self

    @undo_chunk("hlibTransformCenterPivot")
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
        cmds.xform(self.fullName(), centerPivots=True, preserve=True)
        return self

    def boundingBox(self, space=MSpace.kObject):
        """直下の Shape 階層を含むバウンディングボックスを取得する。

        MFnDagNode.boundingBox は自身の translate/rotate/scale は含むが、
        親から継承した変換は含まない（``cmds.xform(-boundingBox)`` と同じ）。
        ``space=MSpace.kWorld`` はそこへ親のワールド行列をさらに適用し、真のワールド空間の
        バウンディングボックスを返す。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
                （親の変換は含まない）。

        Returns:
            om2.MBoundingBox: 軸並行境界ボックス。Maya API の内部距離単位。
                子 Shape が無い場合は原点のみを含む空に近いボックスになる。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        ws = world_space(space)
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

    def root(self):
        """DAG 階層の最上位祖先を取得する。

        DAG 上の親は常に Transform であるため、祖先も常に Transform になる。

        Returns:
            Transform: ワールド直下の祖先ノード。自身がワールド直下ならその自身を返す。
        """
        node = self
        parent = node.parentNode()
        while parent is not None:
            node = parent
            parent = node.parentNode()
        return node

    def childNodes(self):
        """直接の子ノードを汎用 Node のリストとして取得する。

        Returns:
            list[Node]: 直接の子ノード。
        """
        if not self.isValid():
            return []
        dagPath = self.dagPath()
        dagFn = self.dagFn()
        children = []
        for index in range(dagFn.childCount()):
            child_path = om2.MDagPath(dagPath)
            child_path.push(dagFn.child(index))
            children.append(Node(child_path))
        return children

    def childTransforms(self):
        """直接の子 Transform のみを取得する（Shape 子は含まない）。

        Returns:
            list[Transform]: 直接の子 Transform。
        """
        return [child for child in self.childNodes() if isinstance(child, Transform)]

    def leaves(self):
        """Transform 階層下の葉ノード（子 Transform を持たないもの）をすべて取得する。

        Shape の有無は判定に関与しない。

        Returns:
            list[Transform]: 葉ノードのリスト。子 Transform が無い場合は自身のみを含む。
        """
        children = self.childTransforms()
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
        if not self.isValid():
            return []
        parent = self.parentNode()
        if parent is not None:
            candidates = parent.childTransforms()
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

        if not self.isValid():
            return []
        shapes = []
        dagPath = self.dagPath()
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

    @fast_edit
    @undo_chunk("hlibTransformMirrorGeometry")
    def mirrorGeometry(self, axis="x", space=MSpace.kObject, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False):
        """直下のすべてのShapeのジオメトリをミラーする。

        直下の各Shape（Mesh、NurbsCurveなど mirror を実装するもの）へ同じ引数で
        処理を委譲する。indices は Shape ごとの要素番号（Mesh は頂点、NurbsCurve は
        CV）として解釈される。Transform自身の行列やShapeの構造は変更しない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            axis (str): 反転する座標軸。x、y、z、xy、xz、yz、xyz。大文字も可。
                x は pivot.x を通る YZ 平面で反転する。複数軸は同時に反転する。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
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
        ws = world_space(space)
        for shape in self.shapes():
            shape.mirror(axis=axis, space=MSpace.kWorld if ws else MSpace.kObject, pivot=pivot, indices=indices)
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
            if self.parentPath() is None and not self.dagPath().isInstanced():
                return self
            cmds.parent(self.name(), world=True, relative=relative)
        else:
            target = parent if isinstance(parent, Node) else Node(parent)
            parent_name = target.fullName()
            # 古いMayaでは同じ親への再parentがエラーになる。
            # add=Trueはインスタンス操作なのでMayaの判定に委ねる。
            current = self.parentPath()
            if (not add and not self.dagPath().isInstanced() and current is not None
                    and current.fullPathName() == parent_name):
                return self
            cmds.parent(self.name(), parent_name, relative=relative, add=add)
        return self

    @undo_chunk("hlibTransformMatch")
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
        from hlib.nodes.node import Node as _InputNode

        target = _InputNode._resolve_input(target)
        if not isinstance(target, Transform):
            raise TypeError("Target must be a transform or joint")
        if any((position, rotation, scale, pivots)):
            cmds.matchTransform(self.fullName(), target.fullName(), position=position,
                                rotation=rotation, scale=scale, pivots=pivots)
        return self

    @fast_edit
    @undo_chunk("hlibTransformMirrorTransform")
    def mirrorTransform(self, axis="x", space=MSpace.kObject, pivot=(0.0, 0.0, 0.0), *, fast=False):
        """位置と向きを指定空間でビヘイビアミラーする。

        Matrix.mirroredと同じ回転規約で、負スケールによる形状反転ではない。
        Shapeの頂点・CVは編集しない。子孫は通常の親変換として追従する。
        指定空間のスケール・シアーを保つが、親に非一様スケールがある場合は
        ローカルのスケール・シアーが変わる場合がある。

        Args:
            axis (str | int): x/y/z/xy/xz/yz/xyz、または0/1/2。xはYZ平面。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            pivot (Iterable[float]): 指定空間の中心。内部距離単位cm。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。

        Returns:
            Transform: 自身。Transforms/Jointsからの一括呼出も可能。

        Raises:
            TypeError: wsまたはfastがboolでない場合。
            ValueError: 入力不正、特異な親行列、未対応のピボット/rotateAxisの場合。
            RuntimeError: ロックや入力接続で更新できない場合。

        既存set_matrixと同じ制約があり、非ゼロのピボット・
        TransformのrotateAxisは更新前に拒否する。
        """
        ws = world_space(space)
        from ..utils.mirror import mirror_arguments
        if not isinstance(ws, bool):
            raise TypeError("ws must be a bool")
        _, center = mirror_arguments(axis, pivot)
        name = self.fullName()
        parentNode = self.parentNode()
        parent = Matrix()
        if parentNode is not None and self.plug("inheritsTransform").get():
            # 親のチャンネル変更直後も評価済み値を取得する。
            parent = parentNode.plug("worldMatrix").element(parentNode.dagPath().instanceNumber()).get()
        offset = self.plug("offsetParentMatrix").get()
        effective_parent = offset * parent
        magnitude = max(1.0, *(sum(abs(effective_parent[row, col]) for col in range(3))
                               for row in range(3)))
        if abs(effective_parent.det4x4()) <= 1e-12 * magnitude ** 3:
            raise ValueError("Cannot mirror with a singular parent or offsetParentMatrix")
        attributes = ["rotatePivot", "scalePivot", "rotatePivotTranslate", "scalePivotTranslate"]
        if not self.mobject().hasFn(om2.MFn.kJoint):
            attributes.append("rotateAxis")
        if any(any(self.plug(attr).get()) for attr in attributes):
            raise ValueError("mirrorTransform does not support nonzero pivots or transform rotateAxis")
        world = self.getMatrix(space=MSpace.kWorld)
        source = world if ws else world * parent.inverse()
        target = source.mirrored(axis, center)
        target_world = target if ws else target * parent
        local = target_world * effective_parent.inverse()
        self.setMatrix(local, fast=fast)
        return self

    def shadingEngines(self):
        """list[ShadingEngine]: 直下の非中間Shapeで使用中のセット。インスタンス経路を保持。"""
        return list(dict.fromkeys(group for shape in self.shapes() for group in shape.shadingEngines()))

    def getOffsetParentMatrix(self):
        """offsetParentMatrixの現在値を取得する。

        Returns:
            Matrix: アトリビュート値の複製。ワールド行列やローカル行列との合成はしない。

        Raises:
            RuntimeError: ノードやアトリビュートが無効の場合。
        """
        return self.plug("offsetParentMatrix").get()

    @fast_edit
    @undo_chunk("hlibTransformSetOffsetParentMatrix")
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
        self.plug("offsetParentMatrix").set(value)
        return self

    def getMatrix(self, space=MSpace.kObject):
        """変換行列を取得する。

        ワールド空間は保持する DAG パスの inclusiveMatrix から取得する。
        ローカル空間は評価済みの ``matrix`` アトリビュートを直接読み取る。
        どちらも行列値を保持し続けず、呼出し時点の Maya の評価結果を返す。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
                ローカル空間（``matrix``）の値を取得する。ワールド空間では、
                :meth:`dagPath` が示す DAG インスタンスの要素
                (``worldMatrix[<インスタンス番号>]``)を使う。

        Returns:
            Matrix: 指定空間の評価済み行列の複製(om2.MMatrix の派生)。

        Raises:
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        ws = world_space(space)
        if not self.isValid():
            raise RuntimeError("無効なノードの行列は取得できません")
        if ws:
            return Matrix._wrap(self.dagPath().inclusiveMatrix())
        # 名前による findPlug より速い、アトリビュートの MObject からの MPlug 生成を使う。
        plug = om2.MPlug(self.mobject(), _transform_attribute("matrix"))
        return Matrix._wrap(om2.MFnMatrixData(plug.asMObject()).matrix())

    def getTranslation(self, space=MSpace.kObject):
        """Translation を取得する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            Translation: 評価済みの位置。
        """
        ws = world_space(space)
        return self.getMatrix(space=MSpace.kWorld if ws else MSpace.kObject).translate

    def getRotation(self, space=MSpace.kObject):
        """Euler 回転値を、ノードの rotateOrder で取得する。

        ``cmds.xform(query=True, rotation=True)`` と同じく、値はノードの rotateOrder で
        表す(戻り値の order もノードの回転順序)。行列を分解した回転の等価な解のうち、
        transform では現在の rotate チャンネル値に最も近いものを返すため、ローカル空間の
        transform(rotateAxis が 0)ではチャンネル値と一致する(浮動小数点の誤差を除く)。
        joint の値は jointOrient と rotateAxis を含む行列全体の回転で、解は 0 回転に
        最も近いものを選ぶ。スケールの符号の扱いは :meth:`getScale` と同じ。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            EulerRotation: 評価済みの回転値（radian、ノードの回転順序）。

        Raises:
            ValueError: 行列を分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        ws = world_space(space)
        _, quaternion, _, _, reference = self._decompose_like_channels(self.getMatrix(space=MSpace.kWorld if ws else MSpace.kObject))
        return EulerRotation._wrap(_closest_euler(quaternion, self._rotate_reference(reference)))

    def getScale(self, space=MSpace.kObject):
        """Scale を取得する。

        行列を om2.MTransformationMatrix と同じ規約で分解してから、スケールの符号の
        組み合わせを現在の scale チャンネル値へ揃える(2軸の符号の反転を、残りの軸まわりの
        180 度回転で補償する)。例えば scale が (-1, 1, 1) のノードは (-1, 1, 1) を返す。
        行列式の符号と合わない組み合わせ(ワールド空間で親が奇数個の負スケールを持つ
        場合など)は om2 の規約(行列式が負なら Z が負)のまま返す。
        :class:`~hlib.maths.matrix.Matrix` の ``scale`` は常に om2 の規約。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            Scale: 評価済みのスケール値。

        Raises:
            ValueError: 行列を分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        ws = world_space(space)
        _, _, scale, _, _ = self._decompose_like_channels(self.getMatrix(space=MSpace.kWorld if ws else MSpace.kObject))
        return Scale(*scale)

    def getShear(self, space=MSpace.kObject):
        """Shear を取得する。

        スケールの符号の扱いは :meth:`getScale` と同じ(符号を揃えた軸に合わせて
        シアーの符号も変わる)。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            Shear: 評価済みの shear 値。

        Raises:
            ValueError: 行列を分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        ws = world_space(space)
        _, _, _, shear, _ = self._decompose_like_channels(self.getMatrix(space=MSpace.kWorld if ws else MSpace.kObject))
        return Shear(*shear)

    def getQuaternion(self, space=MSpace.kObject):
        """Quaternion を取得する。

        スケールの符号の扱いは :meth:`getScale` と同じ。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            Quaternion: 評価済みの回転値。

        Raises:
            ValueError: 行列を分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        ws = world_space(space)
        _, quaternion, _, _, _ = self._decompose_like_channels(self.getMatrix(space=MSpace.kWorld if ws else MSpace.kObject))
        return Quaternion._wrap(quaternion)

    def getEuler(self, space=MSpace.kObject):
        """回転を XYZ 順序の EulerRotation として取得する。

        :meth:`getQuaternion` と同じ回転を ``om2.MQuaternion.asEulerRotation()`` の解
        (XYZ 順序)で返す。ノードの rotateOrder で表した値は :meth:`getRotation` を使う。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            EulerRotation: 評価済みの回転値（radian、XYZ 順序）。

        Raises:
            ValueError: 行列を分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        ws = world_space(space)
        _, quaternion, _, _, _ = self._decompose_like_channels(self.getMatrix(space=MSpace.kWorld if ws else MSpace.kObject))
        return EulerRotation._wrap(quaternion.asEulerRotation())

    def _parent_world_matrix(self):
        """親Transformのワールド行列を取得する。

        Returns:
            Matrix: 親のワールド行列。親がない、または親に getMatrix がなければ単位行列。
        """
        parent = self.parentNode()
        if parent is None or not hasattr(parent, "getMatrix"):
            return Matrix()
        return parent.getMatrix(space=MSpace.kWorld)

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
        if not self.isValid():
            return (1.0, 1.0, 1.0), om2.MEulerRotation()
        # MFnTransform の scale() / rotation() は scale・rotate アトリビュートそのもの(joint でも
        # jointOrient を含まない)を返す。名前による findPlug より大幅に速い。
        fn = om2.MFnTransform(self.mobject())
        return tuple(fn.scale()), fn.rotation(om2.MSpace.kTransform)

    def _decompose_like_channels(self, matrix, scale_reference=None):
        """行列を分解し、スケールの符号の組み合わせを基準のスケールへ揃える。

        om2.MTransformationMatrix の規約(行列式が負なら Z が負)で分解してから、
        :func:`_match_scale_signs` で符号を揃える。基準は scale_reference (指定時)、
        次に現在の scale チャンネル値の順に、行列式の符号と合う最初のもの。これにより
        scale が (-1, 1, 1) のようなミラーのノードでも、取得・設定の往復でチャンネル値の
        符号と回転が保たれ、``setScale`` では要求した符号がそのまま入る。

        Args:
            matrix (Matrix): 分解する行列。
            scale_reference (Iterable[float] | None): 最優先で符号を合わせるスケール
                (``setScale`` で要求した値)。None なら現在の scale チャンネル値だけ。

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

        transform では行列の回転をそのまま rotate とみなす(rotateAxis は未対応)。

        Args:
            quaternion (om2.MQuaternion): ローカル行列の回転。
            reference (om2.MEulerRotation): 現在の rotate チャンネル値。

        Returns:
            om2.MEulerRotation: ノードの rotateOrder で表した、reference に最も近い解。
        """
        return _closest_euler(quaternion, reference)

    def _apply_local_matrix(self, matrix, scale_reference=None):
        """ローカル行列の各成分をMayaアトリビュートへ適用する。

        行列を1回だけ分解し、平行移動・回転・スケール・シアーを順に書き込む。
        分解は om2.MTransformationMatrix の規約に、次の2点の選択を加えたもの。

        * スケールの符号の組み合わせは、行列式の符号が許す限り scale_reference
          (``setScale`` で要求した値)、次に現在の scale チャンネルに揃える
          (:meth:`_decompose_like_channels`)。
        * 回転はノードの rotateOrder で表し、等価な解のうち現在の rotate チャンネル値に
          最も近いものを選ぶ(``om2.MEulerRotation.closestSolution``)。

        このため ``setMatrix(getMatrix())`` や ``setTranslation`` はチャンネル値を
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
            RuntimeError: Maya がアトリビュートの書き込みを拒否した場合。
        """
        translate, quaternion, scale, shear, reference = self._decompose_like_channels(matrix, scale_reference)
        rotation = self._channel_rotation(quaternion, reference)
        angle_unit = om2.MAngle.uiUnit()
        rotation_values = tuple(om2.MAngle(component).asUnits(angle_unit) for component in rotation)
        if is_fast():
            # 保持するノードから直接プラグを構成する。名前の再解決を省いても
            # 書込順・ロック/接続/範囲検査・UI単位は通常のfast経路と同じ。
            for attribute, values in (("translate", translate), ("rotate", tuple(rotation)),
                                      ("scale", scale), ("shear", shear)):
                set_plug(om2.MPlug(self.mobject(), _transform_attribute(attribute)), values)
            return
        name = self.fullName()
        set_attr(f"{name}.translate", *(om2.MDistance(v).asUnits(om2.MDistance.uiUnit()) for v in translate))
        set_attr(f"{name}.rotate", *rotation_values)
        set_attr(f"{name}.scale", *scale)
        set_attr(f"{name}.shear", *shear)

    @fast_edit
    @undo_chunk("hlibTransformSetMatrix")
    def setMatrix(self, matrix, space=MSpace.kObject, *, fast=False):
        """行列をローカルまたはワールド空間で設定する。

        行列を分解して translate・rotate・scale・shear に書き込む。スケールの符号と
        Euler の解は、同じ行列になる候補のうち現在のチャンネル値に近いものを選ぶ
        (詳細は ``_apply_local_matrix``)。そのため ``cmds.xform(matrix=...)``
        (常に om2 の規約で書く)とは、負スケールのノードや Euler の別解でチャンネル値が
        異なることがあるが、結果の行列は同じ。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            matrix (Matrix | sequence): 適用する変換行列。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: 無効なノード、または Maya がアトリビュート設定を拒否した場合。
            ValueError: 入力行列が不正、分解不能、またはワールド指定時の親行列が逆行列を持たない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        ws = world_space(space)
        return self._set_matrix(matrix, ws)

    def _set_matrix(self, matrix, ws=False, scale_reference=None):
        """:meth:`setMatrix` の本体。Undo チャンクと fast の扱いは呼び出し元に任せる。

        Args:
            matrix (Matrix | sequence): 適用する変換行列。
            ws (bool): ``True`` でワールド空間、``False`` でローカル空間に設定する。
            scale_reference (Iterable[float] | None): 分解したスケールの符号を最優先で
                合わせる値(:meth:`setScale` で要求した値)。None なら現在の scale
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
        local_matrix = matrix if not ws else matrix * self._parent_world_matrix().inverse()
        self._apply_local_matrix(local_matrix, scale_reference)
        return self

    @fast_edit
    @undo_chunk("hlibTransformSetTranslate")
    def setTranslation(self, value, space=MSpace.kObject, *, fast=False):
        """平行移動をローカルまたはワールド空間で設定する。

        rotate・scale・shear のチャンネル値は(浮動小数点の誤差を除いて)変えない
        (transform の rotateAxis は 0 を前提とする。joint は jointOrient / rotateAxis を保つ)。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Translation | sequence): 新しい平行移動値。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: 現在の行列を分解できない、または必要な親行列を反転できない場合。
            RuntimeError: ノードが無効、またはアトリビュートを書き込めない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        ws = world_space(space)
        matrix = self.getMatrix(space=MSpace.kWorld if ws else MSpace.kObject)
        matrix.translate = value
        return self.setMatrix(matrix, space=MSpace.kWorld if ws else MSpace.kObject)

    @fast_edit
    @undo_chunk("hlibTransformSetRotate")
    def setRotation(self, value, unit="rad", space=MSpace.kObject, *, fast=False):
        """Euler回転を設定する。

        3成分の値は ``cmds.xform(rotation=...)`` と同じくノードの rotateOrder の値として
        解釈する(:meth:`getRotation` や ``plug("rotate").get()`` の値をそのまま渡せる)。
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
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: unit が rad/deg 以外、deg を EulerRotation / Quaternion と指定、
                値が3成分でない、行列が分解不能、または必要な親行列が反転不能の場合。
            RuntimeError: ノードが無効、またはアトリビュートを書き込めない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        ws = world_space(space)
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
        matrix = self._replace_components(self.getMatrix(space=MSpace.kWorld if ws else MSpace.kObject), rotate=value)
        return self.setMatrix(matrix, space=MSpace.kWorld if ws else MSpace.kObject)

    @fast_edit
    @undo_chunk("hlibTransformSetScale")
    def setScale(self, value, space=MSpace.kObject, *, fast=False):
        """スケールをローカルまたはワールド空間で設定する。

        回転・シアー・平行移動は保つ(回転とシアーは :meth:`getScale` と同じ規約で
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
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: 現在の行列を分解できない、または必要な親行列を反転できない場合。
            RuntimeError: ノードが無効、またはアトリビュートを書き込めない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        ws = world_space(space)
        value = tuple(value)
        matrix = self._replace_components(self.getMatrix(space=MSpace.kWorld if ws else MSpace.kObject), scale=value)
        return self._set_matrix(matrix, ws, scale_reference=value)

    @fast_edit
    @undo_chunk("hlibTransformSetShear")
    def setShear(self, value, space=MSpace.kObject, *, fast=False):
        """Shearをローカルまたはワールド空間で設定する。

        値は :meth:`getShear` と同じ規約で解釈し、回転・スケール・平行移動は保つ。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Shear | sequence): 新しいShear値。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: 現在の行列を分解できない、または必要な親行列を反転できない場合。
            RuntimeError: ノードが無効、またはアトリビュートを書き込めない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        ws = world_space(space)
        matrix = self._replace_components(self.getMatrix(space=MSpace.kWorld if ws else MSpace.kObject), shear=value)
        return self.setMatrix(matrix, space=MSpace.kWorld if ws else MSpace.kObject)

    @flag_aliases("makeIdentity")
    @undo_chunk("hlibTransformFreeze")
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
        Maya標準に従う。resetやJoint.freeze_rotationの姿勢移送とは異なる。
        """
        if kwargs.pop("apply", True) is not True:
            raise ValueError("freeze requires apply=True")
        return self.makeIdentity(apply=True, **kwargs)

    @undo_chunk("hlibTransformMakeIdentity")
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
        cmds.makeIdentity(self.fullName(), **kwargs)
        return self

    @undo_chunk("hlibTransformReleaseSRT")
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
            plug = self.plug(channel)
            plug.setFlags(locked=False)
            plug.disconnect()
            for child in plug.children():
                child.setFlags(locked=False)
                child.disconnect()
        return self

    def closestAxisToVector(self, ref_vector, include_negative=True):
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
        ref_vector = ref_vector.normalized()
        matrix = self.getMatrix(space=MSpace.kWorld)
        axes = {"x": Vector(1.0, 0.0, 0.0), "y": Vector(0.0, 1.0, 0.0), "z": Vector(0.0, 0.0, 1.0)}
        if include_negative:
            axes.update({f"-{name}": axis * -1.0 for name, axis in axes.items()})
        best_axis = None
        best_dot = None
        for name, axis in axes.items():
            world_axis = matrix.transformVector(axis).normalized()
            dot = world_axis.dot(ref_vector)
            if best_dot is None or dot > best_dot:
                best_dot = dot
                best_axis = name
        return best_axis

    @undo_chunk("hlibTransformCreateOffsetGroups")
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
            names = (f"{self.name()}_offset",)
        matrix = self.getMatrix(space=MSpace.kWorld)
        parent = self.parentNode()
        groups = []
        for name in names:
            kwargs = {}
            if parent is not None:
                kwargs["parent"] = parent.fullName()
            group = Transform(cmds.group(empty=True, name=name, **kwargs))
            group.setMatrix(matrix, space=MSpace.kWorld)
            groups.append(group)
            parent = group
        self.setParent(groups[-1])
        return groups


@collection_export()
@bulk_api(
    Transform,
    reads=(
        'addConstraint',
        'deleteConstraints',
        'transformFn',
        'getPivot',
        'boundingBox',
        'root',
        'childNodes',
        'childTransforms',
        'leaves',
        'siblings',
        'shapes',
        'shape',
        'shadingEngines',
        'getOffsetParentMatrix',
        'getMatrix',
        'getTranslation',
        'getRotation',
        'getScale',
        'getShear',
        'getQuaternion',
        'getEuler',
        'closestAxisToVector',
        'createOffsetGroups',
    ),
    writes=(
        'freeze',
        'resetPivot',
        'reset',
        'scaleGeometry',
        'setPivot',
        'centerPivot',
        'mirrorGeometry',
        'transform',
        'setParent',
        'matchTransform',
        'mirrorTransform',
        'setOffsetParentMatrix',
        'setMatrix',
        'setTranslation',
        'setRotation',
        'setScale',
        'setShear',
        'makeIdentity',
        'unlockAndDisconnectTransformChannels',
    ),
)
class Transforms(DagNodes):
    """Joint等の派生型を含むTransform参照のコレクション。

    型検証・色設定・参照のコピーはNodesに従う。座標・行列操作は各対象へ転送する。
    """

    item_class = Transform
