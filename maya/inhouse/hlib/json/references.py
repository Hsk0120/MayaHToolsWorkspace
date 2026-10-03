"""シーンを変更せず保持・解決できるMaya参照。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class NodeRef:
    """UUID・絶対名・ノード型を保存する。同名候補は自動選択しない。"""
    uuid: str
    path: str
    node_type: str

    @classmethod
    def capture(cls, node):
        """Nodeまたは一意な名前から参照を取得する。"""
        import maya.api.OpenMaya as om2
        from ..nodes.node import Node
        name = (node.fullName() if hasattr(node, "fullName") else node)
        if isinstance(node, Node):
            if not node.isValid():
                raise ValueError("Expected one node: {}".format(name))
            return cls(node.uuid(), name, node.type())
        selection = om2.MSelectionList()
        try:
            selection.add(name)
        except (RuntimeError, TypeError) as exc:
            raise ValueError("Expected one node: {}".format(name)) from exc
        if selection.length() != 1 or "." in name:
            raise ValueError("Expected one node: {}".format(name))
        try:
            value = selection.getDagPath(0)
        except (RuntimeError, TypeError):
            value = selection.getDependNode(0)
        node = Node(value)
        return cls(node.uuid(), node.fullName(), node.type())

    def resolve(self, mapping=None, namespace_map=None):
        """明示マップ→名前空間変換→UUID→絶対名の順でNodeを解決する。

        マップ指定時は元UUIDへフォールバックしない。型違い・不明・曖昧ならValueError。
        """
        from maya import cmds
        from ..nodes.node import Node
        mapping, namespace_map = mapping or {}, namespace_map or {}
        explicit = self.path in mapping
        name = mapping.get(self.path, self.path)
        name = (name.fullName() if hasattr(name, "fullName") else name)
        if not explicit and namespace_map:
            parts = name.split("|")
            for i, part in enumerate(parts):
                if not part:
                    continue
                ns, sep, leaf = part.rpartition(":")
                key = ns if sep else ""
                if key in namespace_map:
                    dst = namespace_map[key].strip(":")
                    parts[i] = (dst + ":" if dst else "") + (leaf if sep else part)
            name = "|".join(parts)
            explicit = True
        candidates = []
        if not explicit and self.uuid:
            candidates = cmds.ls(self.uuid, long=True) or []
            # インスタンスはUUIDが共通。保存したDAGパスがあればそれを使う。
            if len(candidates) > 1 and self.path in candidates:
                candidates = [self.path]
        if not candidates:
            candidates = cmds.ls(name, long=True) or []
        if len(candidates) != 1:
            raise ValueError("Node missing or ambiguous: {}".format(name))
        node = Node(candidates[0])
        if node.type() != self.node_type:
            raise ValueError("Node type mismatch: {}".format(name))
        return node


@dataclass(frozen=True)
class PlugRef:
    """ノード参照とアトリビュートパス。配列の論理番号を保持する。"""
    node: NodeRef
    attribute: str

    @classmethod
    def capture(cls, plug):
        """Plugまたはアトリビュート名を参照へ変換する。"""
        name = (plug.fullName() if hasattr(plug, "fullName") else plug)
        node, attr = name.split(".", 1)
        return cls(NodeRef.capture(node), attr)

    def resolve(self, **kwargs):
        """現在のシーンのPlugへ解決する。"""
        mapping = kwargs.get("mapping") or {}
        key = self.node.path + "." + self.attribute
        if key in mapping:
            from ..nodes.node import Node
            name = (mapping[key].fullName() if hasattr(mapping[key], "fullName") else mapping[key])
            node, attr = name.split(".", 1)
            return NodeRef.capture(node).resolve().plug(attr)
        return self.node.resolve(**kwargs).plug(self.attribute)


@dataclass(frozen=True)
class ComponentRef:
    """単体コンポーネント参照。UVは取得時のUVセットも保持する。"""
    node: NodeRef
    kind: str
    index: int
    uv_set: str = ""

    @classmethod
    def capture(cls, component):
        """hlibの単体コンポーネントから参照を取得する。"""
        name = component.fullName()
        kind = name.rsplit(".", 1)[1].split("[")[0]
        uv = component.shape.meshFn().currentUVSetName() if kind == "map" else ""
        return cls(NodeRef.capture(component.shape), kind, component.index, uv)

    def resolve(self, **kwargs):
        """番号とUVセットを検証して単体コンポーネントを返す。"""
        from ..components import Vertex, CV, Edge, Face, UV
        types = {"vtx": Vertex, "cv": CV, "e": Edge, "f": Face, "map": UV}
        node = self.node.resolve(**kwargs)
        if self.uv_set and node.meshFn().currentUVSetName() != self.uv_set:
            raise ValueError("UV set mismatch")
        return types[self.kind](node, self.index)
