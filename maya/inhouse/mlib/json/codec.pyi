# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""mlibの数学型をJSONで書ける値へ変換し、読み込んだ値を元の型へ戻す。

数学型は ``{"type": "Matrix", "value": [...]}`` のように型名を付けた辞書にする。
``EulerRotate`` は度で書き、回転順の名前を ``"order"`` に付ける。``Quaternion``・``Matrix`` は
単位を持たないため、om2の成分をそのまま書く。小数は丸めない。
"""

import math
import maya.api.OpenMaya as om2
from ..maths import EulerRotate, Matrix, Quaternion, Scale, Shear, Translate, Vector
from typing import Any

_VECTOR_TYPES: tuple
_TYPE_NAMES: Any

def encode(value: object) -> Any:
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
    ...

def decode(value: object) -> Any:
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
    ...

def _finite(value: float) -> float:
    """有限のfloatを返す。

    Args:
        value (float): 成分。

    Returns:
        float: 同じ値。

    Raises:
        ValueError: NaN・無限大の場合。
    """
    ...

def _is_math(value: dict) -> bool:
    """型名付きの数学型の辞書かを返す。

    Args:
        value (dict): JSONから読んだ辞書。

    Returns:
        bool: 数学型として戻す辞書ならTrue。
    """
    ...

def _decode_math(value: dict) -> Vector | Translate | Scale | Shear | Quaternion | EulerRotate | Matrix:
    """型名付きの辞書から数学型を作る。

    Args:
        value (dict): :func:`_is_math` がTrueの辞書。

    Returns:
        Vector | Translate | Scale | Shear | Quaternion | EulerRotate | Matrix: 新しい値。

    Raises:
        ValueError: 成分の数が型と合わない、または回転順が不正な場合。
    """
    ...
