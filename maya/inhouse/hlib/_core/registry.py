"""Maya の型名とラッパークラスの対応を宣言・管理する。"""

from .discovery import discover_node_package
from .type_hierarchy import inherited_node_types


def node_wrapper(node_type, public=True):
    """Maya の nodeType と Python wrapper class の対応を宣言する。

    Args:
        node_type (str): Maya の ``nodeType`` 名。
        public (bool): hlib のトップレベル API として公開するか。

    Returns:
        callable: wrapper class を受け取り metadata を付与する decorator。

    Raises:
        ValueError: node_type が空文字列または文字列以外の場合。
    """
    if not isinstance(node_type, str) or not node_type:
        raise ValueError("node_type must be a non-empty string")

    def decorate(wrapper_class):
        """wrapper class に nodeType と公開設定を付与する。

        Args:
            wrapper_class (type): メタデータを付与するクラス。

        Returns:
            type: メタデータを設定した入力クラスそのもの。

        Raises:
            TypeError: wrapper_class がクラスでない場合。
        """
        if not isinstance(wrapper_class, type):
            raise TypeError("wrapper_class must be a class")
        wrapper_class.__hlib_node_type__ = node_type
        wrapper_class.__hlib_public__ = bool(public)
        return wrapper_class

    return decorate


def collection_export(public=True):
    """Node collection class を hlib の公開 export として宣言する。

    Args:
        public (bool): hlib のトップレベル API として公開するか。

    Returns:
        callable: collection class を受け取り metadata を付与する decorator。
    """

    def decorate(collection_class):
        """collection class に公開設定を付与する。

        Args:
            collection_class (type): メタデータを付与するクラス。

        Returns:
            type: メタデータを設定した入力クラスそのもの。

        Raises:
            TypeError: collection_class がクラスでない場合。
        """
        if not isinstance(collection_class, type):
            raise TypeError("collection_class must be a class")
        collection_class.__hlib_collection__ = True
        collection_class.__hlib_public__ = bool(public)
        return collection_class

    return decorate


def plug_wrapper(attr_type, public=True):
    """Maya の属性データ型と Python wrapper class の対応を宣言する。

    Args:
        attr_type (str): ``cmds.getAttr(..., type=True)`` が返す型名。
        public (bool): hlib のトップレベル API として公開するか。

    Returns:
        callable: wrapper class を受け取り metadata を付与する decorator。

    Raises:
        ValueError: attr_type が空文字列または文字列以外の場合。
    """
    if not isinstance(attr_type, str) or not attr_type:
        raise ValueError("attr_type must be a non-empty string")

    def decorate(wrapper_class):
        """wrapper class に属性型と公開設定を付与する。

        Args:
            wrapper_class (type): メタデータを付与するクラス。

        Returns:
            type: メタデータを設定した入力クラスそのもの。

        Raises:
            TypeError: wrapper_class がクラスでない場合。
        """
        if not isinstance(wrapper_class, type):
            raise TypeError("wrapper_class must be a class")
        wrapper_class.__hlib_plug_type__ = attr_type
        wrapper_class.__hlib_public__ = bool(public)
        return wrapper_class

    return decorate


class NodeRegistry:
    """ノード型・属性型などの文字列キーとラッパークラスを対応付ける登録表。"""

    def __init__(self, fallback_class, resolve_inherited_types=False):
        """フォールバッククラスと空のノード型対応表を初期化する。

        Args:
            fallback_class (type): 未登録キーに対して使用するクラス。
            resolve_inherited_types (bool): ``True`` の場合、完全一致が
                無いキーに対して Maya のノードタイプ継承チェーンを辿り、
                最も近い登録済み祖先型のクラスを返す(Plug の属性型など、
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

    def register_discovered(self, wrappers):
        """発見済み wrapper の対応表を registry へ登録する。

        登録表を消去してから順に登録する。途中で失敗した場合は部分的に登録された状態になる。

        Args:
            wrappers (Mapping[str, type]): 型名からラッパークラスへの対応表。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: キーが空文字列または文字列以外の場合。
            TypeError: 値がクラスでない場合。
        """
        self.clear()
        for node_type, wrapper_class in wrappers.items():
            self.register(node_type, wrapper_class)

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
        （例: Plug の属性型 dispatch）。

        Args:
            key (str): 登録キー（nodeType または属性型など）。

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

__all__ = [
    "NodeRegistry",
    "collection_export",
    "discover_node_package",
    "node_wrapper",
]