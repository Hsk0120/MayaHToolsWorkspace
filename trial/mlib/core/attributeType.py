"""アトリビュートの型名を Maya API 2.0 のアトリビュート定義から求める(シーンを変更しない)。

Plug の派生クラスの選択(:class:`~mlib.core.registry.NodeRegistry` のアトリビュート型キー)と、
``Plug.set()`` の配列型の判定に使う型名を、``cmds.getAttr(<プラグ名>, type=True)`` と
同じ文字列で返す。``cmds.getAttr(type=True)`` は存在しないマルチアトリビュートの要素を問い合わせると
要素を作り(blendShape の ``weight[i]`` では ``parentDirectory[i]`` なども作られる)、
nurbsSurface の ``patchUVIds`` の存在しない要素では Maya が異常終了し、mesh の内部アトリビュート
(``edge[i]``・``face[i]`` など)では例外になる。この関数はプラグの値を読まず、
アトリビュート定義(``MFnAttribute`` の各派生クラス)だけから型名を決めるため、存在しない要素でも
シーンを変更せず、評価も起こさない。

アトリビュートの種類と結果:

.. list-table::
   :header-rows: 1

   * - アトリビュート
     - 結果
   * - 数値(``MFnNumericAttribute``)
     - ``bool``/``byte``/``char``/``short``/``long``/``float``/``double``/``addr`` と、
       数値のコンパウンドアトリビュートの ``double3``/``float3``/``long2`` など(``numericType()`` による)
   * - 単位(``MFnUnitAttribute``)
     - ``doubleLinear``/``floatLinear``/``doubleAngle``/``floatAngle``/``time``
   * - enum・message
     - ``enum``・``message``
   * - マトリクス(``MFnMatrixAttribute``)
     - ``matrix`` (float のマトリクスも ``cmds.getAttr`` と同じく ``matrix``)
   * - 型付き(``MFnTypedAttribute``)
     - ``string``/``matrix``/``doubleArray``/``Int32Array``/``mesh``/``nurbsCurve`` など。
       API 2.0 に列挙値の無いデータ型(``Int64Array``・``floatVectorArray``・
       データ型指定の ``double3`` など)は ``MFnAttribute.getAddAttrCmd()`` のデータ型名
   * - コンパウンドアトリビュート(``MFnCompoundAttribute``)・lightData
     - ``TdataCompound``
   * - 不透明(opaque)
     - ``getAddAttrCmd()`` のアトリビュート型名(``TattributeCtypeOf<...>``)

保持する値によって ``cmds.getAttr(type=True)`` の結果が変わるアトリビュート(generic アトリビュート、
任意のデータを受け付ける typed アトリビュート、``geometry`` 型など)は、値を読まない限り
型名が決まらないため ``None`` を返す。

例外として、mesh の ``controlPoints`` はアトリビュート定義が ``double3`` でも、Maya が内部で
float の頂点座標として扱い ``cmds.getAttr(type=True)`` が ``float3`` を返すため、
``float3`` を返す(nurbsCurve・nurbsSurface・lattice は ``double3``)。
"""

import math
import re
from functools import partial

import maya.api.OpenMaya as om2

from ..util import _angle_unit

__all__ = ["attributeType", "is_internal_data_type", "typed_data", "value_reader"]

_N = om2.MFnNumericData
_D = om2.MFnData

#: apiType だけで型名が決まるアトリビュート。
_API_TYPE_NAMES = {
    om2.MFn.kDoubleLinearAttribute: "doubleLinear",
    om2.MFn.kFloatLinearAttribute: "floatLinear",
    om2.MFn.kDoubleAngleAttribute: "doubleAngle",
    om2.MFn.kFloatAngleAttribute: "floatAngle",
    om2.MFn.kTimeAttribute: "time",
    om2.MFn.kEnumAttribute: "enum",
    om2.MFn.kMessageAttribute: "message",
    om2.MFn.kMatrixAttribute: "matrix",
    om2.MFn.kFloatMatrixAttribute: "matrix",
    om2.MFn.kCompoundAttribute: "TdataCompound",
    om2.MFn.kLightDataAttribute: "TdataCompound",
}

