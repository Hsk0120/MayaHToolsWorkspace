"""型タグ付きJSON変換。任意クラスのimport・コード実行は行わない。"""
import math
from dataclasses import fields
from .references import NodeRef, PlugRef, ComponentRef


def encode(value):
    """対応型をタグ付きのJSON基本値へ変換する。非有限値・未対応型は例外。"""
    from .. import maths
    from ..nodes.node import Node
    from ..plugs.plug import Plug
    from ..components import Component, Components
    from ..selection import Selection
    from .snapshots import Snapshot
    if value is None or type(value) in (bool, str, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Non-finite numbers are not supported")
        return value
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
        return {"type": "snapshot", "value": encode(value.to_data())}
    if type(value).__name__ in maths.__all__ and type(value) is getattr(maths, type(value).__name__, None):
        data = {"values": list(value)}
        if isinstance(value, maths.EulerRotation):
            data["order"] = value.order
        return {"type": "math:" + type(value).__name__, "value": encode(data)}
    if type(value) is dict:
        if any(type(k) is not str for k in value):
            raise TypeError("JSON dictionary keys must be strings")
        return {"type": "dict", "value": {k: encode(v) for k, v in value.items()}}
    if type(value) in (list, tuple):
        return {"type": "tuple" if type(value) is tuple else "list", "value": [encode(v) for v in value]}
    raise TypeError("Unsupported JSON value: {}".format(type(value).__name__))


def decode(value):
    """固定の許可型のみ復元する。参照は解決せず、シーンを変更しない。"""
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
        return Snapshot.from_data(decode(data))
    if kind.startswith("math:"):
        from .. import maths
        name = kind[5:]
        allowed = {"Vector", "Translate", "Rotate", "Scale", "Shear", "EulerRotation", "Quaternion", "Matrix"}
        if name not in allowed:
            raise ValueError("Unknown math type")
        args = decode(data)
        cls = getattr(maths, name)
        if name == "Matrix":
            return cls(args["values"])
        if name == "EulerRotation":
            return cls(*args["values"], order=args["order"])
        return cls(*args["values"])
    raise ValueError("Unknown JSON type: {}".format(kind))
