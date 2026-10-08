"""Bifrostの対応版確認と明示ロード。"""

import maya.cmds as cmds

from .._binding import coreModule


class Bifrost:
    """プラグイン状態をhlib.commonで照会する。import時にはロードしない。"""

    MIN_VERSION = (3, 0, 0, 0)

    @classmethod
    def is_available(cls):
        """Maya 2025以降で対応Bifrostがロード済みならTrue。

        Returns:
            bool: Maya 2025以降で対応Bifrostがロード済みならTrue。
        """
        Plugin = coreModule('common').Plugin

        if cmds.about(apiVersion=True) < 20250000:
            return False
        plugin = Plugin("bifrostGraph")
        if not plugin.isLoaded():
            return False
        version = plugin.getVersion()
        return version is not None and version.isAtLeast(cls.MIN_VERSION)

    @classmethod
    def ensure_available(cls):
        """対応Bifrostをロードする。autoloadとセキュリティ設定は変更しない。

        Raises:
            RuntimeError: MayaやBifrostが対応版でない、またはロードに失敗した場合。
        """
        Plugin = coreModule('common').Plugin

        if cmds.about(apiVersion=True) < 20250000:
            raise RuntimeError(__package__.split(".", 1)[0] + " requires Maya 2025 or newer")
        Plugin("bifrostGraph").ensureLoaded()
        if not cls.is_available():
            raise RuntimeError(__package__.split(".", 1)[0] + " requires Bifrost 3.0.0.0 or newer")