#: 数値アトリビュートの ``numericType()`` と型名。
_NUMERIC_TYPE_NAMES = {
    _N.kBoolean: "bool",
    _N.kByte: "byte",
    _N.kChar: "char",
    _N.kShort: "short",
    _N.k2Short: "short2",
    _N.k3Short: "short3",
    _N.kInt: "long",
    _N.k2Int: "long2",
    _N.k3Int: "long3",
    _N.kFloat: "float",
    _N.k2Float: "float2",
    _N.k3Float: "float3",
    _N.kDouble: "double",
    _N.k2Double: "double2",
    _N.k3Double: "double3",
    _N.k4Double: "double4",
    _N.kAddr: "addr",
}

#: 型付きアトリビュートの ``attrType()`` と型名。ここに無いデータ型は getAddAttrCmd() から求める。
_DATA_TYPE_NAMES = {
    _D.kString: "string",
    _D.kMatrix: "matrix",
    _D.kStringArray: "stringArray",
    _D.kDoubleArray: "doubleArray",
    _D.kFloatArray: "floatArray",
    _D.kIntArray: "Int32Array",
    _D.kPointArray: "pointArray",
    _D.kVectorArray: "vectorArray",
    _D.kMatrixArray: "matrixArray",
    _D.kComponentList: "componentList",
    _D.kMesh: "mesh",
    _D.kLattice: "lattice",
    _D.kNurbsCurve: "nurbsCurve",
    _D.kNurbsSurface: "nurbsSurface",
    _D.kSphere: "sphere",
    _D.kSubdSurface: "subd",
}

#: 値によって型が変わるため、アトリビュート定義だけでは型名が決まらない apiType。
_VALUE_DEPENDENT_API_TYPES = frozenset((om2.MFn.kGenericAttribute,))

#: getAddAttrCmd() のデータ型名のうち、保持する値によって型が変わるもの。
_VALUE_DEPENDENT_DATA_TYPES = frozenset(("geometry",))

#: getAddAttrCmd() のアトリビュート型名と ``cmds.getAttr(type=True)`` の型名が異なるもの。
#: ``typed`` は任意のデータを受け付ける型付きアトリビュートで、値によって型が変わる(None)。
_ADD_ATTR_TYPE_NAMES = {
    "reflectance": "reflectanceRGB",
    "spectrum": "spectrumRGB",
    "fltMatrix": "matrix",
    "compound": "TdataCompound",
    "lightData": "TdataCompound",
    "typed": None,
}

#: ``cmds.addAttr(dataType=...)`` で作成できるデータ型名(maya.cmds で値を読み書きできる型)。
#: 型付きアトリビュートのうちこれら以外(``nurbsPatchUVIds``・``polyFaces`` などの Maya 内部のデータ型)は、
#: 存在しないマルチアトリビュートの要素の値を maya.cmds で問い合わせると Maya が異常終了する場合がある。
_PUBLIC_DATA_TYPES = frozenset(_DATA_TYPE_NAMES.values()) | frozenset((
    "Int64Array", "floatVectorArray", "reflectanceRGB", "spectrumRGB",
    "short2", "short3", "long2", "long3", "float2", "float3", "double2", "double3", "double4",
))

_ADD_ATTR_DATA_TYPE = re.compile(r'-dataType "([^"]+)"')
_ADD_ATTR_ATTRIBUTE_TYPE = re.compile(r'-attributeType "([^"]+)"')

#: 自身の単位を持つため、数値の角度として換算しない値。
_SELF_UNIT_VALUES = (om2.MEulerRotation, om2.MQuaternion, om2.MAngle, om2.MDistance, om2.MTime,
                     om2.MMatrix, om2.MTransformationMatrix)


def _add_attr_type_name(attribute):
    """``MFnAttribute.getAddAttrCmd()`` の型指定から型名を求める。

    API 2.0 の列挙値で表せないデータ型(``Int64Array``、データ型指定の ``double3`` など)や
    アトリビュート型(``reflectance``、opaque アトリビュート)に使う。

    Args:
        attribute (om2.MObject): アトリビュートの MObject。

    Returns:
        str | None: 型名。データ型を複数受け付けるアトリビュート、または値によって型が変わる
            アトリビュートは None。
    """
    command = om2.MFnAttribute(attribute).getAddAttrCmd(True)
    data_types = _ADD_ATTR_DATA_TYPE.findall(command)
    if data_types:
        if len(data_types) != 1 or data_types[0] in _VALUE_DEPENDENT_DATA_TYPES:
            return None
        return data_types[0]
    match = _ADD_ATTR_ATTRIBUTE_TYPE.search(command)
    if match is None:
        return None
    name = match.group(1)
    return _ADD_ATTR_TYPE_NAMES.get(name, name)


