"""マトリクスを介して Transform ノードを操作する。"""

import math
import numbers
from typing import Any, Dict

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace

from ..core.attributeType import value_reader
from ..core.fastWrite import require_writable
from ..core.nodeEdit import require_editable
from ..decorator import (_edit_context, _merge_flags, _pick_alias, _require_bool, _transform_argument_hints,
                         nativeUnits, undoChunk, undoTransaction)
from ..maths import EulerRotate, Matrix, Quaternion, Scale, Shear, Translate, Vector
from ..maths.eulerRotate import orderIndex
from ..plugs.plug import Plug
from ..util import _angle_unit, _from_radians, _to_radians, _world_space
from ..util import _ArgumentError, _UNSET
from .dagNode import DagNode
from .node import Node, Nodes

#: ターゲットの transform の値(位置・回転など)を使うコンストレイント。ターゲットは Transform に限る。
_TRANSFORM_SOURCE_CONSTRAINTS = frozenset((
    "parentConstraint", "pointConstraint", "orientConstraint", "scaleConstraint",
    "aimConstraint", "poleVectorConstraint",
))


#: setLimitsのキーと、cmds.transformLimitsの値・有効化フラグ、値の種類(角度・距離・倍率)。
_LIMIT_FLAGS = {
    "translate" + axis: ("translation" + axis, "enableTranslation" + axis, "distance") for axis in "XYZ"
}
_LIMIT_FLAGS.update({"rotate" + axis: ("rotation" + axis, "enableRotation" + axis, "angle") for axis in "XYZ"})
_LIMIT_FLAGS.update({"scale" + axis: ("scale" + axis, "enableScale" + axis, "scale") for axis in "XYZ"})

#: 変換アトリビュート名の照会キャッシュ。
_TRANSFORM_ATTRIBUTES = {}

#: getRotateでゼロとみなすスケール軸の長さ。Mayaは scale 0 を 1e-12 として評価する。
_NEAR_ZERO_AXIS = 1e-10


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
    マトリクスは変わらない(D を2軸が -1 の対角マトリクスとして S·Sh·R = (S·D)·(D·Sh·D)·(D·R))。
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
    # om2 のクォータニオンの積は左を先に適用する。D(残りの軸まわりの 180 度)の後に元の回転。
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


def _unwritable_channel_message(plug):
    """ロック・入力接続された子を含むチャンネルへの書込み失敗を、原因の子を示す文言にする。

    Args:
        plug (Plug): 書込みに失敗したtranslate・rotate等のコンパウンドアトリビュート。

    Returns:
        str | None: 例外の文言。書込みを妨げる子(または自身)が見つからなければNone。
    """
    for target in [plug] + list(plug.getChildren()):
        if target.isLocked():
            reason = "is locked"
        elif target.isDestination():
            source = target.getSource()
            reason = f"is connected from {source.getFullName()}" if source is not None else "has an input connection"
        else:
            continue
        return (f"Cannot set {plug.getFullName()}: {target.getFullName()} {reason}; "
                "unlock/disconnect it, or pass safe=True to skip channels that cannot be written")
    return None


