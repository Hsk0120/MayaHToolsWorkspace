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
        """Nodeまたは一意な名前から参照を取得する。

        Args:
            node (Node | str): 有効なノードまたは一意に解決できる名前。

        Returns:
            NodeRef: UUID、パス、ノード型を保持する参照。
        """
        import maya.api.OpenMaya as om2
        from ..nodes.node import Node
        name = (node.getFullName() if hasattr(node, "getFullName") else node)
        if isinstance(node, Node):
            if not node.isValid():
                raise ValueError("Expected one node: {}".format(name))
            return cls(node.getUuid(), name, node.getType())
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
        return cls(node.getUuid(), node.getFullName(), node.getType())

    def resolve(self, mapping=None, namespace_map=None):
        """保存参照を現在のシーンのノードへ解決する。

        明示的なパスマップを優先し、該当しない場合は名前空間マップを適用する。
        パスマップが該当せず名前空間マップも空の場合だけ UUID を検索し、
        見つからなければ保存パスで検索する。名前空間マップが非空の場合は、
        置換対象がなくても元の UUID へフォールバックしない。

        Args:
            mapping (dict | None): 保存パスから移行先ノード名または Node への対応。
            namespace_map (dict | None): 保存名前空間から移行先名前空間への対応。

        Returns:
            Node: 保存した node_type と一致するノード。

        Raises:
            ValueError: 対象が不明・曖昧、またはノード型が異なる場合。
        """
        from maya import cmds
        from ..nodes.node import Node
        mapping, namespace_map = mapping or {}, namespace_map or {}
        explicit = self.path in mapping
        name = mapping.get(self.path, self.path)
        name = (name.getFullName() if hasattr(name, "getFullName") else name)
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
        if node.getType() != self.node_type:
            raise ValueError("Node type mismatch: {}".format(name))
        return node


@dataclass(frozen=True)
class PlugRef:
    """ノード参照とアトリビュートパス。配列の論理番号を保持する。"""

    node: NodeRef
    attribute: str

    @classmethod
    def capture(cls, plug):
        """Plugまたはアトリビュート名を参照へ変換する。

        Args:
            plug (Plug | str): プラグまたはノード名を含むアトリビュート名。

        Returns:
            PlugRef: ノード参照とアトリビュートパス。ここではノードを検証し、
                アトリビュートの存在検証は resolve() に委ねる。
        """
        name = (plug.getFullName() if hasattr(plug, "getFullName") else plug)
        node, attr = name.split(".", 1)
        return cls(NodeRef.capture(node), attr)

    def resolve(self, **kwargs):
        """現在のシーンのPlugへ解決する。

        Args:
            **kwargs: NodeRef.resolve() に渡す mapping、namespace_map。
                mapping には完全なアトリビュート名同士の対応も指定できる。

        Returns:
            Plug: 現在のシーンで解決したプラグ。
        """
        mapping = kwargs.get("mapping") or {}
        key = self.node.path + "." + self.attribute
        if key in mapping:
            from ..nodes.node import Node
            name = (mapping[key].getFullName() if hasattr(mapping[key], "getFullName") else mapping[key])
            node, attr = name.split(".", 1)
            return NodeRef.capture(node).resolve().getPlug(attr)
        return self.node.resolve(**kwargs).getPlug(self.attribute)


@dataclass(frozen=True)
class ComponentRef:
    """単体コンポーネント参照。UVは取得時のUVセットも保持する。"""

    node: NodeRef
    kind: str
    index: int
    uv_set: str = ""

    @classmethod
    def capture(cls, component):
        """hlibの単体コンポーネントから参照を取得する。

        Args:
            component (Component): 対応する単体コンポーネント。

        Returns:
            ComponentRef: 形状参照、種類、API の番号。UV は現在の UV セット名も保持する。
        """
        name = component.getFullName()
        kind = name.rsplit(".", 1)[1].split("[")[0]
        uv = component.shape.meshFn().currentUVSetName() if kind == "map" else ""
        return cls(NodeRef.capture(component.shape), kind, component.index, uv)

    def resolve(self, **kwargs):
        """番号とUVセットを検証して単体コンポーネントを返す。

        Args:
            **kwargs: NodeRef.resolve() に渡す mapping、namespace_map。

        Returns:
            Component: 現在の形状の単体コンポーネント。UV セットは切り替えない。
        """
        from ..components import Vertex, CV, Edge, Face, UV
        types = {"vtx": Vertex, "cv": CV, "e": Edge, "f": Face, "map": UV}
        node = self.node.resolve(**kwargs)
        if self.uv_set and node.meshFn().currentUVSetName() != self.uv_set:
            raise ValueError("UV set mismatch")
        return types[self.kind](node, self.index)
