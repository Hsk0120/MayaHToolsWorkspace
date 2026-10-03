"""Mayaのシェルフボタンを操作する。"""

import maya.cmds as cmds


class ShelfButton:
    """Mayaが所有する既存ボタンへの参照。UI操作はシーンUndo対象外。"""

    def __init__(self, name):
        """既存ボタンを参照する。

        Args:
            name (str): shelfButtonのUI名。
        """
        if cmds.about(batch=True):
            raise RuntimeError("ShelfButton requires Maya GUI")
        self._name = str(name)
        self.name()

    def __str__(self):
        """str: 保持したUI名を返す。"""
        return self._name

    def exists(self):
        """bool: ボタンが存在するか取得する。"""
        return bool(cmds.shelfButton(self._name, exists=True))

    def name(self):
        """str: 存在を確認したUI名。削除済みはRuntimeError。"""
        if not self.exists():
            raise RuntimeError("Shelf button is unavailable: " + self._name)
        return self._name

    def getLabel(self):
        """str: ボタンのラベルを取得する。"""
        return cmds.shelfButton(self.name(), query=True, label=True)

    def setLabel(self, label):
        """ラベルを変更する。ディスクへは保存しない。

        Args:
            label (str): 表示ラベル。
        """
        cmds.shelfButton(self.name(), edit=True, label=label)

    def getAnnotation(self):
        """str: ツールチップを取得する。"""
        return cmds.shelfButton(self.name(), query=True, annotation=True)

    def setAnnotation(self, text):
        """ツールチップを変更する。

        Args:
            text (str): 説明。
        """
        cmds.shelfButton(self.name(), edit=True, annotation=text)

    def getIcon(self):
        """str: アイコン名またはパスを取得する。"""
        return cmds.shelfButton(self.name(), query=True, image1=True)

    def setIcon(self, image):
        """アイコンを変更する。

        Args:
            image (str): Mayaの画像名またはパス。
        """
        cmds.shelfButton(self.name(), edit=True, image1=str(image))

    def getCommand(self):
        """str: 登録済みコマンドを取得する。実行はしない。"""
        return cmds.shelfButton(self.name(), query=True, command=True)

    def setCommand(self, command, language="python"):
        """実行コードと言語を変更する。コードは実行しない。

        Args:
            command (str): コード文字列。
            language (str): pythonまたはmel。
        """
        self._validate_command(command, language)
        cmds.shelfButton(self.name(), edit=True, command=command, sourceType=language)

    def getLanguage(self):
        """str: pythonまたはmelを取得する。"""
        return cmds.shelfButton(self.name(), query=True, sourceType=True)

    def delete(self):
        """ボタンをUIから削除する。保存済みファイルは変更しない。"""
        cmds.deleteUI(self.name(), control=True)

    @staticmethod
    def _validate_command(command, language):
        """永続化可能なコマンド入力を検証する。

        Args:
            command (str): コード文字列。callableは保存できないため拒否する。
            language (str): pythonまたはmel。
        """
        if not isinstance(command, str):
            raise TypeError("command must be a string")
        if language not in ("python", "mel"):
            raise ValueError("language must be python or mel")
