"""Python呼出しをMayaのアイドルへ予約する。"""


def executeDeferred(callback, *args, **kwargs):
    """遅延実行を予約する。

    Args:
        callback (Callable): 実行する関数。
        *args: 関数の位置引数。
        **kwargs: 関数のキーワード引数。
    """
    from ..general.deferred import Deferred

    Deferred.call(callback, *args, **kwargs)