def _is_mesh_control_points(mplug, attribute):
    """mesh の ``controlPoints`` (Maya が float3 として扱うアトリビュート)のプラグか判定する。

    Args:
        mplug (om2.MPlug): 対象のプラグ。
        attribute (om2.MObject): プラグのアトリビュート。

    Returns:
        bool: mesh の ``controlPoints`` の場合は True。
    """
    return mplug.node().hasFn(om2.MFn.kMesh) and om2.MFnAttribute(attribute).name == "controlPoints"


def attributeType(mplug):
    """プラグのアトリビュート型名を、``cmds.getAttr(<プラグ名>, type=True)`` と同じ文字列で取得する。

    core の関数は snake_case を基本とするが、この名前は ``Plug`` 側のアトリビュート型 dispatch
    (``Plug._registry`` のキー)と ``cmds.getAttr(type=True)`` の呼び方に合わせた既存名として維持する。

    アトリビュート定義だけから求めるため、存在しないマルチアトリビュートの要素や、``cmds.getAttr`` が例外になる
    mesh の内部アトリビュートにも使え、シーンを変更しない。マルチアトリビュートのプラグは要素の型名を返す
    (``cmds.getAttr(type=True)`` をマルチアトリビュート全体に使った結果とは異なる)。規則はモジュールの
    説明を参照。

    Args:
        mplug (om2.MPlug): 対象のプラグ。

    Returns:
        str | None: ``double3``/``doubleLinear``/``matrix`` などの型名。値によって型が
            変わるアトリビュート(generic アトリビュートなど)は None。

    Raises:
        RuntimeError: アトリビュートが削除されて存在しない場合(Undo の対象から外れた削除済みの
            動的アトリビュートなど)。
    """
    attribute = mplug.attribute()
    api_type = attribute.apiType()
    name = _API_TYPE_NAMES.get(api_type)
    if name is not None:
        return name
    if attribute.hasFn(om2.MFn.kNumericAttribute):
        name = _NUMERIC_TYPE_NAMES.get(om2.MFnNumericAttribute(attribute).numericType())
        if name is None:
            return _add_attr_type_name(attribute)
        if name == "double3" and _is_mesh_control_points(mplug, attribute):
            return "float3"
        return name
    if api_type == om2.MFn.kTypedAttribute:
        data_type = om2.MFnTypedAttribute(attribute).attrType()
        name = _DATA_TYPE_NAMES.get(data_type)
        if name is not None:
            return name
        if data_type == _D.kAny:
            return None
        return _add_attr_type_name(attribute)
    if api_type in _VALUE_DEPENDENT_API_TYPES:
        return None
    return _add_attr_type_name(attribute)


def is_internal_data_type(mplug):
    """Maya 内部のデータ型(``cmds.addAttr`` で作成できない型)の型付きアトリビュートか判定する。

    nurbsSurface の ``patchUVIds`` (``nurbsPatchUVIds``)のような内部のデータ型は、
    存在しないマルチアトリビュートの要素の値や型を maya.cmds・MPlug で読むと Maya が異常終了する場合がある。
    mlibはこれらの存在しない要素の値を読まず、``Plug.get()`` でRuntimeErrorにする。
    要素の参照取得だけでは値を評価しない。任意のデータを受け付ける
    型付きアトリビュート(値によって型が変わるアトリビュート)は対象外。

    Args:
        mplug (om2.MPlug): 対象のプラグ。

    Returns:
        bool: 内部のデータ型の型付きアトリビュートの場合は True。
    """
    attribute = mplug.attribute()
    if attribute.apiType() != om2.MFn.kTypedAttribute:
        return False
    data_type = om2.MFnTypedAttribute(attribute).attrType()
    if data_type in _DATA_TYPE_NAMES or data_type == _D.kAny:
        return False
    name = _add_attr_type_name(attribute)
    return name is not None and name not in _PUBLIC_DATA_TYPES


