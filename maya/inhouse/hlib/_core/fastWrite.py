"""対応する値更新のcmds/OpenMayaバックエンド。独自プラグインは使わない。"""
import maya.cmds as cmds
import maya.api.OpenMaya as om
from ..decorators._fast import is_fast
from .attributeType import NUMERIC_WRITERS
from .unitValue import convert


def writable(plug, _fn=None):
    """ロック・入力接続・書込み不能アトリビュートをAPIで検査する。

    Args:
        plug (om.MPlug): 検査するプラグ。
        _fn (om.MFnAttribute | None): 同じ更新内で生成したアトリビュートの
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
    if not (_fn if _fn is not None else om.MFnAttribute(plug.attribute())).writable:
        raise RuntimeError("Attribute is not writable: " + plug.name())


def check_range(plug, value, _fn=None):
    """cmds.setAttrと同様、アトリビュートに設定されたハード範囲を検査する。

    Args:
        plug (om.MPlug): 検査するプラグ。
        value (float): 設定予定の値。単位型ではcm/rad/秒。
        _fn (om.MFnNumericAttribute | om.MFnUnitAttribute | None): 同じ更新内で
            生成したfunction set。範囲と単位定義は呼出しごとに照会する。

    Raises:
        RuntimeError: 値が設定されたハード範囲外の場合。
    """
    fn = _fn
    if fn is None:
        attribute = plug.attribute()
        if attribute.hasFn(om.MFn.kUnitAttribute):
            fn = om.MFnUnitAttribute(attribute)
        elif attribute.hasFn(om.MFn.kNumericAttribute):
            fn = om.MFnNumericAttribute(attribute)
        else:
            return
    for exists, getter, lower in ((fn.hasMin, fn.getMin, True), (fn.hasMax, fn.getMax, False)):
        if not exists():
            continue
        limit = getter()
        if isinstance(limit, (om.MAngle, om.MDistance, om.MTime)):
            limit = convert(plug, limit, to_ui=False)
        if (lower and value < limit) or (not lower and value > limit):
            raise RuntimeError("Value outside attribute limits: " + plug.name())


def set_plug(plug, value):
    """MPlugへ単位を維持して直接設定する。未対応型は変更前に拒否する。"""
    attribute = plug.attribute()
    # 型判定・function set は1回の更新内で共有する。範囲・ロック等の
    # 可変情報は毎回照会し、動的アトリビュートの削除をまたぐキャッシュは持たない。
    unit = attribute.hasFn(om.MFn.kUnitAttribute)
    numeric = not unit and attribute.hasFn(om.MFn.kNumericAttribute)
    fn = (om.MFnUnitAttribute(attribute) if unit else
          om.MFnNumericAttribute(attribute) if numeric else om.MFnAttribute(attribute))
    writable(plug, fn)
    if plug.isCompound:
        values = tuple(value)
        if len(values) != plug.numChildren():
            raise ValueError("Compound value length mismatch")
        for i in range(plug.numChildren()):
            writable(plug.child(i))
        for i, item in enumerate(values):
            set_plug(plug.child(i), item)
    elif unit:
        check_range(plug, value, fn)
        kind = fn.unitType()
        if kind == om.MFnUnitAttribute.kAngle:
            plug.setMAngle(om.MAngle(value, om.MAngle.kRadians))
        elif kind == om.MFnUnitAttribute.kDistance:
            plug.setMDistance(om.MDistance(value, om.MDistance.kCentimeters))
        else:
            plug.setMTime(om.MTime(value, om.MTime.kSeconds))
    elif attribute.hasFn(om.MFn.kEnumAttribute):
        plug.setInt(int(value))
    elif numeric:
        check_range(plug, value, fn)
        kind = fn.numericType()
        writer = NUMERIC_WRITERS.get(kind)
        if writer is None:
            raise NotImplementedError("fast numeric type is not supported: " + plug.name())
        setter, convert = writer
        setter(plug, convert(value))
    elif attribute.hasFn(om.MFn.kMatrixAttribute):
        # hlib の Matrix は om.MMatrix の派生なので、変換せずにそのまま渡せる。
        matrix = value if isinstance(value, om.MMatrix) else om.MMatrix(value)
        plug.setMObject(om.MFnMatrixData().create(matrix))
    elif attribute.hasFn(om.MFn.kTypedAttribute):
        kind = om.MFnTypedAttribute(attribute).attrType()
        factories = {
            om.MFnData.kDoubleArray: om.MFnDoubleArrayData,
            om.MFnData.kIntArray: om.MFnIntArrayData,
            om.MFnData.kStringArray: om.MFnStringArrayData,
            om.MFnData.kVectorArray: om.MFnVectorArrayData,
            om.MFnData.kPointArray: om.MFnPointArrayData,
        }
        if kind == om.MFnData.kString:
            plug.setString(str(value))
        elif kind == om.MFnData.kMatrix:
            matrix = value if isinstance(value, om.MMatrix) else om.MMatrix(value)
            plug.setMObject(om.MFnMatrixData().create(matrix))
        elif kind in factories:
            plug.setMObject(factories[kind]().create(value))
        else:
            raise NotImplementedError("fast typed data is not supported: " + plug.name())
    else:
        raise NotImplementedError("fast attribute type is not supported: " + plug.name())


def set_attr(name, *values, **kwargs):
    """既存のsetAttrと同じ値入力を、明示fast時だけMPlugへ渡す。"""
    if not is_fast():
        return cmds.setAttr(name, *values, **kwargs)
    selection = om.MSelectionList()
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
    set_plug(plug, convert(plug, value, to_ui=False))
