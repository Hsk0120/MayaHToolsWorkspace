"""Maya標準UIの削除通知を共有し、名前の再利用を識別する。"""
import weakref


class _UiLifetime:
    """同じUIへの参照が共有する寿命。Qtやウィジェットは保持しない。"""

    _instances = weakref.WeakValueDictionary()

    @classmethod
    def acquire(cls, command, name):
        """生存中の監視を共有し、削除後の同名UIには新しい寿命を割り当てる。

        Args:
            command (str): windowまたはworkspaceControl。
            name (str): 既存のMaya UI名。

        Returns:
            _UiLifetime: 対象UIの監視参照。
        """
        key = (command, name)
        lifetime = cls._instances.get(key)
        if lifetime is None or not lifetime.alive:
            lifetime = cls(name)
            cls._instances[key] = lifetime
        return lifetime

    def __init__(self, name):
        """UI削除通知を登録する。監視対象のUIを作成・変更しない。

        Args:
            name (str): Maya UI名。
        """
        from maya.api import OpenMayaUI
        self.alive = True
        reference = weakref.ref(self)

        def deleted(*args):
            """削除を記録する。callbackから寿命オブジェクトを強参照しない。"""
            lifetime = reference()
            if lifetime is not None:
                lifetime.alive = False

        callback_id = OpenMayaUI.MUiMessage.addUiDeletedCallback(name, deleted)
        # 最後の参照/スナップショットが解放されたら、この監視だけ解除する。
        # Maya終了後にAPIを呼ばないようPython終了時のfinalize実行は無効にする。
        self._cleanup = weakref.finalize(self, self._remove_callback, callback_id)
        self._cleanup.atexit = False

    @staticmethod
    def _remove_callback(callback_id):
        """参照解放時に監視を解除する。Maya側で解除済みなら何もしない。"""
        from maya.api import OpenMaya
        try:
            OpenMaya.MMessage.removeCallback(callback_id)
        except RuntimeError:
            pass
