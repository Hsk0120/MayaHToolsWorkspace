"""明示したfast引数の有効範囲。Undoのグローバル設定は変更しない。"""

import inspect
from contextvars import ContextVar
from functools import wraps

_active = ContextVar("hlib_fast_edit", default=False)


def is_fast():
    """bool: 現在の呼出しがOpenMaya直接編集を要求しているか。"""
    return _active.get()


def fast_edit(function):
    """fast引数を検証し、内側の対応メソッドへ実行モードを伝える。

    Args:
        function (callable): fast 引数を持つ編集関数。

    Returns:
        callable: fast の検証と実行モードの伝播を行う関数。
    """
    signature = inspect.signature(function)
    parameter = signature.parameters.get("fast")
    keyword_only = parameter is not None and parameter.kind == inspect.Parameter.KEYWORD_ONLY

    @wraps(function)
    def wrapped(*args, **kwargs):
        # keyword-only は呼出しごとの Signature.bind を避ける。
        # その他の引数の正当性は元関数の Python 呼出しが検証する。
        if keyword_only:
            fast = kwargs.get("fast", False)
        else:
            fast = signature.bind(*args, **kwargs).arguments.get("fast", False)
        if type(fast) is not bool:
            raise TypeError("fast must be a bool")
        if is_fast() or not fast:
            return function(*args, **kwargs)
        token = _active.set(True)
        try:
            return function(*args, **kwargs)
        finally:
            _active.reset(token)
    return wrapped
