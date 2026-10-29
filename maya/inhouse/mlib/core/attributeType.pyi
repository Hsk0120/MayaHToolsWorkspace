# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
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
from typing import Any, Callable

__all__ = ['attributeType', 'is_internal_data_type', 'typed_data', 'value_reader']
_N: Any
_D: Any
_API_TYPE_NAMES: dict
_NUMERIC_TYPE_NAMES: dict
_DATA_TYPE_NAMES: dict
_VALUE_DEPENDENT_API_TYPES: frozenset
_VALUE_DEPENDENT_DATA_TYPES: frozenset
_ADD_ATTR_TYPE_NAMES: dict
_PUBLIC_DATA_TYPES: Any
_ADD_ATTR_DATA_TYPE: Any
_ADD_ATTR_ATTRIBUTE_TYPE: Any
_SELF_UNIT_VALUES: tuple

def _add_attr_type_name(attribute: om2.MObject) -> str | None:
    """``MFnAttribute.getAddAttrCmd()`` の型指定から型名を求める。

    API 2.0 の列挙値で表せないデータ型(``Int64Array``、データ型指定の ``double3`` など)や
    アトリビュート型(``reflectance``、opaque アトリビュート)に使う。

    Args:
        attribute (om2.MObject): アトリビュートの MObject。

    Returns:
        str | None: 型名。データ型を複数受け付けるアトリビュート、または値によって型が変わる
            アトリビュートは None。
    """
    ...

def _is_mesh_control_points(mplug: om2.MPlug, attribute: om2.MObject) -> bool:
    """mesh の ``controlPoints`` (Maya が float3 として扱うアトリビュート)のプラグか判定する。

    Args:
        mplug (om2.MPlug): 対象のプラグ。
        attribute (om2.MObject): プラグのアトリビュート。

    Returns:
        bool: mesh の ``controlPoints`` の場合は True。
    """
    ...

def attributeType(mplug: om2.MPlug) -> str | None:
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
    ...

def is_internal_data_type(mplug: om2.MPlug) -> bool:
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
    ...

def _require_number(plug: om2.MPlug, value: object) -> None:
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
    ...

def _convert_units(plug: om2.MPlug, value: object, to_ui: bool = ...) -> Any:
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
    ...

def _plain_angle_unit(unit: str | None, ui_units: bool) -> str | None:
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
    ...

def _is_angle_attribute(attribute: om2.MObject) -> bool:
    """角度の単位アトリビュート(doubleAngle・floatAngle)か判定する。

    Args:
        attribute (om2.MObject): アトリビュート定義。

    Returns:
        bool: 角度の単位アトリビュートならTrue。
    """
    ...

def _convert_angles(plug: om2.MPlug, value: object, unit: str | None, to_internal: bool = ...) -> Any:
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
    ...

def _read_angle(mplug: om2.MPlug) -> float:
    """角度アトリビュートの値をラジアンで返す。

    UIの角度単位に依存しない。

    Args:
        mplug (om2.MPlug): 角度アトリビュートのプラグ。

    Returns:
        float: rad単位の値。
    """
    ...

def _read_distance(mplug: om2.MPlug) -> float:
    """距離アトリビュートの値をcmで返す。

    Args:
        mplug (om2.MPlug): 距離アトリビュートのプラグ。

    Returns:
        float: 内部単位の値。
    """
    ...

def _read_time(mplug: om2.MPlug) -> float:
    """時間アトリビュートの値を秒で返す。

    Args:
        mplug (om2.MPlug): 時間アトリビュートのプラグ。

    Returns:
        float: 内部単位の値。
    """
    ...

def _round_integer(value: int | float) -> int:
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
    ...

def _round_bool(value: int | float) -> bool:
    """cmds.setAttrと同じく、四捨五入した値が0以外ならTrueにする(0.4はFalse、0.6はTrue)。

    Args:
        value (int | float): 数値。範囲(0〜1)の検査は呼出し元が行う。

    Returns:
        bool: 四捨五入した値が0以外ならTrue。
    """
    ...
_NUMERIC_ACCESS: dict
_NUMERIC_READERS: dict
NUMERIC_WRITERS: dict
_UNIT_READERS: dict
_CMDS_READER: bool

def typed_data(mplug: om2.MPlug) -> om2.MObject:
    """型付きデータを取得し、未初期化値だけをnullとして扱う。

    Args:
        mplug (om2.MPlug): 所有ノードとアトリビュートの有効性を検証済みのプラグ。

    Returns:
        om2.MObject: 読み出した型付きデータのAPI参照。未初期化値はnull。
            list等の独立したPython値への変換は呼出元が担当する。

    Raises:
        RuntimeError: null以外の理由でデータを取得できない場合。
    """
    ...

def _read_array(mplug: om2.MPlug, factory: type, tuples: bool = ...) -> list | None:
    """型付き配列を要素数によらずlistとして返す。

    Args:
        mplug (om2.MPlug): 読取対象。
        factory (type): データfunction set。
        tuples (bool): 点・ベクトル・マトリクスの各要素をtupleへ変換する。

    Returns:
        list | None: 値のコピー。空配列は[]、未初期化データはNone。
    """
    ...
_ARRAY_READERS: dict

def value_reader(attribute: om2.MObject) -> Callable[..., Any] | bool:
    """``Plug.get()`` が MPlug から直接値を読む関数を、アトリビュート定義から選ぶ。

    関数を選ぶだけで値は読み取らない。呼出元のPlugが読取関数を保持し、
    getのたびに現在値を取得する。

    Args:
        attribute (om2.MObject): アトリビュートの MObject。

    Returns:
        callable | bool: MPlug を受け取って値を返す関数。bool/int/float 系の数値アトリビュート、
            角度・距離・時間の単位アトリビュート、enum、文字列、doubleArray/Int32Array/
            stringArray/vectorArray/pointArray/matrixArrayが対象。それ以外は
            ``_CMDS_READER``。この場合は呼出元がgenericマトリクスの判定やcmdsへの読取委譲を行う。
    """
    ...
