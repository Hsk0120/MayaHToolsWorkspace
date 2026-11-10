"""コンポーネントの集まりを、シェイプの参照・種類・番号で記録する。"""

from .nameMapping import NameMapping
from .nodeRef import NodeRef

#: 記録するコンポーネントの種類(Mayaの表記)と、mlibの集まりのクラス名。
_COLLECTIONS = {"vtx": "Vertices", "e": "Edges", "f": "Faces", "map": "UVs", "cv": "CVs"}


class ComponentRef:
    """同じシェイプ・同じ種類のコンポーネントを、シェイプの :class:`NodeRef`・種類・番号で記録した参照。

    種類はMayaの表記(``"vtx"``・``"e"``・``"f"``・``"map"``・``"cv"``)。番号は記録した順のまま保つ。
    名前の対応付けはシェイプの部分にだけ当てる。
    """

    __hash__ = None  # type: ignore[assignment]

    def __init__(self, node, type, indices):
        """記録する値を保持する。

        Args:
            node (NodeRef): シェイプの参照。
            type (str): コンポーネントの種類(``"vtx"`` 等)。
            indices (Iterable[int]): 番号。

        Raises:
            TypeError: nodeがNodeRefでない、または番号がint以外(boolを含む)の場合。
            ValueError: 種類が対応外、または番号が負の場合。
        """
        if not isinstance(node, NodeRef):
            raise TypeError("node must be a NodeRef")
        if type not in _COLLECTIONS:
            raise ValueError(f"Unsupported component type {type!r}; expected one of {sorted(_COLLECTIONS)}")
        values = []
        for index in indices:
            if isinstance(index, bool) or not isinstance(index, int):
                raise TypeError("component indices must be ints")
            if index < 0:
                raise ValueError("component indices must not be negative")
            values.append(index)
        self._node = node
        self._type = type
        self._indices = tuple(values)

    def __repr__(self):
        """シェイプ名・種類・番号の数を含む表記を返す。

        Returns:
            str: ``ComponentRef('chrA:bodyShape', 'vtx', 12 indices)`` の形式。
        """
        return f"ComponentRef({self._node.name!r}, {self._type!r}, {len(self._indices)} indices)"

    def __eq__(self, other):
        """シェイプの参照・種類・番号が同じかを返す。

        Args:
            other (object): 比較する値。

        Returns:
            bool: 同じ記録ならTrue。ComponentRef以外はNotImplemented。
        """
        if not isinstance(other, ComponentRef):
            return NotImplemented
        return (self._node, self._type, self._indices) == (other._node, other._type, other._indices)

    @classmethod
    def capture(cls, components):
        """mlibのコンポーネントまたはその集まりから参照を作る。

        Args:
            components (Component | Components): 記録するコンポーネント。

        Returns:
            ComponentRef: シェイプ・種類・番号を記録した参照。

        Raises:
            TypeError: componentsがmlibのコンポーネントでない場合。
            ValueError: 種類が記録できないものの場合。
        """
        # 循環参照の回避: componentsはnodesを経由してmlib.jsonを使う。
        from ..components import Component, Components
        if isinstance(components, Component):
            shape, kind, indices = components.shape, components.component_type, [components.index]
        elif isinstance(components, Components):
            shape = components.shape
            kind = components.component_class.component_type
            indices = list(components.indices)
        else:
            raise TypeError("components must be an mlib Component or Components")
        return cls(NodeRef.capture(shape), kind, indices)

    @classmethod
    def fromData(cls, data):
        """:meth:`toData` の辞書から作る。

        Args:
            data (dict): ``node``・``type``・``indices`` を持つ辞書。

        Returns:
            ComponentRef: 新しい参照。

        Raises:
            ValueError: 辞書の形が違う場合。
        """
        if not isinstance(data, dict) or "node" not in data or not isinstance(data.get("indices"), list):
            raise ValueError(f"Invalid component reference in JSON: {data!r}")
        try:
            return cls(NodeRef.fromData(data["node"]), data.get("type"), data["indices"])
        except TypeError as error:
            raise ValueError(f"Invalid component reference in JSON: {data!r}") from error

    @property
    def node(self):
        """シェイプの参照を返す。

        Returns:
            NodeRef: 保持する参照。
        """
        return self._node

    @property
    def type(self):
        """コンポーネントの種類を返す。

        Returns:
            str: ``"vtx"``・``"e"``・``"f"``・``"map"``・``"cv"``。
        """
        return self._type

    @property
    def indices(self):
        """記録した番号を返す。

        Returns:
            tuple[int, ...]: 記録した順の番号。
        """
        return self._indices

    def toData(self):
        """JSONに書く辞書を返す。

        Returns:
            dict: ``{"node": {...}, "type": ..., "indices": [...]}``。
        """
        return {"node": self._node.toData(), "type": self._type, "indices": list(self._indices)}

    def mappedName(self, mapping=None):
        """対応付けを当てたシェイプ名と種類を返す。

        Args:
            mapping (NameMapping | None): 名前の対応付け。

        Returns:
            str: ``<シェイプ名>.<種類>[...]``。警告や報告の表示に使う。
        """
        return f"{self._node.mappedName(mapping)}.{self._type}[...]"

    def resolve(self, mapping=None):
        """対応付けを当てたシェイプの、同じ番号のコンポーネントの集まりを返す。

        Args:
            mapping (NameMapping | None): 名前の対応付け。

        Returns:
            Components | None: ``Vertices`` 等の集まり。シェイプが無い、型が合わない、または
                番号が範囲外ならNone。

        Raises:
            TypeError: mappingがNameMapping・None以外の場合。
        """
        if mapping is not None and not isinstance(mapping, NameMapping):
            raise TypeError("mapping must be a NameMapping or None")
        shape = self._node.resolve(mapping)
        if shape is None:
            return None
        # 循環参照の回避: componentsはnodesを経由してmlib.jsonを使う。
        from .. import components
        try:
            return getattr(components, _COLLECTIONS[self._type])(shape, self._indices)
        except (IndexError, TypeError, RuntimeError):
            return None
