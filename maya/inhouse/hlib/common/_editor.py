"""既存エディターの表示設定を扱う内部共通処理。"""

from contextlib import contextmanager

import maya.cmds as cmds

from .._core.getterAlias import _getter_alias


class _Editor:
    """UIを作成せず、指定したエディターを参照する。"""

    _command = ""
    _flags = ()

    @property
    def name(self):
        """str: 保持しているエディター名を返す。"""
        return self._name

    def exists(self):
        """エディターが現在存在するか返す。

        Returns:
            bool: エディターが現在存在するか返す。
        """
        return bool(getattr(cmds, self._command)(self._name, exists=True))

    def getSettings(self, *flags):
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

    def setSettings(self, **flags):
        """表示設定を変更する。フラグ値の検証はMayaへ委譲する。

        Args:
            **flags (object): 対応するMayaの長いフラグ名と値。

        Returns:
            None: 値を返さない。複数設定の原子的な変更は保証しない。

        Raises:
            ValueError: 未対応のフラグの場合。
            RuntimeError: エディターが存在しない場合。
        """
        self._validate_flags(flags)
        self._require_exists()
        if flags:
            getattr(cmds, self._command)(self._name, edit=True, **flags)

    @contextmanager
    def temporarySettings(self, **flags):
        """表示設定を一時変更し、例外時も指定した設定を元に戻す。

        Args:
            **flags (object): 一時的に変更する表示設定。

        Yields:
            _Editor: このインスタンス。削除されたエディターは再作成しない。

        Raises:
            ValueError: 未対応のフラグの場合。
            RuntimeError: エディターが存在しない場合。
        """
        previous = self.getSettings(*flags) if flags else {}
        try:
            self.setSettings(**flags)
            yield self
        finally:
            if previous and self.exists():
                self.setSettings(**previous)

    @_getter_alias(getSettings)
    def settings(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getSettings(*args, **kwargs)

    def _require_exists(self):
        """参照先が削除されていた場合は RuntimeError を送出する。"""
        if not self.exists():
            raise RuntimeError(f"Editor no longer exists: {self._name}")

    def _validate_flags(self, flags):
        """未対応のフラグがある場合は変更前に ValueError を送出する。

        Args:
            flags: 処理先へ渡すキーワード引数の辞書。
        """
        unknown = set(flags) - set(self._flags)
        if unknown:
            raise ValueError(f"Unsupported display flags: {sorted(unknown)}")
