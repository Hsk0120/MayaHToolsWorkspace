"""Python呼出しをMayaのアイドルへ予約する。"""


def executeDeferred(callback, *args, **kwargs):
    """遅延実行を予約する。

    Args:
        callback (Callable): 実行する関数。
        *args: 関数の位置引数。
        **kwargs: 関数のキーワード引数。

    Returns:
        None: 予約のみを行い、コールバックの戻り値は返さない。

    Raises:
        TypeError: callbackが呼び出し可能でない場合。

    予約時にはシーンやUndoを変更しない。実行タイミングと遅延中の例外は
    Mayaのアイドル処理に従い、例外はMaya側へ通知される。
    """
    from ..common.deferred import Deferred

    return Deferred.call(callback, *args, **kwargs)
