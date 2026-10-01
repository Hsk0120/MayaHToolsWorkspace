"""同種コレクションに単体の公開インスタンスAPIを明示登録する。"""

import contextlib
import inspect
from ..decorators.undo import undo_chunk
from .flags import normalize_flags


class BulkCollection:
    """保持順の一括呼び出し。クラス固有の既存メソッドを優先する。"""

    def __iter__(self):
        """保持順に要素を反復する。

        Returns:
            Iterator: 保持している要素のイテレータ。
        """
        return iter(self._items)

    def __len__(self):
        """int: 保持要素数。"""
        return len(self._items)

    def __getitem__(self, index):
        """単体、またはsliceに対応する同型コレクションを返す。"""
        return type(self)(self._items[index]) if isinstance(index, slice) else self._items[index]

    def call_each(self, method, arguments, keyword_arguments=None):
        """各要素へ異なる引数を渡す。メソッド名は単体の公開インスタンスメソッドのみ。

        Args:
            method (str): set_translate等。create・特殊メソッドは不可。
            arguments (Iterable[tuple]): 要素数と同じ数の位置引数タプル。
            keyword_arguments (Iterable[dict] | None): 要素別キーワード引数。省略時は空。
        Returns:
            list | BulkCollection: 照会・結果を返す操作は保持順のリスト、更新は自身。
                ネストしたリストもそのまま保持する。
        Raises:
            ValueError: メソッド名・件数が不正な場合。
            TypeError: 引数のシグネチャが不正な場合。実行前に全件確認する。
            RuntimeError: 単体の処理が失敗した場合。対象番号を含み、後続は実行しない。

        シーン編集は1回のUndoにまとめる。自動ロールバックはしない。
        Pluginのload/unloadやファイルI/OはUndo対象外。
        """
        functions, args, kwargs = self._prepare_calls(method, arguments, keyword_arguments)
        return self._execute_calls(method, functions, args, kwargs)

    def _execute_calls(self, method, functions, args, kwargs):
        """検証済み呼出しを実行し、更新操作では不要な結果配列を作らない。"""
        all_fast = bool(kwargs) and all(flags.get("fast") is True for flags in kwargs)
        context = undo_chunk("hlibBulk_" + method) if self._bulk_undo and not all_fast else contextlib.nullcontext()
        result = [] if self._bulk_returns[method] != "self" else None
        with context:
            for index, (function, row, flags) in enumerate(zip(functions, args, kwargs)):
                try:
                    value = function(*row, **flags)
                    if result is not None:
                        result.append(value)
                except Exception as exc:
                    raise RuntimeError(f"{type(self).__name__}.{method} failed at item {index}: {exc}") from exc
        return self if result is None else result

    def _call_shared(self, method, args, kwargs):
        """同じ入力の検証を実関数ごとに共有し、全件検証後に実行する。

        共有はこの呼出し内だけに限定する。派生overrideと個体callableは別に
        検証し、クラス差替え・reload後の古いメソッドを保持しない。
        """
        functions = [getattr(item, method) for item in self._items]
        shared = {}
        signatures = {}
        keywords = []
        for function in functions:
            key = function.__func__ if inspect.ismethod(function) else None
            if key is not None and key in shared:
                flags = shared[key]
            else:
                flags = normalize_flags(function, kwargs)
                self._signature(function, signatures).bind(*args, **flags)
                if key is not None:
                    shared[key] = flags
            keywords.append(flags)
        return self._execute_calls(method, functions, [args] * len(functions), keywords)

    def _prepare_calls(self, method, arguments, keyword_arguments):
        """全要素の引数を実行前に解決・検証する。

        Args:
            method (str): 登録済みの単体メソッド名。
            arguments (Iterable[tuple]): 要素別の位置引数。
            keyword_arguments (Iterable[dict] | None): 要素別のキーワード引数。

        Returns:
            tuple: 呼出先・位置引数・正規化済みキーワード引数の各リスト。

        Raises:
            ValueError: メソッド名または件数が不正な場合。
            TypeError: 引数が各呼出先のシグネチャと一致しない場合。
        """
        if method not in self._bulk_methods:
            raise ValueError(f"Unsupported instance method: {method}")
        args = [tuple(row) for row in arguments]
        kwargs = [{} for _ in self._items] if keyword_arguments is None else [dict(row) for row in keyword_arguments]
        if len(args) != len(self) or len(kwargs) != len(self):
            raise ValueError("Argument count must match collection length")
        functions = [getattr(item, method) for item in self._items]
        kwargs = [normalize_flags(function, flags) for function, flags in zip(functions, kwargs)]
        # この呼出内だけ共有し、reloadやクラスの差替え後に古いsignatureを保持しない。
        signatures = {}
        for function, row, flags in zip(functions, args, kwargs):
            self._signature(function, signatures).bind(*row, **flags)
        return functions, args, kwargs

    @staticmethod
    def _signature(function, signatures):
        """一回の検証内で実メソッドのsignatureだけを共有する。

        Args:
            function (callable): 実際に呼び出すメソッドまたは個体callable。
            signatures (dict): 呼出し内だけで使うキャッシュ。

        Returns:
            inspect.Signature: 束縛済み引数に対応するsignature。
        """
        if not inspect.ismethod(function):
            return inspect.signature(function)
        key = function.__func__
        if key not in signatures:
            signatures[key] = inspect.signature(function)
        return signatures[key]


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
        # 独自コレクションが公開入口をoverrideしている場合は従来どおり委譲する。
        if type(self).call_each is not BulkCollection.call_each:
            return self.call_each(name, [args] * len(self), [kwargs] * len(self))
        return self._call_shared(name, args, kwargs)
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
