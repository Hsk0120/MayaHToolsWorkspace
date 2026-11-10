"""Plugを、所有ノードの参照とアトリビュートのパスで記録する。"""

from .nameMapping import NameMapping
from .nodeRef import NodeRef


class PlugRef:
    """Plugを所有ノードの :class:`NodeRef` とアトリビュートのパスで記録した参照。

    アトリビュートのパスはロング名で、マルチアトリビュートの要素は ``weight[3]``、コンパウンドの子は
    ``translate.translateX`` のように書く。エイリアスは使わない。名前の対応付けはノードの部分にだけ当てる。
    """

    __hash__ = None  # type: ignore[assignment]

    def __init__(self, node, attribute):
        """記録する値を保持する。

        Args:
            node (NodeRef): 所有ノードの参照。
            attribute (str): アトリビュートのパス(ノード名を含めない)。

        Raises:
            TypeError: nodeがNodeRefでない、またはattributeが文字列でない場合。
            ValueError: attributeが空の場合。
        """
        if not isinstance(node, NodeRef):
            raise TypeError("node must be a NodeRef")
        if not isinstance(attribute, str):
            raise TypeError("attribute must be a string")
        if not attribute:
            raise ValueError("attribute must not be empty")
        self._node = node
        self._attribute = attribute

    def __repr__(self):
        """ノード名とアトリビュートを含む表記を返す。

        Returns:
            str: ``PlugRef('chrA:arm_L_jnt.translateX')`` の形式。
        """
        return f"PlugRef({self._node.name + '.' + self._attribute!r})"

    def __eq__(self, other):
        """ノードの参照とアトリビュートのパスが同じかを返す。

        Args:
            other (object): 比較する値。

        Returns:
            bool: 同じ記録ならTrue。PlugRef以外はNotImplemented。
        """
        if not isinstance(other, PlugRef):
            return NotImplemented
        return self._node == other._node and self._attribute == other._attribute

    @classmethod
    def capture(cls, plug):
        """シーンのPlugから参照を作る。

        Args:
            plug (Plug | str | om2.MPlug): 記録するPlug。

        Returns:
            PlugRef: 所有ノードとアトリビュートのパスを記録した参照。

        Raises:
            TypeError: plugが対応しない型の場合。
            ValueError: Plugが存在しない場合。
            RuntimeError: Plugが無効な場合。
        """
        # 循環参照の回避: plugs・cmdsはノードのメソッドからmlib.jsonを使う。
        from ..cmds import getPlug
        from ..plugs.plug import Plug
        plug = plug if isinstance(plug, Plug) else getPlug(plug)
        if not plug.isValid():
            raise RuntimeError("Cannot record a deleted plug")
        attribute = plug.mplug().partialName(includeNodeName=False, includeNonMandatoryIndices=True,
                                             includeInstancedIndices=True, useLongNames=True)
        return cls(NodeRef.capture(plug.getNode()), attribute)

    @classmethod
    def fromData(cls, data):
        """:meth:`toData` の辞書から作る。

        Args:
            data (dict): ``node``・``attr`` を持つ辞書。

        Returns:
            PlugRef: 新しい参照。

        Raises:
            ValueError: 辞書の形が違う場合。
        """
        if not isinstance(data, dict) or "node" not in data or not isinstance(data.get("attr"), str):
            raise ValueError(f"Invalid plug reference in JSON: {data!r}")
        return cls(NodeRef.fromData(data["node"]), data["attr"])

    @property
    def node(self):
        """所有ノードの参照を返す。

        Returns:
            NodeRef: 保持する参照。
        """
        return self._node

    @property
    def attribute(self):
        """アトリビュートのパスを返す。

        Returns:
            str: ``"translateX"``・``"weight[3]"`` 等。
        """
        return self._attribute

    def toData(self):
        """JSONに書く辞書を返す。

        Returns:
            dict: ``{"node": {...}, "attr": ...}``。
        """
        return {"node": self._node.toData(), "attr": self._attribute}

    def mappedName(self, mapping=None):
        """対応付けを当てたPlug名を返す。

        Args:
            mapping (NameMapping | None): 名前の対応付け。

        Returns:
            str: ``<ノード名>.<アトリビュート>``。警告や報告の表示に使う。
        """
        return self._node.mappedName(mapping) + "." + self._attribute

    def resolve(self, mapping=None):
        """対応付けを当てたノードの、同じアトリビュートのPlugを返す。

        Args:
            mapping (NameMapping | None): 名前の対応付け。

        Returns:
            Plug | None: 見つかったPlug。ノードまたはアトリビュートが無ければNone。

        Raises:
            TypeError: mappingがNameMapping・None以外の場合。
        """
        if mapping is not None and not isinstance(mapping, NameMapping):
            raise TypeError("mapping must be a NameMapping or None")
        node = self._node.resolve(mapping)
        if node is None:
            return None
        try:
            return node.getPlug(self._attribute)
        except (AttributeError, RuntimeError, ValueError):
            return None
