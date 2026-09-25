"""対応する値更新のcmds/OpenMayaバックエンド。独自プラグインは使わない。"""
import maya.cmds as cmds
import maya.api.OpenMaya as om
from ..decorators._fast import is_fast


def writable(plug):
    """ロック・入力接続・書込み不能属性をAPIで検査する。"""
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
    if not om.MFnAttribute(plug.attribute()).writable:
        raise RuntimeError("Attribute is not writable: " + plug.name())


def check_range(plug, value):
    """cmds.setAttrと同様、属性に設定されたハード範囲を検査する。"""
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
            limit = limit.asUnits(type(limit).uiUnit())
        if (lower and value < limit) or (not lower and value > limit):
            raise RuntimeError("Value outside attribute limits: " + plug.name())


def set_plug(plug, value):
    """MPlugへ単位を維持して直接設定する。未対応型は変更前に拒否する。"""
    writable(plug)
    attribute = plug.attribute()
    if plug.isCompound:
        values = tuple(value)
        if len(values) != plug.numChildren():
            raise ValueError("Compound value length mismatch")
        for i in range(plug.numChildren()):
            writable(plug.child(i))
        for i, item in enumerate(values):
            set_plug(plug.child(i), item)
    elif attribute.hasFn(om.MFn.kUnitAttribute):
        check_range(plug, value)
        kind = om.MFnUnitAttribute(attribute).unitType()
        if kind == om.MFnUnitAttribute.kAngle:
            plug.setMAngle(om.MAngle(value, om.MAngle.uiUnit()))
        elif kind == om.MFnUnitAttribute.kDistance:
            plug.setMDistance(om.MDistance(value, om.MDistance.uiUnit()))
        else:
            plug.setMTime(om.MTime(value, om.MTime.uiUnit()))
    elif attribute.hasFn(om.MFn.kEnumAttribute):
        plug.setInt(int(value))
    elif attribute.hasFn(om.MFn.kNumericAttribute):
        check_range(plug, value)
        kind = om.MFnNumericAttribute(attribute).numericType()
        if kind == om.MFnNumericData.kBoolean:
            plug.setBool(bool(value))
        elif kind in (om.MFnNumericData.kByte, om.MFnNumericData.kChar,
                      om.MFnNumericData.kShort, om.MFnNumericData.kInt):
            plug.setInt(int(value))
        elif kind == om.MFnNumericData.kFloat:
            plug.setFloat(float(value))
        elif kind == om.MFnNumericData.kDouble:
            plug.setDouble(float(value))
        else:
            raise NotImplementedError("fast numeric type is not supported: " + plug.name())
    elif attribute.hasFn(om.MFn.kMatrixAttribute):
        matrix = value.to_mmatrix() if hasattr(value, "to_mmatrix") else om.MMatrix(value)
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
            matrix = value.to_mmatrix() if hasattr(value, "to_mmatrix") else om.MMatrix(value)
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
    set_plug(plug, value)
