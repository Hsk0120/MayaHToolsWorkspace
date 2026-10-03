"""型タグ付きJSON変換。任意クラスのimport・コード実行は行わない。"""

import math
from dataclasses import fields

import maya.api.OpenMaya as om2

# 数学型は定義元のモジュールから直接 import する。hlib.reload() は module の globals にある
# クラスの定義元から依存順を推定するため、定義元の再読み込み後にこの module も読み直され、
# 下の対応表が新しいクラスで作り直される。
from ..maths.eulerRotation import ORDER_NAMES, EulerRotation
from ..maths.matrix import Matrix
from ..maths.quaternion import Quaternion
from ..maths.scale import Scale
from ..maths.shear import Shear
from ..maths.translation import Translation
from ..maths.vector import Vector
from .references import NodeRef, PlugRef, ComponentRef

#: 数学型の記録の要素数。EulerRotation はラジアンの3成分(順序は別の "order" キー)。
_MATH_SIZES = {
    "Vector": 3,
    "Translation": 3,
    "Scale": 3,
    "Shear": 3,
    "EulerRotation": 3,
    "Quaternion": 4,
    "Matrix": 16,
}

#: 記録の型名から復元に使う hlib.maths のクラス。
_MATH_CLASSES = {
    "Vector": Vector,
    "Translation": Translation,
    "Scale": Scale,
    "Shear": Shear,
    "EulerRotation": EulerRotation,
    "Quaternion": Quaternion,
    "Matrix": Matrix,
}

#: 保存できる数学型(型そのもので照合し、派生クラスは含めない)から記録の型名への対応。
#: om2 名のメソッド(``normal()``、``asMatrix()`` など)が返す om2 の基底型も、対応する
#: hlib の型の記録として保存する。
_MATH_TYPES = {cls: name for name, cls in _MATH_CLASSES.items()}
_MATH_TYPES.update({
    om2.MVector: "Vector",
    om2.MQuaternion: "Quaternion",
    om2.MEulerRotation: "EulerRotation",
    om2.MMatrix: "Matrix",
})


def _math_type_name(value):
    """数学型として保存できる値の型名を返す。

    hlib.maths の公開型(派生クラスは除く)と、om2 名のメソッド(``normal()``、
    ``asMatrix()`` など)が返す om2 の基底型(MVector / MQuaternion / MEulerRotation /
    MMatrix)を対象にする。om2 の基底型は対応する hlib の型の記録として保存する。
    対応表はモジュールの読み込み時に1回だけ作る。

    Args:
        value (object): 判定する値。

    Returns:
        str | None: ``"Vector"`` などの型名。対象外なら None。
    """
    return _MATH_TYPES.get(type(value))


def _decode_math(name, args):
    """数学型の記録を検証し、hlib.maths の値へ復元する。

    Args:
        name (str): ``"Vector"`` などの型名。
        args (object): 記録の中身を decode した値。``{"values": [...]}``、EulerRotation は
            ``"order"`` (名前または om2 の番号)も持てる。

    Returns:
        object: 復元した hlib.maths の値。

    Raises:
        ValueError: 未知の型、キーの過不足、要素数の不一致、数値(bool を除く int / float)
            以外の要素、または未対応の回転順序の場合。
    """
    size = _MATH_SIZES.get(name)
    if size is None:
        raise ValueError("Unknown math type")
    allowed = {"values", "order"} if name == "EulerRotation" else {"values"}
    if type(args) is not dict or "values" not in args or not set(args) <= allowed:
        raise ValueError("Invalid {} record".format(name))
    values = args["values"]
    if type(values) not in (list, tuple) or len(values) != size:
        raise ValueError("{} expects {} values".format(name, size))
    if any(type(item) not in (int, float) for item in values):
        raise ValueError("{} values must be numbers".format(name))
    if "order" in args and type(args["order"]) not in (str, int):
        raise ValueError("EulerRotation order must be a name or an om2 order number")
    cls = _MATH_CLASSES[name]
    if name == "Matrix":
        return cls(values)
    if name == "EulerRotation":
        return cls(*values, order=args.get("order", "xyz"))
    return cls(*values)


