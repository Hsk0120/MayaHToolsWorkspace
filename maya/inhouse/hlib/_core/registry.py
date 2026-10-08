"""Mayaの型名と明示したラッパークラスの対応を管理する。"""

from .typeHierarchy import inherited_node_types

__all__ = ["NodeRegistry"]

for _name in ("collection_export", "discover_node_package", "node_wrapper", "plug_wrapper"):
    globals().pop(_name, None)


class NodeRegistry:
    """ノード型・アトリビュート型などの文字列キーとラッパークラスを対応付ける登録表。"""

    def __init__(self, fallback_class, resolve_inherited_types=False):
        """フォールバッククラスと空のノード型対応表を初期化する。

        Args:
            fallback_class (type): 未登録キーに対して使用するクラス。
            resolve_inherited_types (bool): ``True`` の場合、完全一致が
                無いキーに対して Maya のノードタイプ継承チェーンを辿り、
                最も近い登録済み祖先型のクラスを返す(Plug のアトリビュート型など、
                Mayaのノードタイプ継承と無関係なキー体系では使わない)。

        Returns:
            None: 値を返さない。
        """
        self._fallback_class = fallback_class
        self._resolve_inherited_types = resolve_inherited_types
        self._classes = {}

    def register(self, node_type, wrapper_class):
        """Maya ノード型へラッパークラスを登録する。

        同じキーが既にある場合は上書きする。

        Args:
            node_type (str): Maya の nodeType 名。
            wrapper_class (type): ノードをラップする hlib クラス。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: node_type が空文字列または文字列以外の場合。
            TypeError: wrapper_class がクラスでない場合。
        """
        if not isinstance(node_type, str) or not node_type:
            raise ValueError("node_type must be a non-empty string")
        if not isinstance(wrapper_class, type):
            raise TypeError("wrapper_class must be a class")
        self._classes[node_type] = wrapper_class

    def clear(self):
        """登録済みの Maya nodeType 対応をすべて解除する。

        Returns:
            None: 値を返さない。
        """
        self._classes.clear()

    def replace(self, wrappers):
        """明示した型対応で登録表を置き換える。

        全入力を検証してから置き換えるため、不正な入力で現在の登録を失わない。

        Args:
            wrappers (Mapping[str, type]): 型名からラッパークラスへの対応表。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: キーが空文字列または文字列以外の場合。
            TypeError: 値がクラスでない場合。
        """
        validated = {}
        for node_type, wrapper_class in wrappers.items():
            if not isinstance(node_type, str) or not node_type:
                raise ValueError("node_type must be a non-empty string")
            if not isinstance(wrapper_class, type):
                raise TypeError("wrapper_class must be a class")
            validated[node_type] = wrapper_class
        self._classes.clear()
        self._classes.update(validated)

    def wrapper_class(self, node_type):
        """ノード型に対応するクラス、またはフォールバッククラスを返す。

        完全一致する登録が無く ``resolve_inherited_types`` が有効な場合、
        Maya のノードタイプ継承チェーンを直接の親から基底型へ向かって辿り、
        最初に見つかった登録済み祖先型のクラスを返す。例えばプラグインが
        ``locator`` を継承した独自ノードタイプを追加した場合でも、
        ``locator`` 用に登録済みのクラスが選ばれる。

        Args:
            node_type (str): Maya の nodeType 名。

        Returns:
            type: 登録済み、継承チェーン経由、またはフォールバックのラッパークラス。
        """
        resolved = self._classes.get(node_type)
        if resolved is not None:
            return resolved
        if self._resolve_inherited_types:
            for ancestor in inherited_node_types(node_type)[1:]:
                resolved = self._classes.get(ancestor)
                if resolved is not None:
                    return resolved
        return self._fallback_class

    def lookup(self, key):
        """登録済みクラスを返す。未登録なら ``None``。

        フォールバックを伴わずに「完全一致する登録があるか」だけを知りたい場合に使う
        （例: Plug のアトリビュート型 dispatch）。

        Args:
            key (str): 登録キー（nodeType またはアトリビュート型など）。

        Returns:
            type | None: 登録済みクラス。
        """
        return self._classes.get(key)

    def get(self, node_type):
        """ノード型に対応するラッパークラスを返す。

        Args:
            node_type (str): Maya の nodeType 名。

        Returns:
            type: 登録済みまたはフォールバックのラッパークラス。
        """
        return self.wrapper_class(node_type)
