"""複数のscriptJobを所有者単位で管理する。"""

from .scriptJob import ScriptJob


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
