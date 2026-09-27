"""シーンから独立した、JSON保存可能なリグ定義。距離はシーン単位。"""

import math
import re
from dataclasses import asdict, dataclass


def _name(value):
    """名前空間やパスを含まない安定識別子を検証する。

    Args:
        value (str): 英数字とアンダースコアで構成した識別子。
    """
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("Invalid identifier: {!r}".format(value))


def _level(value):
    """0以上の整数LODを検証する。0が最軽量。

    Args:
        value (int): 検証するLOD。boolは受け付けない。
    """
    if type(value) is not int or value < 0:
        raise ValueError("LOD must be a non-negative integer")


def _order(items, dependencies):
    """依存が先になる安定順序を返し、循環・重複・欠落を拒否する。

    Args:
        items (Sequence): idを持つ定義の列。
        dependencies (Callable): 定義から依存識別子の列を返す関数。


    Returns:
        tuple: 依存順に並べた定義。
    """
    lookup = {item.id: item for item in items}
    if len(lookup) != len(items):
        raise ValueError("Duplicate identifiers")
    result, visiting, visited = [], set(), set()

    def visit(key):
        """深さ優先で依存を検査する。

        Args:
            key (str): 探索する定義の識別子。
        """
        if key in visiting:
            raise ValueError("Dependency cycle: " + key)
        if key not in lookup:
            raise ValueError("Missing dependency: " + key)
        if key in visited:
            return
        visiting.add(key)
        for dep in dependencies(lookup[key]):
            visit(dep)
        visiting.remove(key)
        visited.add(key)
        result.append(lookup[key])

    for item in items:
        visit(item.id)
    return tuple(result)


@dataclass(frozen=True)
class JointSpec:
    """親空間での基準位置を保持する骨の定義。"""

    id: str
    parent: str | None
    translation: tuple[float, float, float]

    def __post_init__(self):
        """識別子と有限の3成分を検証して不変化する。"""
        _name(self.id)
        if self.parent is not None:
            _name(self.parent)
        values = tuple(float(v) for v in self.translation)
        if len(values) != 3 or not all(math.isfinite(v) for v in values):
            raise ValueError("Expected three finite translation components")
        object.__setattr__(self, "translation", values)


@dataclass(frozen=True)
class LayerSpec:
    """依存と有効になる最小LODを保持するレイヤー。"""

    id: str
    kind: str
    dependencies: tuple[str, ...] = ()
    min_lod: int = 0

    def __post_init__(self):
        """レイヤーの種類と依存識別子を検証する。"""
        _name(self.id)
        _level(self.min_lod)
        if self.kind not in {
            "fk",
            "ik",
            "soft_ik",
            "helper",
            "reverse_foot",
            "spline_ik",
            "rbf",
            "space",
            "twist",
            "bend",
            "driven",
            "follow",
        }:
            raise ValueError("Unknown layer kind: " + self.kind)
        if isinstance(self.dependencies, str):
            raise TypeError("dependencies must be a sequence of identifiers")
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        for dep in self.dependencies:
            _name(dep)
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("Duplicate layer dependencies")


@dataclass(frozen=True)
class RigDefinition:
    """骨とレイヤーの宣言。バックエンドは対応する種類だけを構築する。"""

    name: str
    joints: tuple[JointSpec, ...]
    layers: tuple[LayerSpec, ...]
    schema_version: int = 1

    def __post_init__(self):
        """識別子、スキーマ、依存グラフを検証する。"""
        _name(self.name)
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("Unsupported rig schema")
        object.__setattr__(self, "joints", tuple(self.joints))
        object.__setattr__(self, "layers", tuple(self.layers))
        if not self.joints or not all(isinstance(j, JointSpec) for j in self.joints):
            raise ValueError("Expected at least one JointSpec")
        if not all(isinstance(layer, LayerSpec) for layer in self.layers):
            raise TypeError("Expected LayerSpec entries")
        self.joint_order()
        _order(self.layers, lambda layer: layer.dependencies)

    def joint_order(self):
        """親を先にした安定順序を取得する。


        Returns:
            tuple[JointSpec, ...]: 親子関係順の骨定義。
        """
        return _order(self.joints, lambda joint: (joint.parent,) if joint.parent else ())

    def active_layers(self, lod):
        """有効レイヤーを依存順に取得する。無効な依存が必要なLODは拒否する。

        Args:
            lod (int): 0以上の詳細度。


        Returns:
            tuple[LayerSpec, ...]: 指定LODで有効なレイヤー。
        """
        _level(lod)
        return _order(
            tuple(layer for layer in self.layers if layer.min_lod <= lod),
            lambda layer: layer.dependencies,
        )

    def to_data(self):
        """JSONへ保存できる辞書へ変換する。


        Returns:
            dict: 骨・レイヤー・スキーマの宣言。
        """
        return asdict(self)

    @classmethod
    def from_data(cls, data):
        """辞書から復元する。未知のフィールドやスキーマは拒否する。

        Args:
            data (Mapping): to_data形式の宣言。


        Returns:
            RigDefinition: 検証済み定義。
        """
        data = dict(data)
        data["joints"] = tuple(JointSpec(**item) for item in data["joints"])
        data["layers"] = tuple(LayerSpec(**item) for item in data["layers"])
        return cls(**data)


def limb_definition(name="limb"):
    """X軸に伸びる長さ5+5の最小検証用チェーンを定義する。

    Args:
        name (str): 部位ルート名。既定はlimb。


    Returns:
        RigDefinition: FK/IK/Soft IK/補助骨レイヤーを含む定義。
    """
    return RigDefinition(
        name,
        (
            JointSpec("root", None, (0, 0, 0)),
            JointSpec("mid", "root", (5, 0, 0)),
            JointSpec("tip", "mid", (5, 0, 0)),
        ),
        (
            LayerSpec("fk", "fk"),
            LayerSpec("ik", "ik", ("fk",)),
            LayerSpec("soft", "soft_ik", ("ik",), 1),
            LayerSpec("helper", "helper", ("fk",), 1),
            LayerSpec("space", "space"),
        ),
    )
