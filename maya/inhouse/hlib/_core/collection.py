"""ノードコレクションに単体の公開APIを明示登録する。"""

import inspect


def bulk_api(item_class, undo=True, per_item_only=(), *, reads=(), writes=(), properties=()):
    """宣言した単体APIだけをコレクションへ公開する。

    Args:
        item_class (type): 単体クラス。派生での同名overrideにも追従する。
        undo (bool): 一括呼出をUndoチャンクにまとめるか。
        per_item_only (Iterable[str]): call_eachによる要素別指定だけを許可する名前。
        reads (Iterable[str]): 各戻り値のリストを返す操作。生成など結果が必要な更新も含む。
        writes (Iterable[str]): 更新後にコレクション自身を返す操作。
        properties (Iterable[str]): 保持値をリストとして公開する読取プロパティ。

    Returns:
        callable: コレクションクラス用デコレータ。基底の宣言と明示実装を継承する。
    """
    def decorate(collection):
        """宣言と継承先を検証し、必要な転送だけを生成する。"""
        policies = {}
        restricted = set(per_item_only)
        for base in reversed(collection.__bases__):
            policies.update(getattr(base, "_bulk_returns", {}))
            restricted.update(getattr(base, "_bulk_per_item_only", ()))
        if set(reads) & set(writes):
            raise ValueError("Bulk read/write declarations overlap")
        policies.update((name, "list") for name in reads)
        policies.update((name, "self") for name in writes)
        if not restricted <= policies.keys():
            raise ValueError("Per-item methods must be explicitly declared")
        methods = {}
        for name in policies:
            descriptor = inspect.getattr_static(item_class, name)
            if name.startswith("_") or not inspect.isfunction(descriptor):
                raise TypeError("Expected a public instance method: " + name)
            methods[name] = descriptor
            existing = inspect.getattr_static(collection, name, None)
            if name in restricted:
                setattr(collection, name, _PerItemOnly(name))
            elif existing is None or getattr(existing, "_bulk_generated", False):
                setattr(collection, name, _method(name, descriptor, collection, policies[name]))
        for name in properties:
            if not isinstance(inspect.getattr_static(item_class, name), property):
                raise TypeError("Expected a property: " + name)
            if not hasattr(collection, name):
                setattr(collection, name, _property(name))
        collection._bulk_returns = policies
        collection._bulk_per_item_only = frozenset(restricted)
        collection._bulk_methods = methods
        collection._bulk_undo = undo
        return collection
    return decorate


def _method(name, original, collection, result_kind):
    """同一引数で単体メソッドを呼ぶ公開メソッドを生成する。"""
    def method(self, *args, **kwargs):
        return self._dispatch_shared(name, args, kwargs)
    method._bulk_generated = True
    method.__name__ = name
    method.__qualname__ = collection.__name__ + "." + name
    method.__module__ = collection.__module__
    method.__signature__ = inspect.signature(original)
    result_doc = "コレクション自身" if result_kind == "self" else "保持順の戻り値リスト"
    method.__doc__ = (f"各要素の{name}を同じ引数で呼び、{result_doc}を返す。\n\n"
                      "単体メソッドの引数を受け取る。途中の失敗はRuntimeErrorで停止し、"
                      "完了済み変更は自動で戻さない。")
    return method


def _property(name):
    """単体の読取プロパティを保持順のリストとして公開する。"""
    return property(lambda self: [getattr(item, name) for item in self._items],
                    doc=f"list: 保持順の{name}。個別の値を返し、集約しない。")


class _PerItemOnly:
    """基底クラスの一括入口も隠し、要素別指定だけを許可する記述子。"""

    def __init__(self, name):
        """禁止するメソッド名を保持する。"""
        self._name = name

    def __get__(self, instance, owner=None):
        """直接取得を拒否する。call_eachは単体から関数を取得するため利用可能。"""
        raise AttributeError(f"{self._name} requires call_each with per-item arguments")
