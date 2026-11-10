"""mlibの数学型をJSONで書ける値へ変換し、読み込んだ値を元の型へ戻す。

数学型は ``{"type": "Matrix", "value": [...]}`` のように型名を付けた辞書にする。
``EulerRotate`` は度で書き、回転順の名前を ``"order"`` に付ける。``Quaternion``・``Matrix`` は
単位を持たないため、om2の成分をそのまま書く。小数は丸めない。
"""

import math

import maya.api.OpenMaya as om2

from ..maths import EulerRotate, Matrix, Quaternion, Scale, Shear, Translate, Vector

#: 型名と、読み込み時に作るmlibのクラス。Vectorの派生は派生を先に判定する。
_VECTOR_TYPES = (("Translate", Translate), ("Scale", Scale), ("Shear", Shear), ("Vector", Vector))
_TYPE_NAMES = frozenset(name for name, _cls in _VECTOR_TYPES) | {"Quaternion", "EulerRotate", "Matrix"}


def encode(value):
    """値をJSONで書ける値へ変換する。

    辞書・list・tupleの中もたどって変換する。辞書のキーは文字列に限る。tupleはlistになる。
    om2の ``MVector``・``MQuaternion``・``MEulerRotation``・``MMatrix`` もmlibの型名で書く。

    Args:
        value (object): 変換する値。None・bool・int・float・str・数学型・それらの辞書とlist。

    Returns:
        object: JSONで書ける値。入力の辞書・listは変更しない。

    Raises:
        TypeError: 対応しない型、または辞書のキーが文字列でない場合。
        ValueError: floatがNaN・無限大の場合。
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Cannot write a non-finite number to JSON: {value!r}")
        return value
    if isinstance(value, om2.MEulerRotation):
        rotate = value if isinstance(value, EulerRotate) else EulerRotate(value.x, value.y, value.z, value.order)
        return {"type": "EulerRotate", "value": [_finite(item) for item in rotate.asDegrees()],
                "order": rotate.orderName}
    if isinstance(value, om2.MQuaternion):
        return {"type": "Quaternion", "value": [_finite(item) for item in (value.x, value.y, value.z, value.w)]}
    if isinstance(value, om2.MMatrix):
        return {"type": "Matrix", "value": [_finite(value[index]) for index in range(16)]}
    if isinstance(value, om2.MVector):
        name = next((name for name, cls in _VECTOR_TYPES if isinstance(value, cls)), "Vector")
        return {"type": name, "value": [_finite(item) for item in (value.x, value.y, value.z)]}
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"JSON object keys must be strings, not {type(key).__name__}")
            result[key] = encode(item)
        return result
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    raise TypeError(f"Cannot write {type(value).__name__} to JSON")


def decode(value):
    """:func:`encode` で書いた値を、数学型を含む元の値へ戻す。

    ``{"type": <型名>, "value": [...]}`` (EulerRotateは ``"order"`` も)の形の辞書だけを数学型にし、
    ほかの辞書・listは中をたどって同じ形で返す。

    Args:
        value (object): JSONから読んだ値。

    Returns:
        object: 数学型へ戻した値。入力の辞書・listは変更しない。

    Raises:
        ValueError: 型名付きの辞書の成分の数が型と合わない場合。
    """
    if isinstance(value, list):
        return [decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    if _is_math(value):
        return _decode_math(value)
    return {key: decode(item) for key, item in value.items()}


def _finite(value):
    """有限のfloatを返す。

    Args:
        value (float): 成分。

    Returns:
        float: 同じ値。

    Raises:
        ValueError: NaN・無限大の場合。
    """
    if not math.isfinite(value):
        raise ValueError(f"Cannot write a non-finite number to JSON: {value!r}")
    return float(value)


def _is_math(value):
    """型名付きの数学型の辞書かを返す。

    Args:
        value (dict): JSONから読んだ辞書。

    Returns:
        bool: 数学型として戻す辞書ならTrue。
    """
    name = value.get("type")
    if name not in _TYPE_NAMES or not isinstance(value.get("value"), list):
        return False
    expected = {"type", "value", "order"} if name == "EulerRotate" else {"type", "value"}
    return set(value) == expected


def _decode_math(value):
    """型名付きの辞書から数学型を作る。

    Args:
        value (dict): :func:`_is_math` がTrueの辞書。

    Returns:
        Vector | Translate | Scale | Shear | Quaternion | EulerRotate | Matrix: 新しい値。

    Raises:
        ValueError: 成分の数が型と合わない、または回転順が不正な場合。
    """
    name, items = value["type"], value["value"]
    sizes = {"Quaternion": 4, "Matrix": 16, "EulerRotate": 3}
    size = sizes.get(name, 3)
    if len(items) != size or not all(isinstance(item, (int, float)) and not isinstance(item, bool)
                                     for item in items):
        raise ValueError(f"{name} expects {size} numbers in JSON, got {items!r}")
    if name == "EulerRotate":
        return EulerRotate.fromDegrees(items[0], items[1], items[2], value["order"])
    if name == "Quaternion":
        return Quaternion(items[0], items[1], items[2], items[3])
    if name == "Matrix":
        return Matrix(items)
    return dict(_VECTOR_TYPES)[name](items[0], items[1], items[2])
