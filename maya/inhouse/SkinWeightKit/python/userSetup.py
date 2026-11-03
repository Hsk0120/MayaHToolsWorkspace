"""Skin Weight Kit の起動処理。前回表示していれば、Maya GUI の起動後に右端へパネルを表示する。

ほかの userSetup と独立させ、失敗しても Maya の起動を止めない。
"""

import maya.cmds as cmds
import maya.utils


def _install():
    """パネルを準備する。失敗は警告に留める。"""
    try:
        from skinWeightKit.ui import startup
        startup.install()
    except Exception as error:  # 起動時は他のツールの読込みを止めないよう、失敗を警告にする。
        cmds.warning("Skin Weight Kit could not start: {}".format(error))


if not cmds.about(batch=True):
    maya.utils.executeDeferred(_install)
