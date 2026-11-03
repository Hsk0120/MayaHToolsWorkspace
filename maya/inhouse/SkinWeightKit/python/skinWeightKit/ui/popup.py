"""マウスの位置に出す、ウェイトの値のメニュー(ホットキーから呼ぶ)。

Paint Skin Weights ツールを開かずに、頂点を選んだまま値を設定できるようにする。対象のインフルエンスは、
パネルでアクティブにしたもの。パネルが開いていなければ、パネルを開いて選ぶよう知らせる。
"""

import functools

from ..core import weights
from . import panel as panel_module
from .qt import QtGui, QtWidgets

#: メニューに出す値。
VALUES = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)


def buildMenu(menu, owner):
    """値のメニューの項目を足す。

    Args:
        menu (QtWidgets.QMenu): 足す先のメニュー。
        owner (SkinWeightKitPanel): 処理を行うパネル。

    Returns:
        QtWidgets.QMenu: 項目を足したメニュー。
    """
    title = menu.addAction("Active: {}".format(owner.active or "(none)"))
    title.setEnabled(False)
    menu.addSeparator()
    for value in VALUES:
        panel_module._action(menu, "Set {:g}".format(value), functools.partial(owner._apply_value, value, "set"),
                             "Set the active influence to {:g} on the selected vertices.".format(value))
    menu.addSeparator()
    step = owner.step.value()
    panel_module._action(menu, "Add {:g}".format(step), functools.partial(owner._apply_value, step, "add"),
                         "Add the step ({:g}) to the active influence on the selected vertices.".format(step))
    panel_module._action(menu, "Subtract {:g}".format(step), functools.partial(owner._apply_value, -step, "add"),
                         "Subtract the step ({:g}) from the active influence on the selected vertices.".format(step))
    menu.addSeparator()
    panel_module._action(menu, "Hammer", functools.partial(owner._edit, weights.hammer),
                         "Replace the weights of each selected vertex with the average of its neighbors.")
    panel_module._action(menu, "Smooth", owner._run_smooth,
                         "Smooth the selected vertices with the strength and iterations set in the panel.")
    panel_module._action(menu, "Copy", functools.partial(owner._edit, weights.copy, refresh=False),
                         "Copy the weights of the selected vertex (the average if several are selected).")
    panel_module._action(menu, "Paste", functools.partial(owner._edit, weights.paste),
                         "Paste the copied weights onto every selected vertex.")
    return menu


def showValueMenu():
    """マウスの位置に値のメニューを出す。

    Returns:
        bool: メニューを出したらTrue。パネルが開いていなければFalse(警告を出す)。
    """
    owner = panel_module._panel["widget"]
    if owner is None:
        panel_module._warn("Open the Skin Weight Kit panel and click an influence first")
        return False
    menu = QtWidgets.QMenu(owner)
    buildMenu(menu, owner)
    menu.exec_(QtGui.QCursor.pos())
    return True
