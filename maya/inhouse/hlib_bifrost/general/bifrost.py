"""Bifrostの対応版確認と明示ロード。"""

from maya import cmds


class Bifrost:
    """プラグイン状態をhlib.generalで照会する。import時にはロードしない。"""

    MIN_VERSION = (3, 0, 0, 0)

    @classmethod
    def is_available(cls):
        """bool: Maya 2025以降で対応Bifrostがロード済みならTrue。"""
        from hlib.general import Plugin

        if cmds.about(apiVersion=True) < 20250000:
            return False
        plugin = Plugin("bifrostGraph")
        if not plugin.is_loaded():
            return False
        version = plugin.version()
        return version is not None and version.is_at_least(cls.MIN_VERSION)

    @classmethod
    def ensure_available(cls):
        """対応Bifrostをロードする。autoloadとセキュリティ設定は変更しない。

        Raises:
            RuntimeError: MayaやBifrostが対応版でない、またはロードに失敗した場合。
        """
        from hlib.general import Plugin

        if cmds.about(apiVersion=True) < 20250000:
            raise RuntimeError("hlib_bifrost requires Maya 2025 or newer")
        Plugin("bifrostGraph").ensure_loaded()
        if not cls.is_available():
            raise RuntimeError("hlib_bifrost requires Bifrost 3.0.0.0 or newer")
