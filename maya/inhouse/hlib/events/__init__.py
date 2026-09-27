"""Maya GUIのscriptJobを明示的に登録・解除する。

importだけでは監視を開始しない。バッチ・再生中の評価用途には使用せず、
所有者が不要になった時点でstop()を呼ぶ。シーンへスクリプトは保存しない。
"""

from maya import cmds

__all__ = ["ScriptJob", "ScriptJobs"]


class ScriptJob:
    """自身が登録したscriptJobの寿命を管理する参照。"""

    def __init__(self, *, event=None, attribute=None, callback,
                 kill_with_scene=False, compress_undo=False):
        """イベントまたは属性変更の監視を開始する。

        Args:
            event (str | None): Mayaのイベント名。attributeと排他的。
            attribute (str | Plug | MPlug | None): 監視する属性。eventと排他的。
            callback (Callable): 引数なしで呼ぶ処理。
            kill_with_scene (bool): シーンをクリアするときに解除する。
            compress_undo (bool): コールバックの更新を直前の操作のUndoにまとめる。

        Raises:
            ValueError: eventとattributeの指定が一方だけでない場合。
            TypeError: callbackが呼び出せない場合。
            RuntimeError: バッチ実行中、またはMayaが登録を拒否した場合。
        """
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
            from .._core.coerce import to_plug

            options["attributeChange"] = [to_plug(attribute).full_name(), callback]
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


class ScriptJobs:
    """複数のscriptJobを所有者単位で管理する。GC時には自動解除しない。"""

    def __init__(self):
        """登録を伴わない空の監視グループを作る。"""
        self._jobs = {}

    def add(self, key, **options):
        """キーに対応する監視を追加する。生存中の同じキーは再登録しない。

        Args:
            key (Hashable): 所有者内で一意な識別子。
            **options (object): ScriptJobへ渡す登録オプション。

        Returns:
            ScriptJob: 既存または新規の監視。既存の場合optionsは適用しない。

        Raises:
            RuntimeError: Mayaが監視を登録できない場合。
        """
        existing = self._jobs.get(key)
        if existing is not None and existing.exists():
            return existing
        job = ScriptJob(**options)
        self._jobs[key] = job
        return job

    def exists(self):
        """所有する監視が空でなく、すべて生存しているか照会する。

        Returns:
            bool: 全監視が生存している場合はTrue。
        """
        return bool(self._jobs) and all(job.exists() for job in self._jobs.values())

    def stop(self):
        """所有する監視だけを解除する。外部のscriptJobには触れない。"""
        for key, job in list(self._jobs.items()):
            job.stop()
            del self._jobs[key]
