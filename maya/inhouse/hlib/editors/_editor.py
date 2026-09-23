"""既存エディターの表示設定を扱う内部共通処理。"""

from contextlib import contextmanager

import maya.cmds as cmds


class _Editor:
    """UIを作成せず、指定したエディターを参照する。"""

    _command = ""
    _flags = ()

    def name(self):
        """str: 保持しているエディター名を返す。"""
        return self._name

    def exists(self):
        """bool: エディターが現在存在するか返す。"""
        return bool(getattr(cmds, self._command)(self._name, exists=True))

    def _require_exists(self):
        """参照先が削除されていた場合は RuntimeError を送出する。"""
        if not self.exists():
            raise RuntimeError(f"Editor no longer exists: {self._name}")

    def settings(self, *flags):
        """指定した表示設定を取得する。

        Args:
            *flags (str): Mayaの長いフラグ名。省略時は対応する全表示設定。

        Returns:
            dict[str, object]: フラグ名と現在値。UI全体のスナップショットではない。

        Raises:
            ValueError: 未対応のフラグの場合。
            RuntimeError: エディターが存在しない場合。
        """
        self._validate_flags(flags)
        self._require_exists()
        command = getattr(cmds, self._command)
        return {flag: command(self._name, query=True, **{flag: True})
                for flag in (flags or self._flags)}

    def _validate_flags(self, flags):
        """未対応のフラグがある場合は変更前に ValueError を送出する。"""
        unknown = set(flags) - set(self._flags)
        if unknown:
            raise ValueError(f"Unsupported display flags: {sorted(unknown)}")

    def set_settings(self, **flags):
        """表示設定を変更する。値の検証はMayaへ委譲する。

        Args:
            **flags (object): 対応するMayaの長いフラグ名と値。

        Returns:
            None: 値を返さない。複数設定の原子的な変更は保証しない。
        """
        self._validate_flags(flags)
        self._require_exists()
        if flags:
            getattr(cmds, self._command)(self._name, edit=True, **flags)

    @contextmanager
    def temporary_settings(self, **flags):
        """表示設定を一時変更し、例外時も指定した設定を元に戻す。

        Args:
            **flags (object): 一時的に変更する表示設定。

        Yields:
            _Editor: このインスタンス。削除されたエディターは再作成しない。
        """
        previous = self.settings(*flags) if flags else {}
        try:
            self.set_settings(**flags)
            yield self
        finally:
            if previous and self.exists():
                self.set_settings(**previous)
