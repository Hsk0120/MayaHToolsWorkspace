"""動的アトリビュートをシーン変更前に組み立て、OpenMayaで追加する。"""

import maya.api.OpenMaya as om2

from .nodeEdit import require_editable


_NUMERIC_TYPES = {
    "bool": om2.MFnNumericData.kBoolean, "byte": om2.MFnNumericData.kByte,
    "char": om2.MFnNumericData.kChar, "short": om2.MFnNumericData.kShort,
    "long": om2.MFnNumericData.kInt, "float": om2.MFnNumericData.kFloat,
    "double": om2.MFnNumericData.kDouble,
}
_DATA_TYPES = {
    "string": om2.MFnData.kString, "stringArray": om2.MFnData.kStringArray,
    "doubleArray": om2.MFnData.kDoubleArray, "floatArray": om2.MFnData.kFloatArray,
    "Int32Array": om2.MFnData.kIntArray, "vectorArray": om2.MFnData.kVectorArray,
    "pointArray": om2.MFnData.kPointArray, "matrixArray": om2.MFnData.kMatrixArray,
    "componentList": om2.MFnData.kComponentList, "matrix": om2.MFnData.kMatrix,
    "mesh": om2.MFnData.kMesh, "nurbsCurve": om2.MFnData.kNurbsCurve,
    "nurbsSurface": om2.MFnData.kNurbsSurface, "lattice": om2.MFnData.kLattice,
}
_PROPERTIES = {
    "keyable": "keyable", "hidden": "hidden", "readable": "readable",
    "writable": "writable", "storable": "storable", "connectable": "connectable",
    "multi": "array", "indexMatters": "indexMatters", "cachedInternally": "cached",
    "usedAsColor": "usedAsColor", "usedAsFilename": "usedAsFilename",
}
_DEFINITION_FLAGS = {"longName", "shortName", "attributeType", "dataType", "defaultValue",
                     "minValue", "maxValue", "softMinValue", "softMaxValue", "enumName",
                     "niceName", "numberOfChildren", "disconnectBehaviour", "hasMinValue",
                     "hasMaxValue", "hasSoftMinValue", "hasSoftMaxValue"} | set(_PROPERTIES)


def _build(flags, children=None):
    """未登録のアトリビュート定義を作る。失敗してもシーンは変えない。

    Args:
        flags (dict): 正規化済みのaddAttrフラグ。
        children (list[MObject] | None): 先に構築した子定義。

    Returns:
        MObject: 新しいアトリビュート定義。
    """
    unsupported = set(flags) - _DEFINITION_FLAGS
    if unsupported:
        raise NotImplementedError("Unsupported fast addAttr flags: " + ", ".join(sorted(unsupported)))
    name = flags.get("longName") or flags.get("shortName")
    short = flags.get("shortName") or name
    if not isinstance(name, str) or not name:
        raise ValueError("Specify longName or shortName")
    kind = flags.get("attributeType", "double")
    default = flags.get("defaultValue", 0)
    if flags.get("dataType"):
        kind = flags["dataType"]
        if kind not in _DATA_TYPES:
            raise NotImplementedError("Unsupported fast dataType: " + str(kind))
        fn = om2.MFnTypedAttribute()
        obj = fn.create(name, short, _DATA_TYPES[kind])
    elif kind in _NUMERIC_TYPES:
        fn = om2.MFnNumericAttribute()
        obj = fn.create(name, short, _NUMERIC_TYPES[kind], default)
    elif children and kind.startswith(("double", "float", "long", "short")):
        if len(children) not in (2, 3):
            raise NotImplementedError("fast numeric compounds support two or three children")
        fn = om2.MFnNumericAttribute()
        obj = fn.create(name, short, *children)
    elif kind in ("doubleAngle", "doubleLinear", "time"):
        fn = om2.MFnUnitAttribute()
        units = {"doubleAngle": fn.kAngle, "doubleLinear": fn.kDistance, "time": fn.kTime}
        # MFnUnitAttribute.createのtime既定値も現在の時間単位で受け取る。
        # Node.addAttrが事前変換したフレーム値を再度秒へ変換しない。
        obj = fn.create(name, short, units[kind], default)
    elif kind == "enum":
        fn = om2.MFnEnumAttribute()
        obj = fn.create(name, short, int(default))
        next_value = 0
        for field in str(flags.get("enumName", "")).split(":"):
            if "=" in field:
                field, raw_value = field.rsplit("=", 1)
                next_value = int(raw_value)
            if field:
                fn.addField(field, next_value)
            next_value += 1
    elif kind == "message":
        fn = om2.MFnMessageAttribute()
        obj = fn.create(name, short)
    elif kind in ("matrix", "fltMatrix"):
        fn = om2.MFnMatrixAttribute()
        obj = fn.create(name, short, fn.kFloat if kind == "fltMatrix" else fn.kDouble)
    elif kind == "compound":
        fn = om2.MFnCompoundAttribute()
        obj = fn.create(name, short)
        for child in children or []:
            fn.addChild(child)
    else:
        raise NotImplementedError("Unsupported fast attributeType: " + str(kind))
    base = om2.MFnAttribute(obj)
    for flag, property_name in _PROPERTIES.items():
        if flag in flags:
            setattr(base, property_name, bool(flags[flag]))
    if "niceName" in flags:
        base.setNiceNameOverride(str(flags["niceName"]))
    if "disconnectBehaviour" in flags:
        base.disconnectBehavior = int(flags["disconnectBehaviour"])
    for flag, method in (("minValue", "setMin"), ("maxValue", "setMax"),
                         ("softMinValue", "setSoftMin"), ("softMaxValue", "setSoftMax")):
        enabled = {"minValue": "hasMinValue", "maxValue": "hasMaxValue",
                   "softMinValue": "hasSoftMinValue", "softMaxValue": "hasSoftMaxValue"}[flag]
        if flag in flags and flags.get(enabled, True):
            value = flags[flag]
            getattr(fn, method)(value)
    return obj


