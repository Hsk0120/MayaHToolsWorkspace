"""複数のscriptJobを所有者単位で管理する。"""

from contextlib import contextmanager

from .scriptJob import ScriptJob


class ScriptJobs:
    """複数のscriptJobを所有者単位で管理する。GC時には自動解除しない。"""

    def __init__(self):
        """登録を伴わない空の監視グループを作る。"""
        self._jobs = {}
        self._temporary_active = False

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
        """所有する全監視の解除を試み、成功分だけを保持表から除く。

        通常の解除例外は警告して残りも処理し、失敗した監視は後からstop()で再試行できる。
        他の所有者の監視は解除しない。

        Raises:
            RuntimeError: 解除失敗が一つ以上ある場合。最初の原因例外を__cause__に保持する。
        """
        from .. import logger

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

    @contextmanager
    def temporary(self):
        """終了時に、このグループが持つ監視を解除する。

        開始前からの監視も対象で、UI・シーン自体の寿命は管理しない。
        失敗した監視は保持し、stop()で再試行できる。本文が失敗した場合は解除時の通常例外で置き換えない。

        Yields:
            ScriptJobs: 自身。

        Raises:
            RuntimeError: 同一インスタンスで入れ子にした、または正常終了時に解除が失敗した場合。
        """
        if self._temporary_active:
            raise RuntimeError("ScriptJobs.temporary cannot be nested on the same instance")
        self._temporary_active = True
        body_failed = False
        try:
            try:
                yield self
            except BaseException:
                body_failed = True
                raise
        finally:
            try:
                self.stop()
            except Exception:
                if not body_failed:
                    raise
            finally:
                self._temporary_active = False
