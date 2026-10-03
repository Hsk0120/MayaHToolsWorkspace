"""MPlugの単位定義に基づく内部単位とコマンド単位の境界変換。"""

import maya.api.OpenMaya as om2


def convert(plug, value, to_ui=True):
    """数値・複合値を変換する。単位のない型はそのまま返す。

    Args:
        plug (om2.MPlug): 型を判定するプラグ。
        value (object): 変換する値。
        to_ui (bool): Trueはcm/rad/秒からUI単位、Falseは逆方向。

    Returns:
        object: 変換した値。行列や型付き配列の成分は単位変換しない。
    """
    if plug.isCompound:
        return tuple(convert(plug.child(i), item, to_ui) for i, item in enumerate(value))
    attribute = plug.attribute()
    if not attribute.hasFn(om2.MFn.kUnitAttribute):
        return value
    cls, internal = {
        om2.MFnUnitAttribute.kAngle: (om2.MAngle, om2.MAngle.kRadians),
        om2.MFnUnitAttribute.kDistance: (om2.MDistance, om2.MDistance.kCentimeters),
        om2.MFnUnitAttribute.kTime: (om2.MTime, om2.MTime.kSeconds),
    }[om2.MFnUnitAttribute(attribute).unitType()]
    if isinstance(value, cls):
        return value.asUnits(cls.uiUnit() if to_ui else internal)
    source, target = (internal, cls.uiUnit()) if to_ui else (cls.uiUnit(), internal)
    return cls(value, source).asUnits(target)