def _require_number(plug, value):
    """数値・単位・enumへの入力が数値か確かめる(cmds.setAttrと同じ拒否)。

    通常経路の ``cmds.setAttr`` は数値アトリビュートへの文字列・None・列を拒否するため、
    fastと単位アトリビュートの換算でも変換せず、型違いの規則に合わせてTypeErrorで拒否する。
    boolは数値として受け付ける。

    Args:
        plug (om2.MPlug): エラー表示に使う書込み先。
        value (object): 書き込む値。

    Returns:
        None: 値を返さない。

    Raises:
        TypeError: 文字列・bytes・None、またはfloatへ変換できない値の場合。
    """
    if not isinstance(value, (str, bytes)) and value is not None:
        try:
            float(value)
            return
        except (TypeError, ValueError):
            pass
    raise TypeError(f"Expected a numeric value for {plug.name()}: {value!r}")


def _convert_units(plug, value, to_ui=True):
    """数値・コンパウンドアトリビュートの値を変換する。単位のない型はそのまま返す。

    Args:
        plug (om2.MPlug): 型を判定するプラグ。
        value (object): 変換する値。
        to_ui (bool): Trueはcm/rad/秒からUI単位、Falseは逆方向。

    Returns:
        object: 変換した値。マトリクスや型付き配列の成分は単位変換しない。

    Raises:
        RuntimeError: 単位アトリビュートへ数値以外(文字列・None等)を指定した場合。
    """
    if plug.isCompound:
        return tuple(_convert_units(plug.child(i), item, to_ui) for i, item in enumerate(value))
    attribute = plug.attribute()
    if not attribute.hasFn(om2.MFn.kUnitAttribute):
        return value
    unit_type = om2.MFnUnitAttribute(attribute).unitType()
    if unit_type == om2.MFnUnitAttribute.kInvalid:
        # Maya 2023のmesh.pnts子はUnitAttributeとして解決されても単位型が
        # kInvalidになる。座標の数値を維持し、存在しない単位を変換しない。
        return value
    unit_class, internal_unit = {
        om2.MFnUnitAttribute.kAngle: (om2.MAngle, om2.MAngle.kRadians),
        om2.MFnUnitAttribute.kDistance: (om2.MDistance, om2.MDistance.kCentimeters),
        om2.MFnUnitAttribute.kTime: (om2.MTime, om2.MTime.kSeconds),
    }[unit_type]
    if isinstance(value, unit_class):
        # 単位オブジェクトは元単位を保持するため、数値用の元単位を付け直さない。
        return value.asUnits(unit_class.uiUnit() if to_ui else internal_unit)
    # 文字列・None等はcmds.setAttrの数値アトリビュートと同じくRuntimeErrorにする。
    _require_number(plug, value)
    if to_ui:
        source_unit, target_unit = internal_unit, unit_class.uiUnit()
    else:
        source_unit, target_unit = unit_class.uiUnit(), internal_unit
    return unit_class(value, source_unit).asUnits(target_unit)


def _plain_angle_unit(unit, ui_units):
    """get/setの ``unit`` と ``uiUnits`` から、数値の角度の単位を決める。

    Args:
        unit (str | None): 角度の単位名。Noneは度。
        ui_units (bool): Trueは現在のUI単位を使う(unitとは同時指定できない)。

    Returns:
        str | None: ``"deg"`` / ``"rad"``。uiUnits=TrueではNone(UI単位の換算に任せる)。

    Raises:
        TypeError: unitが文字列・None以外の場合。
        ValueError: 未対応の単位名、またはuiUnits=Trueとunitを同時に指定した場合。
    """
    if ui_units:
        if unit is not None:
            # 単位名の誤りを先に伝え、正しい名前なら同時指定を拒否する。
            _angle_unit(unit)
            raise ValueError("Specify either unit or uiUnits=True, not both")
        return None
    return _angle_unit(unit)


def _is_angle_attribute(attribute):
    """角度の単位アトリビュート(doubleAngle・floatAngle)か判定する。

    Args:
        attribute (om2.MObject): アトリビュート定義。

    Returns:
        bool: 角度の単位アトリビュートならTrue。
    """
    return (attribute.hasFn(om2.MFn.kUnitAttribute)
            and om2.MFnUnitAttribute(attribute).unitType() == om2.MFnUnitAttribute.kAngle)


