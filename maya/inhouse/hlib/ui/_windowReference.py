"""ウィンドウ参照の存在確認・入力検証・一時復元を共通化する。"""
from contextlib import contextmanager
import maya.cmds as cmds
from ..ui.uiSnapshot import UiSnapshot
from ..ui._uiLifetime import _UiLifetime


class _WindowReference:
    """Maya所有の既存UIを操作する内部基底。任意フラグの公開転送は行わない。"""

    _command = ""

    @staticmethod
    def _require_gui():
        """GUIがない場合は明示的に失敗する。"""
        if cmds.about(batch=True):
            raise RuntimeError("Window operations require Maya GUI")

    @staticmethod
    def _boolean(value):
        """boolを検証する。

        Args:
            value (bool): 設定値。

        Returns:
            bool: 検証した値。
        """
        if type(value) is not bool:
            raise TypeError("Expected bool")
        return value

    @staticmethod
    def _pair(first, second, positive=False):
        """座標またはサイズの整数ペアを検証する。

        Args:
            first (int): 一つ目の値。
            second (int): 二つ目の値。
            positive (bool): 正数だけを許可するか。

        Returns:
            tuple[int, int]: 検証済みのペア。
        """
        if any(type(value) is not int for value in (first, second)):
            raise TypeError("Expected integer coordinates")
        if positive and min(first, second) <= 0:
            raise ValueError("Size must be positive")
        return first, second

    def __init__(self, name):
        """既存UIを参照する。UIは作成しない。

        Args:
            name (str): MayaのUI名。
        """
        self._require_gui()
        if not isinstance(name, str) or not name:
            raise TypeError("Expected a non-empty UI name")
        self._name = name
        if not getattr(cmds, self._command)(name, exists=True):
            raise RuntimeError("UI does not exist: " + name)
        self._lifetime = _UiLifetime.acquire(self._command, name)
        self.name()

    def _capture(self, data):
        """参照寿命付きの変更不可スナップショットを作る。"""
        return UiSnapshot(self._command, self.name(), data, (self,))

    def exists(self):
        """bool: 保持したUIが存在するか照会する。"""
        self._require_gui()
        return (self._lifetime.alive
                and bool(getattr(cmds, self._command)(self._name, exists=True)))

    def name(self):
        """str: 存在を確認したUI名。削除済みはRuntimeError。"""
        if not self.exists():
            raise RuntimeError("UI no longer exists: " + self._name)
        return self._name

    def getVisible(self):
        """bool: 現在の表示設定を照会する。"""
        return bool(getattr(cmds, self._command)(self.name(), query=True, visible=True))

    def hide(self):
        """UIを削除せず非表示にする。保存は行わない。"""
        getattr(cmds, self._command)(self.name(), edit=True, visible=False)

    def _validate_snapshot(self, snapshot, fields):
        """復元対象とデータ型を更新前に検証する。

        Args:
            snapshot (UiSnapshot): captureの返り値。
            fields (dict): キーと型。
        """
        self.name()
        if not isinstance(snapshot, UiSnapshot) or snapshot.scope != self._command or snapshot.name != self.name():
            raise ValueError("Snapshot belongs to another UI or type")
        snapshot.validate()
        if len(snapshot._targets) != 1 or snapshot._targets[0]._lifetime is not self._lifetime:
            raise ValueError("Snapshot belongs to another UI instance")
        for key, expected in fields.items():
            if type(snapshot.data.get(key)) is not expected:
                raise ValueError("Invalid snapshot field: " + key)

    @contextmanager
    def temporaryState(self):
        """表示状態を退避し、例外時も復元する。ファイル保存は行わない。

        Yields:
            _WindowReference: このUI参照。

        Note:
            UIを削除しないこと。削除済みの復元はRuntimeErrorで、再作成は行わない。
            復元失敗時は例外を伝え、ブロック内例外がある場合は例外チェーンに残す。
        """
        snapshot = self.capture()
        try:
            yield self
        finally:
            self.restore(snapshot)

    def __str__(self):
        """str: 保持したUI名。"""
        return self._name
