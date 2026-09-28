"""GUIテスト用に、C++のhedit画面とworkspaceControlをPySideから参照する補助。

ドッキング・開閉状態の保存と復元はhedit.mll(dock.cpp)が行い、Python側に状態は持たない。
テストはこの補助を通して、Mayaのコマンドと実際のQtの親子関係から状態を確かめる。
"""
from pathlib import Path

from maya import cmds, OpenMayaUI
try:
    from PySide6 import QtWidgets
    from shiboken6 import getCppPointer, wrapInstance
except ImportError:
    from PySide2 import QtWidgets
    from shiboken2 import getCppPointer, wrapInstance

CONTROL = 'heditDockWorkspaceControl'
MENU = 'heditWindowMenuItem'


def pointer(widget):
    """int: Qtウィジェットの実体のアドレス。同じ画面かどうかの比較に使う。"""
    return int(getCppPointer(widget)[0])


def _live_widget(address):
    """QWidget | None: アドレスが一致する生存中のウィジェット。

    Mayaが作って破棄したQMainWindowとアドレスが重なると、QMainWindow型で取り出したラッパーが
    古い「削除済み」扱いのものになる場合がある。QApplication.allWidgets()から取り直すと、
    実体に対応する有効なラッパーが得られる。
    """
    for widget in QtWidgets.QApplication.allWidgets():
        if pointer(widget) == address:
            return widget
    return None


def editor():
    """QWidget: 編集画面(実体はQMainWindow)。未作成なら作る。

    Qt5ではドックへの付け替えや再表示で既存のPythonラッパーが無効になるため、毎回取り直す。
    """
    address = int(cmds.hedit())
    return _live_widget(address) or wrapInstance(address, QtWidgets.QWidget)


def control():
    """QWidget | None: heditのworkspaceControl。無ければNone。"""
    address = OpenMayaUI.MQtUtil.findControl(CONTROL)
    return wrapInstance(int(address), QtWidgets.QWidget) if address else None


def editors():
    """list[QWidget]: 生存中のhedit画面(objectNameがhedit)。"""
    return [widget for widget in QtWidgets.QApplication.allWidgets() if widget.objectName() == 'hedit']


def docked_editor():
    """QWidget | None: ドックの中に入っている編集画面。作成はしない。"""
    widget = control()
    if widget is None:
        return None
    return next((editor for editor in editors() if widget.isAncestorOf(editor)), None)


def visible_editors():
    """list[QWidget]: 表示中のhedit画面。複数あれば重複して作られている。"""
    return [widget for widget in editors() if widget.isVisible()]


def output_text():
    """str: 編集画面の出力欄の本文。未作成なら作る(Mayaの起動時からの履歴を含む)。"""
    editor()
    output = next(widget for widget in QtWidgets.QApplication.allWidgets()
                  if widget.objectName() == 'output' and isinstance(widget, QtWidgets.QPlainTextEdit))
    return output.toPlainText()


def state_path():
    """Path: 開閉状態の保存先ui.json(tabs.jsonと同じフォルダー)。"""
    return Path(cmds.hedit(sessionPath=True)).with_name('ui.json')


def save_state():
    """現在のドック状態をすぐにui.jsonへ保存する(通常は1秒ごと)。"""
    cmds.hedit(saveState=True)
