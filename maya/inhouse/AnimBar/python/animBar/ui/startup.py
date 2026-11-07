"""Maya の起動時に Anim Bar を準備する(userSetup から遅延して呼ぶ)。"""

import maya.cmds as cmds
import maya.mel as mel
from maya import OpenMayaUI as omui

from mlib.common import Environment

from ..core import commands, crashRecovery
from . import bar, icons
from .qt import QtGui, QtWidgets, wrapInstance

#: Mayaのメインウィンドウの Windows メニュー。
WINDOW_MENU = "MayaWindow|mainWindowMenu"

#: Windows メニューに足す項目の名前。
WINDOW_MENU_ITEM = "animBarWindowMenuItem"


def addWindowMenu():
    """Windows メニューの「Anim Bar」を登録し、専用アイコンを設定する。

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
        cmds.menuItem(WINDOW_MENU_ITEM, parent=WINDOW_MENU, label="Anim Bar", sourceType="python",
                      command="import animBar; animBar.show()",
                      annotation="Show the Anim Bar above the Time Slider.")
    pointer = omui.MQtUtil.findMenuItem(item)
    if pointer:
        action_type = getattr(QtGui, "QAction", None) or QtWidgets.QAction
        action = wrapInstance(int(pointer), action_type)
        action.setIcon(icons.icon("animBar", size=32))
    return True


def install():
    """runTimeCommand と Windows メニューを登録し、前回有効にしていれば退避を有効にして新しい退避を戻すかを聞き、
    前回表示していればバーを表示する。

    Returns:
        bool: バーを表示したらTrue。
    """
    if Environment.isBatch():
        return False
    commands.register()
    addWindowMenu()
    if crashRecovery.wasEnabled():
        crashRecovery.setEnabled(True)
        crashRecovery.checkOnOpen()
    if bar.wasVisible():
        bar.show()
        return True
    return False
