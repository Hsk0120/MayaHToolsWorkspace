"""ノードを名前・DAGパス・型で記録し、読み込み先のシーンのノードへ対応付ける。"""

import maya.cmds as cmds

from .nameMapping import NameMapping


class NodeRef:
    """ノードを名前・DAGパス・ノード型で記録した参照。

    読み込み時は :meth:`resolve` が、:class:`NameMapping` で変換した名前でシーンを探す。
    同じ名前が複数あれば変換したDAGパスで絞り、ノード型が違うものは対応させない。
    """

    __hash__ = None  # type: ignore[assignment]

    def __init__(self, name, path=None, type=None):
        """記録する値を保持する。

        Args:
            name (str): 名前空間付きの短い名前(``"chrA:arm_L_jnt"``)。
            path (str | None): DAGノードの完全パス。DGノードやパス不明はNone。
            type (str | None): ノード型(``"joint"`` 等)。Noneは型を検査しない。

        Raises:
            TypeError: nameが文字列でない、またはpath・typeが文字列・None以外の場合。
            ValueError: nameが空、または ``"|"`` を含む場合。
        """
        if not isinstance(name, str):
            raise TypeError("name must be a string")
        if not name or "|" in name:
            raise ValueError("name must be a non-empty node name without '|'")
        for value, label in ((path, "path"), (type, "type")):
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{label} must be a string or None")
        self._name = name
        self._path = path or None
        self._type = type or None

    def __repr__(self):
        """名前と型を含む表記を返す。

        Returns:
            str: ``NodeRef('chrA:arm_L_jnt', type='joint')`` の形式。
        """
        return f"NodeRef({self._name!r}, type={self._type!r})"

    def __eq__(self, other):
        """名前・パス・型がすべて同じかを返す。

        Args:
            other (object): 比較する値。

        Returns:
            bool: 同じ記録ならTrue。NodeRef以外はNotImplemented。
        """
        if not isinstance(other, NodeRef):
            return NotImplemented
        return (self._name, self._path, self._type) == (other._name, other._path, other._type)

    @classmethod
    def capture(cls, node):
        """シーンのノードから参照を作る。

        Args:
            node (Node | str | om2.MObject | om2.MDagPath): 記録するノード。

        Returns:
            NodeRef: 名前・パス・型を記録した参照。

        Raises:
            TypeError: nodeが対応しない型の場合。
            ValueError: ノードが存在しない場合。
            RuntimeError: ノードが無効な場合。
        """
        # 循環参照の回避: nodesはノードのメソッドからmlib.jsonを使う。
        from ..nodes.node import Node
        node = node if isinstance(node, Node) else Node(node)
        full = node.getFullName()
        if not full:
            raise RuntimeError("Cannot record a deleted node")
        path = full if full.startswith("|") else None
        return cls(full.rpartition("|")[2], path, node.getType())

    @classmethod
    def fromData(cls, data):
        """:meth:`toData` の辞書から作る。

        Args:
            data (dict): ``name``・``path``・``type`` を持つ辞書。

        Returns:
            NodeRef: 新しい参照。

        Raises:
            ValueError: 辞書の形が違う場合。
        """
        if not isinstance(data, dict) or "name" not in data:
            raise ValueError(f"Invalid node reference in JSON: {data!r}")
        try:
            return cls(data["name"], data.get("path"), data.get("type"))
        except TypeError as error:
            raise ValueError(f"Invalid node reference in JSON: {data!r}") from error

    @property
    def name(self):
        """記録した名前空間付きの短い名前を返す。

        Returns:
            str: ノード名。
        """
        return self._name

    @property
    def path(self):
        """記録した完全DAGパスを返す。

        Returns:
            str | None: DGノードやパス不明はNone。
        """
        return self._path

    @property
    def type(self):
        """記録したノード型を返す。

        Returns:
            str | None: 型を記録していなければNone。
        """
        return self._type

    def toData(self):
        """JSONに書く辞書を返す。

        Returns:
            dict: ``{"name": ..., "path": ..., "type": ...}``。
        """
        return {"name": self._name, "path": self._path, "type": self._type}

    def mappedName(self, mapping=None):
        """対応付けを当てた名前を返す。

        Args:
            mapping (NameMapping | None): 名前の対応付け。Noneは変換しない。

        Returns:
            str: 変換後の名前。警告や報告の表示に使う。
        """
        return self._name if mapping is None else mapping.apply(self._name)

    def resolve(self, mapping=None):
        """対応付けを当てた名前で、シーンのノードを探す。

        候補が1つならそれを返す。複数あれば変換したDAGパスと一致するものを返す。
        記録した型と違うノードは候補にしない。

        Args:
            mapping (NameMapping | None): 名前の対応付け。Noneは保存時の名前で探す。

        Returns:
            Node | None: 見つかったノード。見つからない、または1つに絞れない場合はNone。

        Raises:
            TypeError: mappingがNameMapping・None以外の場合。
        """
        if mapping is not None and not isinstance(mapping, NameMapping):
            raise TypeError("mapping must be a NameMapping or None")
        name = self.mappedName(mapping)
        candidates = cmds.ls(name, long=True) or []
        if self._type is not None:
            candidates = [candidate for candidate in candidates if cmds.nodeType(candidate) == self._type]
        if len(candidates) > 1 and self._path is not None:
            path = self._path if mapping is None else mapping.applyPath(self._path)
            candidates = [candidate for candidate in candidates if candidate == path]
        if len(candidates) != 1:
            return None
        # 循環参照の回避: nodesはノードのメソッドからmlib.jsonを使う。
        from ..nodes.node import Node
        return Node(candidates[0])