class Transform(DagNode):
    """Transformのノード参照とDAGパスを保持し、変換値を照会・設定する。

    マトリクス・TRS・ピボットを扱い、Shapeの頂点やCVの編集とは区別する。
    距離はcm、角度はradを基本とし、MayaのUI単位とは独立する。
    ローカル側の基準は各メソッドで異なる。
    通常の変更はmaya.cmdsでUndoに記録し、対応するfastはOpenMayaで直接更新する。
    safeを持つsetterは書けない成分を残すが、目標値との一致や全体の巻き戻しは保証しない。
    """

    def addConstraint(self, sources, type=_UNSET, maintainOffset=_UNSET, *, typ=_UNSET, mo=_UNSET,
        createCache=_UNSET, cc=_UNSET, decompRotationToChild=_UNSET, dr=_UNSET, deleteCache=_UNSET, dc=_UNSET,
        edit=_UNSET, e=_UNSET, layer=_UNSET, l=_UNSET, name=_UNSET, n=_UNSET, query=_UNSET, q=_UNSET,
        remove=_UNSET, rm=_UNSET, skipRotate=_UNSET, sr=_UNSET, skipTranslate=_UNSET, st=_UNSET,
        targetList=_UNSET, tl=_UNSET, weight=_UNSET, w=_UNSET, weightAliasList=_UNSET, wal=_UNSET, offset=_UNSET,
        o=_UNSET, skip=_UNSET, sk=_UNSET, scaleCompensate=_UNSET, sc=_UNSET, aimVector=_UNSET, aim=_UNSET,
        upVector=_UNSET, u=_UNSET, worldUpObject=_UNSET, wuo=_UNSET, worldUpType=_UNSET, wut=_UNSET,
        worldUpVector=_UNSET, wu=_UNSET, **kwargs):
        """指定したターゲットで自身を制御するコンストレイントを作成する。

        選択状態で対象を補完しない。通常のcmds更新をUndo有効時にまとめ、途中失敗の変更は戻さない。

        Args:
            sources (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug | Iterable):
                単一参照またはその列。Plug/MPlugは所有ノード、Component/Componentsは所有Shapeへ解決する。
                アトリビュート・コンポーネント文字列も同様。parent/point/orient/scale/aim/poleVectorは
                Transform(Joint・IkHandleを含む)に解決される入力だけを受け付ける。
            type (str): parent、point、orient、scale、aim、poleVector、
                geometry、normal、tangent、pointOnPoly。Constraint接尾辞付きも可。既定parent。
            maintainOffset (bool): 既定False。parent/point/orient/scale/aimだけへ渡すMayaのmaintainOffset。
            createCache (Sequence[float]): MayaのcreateCacheフラグ。開始・終了時刻の2値をUI時間単位で指定する。
            cc (Sequence[float]): createCacheの別名。同時指定は不可。
            decompRotationToChild (bool): MayaのdecompRotationToChildフラグ。省略時はMayaの既定に従う。
            dr (bool): decompRotationToChildの別名。同時指定は不可。
            deleteCache (bool): MayaのdeleteCacheフラグ。省略時はMayaの既定に従う。
            dc (bool): deleteCacheの別名。同時指定は不可。
            edit (bool): Trueは作成専用のこのメソッドでは拒否する。
            e (bool): editの別名。同時指定は不可。
            layer (str): Mayaのlayerフラグ。省略時はMayaの既定に従う。
            l (str): layerの別名。同時指定は不可。
            name (str): Mayaのnameフラグ。省略時はMayaの既定に従う。
            n (str): nameの別名。同時指定は不可。
            query (bool): Trueは作成専用のこのメソッドでは拒否する。
            q (bool): queryの別名。同時指定は不可。
            remove (bool): Mayaのremoveフラグ。省略時はMayaの既定に従う。
            rm (bool): removeの別名。同時指定は不可。
            skipRotate (str | Sequence[str]): MayaのskipRotateフラグ。省略時はMayaの既定に従う。
            sr (str | Sequence[str]): skipRotateの別名。同時指定は不可。
            skipTranslate (str | Sequence[str]): MayaのskipTranslateフラグ。省略時はMayaの既定に従う。
            st (str | Sequence[str]): skipTranslateの別名。同時指定は不可。
            targetList (bool): MayaのtargetListフラグ。省略時はMayaの既定に従う。
            tl (bool): targetListの別名。同時指定は不可。
            weight (float): Mayaのweightフラグ。省略時はMayaの既定に従う。
            w (float): weightの別名。同時指定は不可。
            weightAliasList (bool): MayaのweightAliasListフラグ。省略時はMayaの既定に従う。
            wal (bool): weightAliasListの別名。同時指定は不可。
            offset (Sequence[float]): Mayaのoffsetフラグ。(x, y, z)の3値を指定する。
            o (Sequence[float]): offsetの別名。同時指定は不可。
            skip (str | Sequence[str]): Mayaのskipフラグ。省略時はMayaの既定に従う。
            sk (str | Sequence[str]): skipの別名。同時指定は不可。
            scaleCompensate (bool): MayaのscaleCompensateフラグ。省略時はMayaの既定に従う。
            sc (bool): scaleCompensateの別名。同時指定は不可。
            aimVector (Sequence[float]): MayaのaimVectorフラグ。(x, y, z)の3値を指定する。
            aim (Sequence[float]): aimVectorの別名。同時指定は不可。
            upVector (Sequence[float]): MayaのupVectorフラグ。(x, y, z)の3値を指定する。
            u (Sequence[float]): upVectorの別名。同時指定は不可。
            worldUpObject (Node | Plug | Component | str | om2.MObject | om2.MDagPath | om2.MPlug): ワールドアップの参照ノード。Plug/Componentは所有ノードへ解決する。Componentsは不可。
            wuo (Node | Plug | Component | str | om2.MObject | om2.MDagPath | om2.MPlug): worldUpObjectの別名。同時指定は不可。
            worldUpType (str): MayaのworldUpTypeフラグ。省略時はMayaの既定に従う。
            wut (str): worldUpTypeの別名。同時指定は不可。
            worldUpVector (Sequence[float]): MayaのworldUpVectorフラグ。(x, y, z)の3値を指定する。
            wu (Sequence[float]): worldUpVectorの別名。同時指定は不可。
            **kwargs: 選んだMaya constraintコマンドへ渡す追加の作成フラグ。
            typ (str): typeの別名。同時指定は不可。
            mo (bool): maintainOffsetの別名。同時指定は不可。

        Returns:
            Constraint: 対応する具象ラッパー。同じ種類が既存なら Maya の規則で
                ターゲットが追加される場合がある。

        Raises:
            ValueError: 未対応の型・空のソース、query/edit=True、または無効なworldUpObjectの場合。
            TypeError: 型名・参照型・長短フラグが不正、または上記6型のターゲットがTransformでない場合。
            RuntimeError: ノードが無効、ターゲットの名前を解決できない(存在しない、または
                複数のノードに一致する)場合、または Maya が作成を拒否した場合。
            DeletedAttributeError: 削除済みアトリビュートのPlug/MPlugの場合。ValueErrorとRuntimeErrorの派生。

        Note:
            PoleVectorはRP IKハンドル、Geometry/Normal/PointOnPolyは対応形状、TangentはNURBSカーブが必要。
        """
        _merge_flags(kwargs, (
            (createCache, cc, "createCache", "cc"),
            (decompRotationToChild, dr, "decompRotationToChild", "dr"),
            (deleteCache, dc, "deleteCache", "dc"),
            (layer, l, "layer", "l"),
            (name, n, "name", "n"),
            (remove, rm, "remove", "rm"),
            (skipRotate, sr, "skipRotate", "sr"),
            (skipTranslate, st, "skipTranslate", "st"),
            (targetList, tl, "targetList", "tl"),
            (weight, w, "weight", "w"),
            (weightAliasList, wal, "weightAliasList", "wal"),
            (offset, o, "offset", "o"),
            (skip, sk, "skip", "sk"),
            (scaleCompensate, sc, "scaleCompensate", "sc"),
            (aimVector, aim, "aimVector", "aim"),
            (upVector, u, "upVector", "u"),
            (worldUpType, wut, "worldUpType", "wut"),
            (worldUpVector, wu, "worldUpVector", "wu"),
        ))
        if e is not _UNSET:
            if edit is not _UNSET:
                raise _ArgumentError("Specify only one of 'edit' and 'e'")
            edit = e
        if edit is not _UNSET:
            kwargs["edit"] = edit
        if q is not _UNSET:
            if query is not _UNSET:
                raise _ArgumentError("Specify only one of 'query' and 'q'")
            query = q
        if query is not _UNSET:
            kwargs["query"] = query
        if wuo is not _UNSET:
            if worldUpObject is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldUpObject' and 'wuo'")
            worldUpObject = wuo
        if worldUpObject is not _UNSET:
            kwargs["worldUpObject"] = worldUpObject
        type = _pick_alias(type, typ, "type", "typ", default="parent")
        maintainOffset = _pick_alias(maintainOffset, mo, "maintainOffset", "mo", default=False)
        with undoChunk("mlibTransformAddConstraint"):
            from .constraint import Constraint

            # 型登録を重複管理せず、Constraint 派生として明示登録された型名から判定する。
            # 抽象型 "constraint" は cmds に同名コマンドが無いので除く(生成クラスは含まれない)。
            supported = set(Node._registry._registered_types(base=Constraint)) - {"constraint"}
            if not isinstance(type, str):
                # addConstraint("parent", ctrl) のように型名とターゲットを逆に渡した場合は順序を案内する。
                if isinstance(sources, str) and (sources if sources.endswith("Constraint")
                                                 else sources + "Constraint") in supported:
                    raise TypeError(
                        f"addConstraint() takes the target first and the constraint type as type=; "
                        f"use addConstraint(target, type={sources!r})")
                raise TypeError(f"type must be a string such as 'parent', got {type.__class__.__name__}; "
                                "use addConstraint(target, type=\"parent\")")
            command_name = type if type.endswith("Constraint") else type + "Constraint"
            if command_name not in supported:
                raise ValueError(f"Unsupported constraint type: {type}")
            self._require_valid("constrain")
            from ..components.component import Component, Components
            from ..plugs.plug import Plug

            # Components は要素へ展開せず、所有シェイプを1つのターゲットとして扱う。
            if isinstance(sources, (Node, str, Plug, Component, Components,
                                    om2.MObject, om2.MDagPath, om2.MPlug)):
                sources = [sources]
            # ターゲットの transform の値を使う型。シェイプをターゲットにすると maya.cmds はターゲットの
            # 無い(追従しない)コンストレイントを黙って作るため、Transform 以外は TypeError にする。
            requires_transform = command_name in _TRANSFORM_SOURCE_CONSTRAINTS
            names = []
            for source in Nodes._resolve_inputs(sources):
                if source is None or (isinstance(source, str) and not source):
                    raise TypeError("Constraint sources must be non-empty names or Node objects")
                # 文字列も含めて所有ノードへ解決する。Plug・MPlug・"node.attribute" は所有ノード、
                # Component・"pCube1.vtx[0]" は所有シェイプをターゲットにする(maya.cmds へ
                # プラグ名・コンポーネント名をそのまま渡すとターゲットとして扱われないため)。
                source = Node._resolve_input(source)
                if not source.isValid():
                    raise RuntimeError("Constraint target is invalid")
                if requires_transform and not source.hasFn(om2.MFn.kTransform):
                    raise TypeError(
                        f"{command_name} sources must be transforms (including joints and IK handles), "
                        f"not shapes, components or DG nodes: {source.__class__.__name__} {source.getName()!r}"
                    )
                names.append(source.getFullName())
            if not names:
                raise ValueError("At least one constraint source is required")

            command_kwargs = dict(kwargs)
            if command_kwargs.get("query") or command_kwargs.get("edit"):
                raise ValueError("addConstraint supports creation only; use Maya constraint commands for query/edit")
            if "worldUpObject" in command_kwargs:
                command_kwargs["worldUpObject"] = Node._input_name(command_kwargs["worldUpObject"])
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

    def deleteConstraints(self, *, fast=False):
        """自身に作用するコンストレイントと、その入力側のpairBlendを削除する。

        pairBlend・unitConversionだけを上流へ辿り、unitConversionは残す。
        ターゲットTransform・animCurveは削除せず、姿勢維持・ベイク・入力の再接続はしない。
        対象外への共有出力と削除対象の参照・ロックを先に検査する。

        Args:
            fast (bool): Falseはcmds.deleteをUndo有効時にまとめる。
                Trueは入力を外してOM2で削除し、Undoへ記録しない。設定は変えず、
                後続失敗で切断や削除を自動では戻さない。

        Returns:
            list[str]: 削除前の完全名をソートしたリスト。対象がなければ空リスト。

        Raises:
            TypeError: fastがbool以外の場合。
            RuntimeError: 無効参照、共有出力、参照・ロックされた削除対象、またはMayaの処理失敗。
        """
        with _edit_context("mlibTransformDeleteConstraints", fast):
            self._require_valid("edit")
            owner = self.mnode()
            deleting, bridges, objects = set(), set(), {}

            def key(obj):
                """同一探索内のMObjectへ軽量な識別子を付ける。"""
                token = om2.MObjectHandle(obj).hashCode()
                objects[token] = obj
                return token

            def inputs(obj):
                """message以外の入力接続元を重複なく取得する。"""
                result = {}
                for plug in om2.MFnDependencyNode(obj).getConnections():
                    if plug.attribute().hasFn(om2.MFn.kMessageAttribute):
                        continue
                    for source in plug.connectedTo(True, False):
                        if not source.attribute().hasFn(om2.MFn.kMessageAttribute):
                            result[key(source.node())] = source.node()
                return result.values()

            def upstream(obj, path):
                """constraintへ到達する限定した中継経路を記録する。"""
                token = key(obj)
                if token in path:
                    return False
                fn = om2.MFnDependencyNode(obj)
                if obj.hasFn(om2.MFn.kConstraint):
                    deleting.add(token)
                    return True
                if fn.typeName not in ("pairBlend", "unitConversion"):
                    return False
                found = False
                for source in inputs(obj):
                    found = upstream(source, path | {token}) or found
                if found:
                    (deleting if fn.typeName == "pairBlend" else bridges).add(token)
                return found

            owner_key = key(owner)
            for source in inputs(owner):
                upstream(source, {owner_key})
            allowed = deleting | bridges | {owner_key}
            for token in deleting | bridges:
                fn = om2.MFnDependencyNode(objects[token])
                for plug in fn.getConnections():
                    if plug.attribute().hasFn(om2.MFn.kMessageAttribute):
                        continue
                    for destination in plug.connectedTo(False, True):
                        if (not destination.attribute().hasFn(om2.MFn.kMessageAttribute)
                                and key(destination.node()) not in allowed):
                            raise RuntimeError(f"Constraint path has shared outputs: {fn.name()}")
            for token in deleting:
                require_editable(objects[token])
            names = sorted(Node(objects[token]).getFullName() for token in deleting)
            if names:
                if fast:
                    self._detach_inputs(objects[token] for token in deleting)
                    modifier = om2.MDagModifier()
                    for token in deleting:
                        modifier.deleteNode(objects[token], False)
                    modifier.doIt()
                else:
                    cmds.delete(names)
            return names

    def mfn(self):
        """この Transform で最も具体的な om2 function set を取得する。

        呼び出すたびに新しい ``om2.MFnTransform`` を保持する DAG パスから作る。
        Joint など派生型もこの function set を使う。

        Returns:
            om2.MFnTransform: この Transform の function set。

        Raises:
            RuntimeError: 保持していた DAG パスが無効な場合。
        """
        return om2.MFnTransform(self.mpath())

    def scaleGeometry(self, scale, worldSpace=False, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False):
        """直下の非中間Shapeの頂点・CVを拡縮する。Transformのマトリクスは変更しない。

        Shapeごとに検証・更新するため、後続Shapeの拒否でも先行変更は残る。
        共有形状は全インスタンスに影響する。

        Args:
            scale (float | Iterable[float]): 一様倍率、またはXYZ倍率。
            worldSpace (bool): Trueはワールド空間、Falseは各Shapeのオブジェクト空間。
            pivot (Iterable[float]): 指定空間の拡縮中心。cm。既定は原点。
            indices (Iterable[int | tuple[int, int]] | None): 各Shapeに共通の頂点/CV番号。
                Noneは全要素。サーフェスは(U, V)の組。
            fast (bool): Trueは履歴なしメッシュ・非周期カーブをOM2で更新(Undoなし)。
                Falseは通常更新をUndo有効時にまとめる。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: fast・番号の型が不正な場合。
            ValueError: 倍率・中心・空間が不正な場合。
            IndexError: 対象番号が範囲外の場合。
            RuntimeError: Mayaが変更を拒否した場合。
            NotImplementedError: 未対応Shape、またはfastの編集条件に対応しない場合。
        """
        with _edit_context("mlibTransformScaleGeometry", fast):
            ws = _world_space(worldSpace)
            indices = None if indices is None else tuple(indices)
            scale = scale if isinstance(scale, numbers.Real) else tuple(scale)
            pivot = tuple(pivot)
            for shape in self.getShapes():
                shape.scaleGeometry(scale, worldSpace=ws, pivot=pivot, indices=indices, fast=fast)
            return self

    def getPivot(self, worldSpace=False, *, kind="rotate"):
        """回転またはスケールピボットの位置をcm単位で取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはxformのobjectSpaceに相当する
                MSpace.kPreTransform。
            kind (str): rotateは回転、scaleはスケールピボット。

        Returns:
            Translate: ノードと独立した新しい位置の値。UI距離単位によらずcm。

        Raises:
            ValueError: kindがrotate/scaleでない場合。
        """
        ws = _world_space(worldSpace)
        if kind not in ("rotate", "scale"):
            raise ValueError("kind must be 'rotate' or 'scale'")
        # xformのobjectSpaceはMFnTransformのkPreTransformに対応する。
        fn = self.mfn()
        space = MSpace.kWorld if ws else MSpace.kPreTransform
        point = fn.rotatePivot(space) if kind == "rotate" else fn.scalePivot(space)
        return Translate(point.x, point.y, point.z)

    def setPivot(self, value, worldSpace=False, *, kind="rotate", preserve=True, fast=False):
        """指定した種類のピボットを変更する。既定ではノードの姿勢を保つ。

        Args:
            value (Iterable[float]): 新しいピボット位置のXYZ3成分。UI距離単位によらずcm。
            worldSpace (bool): Trueはワールド空間、FalseはxformのobjectSpaceに相当する
                MSpace.kPreTransform。
            kind (str): rotate/scale/both。bothは両方を同じ位置へ設定する。
            preserve (bool): Trueはピボット補償値を調整してマトリクスを保つ。
                Falseは補償せず、姿勢が変わる場合がある。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: preserveがboolでない、または対象がJointの場合。
            ValueError: kind、座標の要素数・有限値が不正な場合。
            RuntimeError: ノードが無効、変更するピボットまたは補償値(preserve=True時)の
                成分がロック・入力接続されている場合、または Maya が設定を拒否した場合。
                ロックの検査は通常・fastとも更新前に行い、何も変更しない。

        Note:
            Jointは独立したピボットの変更をサポートしないため、更新前に拒否する。
        """
        with _edit_context("mlibTransformSetPivot", fast):
            ws = _world_space(worldSpace)
            if kind not in ("rotate", "scale", "both"):
                raise ValueError("kind must be 'rotate', 'scale' or 'both'")
            _require_bool(preserve, "preserve")
            if self.isType("joint"):
                raise TypeError("Joint does not support independent rotate/scale pivots")
            values = tuple(value)
            if len(values) != 3 or not all(math.isfinite(v) for v in values):
                raise ValueError("Expected three finite pivot coordinates")
            kinds = ("scale", "rotate") if kind == "both" else (kind,)
            # APIはロックを迂回し、cmds.xformはロックされた成分を黙って飛ばすため、
            # 通常とfastのどちらも変更する補償値を含めて書く前に確認する。
            self._require_pivots_writable(kinds, preserve)
            if fast:
                fn = self.mfn()
                point = om2.MPoint(*values)
                space = MSpace.kWorld if ws else MSpace.kPreTransform
                for selected in kinds:
                    setter = fn.setRotatePivot if selected == "rotate" else fn.setScalePivot
                    setter(point, space, preserve)
                return self
            coordinates = [om2.MDistance(v).asUnits(om2.MDistance.uiUnit()) for v in values]
            flag = {"rotate": "rotatePivot", "scale": "scalePivot", "both": "pivots"}[kind]
            pivot_flags: Dict[str, Any] = {flag: coordinates}
            cmds.xform(self.getFullName(), worldSpace=ws, objectSpace=not ws,
                       preserve=preserve, **pivot_flags)
            return self

    def centerPivot(self, *, fast=False):
        """バウンディングボックス中心へ回転・スケールピボットを移す。

        通常はxform(centerPivots=True)、fastはAPIで得た中心をsetPivotへ渡す。
        preserve=Trueでピボット補償値を調整し、コンポーネント選択は使わない。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: fastがbool以外、またはfastで対象がJointの場合。
            RuntimeError: 無効参照の場合、ピボットまたは補償値の成分がロック・入力接続
                されている場合(通常・fastとも更新前に検査する)、またはMayaが更新を拒否した場合。
        """
        with _edit_context("mlibTransformCenterPivot", fast):
            if fast:
                center = self.mfn().boundingBox.center * self.mpath().exclusiveMatrix()
                return self.setPivot((center.x, center.y, center.z), worldSpace=True,
                                     kind="both", preserve=True, fast=fast)
            # fast(setPivot経由)と同じく、xformが黙って飛ばすロックを先に拒否する。
            self._require_pivots_writable(("scale", "rotate"), True)
            cmds.xform(self.getFullName(), centerPivots=True, preserve=True)
            return self

    def getChildren(self, shapes=False, intermediates=False, *, allDescendents=False,
                    order="depthFirst", leaves=False, includeSelf=False, underWorld=False, type=None):
        """指定条件に合う直接の子、または子孫を取得する。

        Args:
            type (str | Iterable[str] | None): Mayaのノード型で結果を絞る(派生型を含む。例 ``type="joint"``)。
                規則は :meth:`~mlib.nodes.dagNode.DagNode.getChildren` と同じ。
            shapes (bool): TrueはShapeも含める。既定FalseはTransformのみ。
            intermediates (bool): Trueは中間オブジェクトも含める。
            allDescendents (bool): Trueは子孫全体。既定は直接の子だけ。
            order (str): depthFirstまたはbreadthFirst。
            leaves (bool): 子Transformを持たないTransformだけを再帰取得する。
            includeSelf (bool): 自身も対象へ含める。葉の自身も取得する場合はTrue。
            underWorld (bool): Shape下のアンダーワールドも探索する。

        Returns:
            list[DagNode]: DAGの子順に並んだノード。該当なしは空リスト。
        """
        return super().getChildren(shapes, intermediates, allDescendents=allDescendents,
                                   order=order, leaves=leaves, includeSelf=includeSelf,
                                   underWorld=underWorld, type=type)

    def getUnusedIntermediateShapes(self):
        """直下から削除可能な未使用中間Shapeを取得する。

        shadingEngineへの標準メンバー接続を除き、出力接続がない中間Shapeを対象とする。
        入力履歴だけが残るShapeも対象。参照・ノードロック・インスタンス・子DAGを持つ
        Shapeは除外する。子Transform以下は検索せず、シーンは変更しない。

        Returns:
            list[Shape]: DAGの子順の削除候補。対象なしは空リスト。

        Raises:
            RuntimeError: 無効なTransform、またはMayaの照会失敗。
        """
        fn = om2.MFnDagNode(self.mpath())
        if fn.isFromReferencedFile or fn.isLocked:
            return []
        result = []
        for shape in self.getShapes(intermediates=True):
            shape_fn = om2.MFnDagNode(shape.mpath())
            if (not shape_fn.isIntermediateObject or shape_fn.isFromReferencedFile
                    or shape_fn.isLocked or shape_fn.childCount()
                    or len(om2.MDagPath.getAllPathsTo(shape.mnode())) > 1):
                continue
            used = False
            for plug in shape_fn.getConnections():
                root = plug
                while root.isChild or root.isElement:
                    root = root.parent() if root.isChild else root.array()
                is_membership = om2.MFnAttribute(root.attribute()).name == "instObjGroups"
                for destination in plug.connectedTo(False, True):
                    if (is_membership and destination.node().hasFn(om2.MFn.kShadingEngine)
                            and om2.MFnAttribute(destination.attribute()).name == "dagSetMembers"):
                        continue
                    used = True
                    break
                if used:
                    break
            if not used:
                result.append(shape)
        return result

    def deleteUnusedIntermediateShapes(self, *, fast=False):
        """直下の未使用中間Shapeだけを削除し、自身を返す。

        getUnusedIntermediateShapes()と同じ判定で、使用中・参照・ロック・
        インスタンス等は残す。Transformや上流の履歴ノードは削除しない。
        Maya標準削除を1回のUndoにまとめ、途中の失敗時は巻き戻す。
        通常モードはUndoが有効な状態で使用する。

        Args:
            fast (bool): TrueはOpenMayaでShapeだけを直接削除し、Undoなし。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: 無効なTransform、または削除失敗。
        """
        _require_bool(fast, "fast")
        shapes = self.getUnusedIntermediateShapes()
        if shapes:
            if fast:
                self._detach_inputs(shape.mnode() for shape in shapes)
                modifier = om2.MDagModifier()
                for shape in shapes:
                    modifier.deleteNode(shape.mnode(), False)
                modifier.doIt()
            else:
                with undoTransaction("mlibTransformDeleteUnusedIntermediateShapes"):
                    # 標準deleteは入力側の生成履歴も削除する場合があるため、
                    # Shapeへの入力だけをUndo可能に外し、上流ノードを保持する。
                    for shape in shapes:
                        for plug in om2.MFnDependencyNode(shape.mnode()).getConnections():
                            for source in plug.connectedTo(True, False):
                                cmds.disconnectAttr(source.name(), plug.name())
                    cmds.delete([shape.getFullName() for shape in shapes])
        return self

    def getShapes(self, intermediates=False):
        """このTransform直下のShapeを取得する。

        Args:
            intermediates (bool): ``True`` の場合は中間Shapeも含める。

        Returns:
            list[Shape]: 条件に一致するShapeのリスト。
        """
        if not self.isValid():
            return []
        # Shape以外の子はラッパーを作る前に除く(子の順と中間Shapeの扱いは同じ)。
        return self._direct_children(True, intermediates, shapes_only=True)

    def replaceShapes(self, source, *, keepSource=False, worldSpace=False):
        """自身のShapeを、sourceの中間でないShapeへ置き換えて自身を返す。

        自身の直下の既存Shape(中間Shapeを含む)を削除し、sourceのShapeを ``cmds.parent(shape=True)`` で
        自身の直下へ移す。自身のtranslate・rotate・scale・pivot・接続・子Transformは変更しない。
        移したShapeは ``<自身の名前>Shape``、2個目以降は ``<自身の名前>Shape<番号>`` へ改名する。
        コントローラーの形状差し替えを想定した操作で、全体を1回のUndoにまとめ、途中で失敗した場合は
        巻き戻す。

        Args:
            source (Transform | Shape | str): 形状の取得元。Transformは直下の中間でないShape全部、
                Shapeはそれ1つを使う。
            keepSource (bool): Trueならsourceを複製して使い、元のノードを変更しない。Falseはsourceの
                Shapeを移動し、Shapeが無くなり子も残らない取得元のTransformを削除する。
            worldSpace (bool): Trueは取得元のTransformのワールド変換を形状へ焼き込み、ワールド空間での
                見た目を保つ。False(既定)はShapeのローカル座標をそのまま使う(``parent -relative -shape``)。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: keepSource・worldSpaceがbool以外、またはsourceがTransform・Shapeでない場合。
            ValueError: sourceが自身・自身のShape・中間Shapeの場合、または使えるShapeが無い場合。
            RuntimeError: 自身・sourceが無効、またはロック・参照等でMayaが変更を拒否した場合。
        """
        _require_bool(keepSource, "keepSource")
        _require_bool(worldSpace, "worldSpace")
        self._require_valid("replace the shapes of")
        source = source if isinstance(source, Node) else Node(source)
        if not source.isValid():
            raise RuntimeError("Cannot replace shapes from an invalid source")
        if isinstance(source, Transform):
            holder = source
            shapes = source.getShapes()
        elif isinstance(source, DagNode) and source._require_mnode().hasFn(om2.MFn.kShape):
            if source.isIntermediateObject():
                raise ValueError("source must not be an intermediate shape")
            holder = source.getParent()
            # DAG 上の Shape は常に親 Transform を持つ。
            assert holder is not None
            shapes = [source]
        else:
            raise TypeError("source must be a Transform or a Shape")
        if holder == self:
            raise ValueError("source must not be the target transform or its shapes")
        if not shapes:
            raise ValueError(f"{source.getName()} has no shapes to use")
        with undoTransaction("mlibTransformReplaceShapes"):
            duplicate = None
            moving = [shape.getFullName() for shape in shapes]
            if keepSource:
                # Shapeだけの複製は親Transformごと作られるため、Transformを複製して同じ位置の子Shapeを使う。
                positions = [holder.getShapes(intermediates=True).index(shape) for shape in shapes]
                duplicate = cmds.duplicate(holder.getFullName(), returnRootsOnly=True)[0]
                duplicate = cmds.ls(duplicate, long=True)[0]
                copies = cmds.listRelatives(duplicate, shapes=True, fullPath=True) or []
                moving = [copies[position] for position in positions]
            old = [shape.getFullName() for shape in self.getShapes(intermediates=True)]
            if old:
                cmds.delete(old)
            target = self.getFullName()
            if worldSpace:
                matrix = list(holder.mpath().inclusiveMatrix())
                temporary = cmds.createNode("transform", name="mlibReplaceShapesTmp#", skipSelect=True)
                temporary = cmds.ls(temporary, long=True)[0]
                # xformの平行移動は現在のUI単位で解釈されるため、内部単位(cm)へ切り替えて渡す。
                with nativeUnits():
                    cmds.xform(temporary, worldSpace=True, matrix=matrix)
                cmds.parent(moving, temporary, shape=True, relative=True)
                temporary = cmds.ls(cmds.parent(temporary, target)[0], long=True)[0]
                # 取得元のワールド変換と自身の逆変換の差分を、Shapeの形状へ焼き込む。
                cmds.makeIdentity(temporary, apply=True, translate=True, rotate=True, scale=True)
                moving = cmds.listRelatives(temporary, shapes=True, fullPath=True) or []
                cmds.parent(moving, target, shape=True, relative=True)
                cmds.delete(temporary)
            else:
                cmds.parent(moving, target, shape=True, relative=True)
            if duplicate is not None:
                cmds.delete(duplicate)
            elif (isinstance(holder, Transform) and holder.isValid()
                    and not cmds.listRelatives(holder.getFullName(), children=True)):
                cmds.delete(holder.getFullName())
            leaf = self.getFullName().rsplit("|", 1)[-1]
            for position, shape in enumerate(self.getShapes(intermediates=True)):
                cmds.rename(shape.getFullName(), leaf + ("Shape" if position == 0 else "Shape#"))
        return self

    def getShape(self, index=0, intermediates=False):
        """指定位置のShapeを取得する。

        Args:
            index (int): Shapeの番号。既定0。
            intermediates (bool): ``True`` の場合は中間Shapeも含める。

        Returns:
            Shape | None: 指定位置のShape。範囲外ではNone。
        """
        shapes = self.getShapes(intermediates=intermediates)
        try:
            return shapes[index]
        except IndexError:
            return None

    def getTransform(self):
        """Transform自身を取得する。

        Returns:
            Transform: 自身。
        """
        return self

    def setParent(self, parent=None, relative=False, add=False, *, fast=False):
        """Transformの親を変更する。

        Args:
            parent (Node | str | om2.MObject | om2.MDagPath | None): 新しい親。None はワールド直下。
                ``Node(parent)`` で解決できる型(Plug・Component は所有ノード)を受け付ける。
            relative (bool): True は親変更前のローカル変換を保持する。既定 False は Maya の既定動作
                (ワールド姿勢を保つ)。
            add (bool): True は既存の親を維持して追加の親を設定する。parent が None の場合は渡されない。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。Joint・インスタンス・親の追加は未対応
                (NotImplementedError)。通常経路の Joint は cmds.parent に従い、relative=False の
                ときだけ親 joint の scale を inverseScale へ接続する(relative=True では接続しない。
                Maya の仕様)。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: fastがbool以外、または fast で parent が Transform 以外の場合。
            RuntimeError: 自身が無効、parent が自身または自身の子孫(fast も同じ)、または fast で
                ロック・参照により変更できない場合。
            NotImplementedError: fast で Joint・インスタンス・add=True を指定した場合。
        """
        with _edit_context("mlibTransformSetParent", fast):
            self._require_valid("parent")
            if fast:
                return self._set_parent_fast(parent, relative, add)
            if parent is None:
                if self.getParent() is None and not self.mpath().isInstanced():
                    return self
                cmds.parent(self.getFullName(), world=True, relative=relative)
            else:
                target = parent if isinstance(parent, Node) else Node(parent)
                if isinstance(target, Transform):
                    self._require_not_own_descendant(target)
                parent_name = target.getFullName()
                # 古いMayaでは同じ親への再parentがエラーになる。
                # add=Trueはインスタンス操作なのでMayaの判定に委ねる。
                current = self.getParent()
                if (not add and not self.mpath().isInstanced() and current is not None
                        and current.mpath().fullPathName() == parent_name):
                    return self
                cmds.parent(self.getFullName(), parent_name, relative=relative, add=add)
            return self

    def matchTransform(self, target, position=True, rotation=True, scale=True, pivots=False):
        """自身の変換を指定Transformへ合わせる。選択状態は使用しない。

        maya.cmds.matchTransformと同じ空間・joint・ピボット処理を使用し、Undo有効時に
        一つのチャンクへ記録する。fast引数は持たない。
        shearの一致やマトリクス全体のコピーは保証しない。

        Args:
            target (Transform | str | om2.MObject | om2.MDagPath): 合わせ先のTransformまたはjoint。
                mlib.nodes.Node._resolve_input が受け付ける型(Plug は所有ノード)を指定できる。
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
        """

        with undoChunk("mlibTransformMatchTransform"):
            target = Node._resolve_input(target)
            if not isinstance(target, Transform):
                raise TypeError("Target must be a transform or joint")
            if any((position, rotation, scale, pivots)):
                cmds.matchTransform(self.getFullName(), target.getFullName(), position=position,
                                    rotation=rotation, scale=scale, pivots=pivots)
            return self

    def mirrorTransform(self, axis="x", worldSpace=False, pivot=(0.0, 0.0, 0.0), *, fast=False):
        """位置と向きを指定空間でビヘイビアミラーする。

        Matrix.mirrorと同じ回転規約で、負スケールによる形状反転ではない。
        Shapeの頂点・CVは編集しない。子孫は通常の親変換として追従する。
        指定空間のスケール・シアーを保つが、親に非一様スケールがある場合は
        ローカルのスケール・シアーが変わる場合がある。

        Args:
            axis (str | int): 反転する軸 ``"x"``・``"y"``・``"z"``、またはミラー面 ``"YZ"``・``"XZ"``・``"XY"``
                (x⇔YZ、y⇔XZ、z⇔XY。文字の順序・大文字小文字は問わない)、または0/1/2。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            pivot (Iterable[float]): 指定空間の中心。内部距離単位cm。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: fastがbool以外、またはaxisが文字列・int以外の場合。
            ValueError: axis・pivotが不正、特異な親マトリクス、未対応のピボット/rotateAxisの場合。
            RuntimeError: ロックや入力接続で更新できない場合。

        Note:
            setMatrix() と同じ制約があり、非ゼロのピボット・
            TransformのrotateAxisは更新前に拒否する。
        """
        with _edit_context("mlibTransformMirrorTransform", fast):
            ws = _world_space(worldSpace)
            from ..util import mirrorArguments
            _require_bool(ws, "worldSpace")
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
            if not self._require_mnode().hasFn(om2.MFn.kJoint):
                attributes.append("rotateAxis")
            if any(any(self.getPlug(attr).get()) for attr in attributes):
                raise ValueError("mirrorTransform does not support nonzero pivots or transform rotateAxis")
            world = self.getMatrix(worldSpace=True)
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

    @_transform_argument_hints
    def getMatrix(self, worldSpace=False, p=False, inv=False):
        """指定空間の評価済みマトリクスを取得する。

        p=Falseのローカル値は ``matrix`` アトリビュート、ワールド値は保持パスの
        inclusiveMatrixを使う。offsetParentMatrixはローカル値に含まれず、ワールド値に含まれる。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            p (bool): Trueは親側のマトリクス。worldSpace=Trueは保持パスのexclusiveMatrix、
                Falseは親パスのinclusiveMatrix * exclusiveMatrixInverseで求める。
            inv (bool): Trueは選んだマトリクスの逆マトリクス。

        Returns:
            Matrix: 呼出し時点のマトリクスの独立した複製。

        Raises:
            RuntimeError: ノードまたは保持するDAGパスが無効な場合。
        """
        ws = _world_space(worldSpace)
        self._require_valid("get the matrix of")
        path = self.mpath()
        if ws:
            matrix = path.exclusiveMatrix() if p else path.inclusiveMatrix()
        elif p:
            parent = om2.MDagPath(path).pop()
            matrix = parent.inclusiveMatrix() * parent.exclusiveMatrixInverse()
        else:
            plug = om2.MPlug(self._require_mnode(), _transform_attribute("matrix"))
            matrix = om2.MFnMatrixData(plug.asMObject()).matrix()
        return Matrix._wrap(matrix.inverse() if inv else matrix)

    @_transform_argument_hints
    def setMatrix(self, matrix, worldSpace=False, safe=False, get=False, *, fast=False):
        """マトリクスを分解し、translate・rotate・scale・shearのうち値が変わるものへ設定する。

        ピボット・rotateAxis・jointOrient・offsetParentMatrixは変更しない。
        スケールの符号とEulerの等価解は現在のチャンネル値を基準に選ぶ。
        分解した書込み値が現在のチャンネル値(距離cm・角度radの内部値)と完全に一致する
        チャンネルは書き込まない。書き込まないチャンネルはロック・接続されていても例外にせず、
        attributeChangedの通知とUndoの記録も書き込んだチャンネルだけになる(通常・fast・safe共通)。
        safeで書けない成分を残した結果、入力マトリクスと一致しない場合がある。

        Args:
            matrix (Matrix | sequence): 適用するマトリクス。
            worldSpace (bool): Trueはワールドマトリクスを保持パスのexclusiveMatrixInverseで
                ローカルへ変換する。既定Falseは ``matrix`` アトリビュートと同じ空間。
            safe (bool): 書けない成分を保持し、書ける成分だけを更新する。
            get (bool): Trueは書き込まず、ローカルの設定予定値を返す。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform | dict[str, Translate | EulerRotate | Scale | Shear]: 通常は自身。
                get=Trueはtranslate・rotate・scale・shearの辞書(距離cm・角度rad)。
                safe/fastによらず計算だけ行い、書込み可否やsafe適用後の結果は検証しない。

        Raises:
            TypeError: fastがbool以外、または ``space=``・``ws=`` を指定した場合(``worldSpace=True`` を案内する)。
            ValueError: マトリクスが不正・分解不能、またはワールド指定時に親側のマトリクスが反転不能の場合。
            RuntimeError: ノードが無効、またはMayaが書込みを拒否した場合(ロック・入力接続された成分と
                ``safe=True`` を案内する)。
        """
        with _edit_context("mlibTransformSetMatrix", fast):
            local_matrix = self._local_matrix(matrix, _world_space(worldSpace))
            if safe or get:
                values = self._matrix_channel_values(local_matrix)
                if get:
                    return values
                self._apply_channel_values(values, safe=True, fast=fast)
            else:
                self._apply_local_matrix(local_matrix, fast=fast)
            return self

    @_transform_argument_hints
    def getTranslation(self, worldSpace=False, at=2):
        """基準位置を取得する。既定は回転ピボットの位置。

        既定の ``at=2`` は回転ピボットの位置(Maya の Local Axis 表示やコンストレイントがノードの
        位置とする基準)で、translate チャンネルの値ではない。translate チャンネルの値は
        ``node.t.get()``(または ``node.getPlug("translate").get()``)で取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseは親側の空間で表す位置。
                getPivotのオブジェクト空間とは異なる。
            at (int): 0以下=親原点、1=translate、2=回転ピボット(既定)、
                3=スケールピボット、4以上=マトリクス原点。

        Returns:
            Translate: ノードと独立したcm単位の位置。既定at=2はtranslateチャンネル値ではない。
        """
        ws = _world_space(worldSpace)
        if at >= 3:
            matrix = self.getMatrix(worldSpace=ws)
            if at >= 4:
                return matrix.translate
            point = om2.MPoint(self._static_value("scalePivot")) * matrix
        elif at < 1:
            point = om2.MPoint()
            if ws:
                point *= self.mpath().exclusiveMatrix()
        else:
            value = om2.MVector(self._static_value("translate"))
            if at >= 2:
                offset = om2.MVector(self._static_value("rotatePivot"))
                offset += om2.MVector(self._static_value("rotatePivotTranslate"))
                inv_scale = self._inverse_scale_values()
                value += om2.MVector(*(offset[i] / inv_scale[i] for i in range(3)))
            point = om2.MPoint(value)
            if ws:
                point *= self.mpath().exclusiveMatrix()
        return Translate(point.x, point.y, point.z)

    @_transform_argument_hints
    def setTranslation(self, value, worldSpace=False, at=2, safe=False, get=False, *, fast=False):
        """指定基準の位置へ移動する。ピボットや回転は変更しない。

        既定の ``at=2`` は回転ピボットの位置(Maya の Local Axis 表示やコンストレイントがノードの
        位置とする基準)を value へ合わせるよう translate を書き換える。translate チャンネルへ
        値をそのまま書く場合は ``node.t.set((x, y, z))`` を使う。

        at=0以下は位置の絶対設定ではなく、親空間へ変換した入力から現在のtranslateを
        引いた値を設定する。例えば現在2・入力5ならtranslateは3になる。

        Args:
            value (Iterable[float]): cm単位の位置。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            at (int): getTranslationと同じ基準。既定2(回転ピボット)。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずローカルtranslateの設定予定値だけを返す。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform | list[float]: 自身。get=Trueはcm単位の独立したXYZ3成分のlist。
                safe指定時も書込み可否を反映した最終結果の予測ではない。

        Raises:
            TypeError: worldSpaceがbool以外、``space=``・``ws=`` を指定した場合(``worldSpace=True`` を
                案内する)、または ``setTranslation(1, 2, 3)`` のように成分を分けて渡した場合。
            RuntimeError: ノードが無効、またはロック・入力接続された成分があり書き込めない場合
                (原因の成分と ``safe=True`` を案内する)。
        """
        with _edit_context("mlibTransformSetTranslation", fast):
            ws = _world_space(worldSpace)
            point = om2.MPoint(tuple(value))
            if ws:
                point *= self.mpath().exclusiveMatrixInverse()
            current = om2.MVector(self._static_value("translate"))
            if at < 1:
                result = om2.MVector(point) - current
            else:
                result = current + (om2.MVector(point) - om2.MVector(tuple(self.getTranslation(at=at))))
            if get:
                return list(result)
            self._set_channel_value("translate", result, safe=safe, fast=fast)
            return self

    @_transform_argument_hints
    def getRotate(self, worldSpace=False, *, order=None):
        """選択空間のマトリクスの回転を Euler 回転として取得する。

        rotateAxisと、JointではjointOrientを含む回転を返す。スケール符号は現在のチャンネルを基準にする。

        回転順序と等価解の選び方は二段の規則に従う。

        * ``order`` を省略、またはノードの rotateOrder と同じ順序を指定した場合は、ノードの
          rotateOrder で表し、Euler の等価解は Transform では現在の rotate チャンネル、
          Joint ではゼロ回転に最も近いものを選ぶ(``setRotate`` の往復でチャンネル値が保たれる)。
        * それ以外の順序を指定した場合は、クォータニオンを ``asEulerRotation().reorder(order)``
          で素直に分解した値(等価解の選択なし)を返す。``order=0`` (xyz)は旧 ``getEuler`` と同じ値。

        Args:
            worldSpace (bool): Trueはワールド、既定Falseはローカルマトリクスの回転。
            order (int | str | None): 戻り値の回転順序。``"xyz"`` などの名前、または om2 の番号
                (``MEulerRotation.kXYZ`` 〜 ``kZYX``、Maya の rotateOrder と同じ 0〜5)。
                None はノードの rotateOrder。

        Returns:
            EulerRotate: 内部がradの独立した回転値。``order`` の回転順序(省略時はノードの
                rotateOrder)。度の3成分は ``getRotate().asDegrees()`` で取得する。

        Raises:
            ValueError: worldSpace が bool 以外、order が未対応、またはマトリクスを分解できない場合。
                いずれかのスケール軸の長さが 1e-10 以下(Maya は scale 0 を 1e-12 として評価する)の
                ときも含む。
        """
        ws = _world_space(worldSpace)
        if order is not None:
            order = orderIndex(order)
        matrix = self.getMatrix(worldSpace=ws)
        for row in range(3):
            if math.sqrt(sum(matrix[row, col] ** 2 for col in range(3))) <= _NEAR_ZERO_AXIS:
                raise ValueError("Cannot decompose a matrix with a zero scale axis")
        _, quaternion, _, _, reference = self._decompose_like_channels(matrix)
        if order is None or order == reference.order:
            return EulerRotate._wrap(_closest_euler(quaternion, self._rotate_reference(reference)))
        return EulerRotate._wrap(quaternion.asEulerRotation().reorder(order))

    @_transform_argument_hints
    def setRotate(self, value, worldSpace=False, safe=False, get=False, *, unit="deg", fast=False):
        """選択空間の回転を設定する。書込むrotateは現在値に最も近い等価解を使う。

        3成分はノードのrotateOrderで解釈し、EulerRotateは値自身の回転順序を使う。
        rotateAxisとJointのjointOrientを保ち、マトリクス経由でチャンネル値を計算する。
        書き込むのはrotateチャンネルだけで、translate・scale・shearは書き込まない
        (ロック・接続されていても例外にせず、通知・Undoの記録もrotateだけ。通常・fast・safe共通)。
        ピボットが0でない場合は、cmds.setAttrでrotateを設定したときと同じくピボットの周りに回る。

        Args:
            value (Iterable[float] | EulerRotate | Quaternion): 回転値。EulerRotate/Quaternionは
                対応するOpenMaya基底型も受理する。書込みはノードのrotateOrderに揃える。
            worldSpace (bool): Trueはワールド、既定Falseはローカルマトリクスの回転。
            safe (bool): 書けない成分を保持する。目標回転との一致は保証しない。
            get (bool): Trueは書き込まず、ローカルrotateの設定予定値を返す。
            unit (str): 数値3成分とget=Trueの戻り値の角度の単位。既定 ``"deg"`` は度、``"rad"`` は
                ラジアン(``"degree"`` / ``"radians"`` 等の別名も可)。EulerRotate/Quaternionは自身の
                単位(rad)を持つため、unitに関係なく換算しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform | list[float]: 通常は自身。get=Trueはunitの単位(既定は度)の独立したXYZ3成分のlist。
                safe適用後の最終結果を予測する値ではない。

        Raises:
            TypeError: fastがbool以外、unitが文字列以外、``space=``・``ws=`` を指定した場合
                (``worldSpace=True`` を案内する)、または成分を分けて渡した場合。
            ValueError: unitが未対応の単位名、値が3成分でない、マトリクスが分解不能、
                または必要な親マトリクスが反転不能の場合。
            RuntimeError: ノードが無効、またはアトリビュートを書き込めない場合(ロック・入力接続された
                成分と ``safe=True`` を案内する)。
        """
        with _edit_context("mlibTransformSetRotate", fast):
            ws = _world_space(worldSpace)
            angle_unit = _angle_unit(unit)
            # 既定値 "deg" を持つため、unit=None でも None にならない。
            assert angle_unit is not None
            if not isinstance(value, (om2.MEulerRotation, om2.MQuaternion)):
                self._require_valid("set")
                x, y, z = value
                x, y, z = _to_radians(x, angle_unit), _to_radians(y, angle_unit), _to_radians(z, angle_unit)
                # cmds.xform と同じく、3成分はノードの rotateOrder の値として解釈する。
                value = EulerRotate(x, y, z, self._rotate_order())
            matrix = self._replace_components(self.getMatrix(worldSpace=ws), rotate=value)
            rotation = self._matrix_channel_values(self._local_matrix(matrix, ws))["rotate"]
            if get:
                return [_from_radians(component, angle_unit) for component in rotation]
            self._set_channel_value("rotate", rotation, safe=safe, fast=fast)
            return self

    def getScale(self, worldSpace=False):
        """指定空間のスケール値を取得する。

        Args:
            worldSpace (bool): ワールド指定。Falseはscaleチャンネル。

        Returns:
            Scale: 独立した無次元のXYZ3成分。ローカルではSSCを除くチャンネル値、
                ワールドではAPI規約の分解値で、チャンネルの符号と一致するとは限らない。
        """
        if _world_space(worldSpace):
            return Scale(*om2.MTransformationMatrix(self.getMatrix(worldSpace=True)).scale(MSpace.kTransform))
        return self.getPlug("scale").get()

    @_transform_argument_hints
    def setScale(self, value, worldSpace=False, safe=False, get=False, *, fast=False):
        """scaleチャンネルだけを設定する。

        ワールド指定では要求スケールをローカル設定値へ変換する。
        変換後も書込み先はscaleだけで、rotateやshearは変更しない。

        Args:
            value (Iterable[float]): 無次元のXYZスケール3成分。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずチャンネル値を返す。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform | list[float]: 自身。get=Trueは独立したローカルXYZ設定値のlist。
        """
        _require_bool(fast, "fast")
        values = self._scale_channel_value(value, _world_space(worldSpace))
        if get:
            return values
        self._set_channel_value("scale", values, safe=safe, fast=fast)
        return self

    def getShear(self, worldSpace=False):
        """指定空間のシアー値を取得する。

        Args:
            worldSpace (bool): ワールド指定。Falseはshearチャンネル。

        Returns:
            Shear: 独立した無次元のXY・XZ・YZ3成分。
                ローカルはチャンネル値、ワールドはAPI規約のマトリクス分解値。
        """
        if _world_space(worldSpace):
            return Shear(*om2.MTransformationMatrix(self.getMatrix(worldSpace=True)).shear(MSpace.kTransform))
        return self.getPlug("shear").get()

    def setShear(self, value, worldSpace=False, safe=False, get=False, *, fast=False):
        """shearチャンネルだけを設定する。

        ワールド指定では要求シアーをローカル設定値へ変換する。
        変換後も書込み先はshearだけで、rotateやscaleは変更しない。

        Args:
            value (Iterable[float]): 無次元のXY・XZ・YZシアー3成分。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずチャンネル値を返す。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform | list[float]: 自身。get=Trueは独立したローカルXY・XZ・YZ設定値のlist。
        """
        _require_bool(fast, "fast")
        values = self._scale_channel_value(value, _world_space(worldSpace), shear=True)
        if get:
            return values
        self._set_channel_value("shear", values, safe=safe, fast=fast)
        return self

    def getQuaternion(self, worldSpace=False, ra=False, r=True, jo=True):
        """回転成分を選んで取得する。既定ではrotateAxisを含めない。

        ローカル空間ではrotateAxis・rotate・JointのjointOrientの順に、選んだ回転を合成する。
        ワールド空間では保持パスのマトリクスから求め、除外する回転成分を取り除く。
        ra/r/joの許容組合せはsetQuaternionと同一ではない。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ra (bool): rotateAxisを含める。
            r (bool): rotateを含める。
            jo (bool): jointOrientを含める。

        Returns:
            Quaternion: ノードと独立した、指定成分の合成回転。成分順はXYZW。

        Raises:
            ValueError: 回転成分と空間指定が未対応の組合せの場合。
        """
        ws = _world_space(worldSpace)
        joint = self._require_mnode().hasFn(om2.MFn.kJoint)
        if ws:
            if (ra and not (r and jo)) or (not ra and r and not jo):
                raise ValueError("Unsupported rotation component combination")
            matrix = self.getMatrix(worldSpace=True, p=not (ra or r or (jo and joint)))
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

    def setQuaternion(self, value, worldSpace=False, ra=False, r=True, jo=True, safe=False, get=False, *,
        unit="deg", fast=False):
        """回転成分の指定に従いrotate・jointOrient・rotateAxisを設定する。

        受理する組合せでは、r=Trueはrotate、r=FalseかつJointでjo=TrueはjointOrient、
        それ以外のr=FalseはrotateAxisだけを書き込む。ra/r/joの許容組合せは
        getQuaternionと同一ではない。

        Args:
            value (Quaternion | om2.MQuaternion | Iterable[float]): xyzwの回転。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ra (bool): 入力にrotateAxisを含む。
            r (bool): rotateを更新する。FalseはjointOrientまたはrotateAxis。
            jo (bool): jointOrientを含む。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まず計算したEuler成分を返す。
            unit (str): get=Trueの戻り値の角度の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
                (``"degree"`` 等の別名も可)。書込みと入力のクォータニオンには影響しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform | list[float]: get=Falseでは自身。get=Trueでは書込み先のEuler3成分を
                unitの単位(既定は度)のlistとして返し、safe/fastの指定によらずシーンは変更しない。
                入力のQuaternionや、XYZWの4成分を返す操作ではない。
                rotateの設定予定値はノードのrotateOrder、他の書込み先はXYZ順序。

        Raises:
            TypeError: unitが文字列以外の場合。
            ValueError: 回転成分と空間指定が未対応の組合せ、またはunitが未対応の単位名の場合。
        """
        with _edit_context("mlibTransformSetQuaternion", fast):
            angle_unit = _angle_unit(unit)
            # 既定値 "deg" を持つため、unit=None でも None にならない。
            assert angle_unit is not None
            name, rotation = self._quaternion_channel_values(value, _world_space(worldSpace), ra, r, jo)
            if get:
                return [_from_radians(component, angle_unit) for component in rotation]
            self._set_channel_value(name, rotation, safe=safe, fast=fast)
            return self

    def makeIdentity(self, *, apply=_UNSET, a=_UNSET, jointOrient=_UNSET, jo=_UNSET, normal=_UNSET, n=_UNSET,
        preserveNormals=_UNSET, pn=_UNSET, rotate=_UNSET, r=_UNSET, scale=_UNSET, s=_UNSET, translate=_UNSET,
        t=_UNSET, query=_UNSET, q=_UNSET, edit=_UNSET, e=_UNSET, **kwargs):
        """自身を対象にcmds.makeIdentityを実行する。

        省略したフラグはMayaの既定に従う。通常更新をUndo有効時にまとめ、途中失敗の変更は戻さない。

        Args:
            **kwargs (object): MayaのmakeIdentityへ渡す追加フラグ。
            apply (bool): Mayaのapplyフラグ。省略時はMayaの既定に従う。
            a (bool): applyの別名。同時指定は不可。
            jointOrient (bool): MayaのjointOrientフラグ。省略時はMayaの既定に従う。
            jo (bool): jointOrientの別名。同時指定は不可。
            normal (int): Mayaのnormalフラグ。省略時はMayaの既定に従う。
            n (int): normalの別名。同時指定は不可。
            preserveNormals (bool): MayaのpreserveNormalsフラグ。省略時はMayaの既定に従う。
            pn (bool): preserveNormalsの別名。同時指定は不可。
            rotate (bool): Mayaのrotateフラグ。省略時はMayaの既定に従う。
            r (bool): rotateの別名。同時指定は不可。
            scale (bool): Mayaのscaleフラグ。省略時はMayaの既定に従う。
            s (bool): scaleの別名。同時指定は不可。
            translate (bool): Mayaのtranslateフラグ。省略時はMayaの既定に従う。
            t (bool): translateの別名。同時指定は不可。
            query (bool): Mayaのqueryフラグ。省略時はMayaの既定に従う。
            q (bool): queryの別名。同時指定は不可。
            edit (bool): Mayaのeditフラグ。省略時はMayaの既定に従う。
            e (bool): editの別名。同時指定は不可。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: 長短フラグを同時指定した場合。
            RuntimeError: ノードが無効、または Maya が拒否した場合。
        """
        _merge_flags(kwargs, (
            (apply, a, "apply", "a"),
            (jointOrient, jo, "jointOrient", "jo"),
            (normal, n, "normal", "n"),
            (preserveNormals, pn, "preserveNormals", "pn"),
            (rotate, r, "rotate", "r"),
            (scale, s, "scale", "s"),
            (translate, t, "translate", "t"),
            (query, q, "query", "q"),
            (edit, e, "edit", "e"),
        ))
        with undoChunk("mlibTransformMakeIdentity"):
            self._require_valid("freeze transform of")
            cmds.makeIdentity(self.getFullName(), **kwargs)
            return self

    def getClosestAxisToVector(self, refVector, includeNegative=True):
        """自身のローカル軸のうち、ワールド空間の方向ベクトルに最も近いものを求める。

        各ローカル軸をワールドマトリクス(回転・スケールのみ、平行移動は無視)で変換し、
        正規化した上で refVector との内積が最大のものを選ぶ。

        Args:
            refVector (Vector | Iterable[float]): 比較対象のワールド空間方向ベクトル。
            includeNegative (bool): True の場合、負方向の軸(-x/-y/-z)も候補に含める。

        Returns:
            str: 最も近い軸名("x"、"y"、"z"。includeNegative が True なら
                "-x"、"-y"、"-z" も返り得る)。

        Raises:
            ValueError: refVector またはいずれかのローカル軸がワールド変換後にゼロベクトルになる場合。
            RuntimeError: ノードが無効な場合。
        """
        self._require_valid("evaluate axes of")
        if not isinstance(refVector, Vector):
            refVector = Vector(*refVector)
        refVector = refVector.unit()
        matrix = self.getMatrix(worldSpace=True)
        axes = {"x": Vector(1.0, 0.0, 0.0), "y": Vector(0.0, 1.0, 0.0), "z": Vector(0.0, 0.0, 1.0)}
        if includeNegative:
            axes.update({f"-{name}": axis * -1.0 for name, axis in axes.items()})
        best_axis = None
        best_dot = None
        for name, axis in axes.items():
            world_axis = matrix.transformVector(axis).unit()
            dot = world_axis.dot(refVector)
            if best_dot is None or dot > best_dot:
                best_dot = dot
                best_axis = name
        return best_axis

    def setLimits(self, *, unit="deg", **limits):
        """移動・回転・スケールの制限を ``cmds.transformLimits`` で設定する。

        ``setLimits(translateX=(0, 10), rotateZ=(-45, 90), scaleY=(None, 2))`` のように、チャンネル名
        (``translateX``〜``scaleZ`` のロング名)へ ``(最小, 最大)`` を渡す。片側の ``None`` はその側の制限を
        無効にし(値は変えない)、値全体の ``None`` は両側を無効にする。指定しないチャンネルは変更しない。
        距離はcm、角度は ``unit`` の単位(既定は度)で、Mayaの現在のUI単位へ換算して渡す。
        全指定を検証してから1回の ``cmds.transformLimits`` で設定し、Undo有効時に1回のUndoで戻る。
        fast引数は持たない(OpenMayaで制限のアトリビュートを書いても速くならない)。

        Args:
            unit (str): 回転の数値の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン(別名も可)。
            **limits (tuple[float | None, float | None] | None): チャンネル名ごとの ``(最小, 最大)``。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: チャンネル名が未対応、値が2要素の列・None以外、要素が数値・None以外、
                またはunitが文字列以外の場合。
            ValueError: unitが未対応の単位名の場合。
            RuntimeError: ノードが無効、またはMayaが設定を拒否した場合(最小が最大より大きい等)。
        """
        angle_unit = _angle_unit(unit)
        unknown = sorted(set(limits) - set(_LIMIT_FLAGS))
        if unknown:
            raise TypeError("Unsupported limit channel(s): " + ", ".join(unknown)
                            + " (use translateX..scaleZ)")
        self._require_valid("set limits of")
        name = self.getFullName()
        flags = {}
        for channel, value in limits.items():
            flag, enable_flag, kind = _LIMIT_FLAGS[channel]
            if value is None:
                value = (None, None)
            if isinstance(value, (str, bytes)) or not isinstance(value, (tuple, list)) or len(value) != 2:
                raise TypeError(f"{channel} limit must be a (min, max) pair or None: {value!r}")
            current = None
            sides = []
            for index, side in enumerate(value):
                if side is None:
                    if current is None:
                        query_flags: Dict[str, Any] = {flag: True}
                        current = cmds.transformLimits(name, query=True, **query_flags)
                    side = current[index]
                    if kind == "distance":
                        # 照会は移動だけcm(内部単位)で返り、設定はUI単位で受け取る。
                        side = om2.MDistance(side, om2.MDistance.kCentimeters).asUnits(om2.MDistance.uiUnit())
                    sides.append(side)
                    continue
                if isinstance(side, bool) or not isinstance(side, numbers.Real):
                    raise TypeError(f"{channel} limit values must be numbers or None: {value!r}")
                if kind == "angle":
                    side = om2.MAngle(side, om2.MAngle.kDegrees if angle_unit == "deg"
                                      else om2.MAngle.kRadians).asUnits(om2.MAngle.uiUnit())
                elif kind == "distance":
                    side = om2.MDistance(side, om2.MDistance.kCentimeters).asUnits(om2.MDistance.uiUnit())
                sides.append(float(side))
            flags[flag] = tuple(sides)
            flags[enable_flag] = (value[0] is not None, value[1] is not None)
        if flags:
            with undoChunk("mlibTransformSetLimits"):
                cmds.transformLimits(name, **flags)
        return self

    def _color_targets(self):
        """:meth:`setColor`・:meth:`getColor` の対象を返す。

        Returns:
            list[DagNode]: 直下の中間でないShape。Shapeが無ければ自身。
        """
        self._require_valid("set the color of")
        return self.getShapes() or [self]

    def _local_matrix(self, matrix, ws):
        """setMatrixの入力を検証し、ローカル空間のマトリクスへ変換する。シーンは更新しない。

        Args:
            matrix (Matrix | sequence): 適用するマトリクス。
            ws (bool): 検証済みのワールド空間指定。Trueは保持パスのexclusiveMatrixInverseを掛ける。

        Returns:
            Matrix: ローカル空間のマトリクス。

        Raises:
            ValueError: マトリクスが不正、またはワールド指定時の親が反転不能な場合。
            RuntimeError: ノードが無効な場合。
        """
        if not isinstance(matrix, Matrix):
            matrix = Matrix(matrix)
        self._require_valid("set")
        if not ws:
            return matrix
        path = self.mpath()
        # Mayaの逆変換取得だけでは特異な親を拒否しないため、書込み前に検査する。
        if path.exclusiveMatrix().isSingular():
            raise ValueError("Cannot apply a world matrix with a singular parent matrix")
        return matrix * Matrix._wrap(path.exclusiveMatrixInverse())

    @staticmethod
    def _detach_inputs(objects):
        """限定削除の上流ノードが孤立履歴として連鎖削除されることを防ぐ。

        Args:
            objects (Iterable[om2.MObject]): 削除予定のノード。

        Returns:
            None: 値を返さない。

        Note:
            直接API更新なのでUndoへ記録しない。削除modifierとは別に先に確定する。
        """
        modifier = om2.MDGModifier()
        connected = False
        for obj in objects:
            for plug in om2.MFnDependencyNode(obj).getConnections():
                for source in plug.connectedTo(True, False):
                    modifier.disconnect(source, plug)
                    connected = True
        if connected:
            modifier.doIt()

    def _set_parent_fast(self, parent, relative, add, *, validate_only=False):
        """対応するTransformだけを検証してAPIで再親付けする。

        Args:
            parent (Node | None): 新しい親。Noneはワールド。
            relative (bool): ローカル変換を保持するか。
            add (bool): 既存の親に追加するか。Trueは未対応。
            validate_only (bool): Trueは全件事前検証用。DAGを変更しない。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: 参照・ロック・循環・特異マトリクスにより変更できない場合。
            NotImplementedError: Joint・インスタンス・親追加の場合。
        """
        target = None if parent is None else Node._resolve_input(parent)
        if target is not None and not isinstance(target, Transform):
            raise TypeError("Parent must be a transform")
        if target is not None:
            self._require_not_own_descendant(target)
        path = self.mpath()
        if (self._require_mnode().hasFn(om2.MFn.kJoint) or path.isInstanced()
                or (target is not None and target.mpath().isInstanced()) or add):
            raise NotImplementedError("fast setParent does not support joints, instances or add=True")
        require_editable(self._require_mnode())
        if target is not None:
            require_editable(target._require_mnode())
        current = self.getParent()
        if (current is None and target is None) or (
                current is not None and target is not None and current.mnode() == target.mnode()):
            return self
        world = None if relative else self.getMatrix(worldSpace=True)
        if world is not None:
            parent_matrix = Matrix() if target is None else target.getMatrix(worldSpace=True)
            opm = self.getPlug("offsetParentMatrix").get()
            if abs(parent_matrix.det4x4()) <= 1e-12 or abs(opm.det4x4()) <= 1e-12:
                raise RuntimeError("Cannot preserve world transform with a singular parent or offset matrix")
            for name in ("translate", "rotate", "scale", "shear"):
                plug = self.getPlug(name).mplug()
                require_writable(plug)
                for index in range(plug.numChildren()):
                    require_writable(plug.child(index))
        if validate_only:
            return self
        modifier = om2.MDagModifier()
        new_parent = om2.MObject.kNullObj if target is None else target._require_mnode()
        modifier.reparentNode(self._require_mnode(), new_parent)
        modifier.doIt()
        # 自分の操作で変えたパスだけ再束縛し、無関係なインスタンスへ切り替えない。
        self._dag_path = om2.MDagPath.getAPathTo(self.mnode())
        if world is not None:
            self.setMatrix(world, worldSpace=True, fast=True)
        return self

    def _require_not_own_descendant(self, target):
        """親にしようとするノードが、自身または自身の子孫でないことを確かめる。

        Mayaはこの場合 ``Not enough objects or values.`` などの原因が分かりにくいエラーになるため、
        変更の前に分かる文言で拒否する。インスタンスでも判定できるよう、target の全パスの祖先を調べる。

        Args:
            target (Transform): 新しい親。

        Raises:
            RuntimeError: target が自身、または自身の子孫の場合。
        """
        own = self._require_mnode()
        for path in om2.MDagPath.getAllPathsTo(target._require_mnode()):
            while path.length():
                if path.node() == own:
                    raise RuntimeError(
                        "Cannot parent a node under itself or one of its descendants: "
                        f"{self.getFullName()} -> {target.getFullName()}")
                path.pop()

    def _static_value(self, name):
        """ノード型に組み込みの数値アトリビュートの内部単位の値を、Plugラッパーを作らずに読む。

        ``getPlug(name).get()`` と同じ読取関数(距離cm・角度rad)をMPlugへ直接適用する。
        コンパウンドアトリビュートは子の値のtuple、単一の値はその値を返す。計算の途中で何度も読む
        translate・ピボット等のために使い、値はキャッシュしない。ノードが無効な場合と
        読取関数を持たない型は、従来どおり ``getPlug(name).get()`` の結果・例外に委ねる。

        Args:
            name (str): 静的アトリビュートのロング名。

        Returns:
            tuple[float, ...] | object: コンパウンドアトリビュートなら子の値のtuple、それ以外は値。
        """
        if not self.isValid():
            # 無効なノードでは、従来と同じgetPlugの例外を送出する。
            return self.getPlug(name).get(unit="rad")
        plug = self._dependency_fn().findPlug(name, False)
        targets = [plug.child(index) for index in range(plug.numChildren())] if plug.isCompound else [plug]
        values = []
        for target in targets:
            reader = value_reader(target.attribute())
            # value_reader は読取関数か False(cmdsでの読取)を返す。
            if not callable(reader):
                value = self.getPlug(name).get(unit="rad")
                return tuple(value) if plug.isCompound else value
            values.append(reader(target))
        return tuple(values) if plug.isCompound else values[0]

    def _inverse_scale_values(self):
        """jointの有効なinverseScaleを返す。それ以外は単位スケール。"""
        if self._require_mnode().hasFn(om2.MFn.kJoint) and self._static_value("segmentScaleCompensate"):
            return self._static_value("inverseScale")
        return (1.0, 1.0, 1.0)

    def _scale_channel_value(self, value, ws, shear=False):
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
            transform = om2.MTransformationMatrix(self.getMatrix(worldSpace=True))
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
        """回転アトリビュートをQuaternionへ変換する。

        rotateはノードの回転順序、rotateAxis・jointOrient等はXYZで解釈する。

        Args:
            name (str): 回転アトリビュート名。

        Returns:
            om2.MQuaternion: 新しい回転値。
        """
        if name == "jointOrient" and not self._require_mnode().hasFn(om2.MFn.kJoint):
            value = self.getPlug(name).get(unit="rad")
        else:
            # 組み込みの角度アトリビュートは、getPlug(name).get()と同じ読取関数でPlugを作らずに読む。
            value = self._static_value(name)
        order = self._rotate_order() if name == "rotate" else om2.MEulerRotation.kXYZ
        return om2.MEulerRotation(*tuple(value), order).asQuaternion()

    def _rotate_order(self):
        """ノードの rotateOrder を om2 の回転順序の番号として取得する。

        Returns:
            int: 0(xyz)〜5(zyx)。om2.MEulerRotation.kXYZ〜kZYX と同じ番号。
        """
        return om2.MFnTransform(self.mnode()).rotation(om2.MSpace.kTransform).order

    def _require_pivots_writable(self, kinds, preserve):
        """変更するピボットと補償値の全成分が書き込めるか、更新前に検査する。

        Args:
            kinds (Iterable[str]): 検査するピボットの種類(rotate/scale)。
            preserve (bool): Trueは補償値(rotatePivotTranslate等)も検査する。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: いずれかの成分がロック・入力接続・書込み不能の場合。
        """
        for selected in kinds:
            names = [selected + "Pivot"]
            if preserve:
                names.append(selected + "PivotTranslate")
            for name in names:
                plug = self.getPlug(name).mplug()
                require_writable(plug)
                for index in range(plug.numChildren()):
                    require_writable(plug.child(index))

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
        """マトリクスを分解し、スケールの符号の組み合わせを基準のスケールへ揃える。

        om2.MTransformationMatrix の規約(行列式が負なら Z が負)で分解してから、
        :func:`_match_scale_signs` で符号を揃える。基準は scale_reference (指定時)、
        次に現在の scale チャンネル値の順に、行列式の符号と合う最初のもの。これにより
        scale が (-1, 1, 1) のようなミラーのノードでも、取得・設定の往復でチャンネル値の
        符号と回転が保たれ、``setScale`` では要求した符号がそのまま入る。

        Args:
            matrix (Matrix): 分解するマトリクス。
            scale_reference (Iterable[float] | None): 最優先で符号を合わせるスケール
                (``setScale`` で要求した値)。None なら現在の scale チャンネル値だけ。

        Returns:
            tuple: (translate(Translate), quaternion(om2.MQuaternion),
            scale(tuple), shear(tuple), reference(om2.MEulerRotation))。reference は
            現在の rotate チャンネル値で、Euler の解を選ぶ基準に使う。

        Raises:
            ValueError: マトリクスを分解できない場合(いずれかのスケール軸がゼロなど)。
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
        """マトリクスの回転・スケール・シアーの一部を置き換えた新しいマトリクスを返す。

        置き換えない成分は :meth:`_decompose_like_channels` の分解値(スケールの符号を
        現在のチャンネルへ揃えた値)を使う。平行移動はマトリクスの値をそのまま保つ。

        Args:
            matrix (Matrix): 元のマトリクス。
            rotate (Iterable[float] | EulerRotate | Quaternion | None): 新しい回転。
                3成分は XYZ 順序のラジアン。None は現在の値。
            scale (Iterable[float] | None): 新しいスケール。None は現在の値。
            shear (Iterable[float] | None): 新しいシアー。None は現在の値。

        Returns:
            Matrix: 合成し直した新しいマトリクス。

        Raises:
            ValueError: 元のマトリクスを分解できない場合、または入力が不正な場合。
        """
        translate, quaternion, old_scale, old_shear, _ = self._decompose_like_channels(matrix)
        return Matrix(
            translate=translate,
            rotate=quaternion if rotate is None else rotate,
            scale=old_scale if scale is None else scale,
            shear=old_shear if shear is None else shear,
        )

    def _rotate_reference(self, reference):
        """:meth:`getRotate` が Euler の解を選ぶ基準を返す。

        transform ではマトリクスの回転と rotate チャンネルが同じ回転(rotateAxis が 0 の場合)
        なので、現在の rotate チャンネル値をそのまま基準にする。

        Args:
            reference (om2.MEulerRotation): 現在の rotate チャンネル値。

        Returns:
            om2.MEulerRotation: 基準の回転(順序はノードの rotateOrder)。
        """
        return reference

    def _channel_rotate(self, quaternion, reference):
        """ローカルマトリクスの回転を、rotate チャンネルへ書き込む値へ変換する。

        transformではrotateAxisを除いてrotateチャンネルの回転を求める。

        Args:
            quaternion (om2.MQuaternion): ローカルマトリクスの回転。
            reference (om2.MEulerRotation): 現在の rotate チャンネル値。

        Returns:
            om2.MEulerRotation: ノードの rotateOrder で表した、reference に最も近い解。
        """
        return _closest_euler(self._component_quaternion("rotateAxis").inverse() * quaternion, reference)

    def _quaternion_channel_values(self, value, ws, ra, r, jo):
        """回転の指定から書込み先とEuler値だけを求め、シーンは変更しない。

        Args:
            value (om2.MQuaternion | Iterable[float]): 入力回転。
            ws (bool): 検証済みのワールド空間指定。
            ra (bool): 入力へrotateAxisを含めるか。
            r (bool): rotateを更新するか。
            jo (bool): jointOrientを含めるか。

        Returns:
            tuple[str, om2.MEulerRotation]: 書込み先名とrad単位の計算値。
        """
        q = om2.MQuaternion(value) if isinstance(value, om2.MQuaternion) else om2.MQuaternion(*value)
        joint = self._require_mnode().hasFn(om2.MFn.kJoint)
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
            return "rotate", q.asEulerRotation().reorder(self._rotate_order())
        return "jointOrient" if jo else "rotateAxis", q.asEulerRotation()

    def _apply_local_matrix(self, matrix, scale_reference=None, *, fast=False):
        """ローカルマトリクスの各成分をMayaアトリビュートへ適用する。

        マトリクスを1回だけ分解し、平行移動・回転・スケール・シアーのうち現在値と
        異なるものを順に書き込む(:meth:`_apply_channel_values`)。
        分解は om2.MTransformationMatrix の規約に、次の2点の選択を加えたもの。

        * スケールの符号の組み合わせは、行列式の符号が許す限り scale_reference
          (``setScale`` で要求した値)、次に現在の scale チャンネルに揃える
          (:meth:`_decompose_like_channels`)。
        * 回転はノードの rotateOrder で表し、等価な解のうち現在の rotate チャンネル値に
          最も近いものを選ぶ(``om2.MEulerRotation.closestSolution``)。

        同じマトリクスの再適用で、不要なスケール符号や等価なEuler解の変化を避ける。
        計算値は距離cm・角度radで、書込みは共通のPlug処理へ委譲する。
        ピボット・rotateAxis・jointOrient・SSCの補正を含める。

        Args:
            matrix (Matrix): ローカル空間のマトリクス。
            scale_reference (Iterable[float] | None): 最優先で符号を合わせるスケール。
                None なら現在の scale チャンネル値に合わせる。
            fast (bool): Trueなら各チャンネルをOpenMayaで更新する。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: マトリクスを分解できない場合。
            RuntimeError: Maya がアトリビュートの書き込みを拒否した場合。
        """
        self._apply_channel_values(self._matrix_channel_values(matrix, scale_reference), safe=False, fast=fast)

    def _apply_channel_values(self, values, safe=False, *, fast=False):
        """計算済みの内部単位値のうち、現在値と異なるものだけを辞書の保持順に設定する。

        書込み値が現在のチャンネル値(内部単位)と完全に一致するチャンネルは書き込まない。
        書き込まないチャンネルはロック・接続されていても例外にせず、通知・Undoの記録も残らない。

        Args:
            values (dict[str, Iterable[float]]): チャンネル名と設定値。
            safe (bool): 書けない成分を残す。通常時は失敗を伝播する。
            fast (bool): 子のPlugへ渡す更新モード。

        Returns:
            None: 値を返さない。
        """
        for name, value in values.items():
            value = tuple(value)
            if self._channel_equals(name, value):
                continue
            self._set_channel_value(name, value, safe=safe, fast=fast)

    def _channel_equals(self, name, value):
        """内部単位の書込み値が、チャンネルの現在値と完全に一致するかを返す。

        Args:
            name (str): 組み込みの数値アトリビュートのロング名。
            value (tuple | object): 書込み予定の値。コンパウンドアトリビュートは成分のtuple。

        Returns:
            bool: 成分数と各成分が完全に一致すればTrue。読取れない場合はFalse(書込みへ委ねる)。
        """
        try:
            current = self._static_value(name)
        except Exception:  # noqa: BLE001 - 判定できなければ従来どおり書込みの結果に委ねる。
            return False
        if isinstance(value, tuple):
            return isinstance(current, tuple) and len(current) == len(value) and all(
                float(a) == float(b) for a, b in zip(current, value))
        return current == value

    def _set_channel_value(self, name, value, safe=False, *, fast=False):
        """内部単位のチャンネル値を、基底Plug.setへ渡す。

        Double3の回転変換を再実行せず、入力された順序の数値を使う。
        通常更新はMayaに従い、fastは接続済み入力への直接書込みを拒否する。
        参照取得・tuple化の失敗はsafeで抑制しない。

        Args:
            name (str): 設定するチャンネル名。
            value (Iterable[float]): 数値列。距離cm、角度rad。
            safe (bool): Plug.setに対応する書込み失敗を数えるか。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug | int: Plug.setの戻り値。通常はPlug、safe=Trueは失敗数。
        """
        # Double3Plug._set_value の回転変換・単位処理を通さず、基底 Plug の書込みを骨格ごと使う。
        plug = self.getPlug(name)
        try:
            return Plug._set_template(plug, tuple(value), safe, fast=fast, unit="rad",
                                      _writer=Plug._set_value)
        except RuntimeError as error:
            message = None if safe else _unwritable_channel_message(plug)
            if message is None:
                raise
            raise RuntimeError(message) from error

    def _matrix_channel_values(self, matrix, scale_reference=None):
        """マトリクスからtranslate/rotate/scale/shearの設定値を計算する。シーンは更新しない。

        Args:
            matrix: 変換または数値計算に使うマトリクス。
            scale_reference: スケール補正の基準となるノードまたは値。
        """
        source = Matrix(matrix)
        inv_scale = self._inverse_scale_values()
        corrected = source * Matrix(scale=inv_scale)
        # Matrix 同士の積は常に Matrix。
        assert isinstance(corrected, Matrix)
        corrected.translate = source.translate
        _, q, scale, shear, reference = self._decompose_like_channels(corrected, scale_reference)
        if type(self)._channel_rotate is Transform._channel_rotate:
            # Transformの_channel_rotateと同じ式で、rotateAxisの読取を1回にする(値は同じ読取関数)。
            rotate_axis = self._component_quaternion("rotateAxis")
            rotation = _closest_euler(rotate_axis.inverse() * q, reference)
        else:
            # Joint等の上書きは独自の読取関数を使うため、従来どおり別に読む。
            rotation = self._channel_rotate(q, reference)
            rotate_axis = self._component_quaternion("rotateAxis")
        sp = self._static_value("scalePivot")
        rp = self._static_value("rotatePivot")
        spt = self._static_value("scalePivotTranslate")
        rpt = self._static_value("rotatePivotTranslate")
        orient = rotate_axis * rotation.asQuaternion()
        if self._require_mnode().hasFn(om2.MFn.kJoint):
            orient *= self._component_quaternion("jointOrient")
        base = (Matrix(translate=tuple(-v for v in sp)) * Matrix(scale=scale, shear=shear)
                * Matrix(translate=sp) * Matrix(translate=spt)
                * Matrix(translate=tuple(-v for v in rp)) * Matrix(rotate=orient)
                * Matrix(translate=rp) * Matrix(translate=rpt)
                * Matrix(scale=tuple(1.0 / v for v in inv_scale)))
        assert isinstance(base, Matrix)
        translate = source.translate - base.translate
        return {"translate": Translate(*translate), "rotate": EulerRotate._wrap(rotation),
                "scale": Scale(*scale), "shear": Shear(*shear)}