def _convert_angles(plug, value, unit, to_internal=True):
    """角度アトリビュートの数値を、指定単位とラジアン(内部単位)の間で換算する。

    コンパウンドアトリビュートは子の定義ごとに換算し、角度以外の子・型付きの値
    (EulerRotate・Quaternion・MAngle・マトリクス等の単位を持つ値)・数値以外はそのまま返す。
    成分数が子数と違う入力も換算せず、検証は書込み側に任せる。

    Args:
        plug (om2.MPlug): 型を判定するプラグ。
        value (object): 換算する値。
        unit (str | None): ``"deg"`` / ``"rad"``。``"rad"`` とNoneは換算しない。
        to_internal (bool): Trueは指定単位からrad、Falseはradから指定単位。

    Returns:
        object: 換算した値。換算した成分を含むコンパウンドアトリビュートはtuple、
            換算の無い値は入力そのもの。
    """
    if unit != "deg" or value is None or isinstance(value, (str, bytes) + _SELF_UNIT_VALUES):
        return value
    if plug.isArray:
        return value
    if plug.isCompound:
        try:
            items = tuple(value)
        except TypeError:
            return value
        if len(items) != plug.numChildren():
            return value
        converted = tuple(_convert_angles(plug.child(index), item, unit, to_internal)
                          for index, item in enumerate(items))
        if all(new is old for new, old in zip(converted, items)):
            return value
        return converted
    if not isinstance(value, (int, float)) or not _is_angle_attribute(plug.attribute()):
        return value
    return math.radians(value) if to_internal else math.degrees(value)


def _read_angle(mplug):
    """角度アトリビュートの値をラジアンで返す。

    UIの角度単位に依存しない。

    Args:
        mplug (om2.MPlug): 角度アトリビュートのプラグ。

    Returns:
        float: rad単位の値。
    """
    return mplug.asMAngle().asRadians()


def _read_distance(mplug):
    """距離アトリビュートの値をcmで返す。

    Args:
        mplug (om2.MPlug): 距離アトリビュートのプラグ。

    Returns:
        float: 内部単位の値。
    """
    return mplug.asMDistance().asCentimeters()


def _read_time(mplug):
    """時間アトリビュートの値を秒で返す。

    Args:
        mplug (om2.MPlug): 時間アトリビュートのプラグ。

    Returns:
        float: 内部単位の値。
    """
    return mplug.asMTime().asUnits(om2.MTime.kSeconds)


def _round_integer(value):
    """cmds.setAttrと同じく、小数を0から遠い側への四捨五入で整数にする。

    整数型・enum・boolのfast書込みで、通常経路(``cmds.setAttr``)と入力の意味を揃える
    (2.5は3、-2.5は-3、2.4999は2)。整数はそのまま返す。

    Args:
        value (int | float): 数値。型の検査は呼出し元が行う。

    Returns:
        int: 四捨五入した整数。

    Raises:
        ValueError: nanの場合。
        OverflowError: 無限大の場合。
    """
    if isinstance(value, int):
        return int(value)
    value = float(value)
    rounded = math.floor(abs(value) + 0.5)
    return int(rounded) if value >= 0 else -int(rounded)


def _round_bool(value):
    """cmds.setAttrと同じく、四捨五入した値が0以外ならTrueにする(0.4はFalse、0.6はTrue)。

    Args:
        value (int | float): 数値。範囲(0〜1)の検査は呼出し元が行う。

    Returns:
        bool: 四捨五入した値が0以外ならTrue。
    """
    return _round_integer(value) != 0


#: 型名 -> (読取、fast setter、入力変換)。数値はOpenMayaで直接読む。
#: floatは読取時にdouble精度で取得し、書込時にはfloatへ設定する。
#: 整数型とboolの入力変換は、cmds.setAttrと同じ四捨五入にする(切捨てにしない)。
_NUMERIC_ACCESS = {
    "bool": (om2.MPlug.asBool, om2.MPlug.setBool, _round_bool),
    "byte": (om2.MPlug.asInt, om2.MPlug.setInt, _round_integer),
    "char": (om2.MPlug.asChar, om2.MPlug.setInt, _round_integer),
    "short": (om2.MPlug.asInt, om2.MPlug.setInt, _round_integer),
    "long": (om2.MPlug.asInt, om2.MPlug.setInt, _round_integer),
    "float": (om2.MPlug.asDouble, om2.MPlug.setFloat, float),
    "double": (om2.MPlug.asDouble, om2.MPlug.setDouble, float),
}
_NUMERIC_READERS = {kind: _NUMERIC_ACCESS[name][0]
                    for kind, name in _NUMERIC_TYPE_NAMES.items() if name in _NUMERIC_ACCESS}
