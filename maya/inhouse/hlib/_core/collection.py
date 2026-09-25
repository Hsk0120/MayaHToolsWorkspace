"""同種コレクションに単体の公開インスタンスAPIを明示登録する。"""

import contextlib
import inspect
from ..decorators.undo import undo_chunk
from .flags import normalize_flags


class BulkCollection:
    """保持順の一括呼び出し。クラス固有の既存メソッドを優先する。"""

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
            list: 各呼び出しの戻り値。ネストしたリストもそのまま保持する。
        Raises:
            ValueError: メソッド名・件数が不正な場合。
            TypeError: 引数のシグネチャが不正な場合。実行前に全件確認する。
            RuntimeError: 単体の処理が失敗した場合。対象番号を含み、後続は実行しない。

        シーン編集は1回のUndoにまとめる。自動ロールバックはしない。
        Pluginのload/unloadやファイルI/OはUndo対象外。
        """
        if method not in self._bulk_methods:
            raise ValueError(f"Unsupported instance method: {method}")
        args = [tuple(row) for row in arguments]
        kwargs = [{} for _ in self._items] if keyword_arguments is None else [dict(row) for row in keyword_arguments]
        if len(args) != len(self) or len(kwargs) != len(self):
            raise ValueError("Argument count must match collection length")
        functions = [getattr(item, method) for item in self._items]
        kwargs = [normalize_flags(function, flags) for function, flags in zip(functions, kwargs)]
        for function, row, flags in zip(functions, args, kwargs):
            inspect.signature(function).bind(*row, **flags)
        all_fast = bool(kwargs) and all(flags.get("fast") is True for flags in kwargs)
        context = undo_chunk("hlibBulk_" + method) if self._bulk_undo and not all_fast else contextlib.nullcontext()
        result = []
        with context:
            for index, (function, row, flags) in enumerate(zip(functions, args, kwargs)):
                try:
                    result.append(function(*row, **flags))
                except Exception as exc:
                    raise RuntimeError(f"{type(self).__name__}.{method} failed at item {index}: {exc}") from exc
        return result


def bulk_api(item_class, undo=True, per_item_only=()):
    """単体の公開APIをコレクションに登録する。属性の暗黙転送は行わない。

    Args:
        item_class (type): 単体クラス。
        undo (bool): 一括呼び出しをUndoチャンクにまとめるか。
        per_item_only (Iterable[str]): 同一引数の転送を禁止するメソッド。call_eachで使用。
    Returns:
        callable: コレクションクラス用デコレータ。
    """
    def decorate(collection):
        methods = {}
        for name in dir(item_class):
            if name.startswith("_"):
                continue
            descriptor = inspect.getattr_static(item_class, name)
            if inspect.isfunction(descriptor):
                methods[name] = descriptor
                if not hasattr(collection, name) and name not in per_item_only:
                    setattr(collection, name, _method(name, descriptor, collection))
            elif isinstance(descriptor, property) and not hasattr(collection, name):
                setattr(collection, name, _property(name))
        collection._bulk_methods = methods
        collection._bulk_undo = undo
        return collection
    return decorate


def _method(name, original, collection):
    """同一引数で単体メソッドを呼ぶ公開メソッドを生成する。"""
    def method(self, *args, **kwargs):
        return self.call_each(name, [args] * len(self), [kwargs] * len(self))
    method.__name__ = name
    method.__qualname__ = collection.__name__ + "." + name
    method.__module__ = collection.__module__
    method.__signature__ = inspect.signature(original)
    method.__doc__ = (f"各要素の{name}を同じ引数で呼び、保持順の戻り値リストを返す。\n\n"
                      "単体メソッドの引数を受け取る。途中の失敗はRuntimeErrorで停止し、"
                      "完了済み変更は自動で戻さない。")
    return method


def _property(name):
    """単体の読取プロパティを保持順のリストとして公開する。"""
    return property(lambda self: [getattr(item, name) for item in self._items],
                    doc=f"list: 保持順の{name}。個別の値を返し、集約しない。")