def encode(value):
    """対応型をタグ付きのJSON基本値へ変換する。非有限値・未対応型は例外。

    頻度の高い基本値・dict・list・tuple・数学型を先に型そのもので判定し、
    Node などの判定に必要な遅延 import(循環 import を避けるため関数内で行う)は
    それ以外の値のときだけ行う。

    Args:
        value (object): 対応する基本値、数学値、シーン参照または保存データ。

    Returns:
        object: JSON 基本値と型タグで表したデータ。JSON 文字列ではない。
    """
    kind = type(value)
    if value is None or kind is bool or kind is str or kind is int:
        return value
    if kind is float:
        if not math.isfinite(value):
            raise ValueError("Non-finite numbers are not supported")
        return value
    if kind is dict:
        if any(type(k) is not str for k in value):
            raise TypeError("JSON dictionary keys must be strings")
        return {"type": "dict", "value": {k: encode(v) for k, v in value.items()}}
    if kind is list or kind is tuple:
        return {"type": "tuple" if kind is tuple else "list", "value": [encode(v) for v in value]}
    math_name = _MATH_TYPES.get(kind)
    if math_name is not None:
        data = {"values": list(value)}
        if math_name == "EulerRotation":
            # order は om2 の番号(int)。JSON には従来どおり名前で保存する。
            data["order"] = ORDER_NAMES[value.order]
        return {"type": "math:" + math_name, "value": encode(data)}
    from ..nodes.node import Node
    from ..plugs.plug import Plug
    from ..components import Component, Components
    from ..scene.selection import Selection
    from .snapshots import Snapshot
    if isinstance(value, Node):
        value = NodeRef.capture(value)
    elif isinstance(value, Plug):
        value = PlugRef.capture(value)
    elif isinstance(value, Component):
        value = ComponentRef.capture(value)
    elif isinstance(value, (Components, Selection)):
        return {"type": "selection", "value": encode(list(value))}
    if type(value) in (NodeRef, PlugRef, ComponentRef):
        return {"type": type(value).__name__, "value": {f.name: encode(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, Snapshot):
        return {"type": "snapshot", "value": encode(value.toData())}
    raise TypeError("Unsupported JSON value: {}".format(type(value).__name__))


def decode(value):
    """固定の許可型のみ復元する。参照は解決せず、シーンを変更しない。

    Args:
        value (object): encode() の出力に対応する基本値または型タグ付きデータ。

    Returns:
        object: 復号した値。シーン参照は NodeRef / PlugRef / ComponentRef のまま保持する。
    """
    if value is None or type(value) in (bool, str, int, float):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite number")
        return value
    if not isinstance(value, dict) or set(value) != {"type", "value"}:
        raise ValueError("Invalid typed JSON record")
    kind, data = value["type"], value["value"]
    if kind == "dict":
        return {k: decode(v) for k, v in data.items()}
    if kind in ("list", "tuple"):
        result = [decode(v) for v in data]
        return tuple(result) if kind == "tuple" else result
    if kind in ("NodeRef", "PlugRef", "ComponentRef"):
        cls = {"NodeRef": NodeRef, "PlugRef": PlugRef, "ComponentRef": ComponentRef}[kind]
        return cls(**{k: decode(v) for k, v in data.items()})
    if kind == "selection":
        # シーン未ロードでも読み込み可能な、参照の順序付きリスト。
        return decode(data)
    if kind == "snapshot":
        from .snapshots import Snapshot
        return Snapshot.fromData(decode(data))
    if kind.startswith("math:"):
        name = kind[5:]
        if name not in _MATH_SIZES:
            raise ValueError("Unknown math type")
        return _decode_math(name, decode(data))
    raise ValueError("Unknown JSON type: {}".format(kind))
