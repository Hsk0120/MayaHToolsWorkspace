"""マトリクスを介して Transform ノードを操作する。"""

import inspect
import math
import numbers
from contextlib import nullcontext

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace

from ..core.attributeType import value_reader
from ..core.fastWrite import writable
from ..decorator import undoChunk, undoTransaction
from ..maths import EulerRotate, Matrix, Quaternion, Scale, Shear, Translate, Vector, Transformation
from ..maths.vector import _vector_of
from ..plugs.plug import Plug
from ..util import _world_space
from ..util import _ArgumentError, _UNSET
from .dagNode import DagNode, DagNodes
from .node import Node

#: ターゲットの transform の値(位置・回転など)を使うコンストレイント。ターゲットは Transform に限る。
_TRANSFORM_SOURCE_CONSTRAINTS = frozenset((
    "parentConstraint", "pointConstraint", "orientConstraint", "scaleConstraint",
    "aimConstraint", "poleVectorConstraint",
))


_TRANSFORM_ATTRIBUTES = {}

# getEulerでゼロとみなすスケール軸の長さ。Mayaは scale 0 を 1e-12 として評価する。
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


class Transform(DagNode):
    """Transformのノード参照とDAGパスを保持し、変換値を照会・設定する。

    マトリクス・TRS・ピボットを扱い、Shapeの頂点やCVの編集とは区別する。
    距離はcm、角度はradを基本とし、MayaのUI単位とは独立する。
    ``worldSpace`` の短縮名は ``ws``。ローカル側の基準は各メソッドで異なる。
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
                Transform（Joint・IkHandleを含む）に解決される入力だけを受け付ける。
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

        PoleVectorはRP IKハンドル、Geometry/Normal/PointOnPolyは対応形状、TangentはNURBSカーブが必要。
        """
        if cc is not _UNSET:
            if createCache is not _UNSET:
                raise _ArgumentError("Specify only one of 'createCache' and 'cc'")
            createCache = cc
        if createCache is not _UNSET:
            kwargs["createCache"] = createCache
        if dr is not _UNSET:
            if decompRotationToChild is not _UNSET:
                raise _ArgumentError("Specify only one of 'decompRotationToChild' and 'dr'")
            decompRotationToChild = dr
        if decompRotationToChild is not _UNSET:
            kwargs["decompRotationToChild"] = decompRotationToChild
        if dc is not _UNSET:
            if deleteCache is not _UNSET:
                raise _ArgumentError("Specify only one of 'deleteCache' and 'dc'")
            deleteCache = dc
        if deleteCache is not _UNSET:
            kwargs["deleteCache"] = deleteCache
        if e is not _UNSET:
            if edit is not _UNSET:
                raise _ArgumentError("Specify only one of 'edit' and 'e'")
            edit = e
        if edit is not _UNSET:
            kwargs["edit"] = edit
        if l is not _UNSET:
            if layer is not _UNSET:
                raise _ArgumentError("Specify only one of 'layer' and 'l'")
            layer = l
        if layer is not _UNSET:
            kwargs["layer"] = layer
        if n is not _UNSET:
            if name is not _UNSET:
                raise _ArgumentError("Specify only one of 'name' and 'n'")
            name = n
        if name is not _UNSET:
            kwargs["name"] = name
        if q is not _UNSET:
            if query is not _UNSET:
                raise _ArgumentError("Specify only one of 'query' and 'q'")
            query = q
        if query is not _UNSET:
            kwargs["query"] = query
        if rm is not _UNSET:
            if remove is not _UNSET:
                raise _ArgumentError("Specify only one of 'remove' and 'rm'")
            remove = rm
        if remove is not _UNSET:
            kwargs["remove"] = remove
        if sr is not _UNSET:
            if skipRotate is not _UNSET:
                raise _ArgumentError("Specify only one of 'skipRotate' and 'sr'")
            skipRotate = sr
        if skipRotate is not _UNSET:
            kwargs["skipRotate"] = skipRotate
        if st is not _UNSET:
            if skipTranslate is not _UNSET:
                raise _ArgumentError("Specify only one of 'skipTranslate' and 'st'")
            skipTranslate = st
        if skipTranslate is not _UNSET:
            kwargs["skipTranslate"] = skipTranslate
        if tl is not _UNSET:
            if targetList is not _UNSET:
                raise _ArgumentError("Specify only one of 'targetList' and 'tl'")
            targetList = tl
        if targetList is not _UNSET:
            kwargs["targetList"] = targetList
        if w is not _UNSET:
            if weight is not _UNSET:
                raise _ArgumentError("Specify only one of 'weight' and 'w'")
            weight = w
        if weight is not _UNSET:
            kwargs["weight"] = weight
        if wal is not _UNSET:
            if weightAliasList is not _UNSET:
                raise _ArgumentError("Specify only one of 'weightAliasList' and 'wal'")
            weightAliasList = wal
        if weightAliasList is not _UNSET:
            kwargs["weightAliasList"] = weightAliasList
        if o is not _UNSET:
            if offset is not _UNSET:
                raise _ArgumentError("Specify only one of 'offset' and 'o'")
            offset = o
        if offset is not _UNSET:
            kwargs["offset"] = offset
        if sk is not _UNSET:
            if skip is not _UNSET:
                raise _ArgumentError("Specify only one of 'skip' and 'sk'")
            skip = sk
        if skip is not _UNSET:
            kwargs["skip"] = skip
        if sc is not _UNSET:
            if scaleCompensate is not _UNSET:
                raise _ArgumentError("Specify only one of 'scaleCompensate' and 'sc'")
            scaleCompensate = sc
        if scaleCompensate is not _UNSET:
            kwargs["scaleCompensate"] = scaleCompensate
        if aim is not _UNSET:
            if aimVector is not _UNSET:
                raise _ArgumentError("Specify only one of 'aimVector' and 'aim'")
            aimVector = aim
        if aimVector is not _UNSET:
            kwargs["aimVector"] = aimVector
        if u is not _UNSET:
            if upVector is not _UNSET:
                raise _ArgumentError("Specify only one of 'upVector' and 'u'")
            upVector = u
        if upVector is not _UNSET:
            kwargs["upVector"] = upVector
        if wuo is not _UNSET:
            if worldUpObject is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldUpObject' and 'wuo'")
            worldUpObject = wuo
        if worldUpObject is not _UNSET:
            kwargs["worldUpObject"] = worldUpObject
        if wut is not _UNSET:
            if worldUpType is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldUpType' and 'wut'")
            worldUpType = wut
        if worldUpType is not _UNSET:
            kwargs["worldUpType"] = worldUpType
        if wu is not _UNSET:
            if worldUpVector is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldUpVector' and 'wu'")
            worldUpVector = wu
        if worldUpVector is not _UNSET:
            kwargs["worldUpVector"] = worldUpVector
        if typ is not _UNSET:
            if type is not _UNSET:
                raise _ArgumentError("Specify only one of 'type' and 'typ'")
            type = typ
        if mo is not _UNSET:
            if maintainOffset is not _UNSET:
                raise _ArgumentError("Specify only one of 'maintainOffset' and 'mo'")
            maintainOffset = mo
        if type is _UNSET:
            type = "parent"
        if maintainOffset is _UNSET:
            maintainOffset = False
        with undoChunk("mlibTransformAddConstraint"):
            from .node import Node as _InputNode
            from .node import Nodes as _InputNodes
            from .constraint import Constraint

            if not isinstance(type, str):
                raise TypeError("type must be a string")
            command_name = type if type.endswith("Constraint") else type + "Constraint"
            # 型登録を重複管理せず、明示登録されたクラスと型名の対応から判定する。
            supported = {
                key for key, wrapper in Node._registry._classes.items()
                if issubclass(wrapper, Constraint)
            }
            if command_name not in supported:
                raise ValueError(f"Unsupported constraint type: {type}")
            if not self.isValid():
                raise RuntimeError("Cannot constrain an invalid transform")
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
            for source in _InputNodes._resolve_inputs(sources):
                if source is None or (isinstance(source, str) and not source):
                    raise TypeError("Constraint sources must be non-empty names or Node objects")
                # 文字列も含めて所有ノードへ解決する。Plug・MPlug・"node.attribute" は所有ノード、
                # Component・"pCube1.vtx[0]" は所有シェイプをターゲットにする(maya.cmds へ
                # プラグ名・コンポーネント名をそのまま渡すとターゲットとして扱われないため)。
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

            command_kwargs = dict(kwargs)
            if command_kwargs.get("query") or command_kwargs.get("edit"):
                raise ValueError("addConstraint supports creation only; use Maya constraint commands for query/edit")
            if "worldUpObject" in command_kwargs:
                command_kwargs["worldUpObject"] = _InputNode._input_name(command_kwargs["worldUpObject"])
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
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformDeleteConstraints"):
            if not self.isValid():
                raise RuntimeError("Cannot edit an invalid transform")
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
                            raise RuntimeError("Constraint path has shared outputs: " + fn.name())
            for token in deleting:
                fn = om2.MFnDependencyNode(objects[token])
                if fn.isFromReferencedFile or fn.isLocked:
                    raise RuntimeError("Cannot delete referenced or locked node: " + fn.name())
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

    def transformFn(self):
        """Transform 用の MFnTransform を取得する。

        Returns:
            om2.MFnTransform: この Transform の function set。
        """
        return om2.MFnTransform(self.mpath())

    def reset(self, attributes=_UNSET, *, fast=False, attrs=_UNSET):
        """指定アトリビュートを定義上の既定値へ戻す。

        Args:
            attributes (str | Iterable[str] | None): tx/translateX/translateなど。
                省略時はtranslate・rotate・scale・shear。独自数値アトリビュートも可。 別名 ``attrs`` も使用可能。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。
            attrs (str | Iterable[str] | None): attributesの別名。同時指定は不可。

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
        if attrs is not _UNSET:
            if attributes is not _UNSET:
                raise _ArgumentError("Specify only one of 'attributes' and 'attrs'")
            attributes = attrs
        if attributes is _UNSET:
            attributes = None
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformReset"):
            if attributes is None:
                attributes = ("translate", "rotate", "scale", "shear")
            elif isinstance(attributes, str):
                attributes = (attributes,)
            attributes = tuple(attributes)
            if not all(isinstance(name, str) and name for name in attributes):
                raise TypeError("attributes must contain non-empty attribute names")
            plugs = [self.getPlug(name) for name in attributes]
            for plug in plugs:
                plug.reset(fast=fast)
            return self

    def resetPivot(self, worldSpace=_UNSET, *, kind="both", fast=False, ws=_UNSET):
        """姿勢を保ち、指定したピボットを指定空間の原点へ移す。

        setPivotへ委譲し、ピボット補償値を調整する。translateはリセットしない。

        Args:
            worldSpace (bool): 既定Trueはワールド空間。FalseはxformのobjectSpace。
            kind (str): bothは両方、rotateは回転、scaleはスケールピボット。
            fast (bool): TrueはUndoなしのOM2更新。FalseはUndo有効時に記録する。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: 対象がJoint、fastがbool以外、またはworldSpace/wsを同時指定した場合。
            ValueError: worldSpaceがbool以外、またはkindが不正な場合。
            RuntimeError: 変更するピボットまたは補償値の成分がロック・入力接続されている
                場合(通常・fastとも更新前に検査し、何も変更しない)、またはMayaが更新を
                拒否した場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = True
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformResetPivot"):
            ws = _world_space(worldSpace)
            if not isinstance(ws, bool):
                raise TypeError("ws must be a bool")
            return self.setPivot((0, 0, 0), ws=ws, kind=kind, preserve=True, fast=fast)

    def scaleGeometry(self, scale, worldSpace=_UNSET, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False, ws=_UNSET):
        """直下の非中間Shapeの頂点・CVを拡縮する。Transformのマトリクスは変更しない。

        Shapeごとに検証・更新するため、後続Shapeの拒否でも先行変更は残る。
        共有形状は全インスタンスに影響する。

        Args:
            scale (float | Iterable[float]): 一様倍率、またはXYZ倍率。
            worldSpace (bool): 既定Falseは各Shapeのobject空間。Trueはworld空間。
            pivot (Iterable[float]): 指定空間の拡縮中心。cm。既定は原点。
            indices (Iterable[int | tuple[int, int]] | None): 各Shapeに共通の頂点/CV番号。
                Noneは全要素。サーフェスは(U, V)の組。
            fast (bool): Trueは履歴なしメッシュ・非周期カーブをOM2で更新（Undoなし）。
                Falseは通常更新をUndo有効時にまとめる。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: fast・番号の型、または長短名の指定が不正な場合。
            ValueError: 倍率・中心・空間が不正な場合。
            IndexError: 対象番号が範囲外の場合。
            NotImplementedError: 未対応Shape、またはfastの編集条件に対応しない場合。
            RuntimeError: Mayaが変更を拒否した場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformScaleGeometry"):
            ws = _world_space(worldSpace)
            indices = None if indices is None else tuple(indices)
            scale = scale if isinstance(scale, numbers.Real) else tuple(scale)
            pivot = tuple(pivot)
            for shape in self.getShapes():
                shape.scaleGeometry(scale, ws=ws, pivot=pivot, indices=indices, fast=fast)
            return self

    def getPivot(self, worldSpace=_UNSET, *, kind="rotate", ws=_UNSET):
        """回転またはスケールピボットの位置をcm単位で取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはxformのobjectSpaceに相当する
                MSpace.kPreTransform。短縮名ws。
            kind (str): rotateは回転、scaleはスケールピボット。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Translate: ノードと独立した新しい位置の値。UI距離単位によらずcm。

        Raises:
            ValueError: kindがrotate/scaleでない場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
        if kind not in ("rotate", "scale"):
            raise ValueError("kind must be 'rotate' or 'scale'")
        # xformのobjectSpaceはMFnTransformのkPreTransformに対応する。
        fn = self.transformFn()
        space = MSpace.kWorld if ws else MSpace.kPreTransform
        point = fn.rotatePivot(space) if kind == "rotate" else fn.scalePivot(space)
        return Translate(point.x, point.y, point.z)

    def setPivot(self, value, worldSpace=_UNSET, *, kind="rotate", preserve=True, fast=False, ws=_UNSET):
        """指定した種類のピボットを変更する。既定ではノードの姿勢を保つ。

        Args:
            value (Iterable[float]): 新しいピボット位置のXYZ3成分。UI距離単位によらずcm。
            worldSpace (bool): Trueはワールド空間、FalseはxformのobjectSpaceに相当する
                MSpace.kPreTransform。短縮名ws。
            kind (str): rotate/scale/both。bothは両方を同じ位置へ設定する。
            preserve (bool): Trueはピボット補償値を調整してマトリクスを保つ。
                Falseは補償せず、姿勢が変わる場合がある。
            fast (bool): TrueはOpenMayaで直接更新し、Undoへ記録しない。
                通常はmaya.cmds.xformで設定する。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: kind、座標の要素数・有限値が不正な場合。
            TypeError: preserveがboolでない、または対象がJointの場合。
            RuntimeError: ノードが無効、変更するピボットまたは補償値(preserve=True時)の
                成分がロック・入力接続されている場合、または Maya が設定を拒否した場合。
                ロックの検査は通常・fastとも更新前に行い、何も変更しない。

        Jointは独立したピボットの変更をサポートしないため、更新前に拒否する。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformSetPivot"):
            ws = _world_space(worldSpace)
            if kind not in ("rotate", "scale", "both"):
                raise ValueError("kind must be 'rotate', 'scale' or 'both'")
            if not isinstance(preserve, bool):
                raise TypeError("preserve must be a bool")
            if self.isType("joint"):
                raise TypeError("Joint does not support independent rotate/scale pivots")
            values = tuple(value)
            if len(values) != 3 or not all(math.isfinite(v) for v in values):
                raise ValueError("Expected three finite pivot coordinates")
            kinds = ("scale", "rotate") if kind == "both" else (kind,)
            # APIはロックを迂回し、cmds.xformはロックされた成分を黙って飛ばすため、
            # 通常とfastのどちらも変更する補償値を含めて書く前に確認する。
            self._check_pivots_writable(kinds, preserve)
            if fast:
                fn = self.transformFn()
                point = om2.MPoint(*values)
                space = MSpace.kWorld if ws else MSpace.kPreTransform
                for selected in kinds:
                    setter = fn.setRotatePivot if selected == "rotate" else fn.setScalePivot
                    setter(point, space, preserve)
                return self
            coordinates = [om2.MDistance(v).asUnits(om2.MDistance.uiUnit()) for v in values]
            flag = {"rotate": "rotatePivot", "scale": "scalePivot", "both": "pivots"}[kind]
            cmds.xform(self.getFullName(), worldSpace=ws, objectSpace=not ws,
                       preserve=preserve, **{flag: coordinates})
            return self

    def centerPivot(self, *, fast=False):
        """バウンディングボックス中心へ回転・スケールピボットを移す。

        通常はxform(centerPivots=True)、fastはAPIで得た中心をsetPivotへ渡す。
        preserve=Trueでピボット補償値を調整し、コンポーネント選択は使わない。

        Args:
            fast (bool): TrueはUndoなしのOM2更新。FalseはUndo有効時に記録する。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: fastがbool以外、またはfastで対象がJointの場合。
            RuntimeError: 無効参照の場合、ピボットまたは補償値の成分がロック・入力接続
                されている場合(通常・fastとも更新前に検査する)、またはMayaが更新を拒否した場合。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformCenterPivot"):
            if fast:
                center = self.dagFn().boundingBox.center * self.mpath().exclusiveMatrix()
                return self.setPivot((center.x, center.y, center.z), worldSpace=True,
                                     kind="both", preserve=True, fast=fast)
            # fast(setPivot経由)と同じく、xformが黙って飛ばすロックを先に拒否する。
            self._check_pivots_writable(("scale", "rotate"), True)
            cmds.xform(self.getFullName(), centerPivots=True, preserve=True)
            return self

    def getBoundingBox(self, worldSpace=_UNSET, *, ws=_UNSET):
        """直下の Shape 階層を含むバウンディングボックスを取得する。

        MFnDagNode.boundingBox は自身の translate/rotate/scale は含むが、
        親から継承した変換は含まない（``cmds.xform(-boundingBox)`` と同じ）。
        ``ws=True`` はそこへ親のワールドマトリクスをさらに適用し、真のワールド空間の
        バウンディングボックスを返す。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
                （親の変換は含まない）。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            om2.MBoundingBox: 軸並行境界ボックス。Maya API の内部距離単位。
                子 Shape が無い場合は原点のみを含む空に近いボックスになる。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
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

    def getChildren(self, shapes=False, intermediates=False, *, allDescendents=False,
                    order="depthFirst", leaves=False, includeSelf=False, underWorld=False):
        """指定条件に合う直接の子、または子孫を取得する。

        Args:
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
                                   underWorld=underWorld)

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
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        shapes = self.getUnusedIntermediateShapes()
        if shapes:
            if fast:
                self._detach_inputs(shape.mnode() for shape in shapes)
                modifier = om2.MDagModifier()
                for shape in shapes:
                    modifier.deleteNode(shape.mnode(), False)
                modifier.doIt()
            else:
                with undoTransaction("mlibDeleteUnusedIntermediateShapes"):
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

    def mirrorGeometry(self, axis="x", worldSpace=_UNSET, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False,
        ws=_UNSET):
        """直下の非中間Shapeへmirrorを順に適用する。

        Mesh・NurbsCurve等のmirrorへ委譲し、Transformのマトリクス・トポロジーは変更しない。
        Shapeごとに検証・更新し、後続の失敗で先行変更は戻さない。
        pivot/indicesの反復子は最初のShapeで消費される場合がある。

        Args:
            axis (str): 反転する軸。x/y/z/xy/xz/yz/xyz。大文字も可。
            worldSpace (bool): 既定FalseはShapeのobject空間。Trueはworld空間。
            pivot (Iterable[float]): 指定空間の中心、cm。既定は原点でTransformのピボットは使わない。
            indices (Iterable[int] | None): 各Shapeへ渡す頂点/CV番号。Noneは全要素。
            fast (bool): TrueはUndoなしのOM2更新。Falseは通常処理をUndo有効時にまとめる。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: fast・要素番号の型、または長短名の指定が不正な場合。
            AttributeError: mirrorを持たないShapeの場合。
            ValueError: 軸・空間・中心が不正、またはworld変換がほぼ特異な場合。
            IndexError: 要素番号が範囲外の場合。
            NotImplementedError: fastの編集条件に対応しない場合。
            RuntimeError: Mayaが形状の取得・編集を拒否した場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformMirrorGeometry"):
            ws = _world_space(worldSpace)
            for shape in self.getShapes():
                shape.mirror(axis=axis, ws=ws, pivot=pivot, indices=indices, fast=fast)
            return self

    def getShape(self, idx=_UNSET, intermediates=False, *, index=_UNSET):
        """指定位置のShapeを取得する。

        Args:
            idx (int): Shapeのインデックス。 別名 ``index`` も使用可能。
            intermediates (bool): ``True`` の場合は中間Shapeも含める。
            index (int): idxの別名。同時指定は不可。

        Returns:
            Shape | None: 指定位置のShape。範囲外ではNone。
        """
        if index is not _UNSET:
            if idx is not _UNSET:
                raise _ArgumentError("Specify only one of 'idx' and 'index'")
            idx = index
        if idx is _UNSET:
            idx = 0
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

    def setParent(self, parent=None, relative=False, add=False, *, fast=False):
        """Transformの親を変更する。

        Args:
            parent (Node | str | om2.MObject | om2.MDagPath | None): 新しい親。None はワールド直下。
                ``Node(parent)`` で解決できる型(Plug・Component は所有ノード)を受け付ける。
            relative (bool): True は親変更前のローカル変換を保持する。False は Maya の既定動作。
            add (bool): True は既存の親を維持して追加の親を設定する。parent が None の場合は渡されない。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。Joint・インスタンス・親の追加は未対応。

        Returns:
            Transform: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformSetParent"):
            if not self.isValid():
                raise RuntimeError("Cannot parent an invalid transform")
            if fast:
                return self._set_parent_fast(parent, relative, add)
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

    @undoChunk("mlibTransformMatch")
    def matchTransform(self, target, position=True, rotation=True, scale=True, pivots=False):
        """自身の変換を指定Transformへ合わせる。選択状態は使用しない。

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

        maya.cmds.matchTransformと同じ空間・joint・ピボット処理を使用する。
        shearの一致やマトリクス全体のコピーは保証しない。
        """
        from .node import Node as _InputNode

        target = _InputNode._resolve_input(target)
        if not isinstance(target, Transform):
            raise TypeError("Target must be a transform or joint")
        if any((position, rotation, scale, pivots)):
            cmds.matchTransform(self.getFullName(), target.getFullName(), position=position,
                                rotation=rotation, scale=scale, pivots=pivots)
        return self

    def mirrorTransform(self, axis="x", worldSpace=_UNSET, pivot=(0.0, 0.0, 0.0), *, fast=False, ws=_UNSET):
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
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Transform: 自身。Transforms/Jointsからの一括呼出も可能。

        Raises:
            TypeError: fast が bool でない場合。
            ValueError: 入力不正、特異な親マトリクス、未対応のピボット/rotateAxisの場合。
            RuntimeError: ロックや入力接続で更新できない場合。

        setMatrix() と同じ制約があり、非ゼロのピボット・
        TransformのrotateAxisは更新前に拒否する。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformMirrorTransform"):
            ws = _world_space(worldSpace)
            from ..util import mirrorArguments
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
            Matrix: アトリビュート値の複製。ワールドマトリクスやローカルマトリクスとの合成はしない。

        Raises:
            RuntimeError: ノードやアトリビュートが無効の場合。
        """
        return self.getPlug("offsetParentMatrix").get()

    def setOffsetParentMatrix(self, value, *, fast=False):
        """offsetParentMatrixへマトリクス値を設定する。

        Args:
            value (Matrix | Iterable[float]): 別Transform.getMatrix()の戻り値などの4x4マトリクス。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Transform: 自身。Transformsでは各対象へ同じ値を設定する。

        Raises:
            TypeError: fastがboolでない場合。
            ValueError: マトリクス値が不正な場合。
            RuntimeError: 無効な対象・ロック・入力接続などで更新できない場合。

        TRSチャンネル値は変更しない。指定マトリクスは既存ローカルマトリクスと親マトリクスに合成される。
        ワールド姿勢の自動一致・入力接続の切断・ロック解除は行わない。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformSetOffsetParentMatrix"):
            self.getPlug("offsetParentMatrix").set(value, fast=fast)
            return self

    def getTransformation(self, worldSpace=_UNSET, *, ws=_UNSET):
        """TRSチャンネルとピボット等の補助成分を、独立した変換値として取得する。

        取得した値やその成分を編集してもシーンは変更しない。
        変更を反映する場合はsetTransformationへ渡す。

        Args:
            worldSpace (bool): ワールド空間へ変換する。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Transformation: 距離cm・角度radの独立した値。
                Euler回転順序・ピボット・補助回転・SSCを含む。
                offsetParentMatrixと親マトリクスはワールド指定時の合成に含める。
                Jointではピボットとその補償値を0にする。
                ワールド指定ではinverseScaleを単位スケールへ整理する。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
        values = {name: self.getPlug(name).get() for name in (
            "translate", "rotate", "scale", "shear", "rotateOrder", "rotateAxis",
            "rotatePivot", "rotatePivotTranslate", "scalePivot", "scalePivotTranslate")}
        values["rotate"] = EulerRotate(values["rotate"], order=values["rotateOrder"])
        values["rotateAxis"] = EulerRotate(values["rotateAxis"])
        if self.mnode().hasFn(om2.MFn.kJoint):
            values.update(jointOrient=EulerRotate(self.getPlug("jointOrient").get()),
                          inverseScale=self.getPlug("inverseScale").get(),
                          segmentScaleCompensate=bool(self.getPlug("segmentScaleCompensate").get()))
            # Mayaのjointマトリクスはピボットを使わない。
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

    def setTransformation(self, value, worldSpace=_UNSET, safe=False, get=False, *, fast=False, ws=_UNSET):
        """補助成分を含む変換を適用する。入力の値は変更しない。

        Args:
            value (Transformation): 適用する変換情報。
            worldSpace (bool): ワールド空間として適用する。短縮名ws。
            safe (bool): 書けない成分を保持し、実際の補助成分でTRSを再計算する。
                TRSにも書けない成分があれば目標マトリクスと一致しない場合がある。
            get (bool): シーンを更新せず、対象ノード用に補正した値を返す。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。通常はcmdsでUndoに記録する。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Transform | Transformation: get=Falseでは適用後の自身。
                get=Trueでは対象ノード用に補正したローカル空間の設定予定値を返し、シーンは変更しない。
                予定値は入力値と独立し、距離cm・角度radを使う。
                get=Trueではsafeの再計算や書込み可否の検査を行わず、
                ロックされた成分を反映した最終結果の予測ではない。

        Raises:
            TypeError: valueがTransformationでない場合。
            ValueError: 分解不能、またはワールド指定時の親マトリクスがほぼ特異な場合。
            RuntimeError: 対象が無効、またはsafeで抑制しない設定失敗の場合。

        Note:
            inverseScaleの接続は保持する。jointとtransformを相互コピーする場合は
            対象で使えない補助成分を除き、マトリクスを維持するようにTRSを補正する。
            補助成分とTRSのうち、書込み値が現在のチャンネル値(内部単位)と完全に一致する
            ものは書き込まない。書き込まない成分はロック・接続されていても例外にせず、
            通知・Undoの記録も書き込んだ成分だけになる(通常・fast・safe共通)。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformSetTransformation"):
            if not isinstance(value, Transformation):
                raise TypeError("value must be a Transformation")
            ws = _world_space(worldSpace)
            fitted, matrix, is_joint = self._fit_transformation(value, ws)
            if get:
                return fitted
            self._apply_transformation_modifiers(fitted, is_joint, safe=safe, fast=fast)
            if safe:
                fitted = self._refit_safe_transformation(fitted, matrix)
            self._apply_channel_values({name: getattr(fitted, name)
                                        for name in ("translate", "rotate", "scale", "shear")}, safe=safe, fast=fast)
            return self

    def getMatrix(self, worldSpace=_UNSET, p=False, inv=False, *, ws=_UNSET):
        """指定空間の評価済みマトリクスを取得する。

        p=Falseのローカル値は ``matrix`` アトリビュート、ワールド値は保持パスの
        inclusiveMatrixを使う。offsetParentMatrixはローカル値に含まれず、ワールド値に含まれる。

        Args:
            worldSpace (bool): Trueはワールド、既定Falseはローカル。短縮名ws。
            p (bool): Trueは親側のマトリクス。worldSpace=Trueは保持パスのexclusiveMatrix、
                Falseは親パスのinclusiveMatrix * exclusiveMatrixInverseで求める。
            inv (bool): Trueは選んだマトリクスの逆マトリクス。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Matrix: 呼出し時点のマトリクスの独立した複製。

        Raises:
            RuntimeError: ノードまたは保持するDAGパスが無効な場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
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

    def setMatrix(self, matrix, worldSpace=_UNSET, safe=False, get=False, *, fast=False, ws=_UNSET):
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
                ローカルへ変換する。既定Falseは ``matrix`` アトリビュートと同じ空間。短縮名ws。
            safe (bool): 書けない成分を保持し、書ける成分だけを更新する。
            get (bool): Trueは書き込まず、ローカルの設定予定値を返す。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。既定Falseはcmdsで更新する。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Transform | dict[str, Translate | EulerRotate | Scale | Shear]: 通常は自身。
                get=Trueはtranslate・rotate・scale・shearの辞書（距離cm・角度rad）。
                safe/fastによらず計算だけ行い、書込み可否やsafe適用後の結果は検証しない。

        Raises:
            TypeError: 長短名の同時指定、またはfastがbool以外の場合。
            RuntimeError: ノードが無効、またはMayaが書込みを拒否した場合。
            ValueError: マトリクスが不正・分解不能、またはワールド指定時に親側のマトリクスが反転不能の場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformSetMatrix"):
            local_matrix = self._local_matrix(matrix, _world_space(worldSpace))
            if safe or get:
                values = self._matrix_channel_values(local_matrix)
                if get:
                    return values
                self._apply_channel_values(values, safe=True, fast=fast)
            else:
                self._apply_local_matrix(local_matrix, fast=fast)
            return self

    def getTranslate(self, worldSpace=_UNSET, at=2, *, ws=_UNSET):
        """基準位置を取得する。既定は回転ピボット位置。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseは親側の空間で表す位置。
                短縮名ws。getPivotのobject空間とは異なる。
            at (int): 0以下=親原点、1=translate、2=回転ピボット、
                3=スケールピボット、4以上=マトリクス原点。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Translate: ノードと独立したcm単位の位置。既定at=2はtranslateチャンネル値ではない。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
        if at >= 3:
            matrix = self.getMatrix(ws=ws)
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

    def setTranslate(self, value, worldSpace=_UNSET, at=2, safe=False, get=False, *, fast=False, ws=_UNSET):
        """指定基準の位置へ移動する。ピボットや回転は変更しない。

        at=0以下は位置の絶対設定ではなく、親空間へ変換した入力から現在のtranslateを
        引いた値を設定する。例えば現在2・入力5ならtranslateは3になる。

        Args:
            value (Iterable[float]): cm単位の位置。
            worldSpace (bool): ワールド指定。短縮名ws。
            at (int): getTranslateと同じ基準。既定2。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずローカルtranslateの設定予定値だけを返す。
            fast (bool): Undoなしの直接更新。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Transform | list[float]: 自身。get=Trueはcm単位の独立したXYZ3成分のlist。
                safe指定時も書込み可否を反映した最終結果の予測ではない。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformSetTranslate"):
            ws = _world_space(worldSpace)
            point = om2.MPoint(tuple(value))
            if ws:
                point *= self.mpath().exclusiveMatrixInverse()
            current = om2.MVector(self._static_value("translate"))
            if at < 1:
                result = om2.MVector(point) - current
            else:
                result = current + (om2.MVector(point) - om2.MVector(tuple(self.getTranslate(at=at))))
            if get:
                return list(result)
            self._set_channel_value("translate", result, safe=safe, fast=fast)
            return self

    def getRotate(self, worldSpace=_UNSET, *, ws=_UNSET):
        """選択空間のマトリクスから、ノードのrotateOrderでEuler回転を取得する。

        rotateAxisと、JointではjointOrientを含む回転を返す。
        スケール符号は現在のチャンネルを基準とし、Eulerの等価解はTransformでは現在の
        rotate、Jointではゼロ回転に最も近いものを選ぶ。

        Args:
            worldSpace (bool): Trueはワールド、既定Falseはローカルマトリクスの回転。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            EulerRotate: rad単位・ノードのrotateOrderで表した独立した回転値。

        Raises:
            ValueError: ゼロスケール等でマトリクスを分解できない場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
        _, quaternion, _, _, reference = self._decompose_like_channels(self.getMatrix(ws=ws))
        return EulerRotate._wrap(_closest_euler(quaternion, self._rotate_reference(reference)))

    def setRotate(self, value, worldSpace=_UNSET, safe=False, get=False, *, unit="rad", fast=False, ws=_UNSET):
        """選択空間の回転を設定する。書込むrotateは現在値に最も近い等価解を使う。

        3成分はノードのrotateOrderで解釈し、EulerRotateは値自身の回転順序を使う。
        rotateAxisとJointのjointOrientを保ち、マトリクス経由でチャンネル値を計算する。
        書き込むのはrotateチャンネルだけで、translate・scale・shearは書き込まない
        (ロック・接続されていても例外にせず、通知・Undoの記録もrotateだけ。通常・fast・safe共通)。
        ピボットが0でない場合は、cmds.setAttrでrotateを設定したときと同じくピボットの周りに回る。

        Args:
            value (Iterable[float] | EulerRotate | Quaternion): 回転値。EulerRotate/Quaternionは
                対応するOpenMaya基底型も受理する。書込みはノードのrotateOrderに揃える。
            worldSpace (bool): Trueはワールド、既定Falseはローカルマトリクスの回転。短縮名ws。
            safe (bool): 書けない成分を保持する。目標回転との一致は保証しない。
            get (bool): Trueは書き込まず、ローカルrotateの設定予定値を返す。
            unit (str): 既定radはラジアン。degは通常の数値3成分だけに使用できる。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。既定Falseはcmdsで更新する。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Transform | list[float]: 通常は自身。get=Trueはrad単位の独立したXYZ3成分のlist。
                safe適用後の最終結果を予測する値ではない。

        Raises:
            TypeError: 長短名の同時指定、またはfastがbool以外の場合。
            ValueError: unitがrad/deg以外、degをEulerRotate/Quaternionと指定、
                値が3成分でない、マトリクスが分解不能、または必要な親マトリクスが反転不能の場合。
            RuntimeError: ノードが無効、またはアトリビュートを書き込めない場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformSetRotate"):
            ws = _world_space(worldSpace)
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
                value = EulerRotate(x, y, z, self._rotate_order())
            matrix = self._replace_components(self.getMatrix(ws=ws), rotate=value)
            rotation = self._matrix_channel_values(self._local_matrix(matrix, ws))["rotate"]
            if get:
                return list(rotation)
            self._set_channel_value("rotate", rotation, safe=safe, fast=fast)
            return self

    def getScale(self, worldSpace=_UNSET, *, ws=_UNSET):
        """指定空間のスケール値を取得する。

        Args:
            worldSpace (bool): ワールド指定。短縮名ws。Falseはscaleチャンネル。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Scale: 独立した無次元のXYZ3成分。ローカルではSSCを除くチャンネル値、
                ワールドではAPI規約の分解値で、チャンネルの符号と一致するとは限らない。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if _world_space(worldSpace):
            return Scale(*om2.MTransformationMatrix(self.getMatrix(ws=True)).scale(MSpace.kTransform))
        return self.getPlug("scale").get()

    def setScale(self, value, worldSpace=_UNSET, safe=False, get=False, *, fast=False, ws=_UNSET):
        """scaleチャンネルだけを設定する。

        ワールド指定では要求スケールをローカル設定値へ変換する。
        変換後も書込み先はscaleだけで、rotateやshearは変更しない。

        Args:
            value (Iterable[float]): 無次元のXYZスケール3成分。
            worldSpace (bool): ワールド指定。短縮名ws。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずチャンネル値を返す。
            fast (bool): Undoなしの直接更新。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Transform | list[float]: 自身。get=Trueは独立したローカルXYZ設定値のlist。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        values = self._scale_channel_value(value, _world_space(worldSpace))
        if get:
            return values
        self._set_channel_value("scale", values, safe=safe, fast=fast)
        return self

    def getShearing(self, worldSpace=_UNSET, *, ws=_UNSET):
        """指定空間のシアー値を取得する。

        Args:
            worldSpace (bool): ワールド指定。短縮名ws。Falseはshearチャンネル。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Shear: 独立した無次元のXY・XZ・YZ3成分。
                ローカルはチャンネル値、ワールドはAPI規約のマトリクス分解値。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if _world_space(worldSpace):
            return Shear(*om2.MTransformationMatrix(self.getMatrix(ws=True)).shear(MSpace.kTransform))
        return self.getPlug("shear").get()

    def setShearing(self, value, worldSpace=_UNSET, safe=False, get=False, *, fast=False, ws=_UNSET):
        """shearチャンネルだけを設定する。

        ワールド指定では要求シアーをローカル設定値へ変換する。
        変換後も書込み先はshearだけで、rotateやscaleは変更しない。

        Args:
            value (Iterable[float]): 無次元のXY・XZ・YZシアー3成分。
            worldSpace (bool): ワールド指定。短縮名ws。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずチャンネル値を返す。
            fast (bool): Undoなしの直接更新。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Transform | list[float]: 自身。get=Trueは独立したローカルXY・XZ・YZ設定値のlist。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        values = self._scale_channel_value(value, _world_space(worldSpace), shear=True)
        if get:
            return values
        self._set_channel_value("shear", values, safe=safe, fast=fast)
        return self

    def getQuaternion(self, worldSpace=_UNSET, ra=False, r=True, jo=True, *, ws=_UNSET):
        """回転成分を選んで取得する。既定ではrotateAxisを含めない。

        ローカル空間ではrotateAxis・rotate・JointのjointOrientの順に、選んだ回転を合成する。
        ワールド空間では保持パスのマトリクスから求め、除外する回転成分を取り除く。
        ra/r/joの許容組合せはsetQuaternionと同一ではない。

        Args:
            worldSpace (bool): ワールド指定。短縮名ws。
            ra (bool): rotateAxisを含める。
            r (bool): rotateを含める。
            jo (bool): jointOrientを含める。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Quaternion: ノードと独立した、指定成分の合成回転。成分順はXYZW。

        Raises:
            ValueError: 回転成分と空間指定が未対応の組合せの場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
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

    def setQuaternion(self, value, worldSpace=_UNSET, ra=False, r=True, jo=True, safe=False, get=False, *,
        fast=False, ws=_UNSET):
        """回転成分の指定に従いrotate・jointOrient・rotateAxisを設定する。

        受理する組合せでは、r=Trueはrotate、r=FalseかつJointでjo=TrueはjointOrient、
        それ以外のr=FalseはrotateAxisだけを書き込む。ra/r/joの許容組合せは
        getQuaternionと同一ではない。

        Args:
            value (Quaternion | om2.MQuaternion | Iterable[float]): xyzwの回転。
            worldSpace (bool): ワールド指定。短縮名ws。
            ra (bool): 入力にrotateAxisを含む。
            r (bool): rotateを更新する。FalseはjointOrientまたはrotateAxis。
            jo (bool): jointOrientを含む。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まず計算したEuler成分を返す。
            fast (bool): Undoなしの直接更新。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            Transform | list[float]: get=Falseでは自身。get=Trueでは書込み先のEuler3成分を
                rad単位のlistとして返し、safe/fastの指定によらずシーンは変更しない。
                入力のQuaternionや、XYZWの4成分を返す操作ではない。
                rotateの設定予定値はノードのrotateOrder、他の書込み先はXYZ順序。

        Raises:
            ValueError: 回転成分と空間指定が未対応の組合せの場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibTransformSetQuaternion"):
            name, rotation = self._quaternion_channel_values(value, _world_space(worldSpace), ra, r, jo)
            if get:
                return list(rotation)
            self._set_channel_value(name, rotation, safe=safe, fast=fast)
            return self

    def getEuler(self, worldSpace=_UNSET, *, ws=_UNSET):
        """回転を XYZ 順序の EulerRotate として取得する。

        マトリクスから分解した回転をXYZ順序で返す。getQuaternionのra/r/joによる
        合成対象の選択は行わない。ノードのrotateOrderで表す場合はgetRotateを使う。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            EulerRotate: 評価済みの回転値（radian、XYZ 順序）。

        Raises:
            ValueError: マトリクスを分解できない場合。いずれかのスケール軸の長さが
                ``_NEAR_ZERO_AXIS`` (1e-10)以下のときも含む。Mayaは scale 0 を 1e-12 として
                評価するため、0 のスケールチャンネル(自身または親)はこの判定で拒否する。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
        matrix = self.getMatrix(ws=ws)
        for row in range(3):
            if math.sqrt(sum(matrix[row, col] ** 2 for col in range(3))) <= _NEAR_ZERO_AXIS:
                raise ValueError("Cannot decompose a matrix with a zero scale axis")
        _, quaternion, _, _, _ = self._decompose_like_channels(matrix)
        return EulerRotate._wrap(quaternion.asEulerRotation())

    def freeze(self, *, apply=_UNSET, a=_UNSET, jointOrient=_UNSET, jo=_UNSET, normal=_UNSET, n=_UNSET,
        preserveNormals=_UNSET, pn=_UNSET, rotate=_UNSET, r=_UNSET, scale=_UNSET, s=_UNSET, translate=_UNSET,
        t=_UNSET, query=_UNSET, q=_UNSET, edit=_UNSET, e=_UNSET, **kwargs):
        """makeIdentity(apply=True)でフリーズする。

        子階層・Joint・スキニング・接続の扱いはMaya標準に従う。
        通常のcmds更新をUndo有効時にまとめ、途中失敗の変更は戻さない。

        Args:
            apply (bool): 省略時True。形状へ変換を適用するため、Trueだけを受け付ける。
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
            **kwargs (object): makeIdentityへ渡す追加フラグ。成分の省略時の扱いもMayaに従う。

        Returns:
            Transform: 自身。

        Raises:
            ValueError: applyにTrue以外を指定した場合。
            TypeError: 長短フラグを重複指定した場合。
            RuntimeError: Mayaがフリーズを拒否した場合。

        resetやJoint.freezeRotateの姿勢移送とは異なる。
        """
        if a is not _UNSET:
            if apply is not _UNSET:
                raise _ArgumentError("Specify only one of 'apply' and 'a'")
            apply = a
        if apply is not _UNSET:
            kwargs["apply"] = apply
        if jo is not _UNSET:
            if jointOrient is not _UNSET:
                raise _ArgumentError("Specify only one of 'jointOrient' and 'jo'")
            jointOrient = jo
        if jointOrient is not _UNSET:
            kwargs["jointOrient"] = jointOrient
        if n is not _UNSET:
            if normal is not _UNSET:
                raise _ArgumentError("Specify only one of 'normal' and 'n'")
            normal = n
        if normal is not _UNSET:
            kwargs["normal"] = normal
        if pn is not _UNSET:
            if preserveNormals is not _UNSET:
                raise _ArgumentError("Specify only one of 'preserveNormals' and 'pn'")
            preserveNormals = pn
        if preserveNormals is not _UNSET:
            kwargs["preserveNormals"] = preserveNormals
        if r is not _UNSET:
            if rotate is not _UNSET:
                raise _ArgumentError("Specify only one of 'rotate' and 'r'")
            rotate = r
        if rotate is not _UNSET:
            kwargs["rotate"] = rotate
        if s is not _UNSET:
            if scale is not _UNSET:
                raise _ArgumentError("Specify only one of 'scale' and 's'")
            scale = s
        if scale is not _UNSET:
            kwargs["scale"] = scale
        if t is not _UNSET:
            if translate is not _UNSET:
                raise _ArgumentError("Specify only one of 'translate' and 't'")
            translate = t
        if translate is not _UNSET:
            kwargs["translate"] = translate
        if q is not _UNSET:
            if query is not _UNSET:
                raise _ArgumentError("Specify only one of 'query' and 'q'")
            query = q
        if query is not _UNSET:
            kwargs["query"] = query
        if e is not _UNSET:
            if edit is not _UNSET:
                raise _ArgumentError("Specify only one of 'edit' and 'e'")
            edit = e
        if edit is not _UNSET:
            kwargs["edit"] = edit
        with undoChunk("mlibTransformFreeze"):
            if kwargs.pop("apply", True) is not True:
                raise ValueError("freeze requires apply=True")
            return self.makeIdentity(apply=True, **kwargs)

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
        if a is not _UNSET:
            if apply is not _UNSET:
                raise _ArgumentError("Specify only one of 'apply' and 'a'")
            apply = a
        if apply is not _UNSET:
            kwargs["apply"] = apply
        if jo is not _UNSET:
            if jointOrient is not _UNSET:
                raise _ArgumentError("Specify only one of 'jointOrient' and 'jo'")
            jointOrient = jo
        if jointOrient is not _UNSET:
            kwargs["jointOrient"] = jointOrient
        if n is not _UNSET:
            if normal is not _UNSET:
                raise _ArgumentError("Specify only one of 'normal' and 'n'")
            normal = n
        if normal is not _UNSET:
            kwargs["normal"] = normal
        if pn is not _UNSET:
            if preserveNormals is not _UNSET:
                raise _ArgumentError("Specify only one of 'preserveNormals' and 'pn'")
            preserveNormals = pn
        if preserveNormals is not _UNSET:
            kwargs["preserveNormals"] = preserveNormals
        if r is not _UNSET:
            if rotate is not _UNSET:
                raise _ArgumentError("Specify only one of 'rotate' and 'r'")
            rotate = r
        if rotate is not _UNSET:
            kwargs["rotate"] = rotate
        if s is not _UNSET:
            if scale is not _UNSET:
                raise _ArgumentError("Specify only one of 'scale' and 's'")
            scale = s
        if scale is not _UNSET:
            kwargs["scale"] = scale
        if t is not _UNSET:
            if translate is not _UNSET:
                raise _ArgumentError("Specify only one of 'translate' and 't'")
            translate = t
        if translate is not _UNSET:
            kwargs["translate"] = translate
        if q is not _UNSET:
            if query is not _UNSET:
                raise _ArgumentError("Specify only one of 'query' and 'q'")
            query = q
        if query is not _UNSET:
            kwargs["query"] = query
        if e is not _UNSET:
            if edit is not _UNSET:
                raise _ArgumentError("Specify only one of 'edit' and 'e'")
            edit = e
        if edit is not _UNSET:
            kwargs["edit"] = edit
        with undoChunk("mlibTransformMakeIdentity"):
            if not self.isValid():
                raise RuntimeError("Cannot freeze transform of an invalid transform")
            cmds.makeIdentity(self.getFullName(), **kwargs)
            return self

    def getClosestAxisToVector(self, ref_vector, include_negative=True):
        """自身のローカル軸のうち、ワールド空間の方向ベクトルに最も近いものを求める。

        各ローカル軸をワールドマトリクス（回転・スケールのみ、平行移動は無視）で変換し、
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

    # 公開APIの短縮メソッド。旧mlib名の互換入口ではない。
    def getJointOrientQuaternion(self, ws=_UNSET, *, worldSpace=_UNSET):
        """getQuaternionでrotateを除いた回転を取得する。

        ``getQuaternion(ws=ws, r=False)`` へ委譲する。
        ローカルではJointのjointOrient、非Jointでは単位回転を返す。
        ワールドでは保持パスから求め、非Jointでは親側のマトリクスの回転を返す。
        jointOrientアトリビュートだけをQuaternionへ変換する入口ではない。

        Args:
            ws (bool): ワールド空間を使う。 別名 ``worldSpace`` も使用可能。
            worldSpace (bool): wsの別名。同時指定は不可。

        Returns:
            Quaternion: ノードと独立した回転値。
        """
        if worldSpace is not _UNSET:
            if ws is not _UNSET:
                raise _ArgumentError("Specify only one of 'ws' and 'worldSpace'")
            ws = worldSpace
        if ws is _UNSET:
            ws = False
        return self.getQuaternion(ws=ws, r=False)

    def _local_matrix(self, matrix, ws):
        """setMatrixの入力を検証し、ローカル空間のマトリクスへ変換する。シーンは更新しない。

        Args:
            matrix (Matrix | sequence): 適用するマトリクス。
            ws (bool): 検証済みのワールド空間指定。Trueは保持パスのexclusiveMatrixInverseを掛ける。

        Returns:
            Matrix: ローカル空間のマトリクス。

        Raises:
            RuntimeError: ノードが無効な場合。
            ValueError: マトリクスが不正、またはワールド指定時の親が反転不能な場合。
        """
        if not isinstance(matrix, Matrix):
            matrix = Matrix(matrix)
        if not self.isValid():
            raise RuntimeError("Cannot set an invalid transform")
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
            NotImplementedError: Joint・インスタンス・親追加の場合。
            RuntimeError: 参照・ロック・循環・特異マトリクスにより変更できない場合。
        """
        target = None if parent is None else Node._resolve_input(parent)
        if target is not None and not isinstance(target, Transform):
            raise TypeError("Parent must be a transform")
        path = self.mpath()
        if (self.mnode().hasFn(om2.MFn.kJoint) or path.isInstanced()
                or (target is not None and target.mpath().isInstanced()) or add):
            raise NotImplementedError("fast parenting does not support joints, instances or add=True")
        if self.dagFn().isLocked or self.dagFn().isFromReferencedFile:
            raise RuntimeError("Cannot reparent a locked or referenced transform")
        if target is not None:
            ancestor = om2.MDagPath(target.mpath())
            while ancestor.length():
                if ancestor.node() == self.mnode():
                    raise RuntimeError("Cannot create a DAG parenting cycle")
                ancestor.pop()
            if target.dagFn().isLocked or target.dagFn().isFromReferencedFile:
                raise RuntimeError("Cannot parent under a locked or referenced transform")
        current = self.getParent()
        if (current is None and target is None) or (
                current is not None and target is not None and current.mnode() == target.mnode()):
            return self
        world = None if relative else self.getMatrix(ws=True)
        if world is not None:
            parent_matrix = Matrix() if target is None else target.getMatrix(ws=True)
            opm = self.getOffsetParentMatrix()
            if abs(parent_matrix.det4x4()) <= 1e-12 or abs(opm.det4x4()) <= 1e-12:
                raise RuntimeError("Cannot preserve world transform with a singular parent or offset matrix")
            for name in ("translate", "rotate", "scale", "shear"):
                plug = self.getPlug(name).mplug()
                writable(plug)
                for index in range(plug.numChildren()):
                    writable(plug.child(index))
        if validate_only:
            return self
        modifier = om2.MDagModifier()
        modifier.reparentNode(self.mnode(), om2.MObject.kNullObj if target is None else target.mnode())
        modifier.doIt()
        # 自分の操作で変えたパスだけ再束縛し、無関係なインスタンスへ切り替えない。
        self._dag_path = om2.MDagPath.getAPathTo(self.mnode())
        if world is not None:
            self.setMatrix(world, ws=True, fast=True)
        return self

    def _fit_transformation(self, value, ws):
        """入力を複製し、親マトリクスとjoint固有成分へ適合させる。

        Args:
            value (Transformation): 元の値。自身を変更しない。
            ws (bool): 検証済みのワールド空間指定。

        Returns:
            tuple: 適合した値・維持するマトリクス・joint判定。
        """
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
        return fitted, matrix, is_joint

    def _apply_transformation_modifiers(self, fitted, is_joint, safe, *, fast=False):
        """TRSより先に補助成分を従来の順序で設定する。現在値と完全に一致する成分は書き込まない。

        Args:
            fitted (Transformation): 対象へ適合した値。
            is_joint (bool): 対象がjointか。
            safe (bool): 書込みできない成分を維持するか。
            fast (bool): Trueなら子のPlugもOpenMayaで更新する。
        """
        modifiers = ["rotateOrder", "rotateAxis"]
        if is_joint:
            modifiers += ["jointOrient", "segmentScaleCompensate"]
        else:
            modifiers += ["rotatePivot", "rotatePivotTranslate", "scalePivot", "scalePivotTranslate"]
        for name in modifiers:
            current = getattr(fitted, name)
            if name in ("rotateAxis", "jointOrient"):
                # 等価なクォータニオンでもチャンネルの数値を不用意に反転しない。
                reference = EulerRotate(self.getPlug(name).get())
                current = current.asEulerRotation().closestSolution(reference)
            if name in ("rotateOrder", "segmentScaleCompensate"):
                if not self._channel_equals(name, current):
                    self.getPlug(name).set(current, safe=safe, fast=fast)
            else:
                current = tuple(current)
                if not self._channel_equals(name, current):
                    self._set_channel_value(name, current, safe=safe, fast=fast)

    def _refit_safe_transformation(self, fitted, matrix):
        """補助成分の実際の状態を読み、safe適用後のTRSを再計算する。

        Args:
            fitted (Transformation): 設定予定の値。
            matrix (Matrix): 維持するローカルマトリクス。

        Returns:
            Transformation: 実際に設定できた補助成分で再計算した値。
        """
        # 書込みできなかった補助成分を実際の状態へ戻してからTRSを計算する。
        actual = self.getTransformation()
        reference = EulerRotate(fitted.rotate)
        reference.reorderIt(actual.rotateOrder)
        actual.rotate = reference
        actual.scale = fitted.scale
        actual.matrix = matrix
        return actual

    def _static_value(self, name):
        """ノード型に組み込みの数値アトリビュートの内部単位の値を、Plugラッパーを作らずに読む。

        ``getPlug(name).get()`` と同じ読取関数(距離cm・角度rad)をMPlugへ直接適用する。
        複合アトリビュートは子の値のtuple、単一の値はその値を返す。計算の途中で何度も読む
        translate・ピボット等のために使い、値はキャッシュしない。ノードが無効な場合と
        読取関数を持たない型は、従来どおり ``getPlug(name).get()`` の結果・例外に委ねる。

        Args:
            name (str): 静的アトリビュートのロング名。

        Returns:
            tuple[float, ...] | object: 複合なら子の値のtuple、それ以外は値。
        """
        if not self.isValid():
            # 無効なノードでは、従来と同じgetPlugの例外を送出する。
            return self.getPlug(name).get()
        plug = self._dependency_fn().findPlug(name, False)
        targets = [plug.child(index) for index in range(plug.numChildren())] if plug.isCompound else [plug]
        values = []
        for target in targets:
            reader = value_reader(target.attribute())
            if reader is False:
                value = self.getPlug(name).get()
                return tuple(value) if plug.isCompound else value
            values.append(reader(target))
        return tuple(values) if plug.isCompound else values[0]

    def _inverse_scale_values(self):
        """jointの有効なinverseScaleを返す。それ以外は単位スケール。"""
        if self.mnode().hasFn(om2.MFn.kJoint) and self._static_value("segmentScaleCompensate"):
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
        """回転アトリビュートをQuaternionへ変換する。

        rotateはノードの回転順序、rotateAxis・jointOrient等はXYZで解釈する。

        Args:
            name (str): 回転アトリビュート名。

        Returns:
            om2.MQuaternion: 新しい回転値。
        """
        if name == "jointOrient" and not self.mnode().hasFn(om2.MFn.kJoint):
            value = self.getPlug(name).get()
        else:
            # 組み込みの角度アトリビュートは、getPlug(name).get()と同じ読取関数でPlugを作らずに読む。
            value = self._static_value(name)
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
                # MItDagが返した有効なパスなので、Node(path) の入力解決を省いて同じ型で包む。
                assemblies.append(Node._wrap_dag_path(path))
            iterator.next()
        return assemblies

    def _parent_world_matrix(self):
        """親Transformのワールドマトリクスを取得する。

        Returns:
            Matrix: 親のワールドマトリクス。親がない、または親に getMatrix がなければ単位マトリクス。
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

    def _check_pivots_writable(self, kinds, preserve):
        """変更するピボットと補償値の全成分が書き込めるか、更新前に検査する。

        Args:
            kinds (Iterable[str]): 検査するピボットの種類(rotate/scale)。
            preserve (bool): Trueは補償値(rotatePivotTranslate等)も検査する。

        Raises:
            RuntimeError: いずれかの成分がロック・入力接続・書込み不能の場合。
        """
        for selected in kinds:
            names = [selected + "Pivot"]
            if preserve:
                names.append(selected + "PivotTranslate")
            for name in names:
                plug = self.getPlug(name).mplug()
                writable(plug)
                for index in range(plug.numChildren()):
                    writable(plug.child(index))

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
            value (tuple | object): 書込み予定の値。複合は成分のtuple。

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
            fast (bool): TrueはUndoなしのOM2更新。通常はcmds。

        Returns:
            Plug | int: Plug.setの戻り値。通常はPlug、safe=Trueは失敗数。
        """
        return Plug.set(self.getPlug(name), tuple(value), safe=safe, fast=fast)

    def _matrix_channel_values(self, matrix, scale_reference=None):
        """マトリクスからtranslate/rotate/scale/shearの設定値を計算する。シーンは更新しない。

        Args:
            matrix: 変換または数値計算に使うマトリクス。
            scale_reference: スケール補正の基準となるノードまたは値。
        """
        source = Matrix(matrix)
        inv_scale = self._inverse_scale_values()
        corrected = source * Matrix(scale=inv_scale)
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
        if self.mnode().hasFn(om2.MFn.kJoint):
            orient *= self._component_quaternion("jointOrient")
        base = (Matrix(translate=tuple(-v for v in sp)) * Matrix(scale=scale, shear=shear)
                * Matrix(translate=sp) * Matrix(translate=spt)
                * Matrix(translate=tuple(-v for v in rp)) * Matrix(rotate=orient)
                * Matrix(translate=rp) * Matrix(translate=rpt)
                * Matrix(scale=tuple(1.0 / v for v in inv_scale)))
        translate = source.translate - base.translate
        return {"translate": Translate(*translate), "rotate": EulerRotate._wrap(rotation),
                "scale": Scale(*scale), "shear": Shear(*shear)}


