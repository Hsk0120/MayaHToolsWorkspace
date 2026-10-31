"""Anim Bar の起動処理。Maya GUI の起動後に、タイムスライダーの上へバーを表示する。

ほかの userSetup と独立させ、失敗しても Maya の起動を止めない。
"""

import maya.cmds as cmds
import maya.utils


def _install():
    """バーを準備する。失敗は警告に留める。"""
    try:
        from animBar.ui import startup
        startup.install()
    except Exception as error:  # 起動時は他のツールの読込みを止めないよう、失敗を警告にする。
        cmds.warning("Anim Bar could not start: {}".format(error))


if not cmds.about(batch=True):
    maya.utils.executeDeferred(_install)
