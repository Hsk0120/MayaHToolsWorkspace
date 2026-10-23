"""対応する値更新のcmds/OpenMayaバックエンド。独自プラグインは使わない。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorator import _is_fast
from .attributeType import NUMERIC_WRITERS, _convert_units


def writable(plug, _fn=None):
    """ロック・入力接続・書込み不能アトリビュートをAPIで検査する。

    Args:
        plug (om2.MPlug): 検査するプラグ。
        _fn (om2.MFnAttribute | None): 同じ更新内で生成したアトリビュートの
            function set。省略時は新しく生成する。値や検査結果はキャッシュしない。

    Raises:
        RuntimeError: ロック・入力接続・書込み禁止がある場合。
    """
    current = plug
    while True:
        if current.isLocked or current.isDestination:
            raise RuntimeError("Attribute is locked or connected: " + plug.name())
        if current.isChild:
            current = current.parent()
        elif current.isElement:
            current = current.array()
        else:
            break
    if not (_fn if _fn is not None else om2.MFnAttribute(plug.attribute())).writable:
        raise RuntimeError("Attribute is not writable: " + plug.name())


def check_range(plug, value, _fn=None):
    """cmds.setAttrと同様、アトリビュートに設定されたハード範囲を検査する。

    Args:
        plug (om2.MPlug): 検査するプラグ。
        value (float): 設定予定の値。単位型ではcm/rad/秒。
        _fn (om2.MFnNumericAttribute | om2.MFnUnitAttribute | None): 同じ更新内で
            生成したfunction set。範囲と単位定義は呼出しごとに照会する。

    Raises:
        RuntimeError: 値が設定されたハード範囲外の場合。
    """
    fn = _fn
    if fn is None:
        attribute = plug.attribute()
        if attribute.hasFn(om2.MFn.kUnitAttribute):
            fn = om2.MFnUnitAttribute(attribute)
        elif attribute.hasFn(om2.MFn.kNumericAttribute):
            fn = om2.MFnNumericAttribute(attribute)
        else:
            return
    for exists, getter, lower in ((fn.hasMin, fn.getMin, True), (fn.hasMax, fn.getMax, False)):
        if not exists():
            continue
        limit = getter()
        if isinstance(limit, (om2.MAngle, om2.MDistance, om2.MTime)):
            limit = _convert_units(plug, limit, to_ui=False)
        if (lower and value < limit) or (not lower and value > limit):
            raise RuntimeError("Value outside attribute limits: " + plug.name())


def _prepared_writes(plug, value):
    """全成分の型・制限を更新前に検査し、直接書込みの列を組み立てる。

    Args:
        plug (om2.MPlug): 書込み先。
        value (object): 内部単位の入力値。

    Returns:
        list[tuple]: setter・プラグ・変換済み値の列。

    Raises:
        NotImplementedError: API 2.0で値を構築できない型の場合。
    """
    attribute = plug.attribute()
    unit = attribute.hasFn(om2.MFn.kUnitAttribute)
    numeric = not unit and attribute.hasFn(om2.MFn.kNumericAttribute)
    fn = (om2.MFnUnitAttribute(attribute) if unit else
          om2.MFnNumericAttribute(attribute) if numeric else om2.MFnAttribute(attribute))
    writable(plug, fn)
    if plug.isCompound:
        values = tuple(value)
        if len(values) != plug.numChildren():
            raise ValueError("Compound value length mismatch")
        writes = []
        for i, item in enumerate(values):
            writes.extend(_prepared_writes(plug.child(i), item))
        return writes
    owner = None
    if unit:
        check_range(plug, value, fn)
        kind = fn.unitType()
        if kind == om2.MFnUnitAttribute.kAngle:
            setter, result = om2.MPlug.setMAngle, om2.MAngle(value, om2.MAngle.kRadians)
        elif kind == om2.MFnUnitAttribute.kDistance:
            setter, result = om2.MPlug.setMDistance, om2.MDistance(value, om2.MDistance.kCentimeters)
        else:
            setter, result = om2.MPlug.setMTime, om2.MTime(value, om2.MTime.kSeconds)
    elif attribute.hasFn(om2.MFn.kEnumAttribute):
        setter, result = om2.MPlug.setInt, int(value)
    elif numeric:
        check_range(plug, value, fn)
        writer = NUMERIC_WRITERS.get(fn.numericType())
        if writer is None:
            raise NotImplementedError("fast numeric type is not supported: " + plug.name())
        setter, converter = writer
        result = converter(value)
    else:
        setter, result, owner = prepare_data(attribute, value, name=plug.name())
    return [(setter, plug, result, owner)]


def set_plug(plug, value):
    """全成分を事前検証してMPlugへ設定する。Undoには記録しない。

    Args:
        plug (om2.MPlug): 更新対象。
        value (object): 角度rad、距離cm、時間秒の値。

    Raises:
        NotImplementedError: API 2.0で未対応の型の場合。更新前に拒否する。
    """
    writes = _prepared_writes(plug, value)
    for setter, target, item, owner in writes:
        # データを受け渡すまで作成用function setを保持する。
        setter(target, item)


def set_attr(name, *values, **kwargs):
    """既存のsetAttrと同じ値入力を、明示fast時だけMPlugへ渡す。

    Args:
        name (str): アトリビュート名。
        *values: cmds.setAttr と同じ形・現在の Maya 単位の値。
        **kwargs: setAttr のフラグ。fast 時の対応フラグは限定される。
    """
    if not _is_fast():
        return cmds.setAttr(name, *values, **kwargs)
    selection = om2.MSelectionList()
    selection.add(name)
    plug = selection.getPlug(0)
    flags = {"lock": "isLocked", "keyable": "isKeyable", "channelBox": "isChannelBox"}
    if not values and kwargs and set(kwargs) <= set(flags):
        for key, value in kwargs.items():
            setattr(plug, flags[key], bool(value))
        return
    if set(kwargs) - {"type"}:
        raise NotImplementedError("Unsupported fast setAttr flags")
    value = values[0] if len(values) == 1 else values
    set_plug(plug, _convert_units(plug, value, to_ui=False))


def prepare_data(attribute, value, *, name=None):
    """MPlugを必要とせず、行列・typed dataの型と値を検査する。

    Args:
        attribute (MObject): 登録前でもよいアトリビュート定義。
        value (object): 設定予定の値。
        name (str | None): エラー表示用の名前。

    Returns:
        tuple: setter、変換済み値、書込み終了まで保持するfunction set。
    """
    label = name or om2.MFnAttribute(attribute).name
    owner = None
    if attribute.hasFn(om2.MFn.kMatrixAttribute):
        matrix = value if isinstance(value, om2.MMatrix) else om2.MMatrix(value)
        owner = om2.MFnMatrixData()
        setter, result = om2.MPlug.setMObject, owner.create(matrix)
    elif attribute.hasFn(om2.MFn.kTypedAttribute):
        kind = om2.MFnTypedAttribute(attribute).attrType()
        factories = {
            om2.MFnData.kDoubleArray: om2.MFnDoubleArrayData,
            om2.MFnData.kIntArray: om2.MFnIntArrayData,
            om2.MFnData.kStringArray: om2.MFnStringArrayData,
            om2.MFnData.kVectorArray: om2.MFnVectorArrayData,
            om2.MFnData.kPointArray: om2.MFnPointArrayData,
            om2.MFnData.kMatrixArray: om2.MFnMatrixArrayData,
        }
        if kind == om2.MFnData.kString:
            setter, result = om2.MPlug.setString, str(value)
        elif kind == om2.MFnData.kMatrix:
            matrix = value if isinstance(value, om2.MMatrix) else om2.MMatrix(value)
            owner = om2.MFnMatrixData()
            setter, result = om2.MPlug.setMObject, owner.create(matrix)
        elif kind in factories:
            if kind == om2.MFnData.kMatrixArray:
                value = [item if isinstance(item, om2.MMatrix) else om2.MMatrix(item) for item in value]
            owner = factories[kind]()
            setter, result = om2.MPlug.setMObject, owner.create(value)
        else:
            raise NotImplementedError("fast typed data is not supported: " + label)
    else:
        raise NotImplementedError("fast attribute type is not supported: " + label)
    return setter, result, owner
