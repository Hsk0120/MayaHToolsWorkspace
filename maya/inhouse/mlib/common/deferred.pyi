# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""MayaのGUIアイドル処理へPython呼出しを予約する。"""

from typing import Callable



class Deferred:
    """maya.utilsの遅延実行を共通化する。"""
    @staticmethod
    def call(callback: Callable, *args: object, **kwargs: object) -> None:
        """Python呼出しをmaya.utils.executeDeferredへ渡す。

        実行時期とcallbackの例外処理はMayaへ委ねる。同期実行・取消・Undo管理は追加しない。
        バッチ時の挙動もexecuteDeferredに従い、予約APIの戻り値を返さない。

        Args:
            callback (Callable): 呼出し可能なPythonオブジェクト。コード文字列は受理しない。
            *args (object): callbackへ渡す位置引数。
            **kwargs (object): callbackへ渡すキーワード引数。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: callbackが呼び出し可能でない場合。
        """
        ...
