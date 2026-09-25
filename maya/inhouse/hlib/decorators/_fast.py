"""明示したfast引数の有効範囲。Undoのグローバル設定は変更しない。"""
from contextvars import ContextVar
from functools import wraps
import inspect

_active = ContextVar("hlib_fast_edit", default=False)


def is_fast():
    """bool: 現在の呼出しがOpenMaya直接編集を要求しているか。"""
    return _active.get()


def fast_edit(function):
    """fast引数を検証し、内側の対応メソッドへ実行モードを伝える。"""
    signature = inspect.signature(function)

    @wraps(function)
    def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        fast = bound.arguments.get("fast", False)
        if type(fast) is not bool:
            raise TypeError("fast must be a bool")
        token = _active.set(is_fast() or fast)
        try:
            return function(*args, **kwargs)
        finally:
            _active.reset(token)
    return wrapped
