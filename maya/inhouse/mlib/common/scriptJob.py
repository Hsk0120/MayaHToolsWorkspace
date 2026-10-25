"""Maya GUIのscriptJobの登録と寿命を管理する。"""

import maya.cmds as cmds


class ScriptJob:
    """Maya GUIへ登録したscriptJobのIDと停止状態を保持する。

    構築時に監視を登録する。オブジェクト回収時の自動解除は行わず、stop()で自身の監視を止める。
    callbackはMayaへ渡し、その実行時期や例外処理はMaya側に従う。独自のUndoチャンクは追加しない。
    """

    def __init__(
        self, *, event=None, attribute=None, callback, kill_with_scene=False, compress_undo=False
    ):
        """イベントまたはアトリビュート変更の監視を開始する。

        Args:
            event (str | None): Mayaのイベント名。attributeと排他的。
            attribute (str | Plug | MPlug | None): 監視するアトリビュート。eventと排他的。
            callback (Callable): 引数なしで呼ぶ処理。
            kill_with_scene (bool): シーンをクリアするときに解除する。
            compress_undo (bool): コールバックの更新を直前の操作のUndoにまとめる。

        Raises:
            ValueError: eventとattributeの指定が一方だけでない場合。
            TypeError: callbackが呼び出せない場合。
            RuntimeError: バッチ実行中、またはMayaが登録を拒否した場合。
        """
        from ..plugs.plug import Plug as _InputPlug
        if (event is None) == (attribute is None):
            raise ValueError("Specify exactly one of event or attribute")
        if not callable(callback):
            raise TypeError("callback must be callable")
        if cmds.about(batch=True):
            raise RuntimeError("scriptJob requires a Maya GUI session")
        options = {"killWithScene": kill_with_scene, "compressUndo": compress_undo}
        if event is not None:
            options["event"] = [event, callback]
        else:

            options["attributeChange"] = [_InputPlug._resolve_input(attribute).getFullName(), callback]
        self._id = cmds.scriptJob(**options)
        self._stopped = False

    @property
    def id(self):
        """int: Mayaが登録時に発行した識別子。"""
        return self._id

    def exists(self):
        """自身の監視が現在もMayaへ登録されているか照会する。

        Returns:
            bool: stop済みならFalse。それ以外はMayaのscriptJob(exists=ID)の結果。
        """
        return not self._stopped and bool(cmds.scriptJob(exists=self._id))

    def stop(self):
        """自身の監視だけを解除する。解除済みの場合は何もしない。

        Returns:
            None: 値を返さない。
        """
        if self.exists():
            cmds.scriptJob(kill=self._id)
        self._stopped = True
