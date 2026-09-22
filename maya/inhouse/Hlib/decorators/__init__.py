"""デコレータ関連ユーティリティを公開するパッケージ。"""

import maya.standalone
import maya.cmds as cmds

from .undo import undo_chunk, undoable

def maya_standalone(func):
    """Maya Standalone の初期化と終了処理で関数を囲む。

    初期化・関数実行中の Exception は Maya の警告として出力する。finally で終了処理を呼ぶが、終了処理自体の例外は伝播する。

    Args:
        func (Callable): 初期化後に実行する関数。

    Returns:
        Callable: 元の戻り値を返さないラッパー関数。
    """
    def wrapper(*args, **kwargs):
        # 実行前後で Maya Standalone の初期化/終了を保証する。
        """Standalone を初期化して関数を実行し、終了処理を呼ぶ。

        初期化または関数実行の Exception を警告に変換する。終了処理の例外は抑制しない。

        Args:
            *args (object): 元の関数に渡す位置引数。
            **kwargs (object): 元の関数に渡すキーワード引数。

        Returns:
            None: 元の関数の戻り値は破棄する。
        """
        try: 			
            maya.standalone.initialize()
            func(*args, **kwargs) 
        except Exception as e:
            cmds.warning(e)
        finally:
            maya.standalone.uninitialize()
    return wrapper


__all__ = [
    "maya_standalone",
    "undo_chunk",
    "undoable",
]