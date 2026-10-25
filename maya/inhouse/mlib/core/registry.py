"""Mayaの型名と明示したラッパークラスの対応を管理する。"""

import maya.cmds as cmds

__all__ = ["NodeRegistry"]

for _name in ("collection_export", "discover_node_package", "node_wrapper", "plug_wrapper"):
    globals().pop(_name, None)


#: node_type -> 継承チェーン(自身を先頭、基底型へ向かう順)の tuple。
_INHERITED_TYPES_CACHE = {}


def _inherited_node_types(node_type):
    """指定ノードタイプの継承チェーンを取得する。

    ``cmds.nodeType(node_type, isTypeName=True, inherited=True)`` は
    ノードの実体を必要とせず型名だけで継承関係を照会できる一方、都度
    Maya に問い合わせるとやや低速なため、認識済みの型名だけ結果をキャッシュする。
    未知型は後からプラグインが導入される可能性があるため、負結果を保存しない。
    Maya API 2.0 に同等の照会手段が無いため cmds を使用する。

    Args:
        node_type (str): Maya の nodeType 名。

    Returns:
        tuple[str, ...]: node_type 自身を先頭に、直接の親から基底型へ
            向かう順の継承チェーン。Maya が認識しない型名の場合は
            node_type 自身のみを含む1要素の tuple。
    """
    cached = _INHERITED_TYPES_CACHE.get(node_type)
    if cached is not None:
        return cached
    try:
        chain = cmds.nodeType(node_type, isTypeName=True, inherited=True)
    except RuntimeError:
        return (node_type,)
    if not chain:
        return (node_type,)
    chain = tuple(reversed(chain))
    _INHERITED_TYPES_CACHE[node_type] = chain
    return chain


def _clear_type_hierarchy_cache():
    """キャッシュを消去する。

    Returns:
        None: 値を返さない。
    """
    _INHERITED_TYPES_CACHE.clear()


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
        """文字列キーへラッパークラスを登録する。同じキーは上書きする。

        NodeのnodeTypeやPlugのアトリビュート型で共通に使い、非空strとclassの対応形式を検証する。

        Args:
            node_type (str): 空でない登録キー。
            wrapper_class (type): 対応するクラス。

        Raises:
            ValueError: キーが空または文字列以外の場合。
            TypeError: wrapper_classがクラス以外の場合。
        """
        self._validate_entry(node_type, wrapper_class)
        self._classes[node_type] = wrapper_class

    def clear(self):
        """この表の登録対応を空にする。フォールバック型と継承検索の設定は保持する。"""
        self._classes.clear()

    def replace(self, wrappers):
        """全キーと値の対応形式を検証してから、この表を置き換える。

        検査は非空strとclassの対応形式に限り、検証失敗時は現在の登録を保つ。

        Args:
            wrappers (Mapping[str, type]): 登録キーとクラスの対応。

        Raises:
            ValueError: キーが空または文字列以外の場合。
            TypeError: 値がクラス以外の場合。
        """
        validated = {}
        for node_type, wrapper_class in wrappers.items():
            self._validate_entry(node_type, wrapper_class)
            validated[node_type] = wrapper_class
        self._classes.clear()
        self._classes.update(validated)

    def wrapper_class(self, node_type):
        """キーの登録クラスを返す。未登録なら設定に応じて祖先型またはフォールバックを使う。

        resolve_inherited_types=Trueの場合だけ、MayaのnodeType継承を近い祖先から調べる。
        Plugの型等、ノード継承を使わない表では完全一致とフォールバックだけを使う。

        Args:
            node_type (str): 登録キー。継承検索を使う表ではMayaのnodeType名。

        Returns:
            type: 完全一致、最寄りの登録祖先型、またはフォールバックのクラス。
        """
        resolved = self._classes.get(node_type)
        if resolved is not None:
            return resolved
        if self._resolve_inherited_types:
            for ancestor in _inherited_node_types(node_type)[1:]:
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
        """登録キーをwrapper_classと同じ規則で解決する。

        Args:
            node_type (str): ノード型・アトリビュート型等の登録キー。

        Returns:
            type: 完全一致、設定された祖先検索、またはフォールバックで選んだクラス。
        """
        return self.wrapper_class(node_type)

    def _node_type_for_class(self, wrapper_class):
        """現在の登録表で具体クラスに一意に対応するnodeTypeを取得する。

        Args:
            wrapper_class (type): 新規作成に使用するノードラッパークラス。

        Returns:
            str: クラスそのものへ登録されたMaya nodeType。

        Raises:
            TypeError: 対応する登録がない、または複数のnodeTypeに登録されている場合。
        """
        node_types = [name for name, registered in self._classes.items()
                      if registered is wrapper_class]
        if len(node_types) != 1:
            raise TypeError("create=True requires a class registered for exactly one Maya nodeType: "
                            + wrapper_class.__name__)
        return node_types[0]

    @staticmethod
    def _validate_entry(node_type, wrapper_class):
        """汎用登録の型名とクラスを検証する。既存キーの上書きは拒否しない。

        Args:
            node_type (str): 登録する型名。
            wrapper_class (type): 対応するクラス。

        Raises:
            ValueError: 型名が空文字列または文字列以外の場合。
            TypeError: wrapper_classがクラスではない場合。
        """
        if not isinstance(node_type, str) or not node_type:
            raise ValueError("node_type must be a non-empty string")
        if not isinstance(wrapper_class, type):
            raise TypeError("wrapper_class must be a class")

    def _snapshot(self):
        """拡張の登録開始前に、現在の型対応を独立したコピーで保持する。

        Returns:
            dict[str, type]: この登録表だけが復元に使う内部状態。
        """
        return dict(self._classes)

    def _restore(self, snapshot):
        """登録中の障害で、検証済みの保存状態を再登録せずに復元する。

        Args:
            snapshot (dict[str, type]): _snapshotで取得した内部状態。
        """
        self._classes.clear()
        self._classes.update(snapshot)
