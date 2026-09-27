"""MayaのGUIアイドル処理へPython呼出しを予約する。"""


class Deferred:
    """maya.utilsの遅延実行を共通化する。"""

    @staticmethod
    def call(callback, *args, **kwargs):
        """次の実行可能なタイミングへコールバックを予約する。

        Args:
            callback (Callable): 実行するPython関数。コード文字列は受け付けない。
            *args: 関数へ渡す位置引数。
            **kwargs: 関数へ渡すキーワード引数。

        Raises:
            TypeError: callbackが呼び出し可能でない場合。

        シーンやUndoは予約時には変更しない。バッチでの実行タイミングは
        maya.utils.executeDeferredに従う。遅延中の例外はMaya側に通知される。
        """
        from maya import utils

        if not callable(callback):
            raise TypeError("Expected a callable")
        utils.executeDeferred(callback, *args, **kwargs)
