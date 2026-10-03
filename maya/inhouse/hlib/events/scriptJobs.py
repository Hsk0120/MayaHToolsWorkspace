"""複数のscriptJobを所有者単位で管理する。"""

from ..events.scriptJob import ScriptJob


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
        """全監視の解除を試み、失敗した監視は再試行のため保持する。

        Raises:
            RuntimeError: 一つ以上の解除に失敗した場合。外部の監視は変更しない。
        """
        from ..utils import logger

        failures = []
        for key, job in list(self._jobs.items()):
            try:
                job.stop()
            except Exception as exc:
                failures.append((key, exc))
                logger.warning("scriptJob cleanup failed for %r: %s", key, exc)
            else:
                del self._jobs[key]
        if failures:
            raise RuntimeError("Failed to stop scriptJobs: " + ", ".join(repr(key) for key, _ in failures)) from failures[0][1]
