"""Maya GUIのscriptJobの登録と寿命を管理する。"""

from maya import cmds


class ScriptJob:
    """自身が登録したscriptJobの寿命を管理する参照。"""

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
        from hlib.plugs.plug import Plug as _InputPlug
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

            options["attributeChange"] = [_InputPlug._resolve_input(attribute).fullName(), callback]
        self._id = cmds.scriptJob(**options)
        self._stopped = False

    @property
    def id(self):
        """int: Mayaが登録時に発行した識別子。"""
        return self._id

    def exists(self):
        """監視が現在も登録されているか照会する。

        Returns:
            bool: 外部からの解除やシーンクリア後はFalse。
        """
        return not self._stopped and bool(cmds.scriptJob(exists=self._id))

    def stop(self):
        """自身の監視だけを解除する。解除済みの場合は何もしない。"""
        if self.exists():
            cmds.scriptJob(kill=self._id)
        self._stopped = True