class Transforms(DagNodes):
    """Joint等の派生型を含むTransform参照のコレクション。

    型検証・色設定・参照のコピーはNodesに従う。座標・マトリクス操作は各対象へ転送する。
    """

    item_class = Transform

    # 単数の呼出し先と返却方針を同じ行で宣言し、追加漏れを防ぐ。
    _bulk_entries = {
        "addConstraint": (Transform.addConstraint, "list"),
        "deleteConstraints": (Transform.deleteConstraints, "list"),
        "transformFn": (Transform.transformFn, "list"),
        "getPivot": (Transform.getPivot, "list"),
        "getBoundingBox": (Transform.getBoundingBox, "list"),
        "getRoot": (Transform.getRoot, "list"),
        "getChildren": (Transform.getChildren, "list"),
        "getSiblings": (Transform.getSiblings, "list"),
        "getShapes": (Transform.getShapes, "list"),
        "getShape": (Transform.getShape, "list"),
        "getShadingEngines": (Transform.getShadingEngines, "list"),
        "getOffsetParentMatrix": (Transform.getOffsetParentMatrix, "list"),
        "getMatrix": (Transform.getMatrix, "list"),
        "getJointOrientQuaternion": (Transform.getJointOrientQuaternion, "list"),
        "getTransformation": (Transform.getTransformation, "list"),
        "getTranslate": (Transform.getTranslate, "list"),
        "getRotate": (Transform.getRotate, "list"),
        "getScale": (Transform.getScale, "list"),
        "getShearing": (Transform.getShearing, "list"),
        "getQuaternion": (Transform.getQuaternion, "list"),
        "getEuler": (Transform.getEuler, "list"),
        "getClosestAxisToVector": (Transform.getClosestAxisToVector, "list"),
        "getUnusedIntermediateShapes": (Transform.getUnusedIntermediateShapes, "list"),
        "freeze": (Transform.freeze, "self"),
        "resetPivot": (Transform.resetPivot, "self"),
        "reset": (Transform.reset, "self"),
        "scaleGeometry": (Transform.scaleGeometry, "self"),
        "setPivot": (Transform.setPivot, "self"),
        "centerPivot": (Transform.centerPivot, "self"),
        "mirrorGeometry": (Transform.mirrorGeometry, "self"),
        "getTransform": (Transform.getTransform, "self"),
        "setParent": (Transform.setParent, "self"),
        "matchTransform": (Transform.matchTransform, "self"),
        "mirrorTransform": (Transform.mirrorTransform, "self"),
        "setOffsetParentMatrix": (Transform.setOffsetParentMatrix, "self"),
        "setMatrix": (Transform.setMatrix, "self"),
        "setTransformation": (Transform.setTransformation, "self"),
        "setTranslate": (Transform.setTranslate, "self"),
        "setRotate": (Transform.setRotate, "self"),
        "setScale": (Transform.setScale, "self"),
        "setShearing": (Transform.setShearing, "self"),
        "setQuaternion": (Transform.setQuaternion, "self"),
        "makeIdentity": (Transform.makeIdentity, "self"),
        "deleteUnusedIntermediateShapes": (Transform.deleteUnusedIntermediateShapes, "self"),
    }
    _bulk_methods = {
        **DagNodes._bulk_methods,
        **{name: entry[0] for name, entry in _bulk_entries.items()},
    }
    _bulk_returns = {
        **DagNodes._bulk_returns,
        **{name: entry[1] for name, entry in _bulk_entries.items()},
    }
    _bulk_per_item_only = frozenset()

    def addConstraint(self, *args, **kwargs):
        """各要素のaddConstraintを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("addConstraint", args, kwargs)

    addConstraint.__signature__ = inspect.signature(Transform.addConstraint)

    def deleteConstraints(self, *args, **kwargs):
        """各要素のdeleteConstraintsを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("deleteConstraints", args, kwargs)

    deleteConstraints.__signature__ = inspect.signature(Transform.deleteConstraints)

    def transformFn(self, *args, **kwargs):
        """各要素のtransformFnを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("transformFn", args, kwargs)

    transformFn.__signature__ = inspect.signature(Transform.transformFn)

    def getPivot(self, *args, **kwargs):
        """各要素のgetPivotを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getPivot", args, kwargs)

    getPivot.__signature__ = inspect.signature(Transform.getPivot)

    def setPivot(self, *args, **kwargs):
        """各要素のsetPivotを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("setPivot", args, kwargs)

    setPivot.__signature__ = inspect.signature(Transform.setPivot)

    def getBoundingBox(self, *args, **kwargs):
        """各要素のgetBoundingBoxを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getBoundingBox", args, kwargs)

    getBoundingBox.__signature__ = inspect.signature(Transform.getBoundingBox)

    def getRoot(self, *args, **kwargs):
        """各要素のgetRootを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getRoot", args, kwargs)

    getRoot.__signature__ = inspect.signature(Transform.getRoot)

    def getChildren(self, *args, **kwargs):
        """各要素のgetChildrenを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getChildren", args, kwargs)

    getChildren.__signature__ = inspect.signature(Transform.getChildren)

    def getSiblings(self, *args, **kwargs):
        """各要素のgetSiblingsを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getSiblings", args, kwargs)

    getSiblings.__signature__ = inspect.signature(Transform.getSiblings)

    def getShapes(self, *args, **kwargs):
        """各要素のgetShapesを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getShapes", args, kwargs)

    getShapes.__signature__ = inspect.signature(Transform.getShapes)

    def getShape(self, *args, **kwargs):
        """各要素のgetShapeを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getShape", args, kwargs)

    getShape.__signature__ = inspect.signature(Transform.getShape)

    def getShadingEngines(self, *args, **kwargs):
        """各要素のgetShadingEnginesを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getShadingEngines", args, kwargs)

    getShadingEngines.__signature__ = inspect.signature(Transform.getShadingEngines)

    def getOffsetParentMatrix(self, *args, **kwargs):
        """各要素のgetOffsetParentMatrixを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getOffsetParentMatrix", args, kwargs)

    getOffsetParentMatrix.__signature__ = inspect.signature(Transform.getOffsetParentMatrix)

    def setOffsetParentMatrix(self, *args, **kwargs):
        """各要素のsetOffsetParentMatrixを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("setOffsetParentMatrix", args, kwargs)

    setOffsetParentMatrix.__signature__ = inspect.signature(Transform.setOffsetParentMatrix)

    def getMatrix(self, *args, **kwargs):
        """各要素のgetMatrixを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getMatrix", args, kwargs)

    getMatrix.__signature__ = inspect.signature(Transform.getMatrix)

    def setMatrix(self, *args, **kwargs):
        """各要素のsetMatrixを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("setMatrix", args, kwargs)

    setMatrix.__signature__ = inspect.signature(Transform.setMatrix)

    def getJointOrientQuaternion(self, *args, **kwargs):
        """各要素のgetJointOrientQuaternionを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getJointOrientQuaternion", args, kwargs)

    getJointOrientQuaternion.__signature__ = inspect.signature(Transform.getJointOrientQuaternion)

    def getTransformation(self, *args, **kwargs):
        """各要素のgetTransformationを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getTransformation", args, kwargs)

    getTransformation.__signature__ = inspect.signature(Transform.getTransformation)

    def setTransformation(self, *args, **kwargs):
        """各要素のsetTransformationを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("setTransformation", args, kwargs)

    setTransformation.__signature__ = inspect.signature(Transform.setTransformation)

    def getTranslate(self, *args, **kwargs):
        """各要素のgetTranslateを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getTranslate", args, kwargs)

    getTranslate.__signature__ = inspect.signature(Transform.getTranslate)

    def setTranslate(self, *args, **kwargs):
        """各要素のsetTranslateを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("setTranslate", args, kwargs)

    setTranslate.__signature__ = inspect.signature(Transform.setTranslate)

    def getRotate(self, *args, **kwargs):
        """各要素のgetRotateを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getRotate", args, kwargs)

    getRotate.__signature__ = inspect.signature(Transform.getRotate)

    def setRotate(self, *args, **kwargs):
        """各要素のsetRotateを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("setRotate", args, kwargs)

    setRotate.__signature__ = inspect.signature(Transform.setRotate)

    def getScale(self, *args, **kwargs):
        """各要素のgetScaleを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getScale", args, kwargs)

    getScale.__signature__ = inspect.signature(Transform.getScale)

    def setScale(self, *args, **kwargs):
        """各要素のsetScaleを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("setScale", args, kwargs)

    setScale.__signature__ = inspect.signature(Transform.setScale)

    def getShearing(self, *args, **kwargs):
        """各要素のgetShearingを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getShearing", args, kwargs)

    getShearing.__signature__ = inspect.signature(Transform.getShearing)

    def setShearing(self, *args, **kwargs):
        """各要素のsetShearingを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("setShearing", args, kwargs)

    setShearing.__signature__ = inspect.signature(Transform.setShearing)

    def getQuaternion(self, *args, **kwargs):
        """各要素のgetQuaternionを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getQuaternion", args, kwargs)

    getQuaternion.__signature__ = inspect.signature(Transform.getQuaternion)

    def setQuaternion(self, *args, **kwargs):
        """各要素のsetQuaternionを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("setQuaternion", args, kwargs)

    setQuaternion.__signature__ = inspect.signature(Transform.setQuaternion)

    def getEuler(self, *args, **kwargs):
        """各要素のgetEulerを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getEuler", args, kwargs)

    getEuler.__signature__ = inspect.signature(Transform.getEuler)

    def getClosestAxisToVector(self, *args, **kwargs):
        """各要素のgetClosestAxisToVectorを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getClosestAxisToVector", args, kwargs)

    getClosestAxisToVector.__signature__ = inspect.signature(Transform.getClosestAxisToVector)

    def getUnusedIntermediateShapes(self, *args, **kwargs):
        """各要素のgetUnusedIntermediateShapesを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getUnusedIntermediateShapes", args, kwargs)

    getUnusedIntermediateShapes.__signature__ = inspect.signature(Transform.getUnusedIntermediateShapes)

    def freeze(self, *args, **kwargs):
        """各要素のfreezeを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("freeze", args, kwargs)

    freeze.__signature__ = inspect.signature(Transform.freeze)

    def resetPivot(self, *args, **kwargs):
        """各要素のresetPivotを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("resetPivot", args, kwargs)

    resetPivot.__signature__ = inspect.signature(Transform.resetPivot)

    def reset(self, *args, **kwargs):
        """各要素のresetを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("reset", args, kwargs)

    reset.__signature__ = inspect.signature(Transform.reset)

    def scaleGeometry(self, *args, **kwargs):
        """各要素のscaleGeometryを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("scaleGeometry", args, kwargs)

    scaleGeometry.__signature__ = inspect.signature(Transform.scaleGeometry)

    def centerPivot(self, *args, **kwargs):
        """各要素のcenterPivotを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("centerPivot", args, kwargs)

    centerPivot.__signature__ = inspect.signature(Transform.centerPivot)

    def mirrorGeometry(self, *args, **kwargs):
        """各要素のmirrorGeometryを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("mirrorGeometry", args, kwargs)

    mirrorGeometry.__signature__ = inspect.signature(Transform.mirrorGeometry)

    def getTransform(self, *args, **kwargs):
        """各要素のgetTransformを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("getTransform", args, kwargs)

    getTransform.__signature__ = inspect.signature(Transform.getTransform)

    def setParent(self, *args, **kwargs):
        """各要素のsetParentを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("setParent", args, kwargs)

    setParent.__signature__ = inspect.signature(Transform.setParent)

    def matchTransform(self, *args, **kwargs):
        """各要素のmatchTransformを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("matchTransform", args, kwargs)

    matchTransform.__signature__ = inspect.signature(Transform.matchTransform)

    def mirrorTransform(self, *args, **kwargs):
        """各要素のmirrorTransformを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("mirrorTransform", args, kwargs)

    mirrorTransform.__signature__ = inspect.signature(Transform.mirrorTransform)

    def makeIdentity(self, *args, **kwargs):
        """各要素のmakeIdentityを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("makeIdentity", args, kwargs)

    makeIdentity.__signature__ = inspect.signature(Transform.makeIdentity)

    def deleteUnusedIntermediateShapes(self, *args, **kwargs):
        """各要素のdeleteUnusedIntermediateShapesを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Transforms | list: コレクション自身。
        """
        return self._dispatch_shared("deleteUnusedIntermediateShapes", args, kwargs)

    deleteUnusedIntermediateShapes.__signature__ = inspect.signature(Transform.deleteUnusedIntermediateShapes)
