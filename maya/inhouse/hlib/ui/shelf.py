"""Mayaのシェルフタブを取得・編集・保存する。"""
import json
import re
from pathlib import Path
import maya.cmds as cmds
import maya.mel as mel
from ..ui.shelfButton import ShelfButton


class Shelf:
    """既存シェルフの参照。生成だけではタブを作らない。"""

    @staticmethod
    def _top():
        """str: Maya標準のシェルフタブ親。GUIなしはRuntimeError。"""
        if cmds.about(batch=True):
            raise RuntimeError("Shelf requires Maya GUI")
        top = mel.eval('global string $gShelfTopLevel; $gShelfTopLevel;')
        if not top or not cmds.shelfTabLayout(top, exists=True):
            raise RuntimeError("Maya shelf tabs are unavailable")
        return top

    def __init__(self, name=None):
        """既存タブを参照する。

        Args:
            name (str | None): UI名。省略時は現在の標準シェルフ。
        """
        if cmds.about(batch=True):
            raise RuntimeError("Shelf requires Maya GUI")
        self._name = name or cmds.shelfTabLayout(self._top(), query=True, selectTab=True)
        self.name()

    def exists(self):
        """bool: 参照先のシェルフが存在するか取得する。"""
        return bool(self._name and cmds.shelfLayout(self._name, exists=True))

    def name(self):
        """str: 存在を確認したUI名。削除済みはRuntimeError。"""
        if not self.exists():
            raise RuntimeError("Shelf is unavailable: " + str(self._name))
        return self._name

    @classmethod
    def list(cls):
        """list[Shelf]: Maya標準シェルフのタブを表示順で取得する。"""
        return [cls(name) for name in cmds.shelfTabLayout(cls._top(), query=True, childArray=True) or []]

    @classmethod
    def create(cls, name):
        """Maya標準シェルフへタブを作成する。既存名は拒否する。

        Args:
            name (str): 英数字とアンダースコアの識別名。先頭は英字かアンダースコア。

        Returns:
            Shelf: 作成したタブ。ファイルへの保存は明示的にsaveで行う。
        """
        cls._top()
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError("name must be an ASCII UI identifier")
        if cmds.shelfLayout(name, exists=True):
            raise ValueError("Shelf already exists: " + name)
        # addNewShelfTabは暗黙にファイル保存するため、UIだけを明示作成する。
        top = cls._top()
        result = cmds.shelfLayout(name, parent=top)
        cmds.shelfTabLayout(top, edit=True, tabLabel=(result, name))
        return cls(result)

    def _load(self):
        """標準タブの遅延ロードを完了させ、未ロード内容の上書きを防ぐ。"""
        name = self.name().split("|")[-1]
        old_parent = cmds.setParent(query=True)
        try:
            mel.eval('loadNamedShelf(' + json.dumps(name) + ');')
        finally:
            cmds.setParent(old_parent)

    def select(self):
        """自身のタブを選択し、標準シェルフの内容をロードする。"""
        cmds.shelfTabLayout(self._top(), edit=True, selectTab=self.name())
        self._load()

    def buttons(self):
        """list[ShelfButton]: ボタンを表示順で取得する。区切り線等は除外する。"""
        self._load()
        parent = self.name()
        result = []
        for child in cmds.shelfLayout(parent, query=True, childArray=True) or []:
            path = child if "|" in child else parent + "|" + child
            if cmds.shelfButton(path, exists=True):
                result.append(ShelfButton(path))
        return result

    def addButton(self, label, command, language="python", icon="commandButton.png", annotation=""):
        """保存可能な文字列コマンドのボタンを追加する。

        Args:
            label (str): ラベル。
            command (str): 実行するコード。追加時には実行しない。
            language (str): pythonまたはmel。
            icon (str): 画像名またはパス。
            annotation (str): ツールチップ。

        Returns:
            ShelfButton: 作成したボタン。保存は別操作。
        """
        ShelfButton._validate_command(command, language)
        self._load()
        return ShelfButton(cmds.shelfButton(parent=self.name(), label=label,
                           command=command, sourceType=language, image1=str(icon), annotation=annotation))

    def clear(self):
        """内容をロード後、ボタンや区切り線をすべて削除する。タブは残す。Undo対象外。"""
        self._load()
        parent = self.name()
        for child in cmds.shelfLayout(parent, query=True, childArray=True) or []:
            cmds.deleteUI(child if "|" in child else parent + "|" + child)

    def save(self, path=None):
        """このタブをMELファイルへ保存する。既存ファイルは上書きする。

        Args:
            path (str | Path | None): shelf_名前.melの保存先。省略時はユーザーのshelvesフォルダー。
                親フォルダーは存在する必要がある。

        Returns:
            Path: 保存先。Mayaのタブ構成の保存とは別で、任意パスは自動ロード登録されない。

        Raises:
            RuntimeError: Mayaが保存に失敗した場合。
        """
        self._load()
        target = Path(path) if path is not None else Path(cmds.internalVar(userShelfDir=True)) / ("shelf_" + self.name().split("|")[-1] + ".mel")
        target = target.expanduser().resolve()
        if target.suffix.lower() != ".mel" or not target.parent.is_dir():
            raise ValueError("Expected a .mel path in an existing directory")
        # saveShelfは拡張子なしの保存名を受け付け、.melを付けて書き出す。
        if not cmds.saveShelf(self.name(), str(target.with_suffix("")).replace("\\", "/")):
            raise RuntimeError("Failed to save shelf: " + str(target))
        return target

    def __str__(self):
        """str: 保持したUI名を返す。"""
        return self._name
