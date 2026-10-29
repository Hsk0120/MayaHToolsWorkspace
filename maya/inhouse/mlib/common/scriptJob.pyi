# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya GUIのscriptJobの登録と寿命を管理する。"""

import maya.cmds as cmds
from typing import Callable
from mlib.plugs.plug import Plug
import maya.api.OpenMaya as om2



class ScriptJob:
    """Maya GUIへ登録したscriptJobのIDと停止状態を保持する。

    構築時に監視を登録する。オブジェクト回収時の自動解除は行わず、stop()で自身の監視を止める。
    callbackはMayaへ渡し、その実行時期や例外処理はMaya側に従う。独自のUndoチャンクは追加しない。
    """
    def __init__(self, *, event: str | None = ..., attribute: str | Plug | om2.MPlug | None = ..., callback: Callable, killWithScene: bool = ..., compressUndo: bool = ...) -> None:
        """イベントまたはアトリビュート変更の監視を開始する。

        Args:
            event (str | None): Mayaのイベント名。attributeと排他的。
            attribute (str | Plug | MPlug | None): 監視するアトリビュート。eventと排他的。
            callback (Callable): 引数なしで呼ぶ処理。
            killWithScene (bool): シーンをクリアするときに解除する。
            compressUndo (bool): コールバックの更新を直前の操作のUndoにまとめる。

        Raises:
            TypeError: callbackが呼び出せない場合。
            ValueError: eventとattributeの指定が一方だけでない場合。
            RuntimeError: バッチ実行中、またはMayaが登録を拒否した場合。
        """
        ...
    @property
    def id(self) -> int:
        """int: Mayaが登録時に発行した識別子。"""
        ...
    def exists(self) -> bool:
        """自身の監視が現在もMayaへ登録されているか照会する。

        Returns:
            bool: stop済みならFalse。それ以外はMayaのscriptJob(exists=ID)の結果。
        """
        ...
    def stop(self) -> None:
        """自身の監視だけを解除する。解除済みの場合は何もしない。

        Returns:
            None: 値を返さない。
        """
        ...