NUMERIC_WRITERS = {kind: _NUMERIC_ACCESS[name][1:]
                   for kind, name in _NUMERIC_TYPE_NAMES.items() if name in _NUMERIC_ACCESS}

#: 単位アトリビュートの ``unitType()`` と、値を読む関数。
_UNIT_READERS = {
    om2.MFnUnitAttribute.kAngle: _read_angle,
    om2.MFnUnitAttribute.kDistance: _read_distance,
    om2.MFnUnitAttribute.kTime: _read_time,
}

#: :func:`value_reader` が「MPlug から直接読めない(``cmds.getAttr`` で読む)」ことを表す値。
_CMDS_READER = False


def typed_data(mplug):
    """型付きデータを取得し、未初期化値だけをnullとして扱う。

    Args:
        mplug (om2.MPlug): 所有ノードとアトリビュートの有効性を検証済みのプラグ。

    Returns:
        om2.MObject: 読み出した型付きデータのAPI参照。未初期化値はnull。
            list等の独立したPython値への変換は呼出元が担当する。

    Raises:
        RuntimeError: null以外の理由でデータを取得できない場合。
    """
    try:
        return mplug.asMObject()
    except RuntimeError:
        # asMObjectはnullでもkFailureを送出する。データハンドルでnullだけを
        # 確認し、借りたハンドルは必ず解放する。評価失敗を空値へ読み替えない。
        handle = mplug.asMDataHandle()
        try:
            if handle.data().isNull():
                return om2.MObject.kNullObj
        finally:
            mplug.destructHandle(handle)
        raise


def _read_array(mplug, factory, tuples=False):
    """型付き配列を要素数によらずlistとして返す。

    Args:
        mplug (om2.MPlug): 読取対象。
        factory (type): データfunction set。
        tuples (bool): 点・ベクトル・マトリクスの各要素をtupleへ変換する。

    Returns:
        list | None: 値のコピー。空配列は[]、未初期化データはNone。
    """
    data = typed_data(mplug)
    if data.isNull():
        return None
    values = factory(data).array()
    if tuples:
        return [tuple(value) for value in values]
    return list(values)


_ARRAY_READERS = {
    _D.kDoubleArray: partial(_read_array, factory=om2.MFnDoubleArrayData),
    _D.kIntArray: partial(_read_array, factory=om2.MFnIntArrayData),
    _D.kStringArray: partial(_read_array, factory=om2.MFnStringArrayData),
    _D.kVectorArray: partial(_read_array, factory=om2.MFnVectorArrayData, tuples=True),
    _D.kPointArray: partial(_read_array, factory=om2.MFnPointArrayData, tuples=True),
    _D.kMatrixArray: partial(_read_array, factory=om2.MFnMatrixArrayData, tuples=True),
}


def value_reader(attribute):
    """``Plug.get()`` が MPlug から直接値を読む関数を、アトリビュート定義から選ぶ。

    関数を選ぶだけで値は読み取らない。呼出元のPlugが読取関数を保持し、
    getのたびに現在値を取得する。

    Args:
        attribute (om2.MObject): アトリビュートの MObject。

    Returns:
        callable | Literal[False]: MPlug を受け取って値を返す関数。bool/int/float 系の数値アトリビュート、
            角度・距離・時間の単位アトリビュート、enum、文字列、doubleArray/Int32Array/
            stringArray/vectorArray/pointArray/matrixArrayが対象。それ以外は
            ``_CMDS_READER``。この場合は呼出元がgenericマトリクスの判定やcmdsへの読取委譲を行う。
    """
    if attribute.hasFn(om2.MFn.kNumericAttribute):
        return _NUMERIC_READERS.get(om2.MFnNumericAttribute(attribute).numericType(), _CMDS_READER)
    if attribute.hasFn(om2.MFn.kUnitAttribute):
        return _UNIT_READERS.get(om2.MFnUnitAttribute(attribute).unitType(), _CMDS_READER)
    if attribute.hasFn(om2.MFn.kEnumAttribute):
        return om2.MPlug.asInt
    if attribute.hasFn(om2.MFn.kTypedAttribute):
        kind = om2.MFnTypedAttribute(attribute).attrType()
        if kind == om2.MFnData.kString:
            return om2.MPlug.asString
        return _ARRAY_READERS.get(kind, _CMDS_READER)
    return _CMDS_READER
