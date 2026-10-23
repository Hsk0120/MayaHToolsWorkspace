"""明示したfast引数の有効範囲。Undoのグローバル設定は変更しない。"""

import inspect
from contextvars import ContextVar
from functools import wraps

_active = ContextVar("mlib_fast_edit", default=False)


def is_fast():
    """現在の呼出しがOpenMaya直接編集を要求しているか。

    Returns:
        bool: 現在の呼出しがOpenMaya直接編集を要求しているか。
    """
    return _active.get()


def fast_edit(function):
    """fast引数を検証し、内側の対応メソッドへ実行モードを伝える。

    外側がfastなら、省略・fast=Falseでも内側は直接更新を継承する。
    各呼出しの引数は継承中もboolを検証し、開始した範囲だけを終了時に復元する。

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
        """fastの型を検証し、有効範囲を復元しながら元の関数を実行する。

        Args:
            *args (object): 元の関数へ渡す位置引数。
            **kwargs (object): fastを含む元の関数のキーワード引数。

        Returns:
            object: 元の関数の戻り値。

        Raises:
            TypeError: fastがboolでない場合、または元の関数の引数が不正な場合。
        """
        # keyword-only は呼出しごとの Signature.bind を避ける。
        # その他の引数の正当性は元関数の Python 呼出しが検証する。
        if keyword_only:
            requested = kwargs.get("fast", False)
        else:
            requested = signature.bind(*args, **kwargs).arguments.get("fast", False)
        if type(requested) is not bool:
            raise TypeError("fast must be a bool")
        # Falseは通常モードへの強制切替ではなく、外側の指定を維持する。
        if is_fast() or not requested:
            return function(*args, **kwargs)
        token = _active.set(True)
        try:
            return function(*args, **kwargs)
        finally:
            _active.reset(token)
    return wrapped
