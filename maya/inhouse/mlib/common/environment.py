"""Mayaの実行環境(バッチ/GUI・版番号)を照会する。"""

import maya.cmds as cmds

from .version import Version


class Environment:
    """実行中のMayaの状態を照会するクラスメソッドの集まり。インスタンスは作らない。

    シーンは変更しない。各メソッドは呼び出すたびにMayaへ問い合わせる。

    .. code-block:: python

        from mlib.common import Environment

        if Environment.isInteractive() and Environment.getMayaVersion() >= Version("2025"):
            ...
    """

    def __new__(cls, *args, **kwargs):
        """インスタンスを作らせない。

        Raises:
            TypeError: 常に送出する。
        """
        raise TypeError("Environment only provides class methods; call Environment.isBatch() etc. directly")

    @classmethod
    def isBatch(cls):
        """バッチ(mayapy・``maya -batch``)で実行中か照会する(``cmds.about(batch=True)``)。

        Returns:
            bool: バッチならTrue。
        """
        return bool(cmds.about(batch=True))

    @classmethod
    def isInteractive(cls):
        """GUIのある対話セッションで実行中か照会する。

        Returns:
            bool: バッチでなければTrue(``not isBatch()``)。
        """
        return not cls.isBatch()

    @classmethod
    def getMayaVersion(cls):
        """Mayaの版を取得する(``cmds.about(version=True)``)。

        Mayaの返す文字列は年版だけ(例 ``"2027"``)で、更新番号を含まない版がある。
        更新番号まで比べる場合は :meth:`getApiVersion` を使う。

        Returns:
            Version: Mayaの版(例 ``Version("2027")``)。``major`` は ``getApiVersion() // 10000`` と一致する。

        Raises:
            RuntimeError: Mayaが返した文字列を版として解釈できない場合。
        """
        text = cmds.about(version=True)
        version = Version.parse(text)
        if version is None:
            raise RuntimeError(f"Cannot parse the Maya version: {text!r}")
        return version

    @classmethod
    def getApiVersion(cls):
        """MayaのAPI版番号を取得する(``cmds.about(apiVersion=True)``)。

        Returns:
            int: API版番号(例 ``20270000``。年版×10000 + 更新番号×100 + パッチ)。
        """
        return int(cmds.about(apiVersion=True))
