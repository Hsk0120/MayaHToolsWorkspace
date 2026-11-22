"""Maya の起動時に Skin Weight Kit を準備する(userSetup から遅延して呼ぶ)。"""

import maya.cmds as cmds
import maya.mel as mel
from maya import OpenMayaUI as omui

from mlib.common import Environment

from . import commands, icons, panel
from .qt import QtGui, QtWidgets, wrapInstance

#: Mayaのメインウィンドウの Windows メニュー。
WINDOW_MENU = "MayaWindow|mainWindowMenu"

#: Windows メニューに足す項目の名前。
WINDOW_MENU_ITEM = "skinWeightKitWindowMenuItem"


def addWindowMenu():
    """Windows メニューの「Skin Weight Kit」を登録し、専用アイコンを設定する。

    Returns:
        bool: 項目があればTrue。メニューが無ければFalse。
    """
    if not cmds.menu(WINDOW_MENU, exists=True):
        return False
    # Windows メニューは初めて開いたときに、空なら中身が作られる。先に項目を足すと空でなくなり Maya の項目が
    # 作られないため、先に作らせる(作成済みなら buildViewMenu は何もしない)。
    mel.eval('buildViewMenu "{}"'.format(WINDOW_MENU))
    item = WINDOW_MENU + "|" + WINDOW_MENU_ITEM
    if not cmds.menuItem(item, exists=True):
        cmds.menuItem(WINDOW_MENU_ITEM, parent=WINDOW_MENU, label="Skin Weight Kit", sourceType="python",
                      command="import skinWeightKit; skinWeightKit.show()",
                      annotation="Show the Skin Weight Kit panel on the right side of the main window.")
    # menuItem の image はファイルのパスしか受け付けないので、描いたアイコンを QAction へ直接付ける。
    pointer = omui.MQtUtil.findMenuItem(item)
    if pointer:
        action_type = getattr(QtGui, "QAction", None) or QtWidgets.QAction
        wrapInstance(int(pointer), action_type).setIcon(icons.icon())
    return True


def install():
    """runTimeCommand と Windows メニューを登録し、前回表示していればパネルを表示する(初めての起動では表示しない)。

    Returns:
        bool: パネルを表示したらTrue。
    """
    if Environment.isBatch():
        return False
    commands.register()
    addWindowMenu()
    if panel.wasVisible():
        panel.show()
        return True
    return False