def _attach(node, attribute):
    """構築済み定義をノードへ一回で追加する。

    Args:
        node (Node): 追加先。
        attribute (MObject): シーン未登録のアトリビュート定義。
    """
    require_editable(node.mnode())
    fn = om2.MFnDependencyNode(node.mnode())
    name = om2.MFnAttribute(attribute).name
    if fn.hasAttribute(name):
        raise RuntimeError("Attribute already exists: " + name)
    modifier = om2.MDGModifier()
    modifier.addAttribute(node.mnode(), attribute)
    modifier.doIt()


def add_attribute(node, flags):
    """単一の動的アトリビュートを追加する。

    Args:
        node (Node): 追加先。
        flags (dict): 正規化済みのaddAttrフラグ。
    """
    _attach(node, _build(flags))


def create_extra_attribute(node, name, flags, numeric, count, deferred,
                           child_names, child_short_names, child_suffixes, sub_type):
    """Node.addAttrの親子定義を登録前に全て作る。

    Args:
        node (Node): 追加先。
        name (str): 親名。
        flags (dict): 親フラグ。
        numeric (Match | None): 数値複合型の一致結果。
        count (int): 子数。
        deferred (object): 子の既定値。
        child_names (Sequence[str] | None): 子の長名。
        child_short_names (Sequence[str] | None): 子の短名。
        child_suffixes (Sequence[str] | None): 子名の接尾辞。
        sub_type (str | None): 子の型。

    Returns:
        tuple | None: 型付き既定値の検証済み書込み計画。データownerを含む。
    """
    flags = dict(flags)
    children = []
    if count:
        suffixes = child_suffixes or ("RGBA" if flags.get("usedAsColor") else "XYZW")[:count]
        names = list(child_names or [name + suffix for suffix in suffixes])
        shorts = list(child_short_names or names)
        if len(names) != count or len(shorts) != count:
            raise ValueError("Child name count does not match its type")
        limits = {key: flags.pop(key) for key in ("minValue", "maxValue", "softMinValue", "softMaxValue")
                  if key in flags}
        for i, child_name in enumerate(names):
            child = {"longName": child_name, "shortName": shorts[i],
                     "attributeType": sub_type or (numeric.group(1) if numeric else "double"),
                     "keyable": bool(flags.get("keyable", False))}
            for key, value in limits.items():
                child[key] = value[i] if isinstance(value, (tuple, list)) else value
            if deferred is not None:
                child["defaultValue"] = deferred[i] if isinstance(deferred, (tuple, list)) else deferred
            children.append(_build(child))
    attribute = _build(flags, children)
    prepared = None
    if deferred is not None and not count:
        from .fastWrite import prepare_data
        definition = om2.MFnAttribute(attribute)
        if definition.array:
            raise TypeError("Set an array element instead of the array plug")
        if not definition.writable:
            raise RuntimeError("Attribute is not writable: " + name)
        if (attribute.hasFn(om2.MFn.kMatrixAttribute) or
                attribute.hasFn(om2.MFn.kTypedAttribute) and
                om2.MFnTypedAttribute(attribute).attrType() == om2.MFnData.kMatrix):
            from ..maths import Matrix
            deferred = Matrix(deferred)
        prepared = prepare_data(attribute, deferred, name=name)
    _attach(node, attribute)
    return prepared
