"""Maya の起動時に Anim Bar を準備する(userSetup から遅延して呼ぶ)。"""

import maya.cmds as cmds

from ..core import commands
from . import bar


def install():
    """runTimeCommand を登録し、前回表示していればバーを表示する。

    Returns:
        bool: バーを表示したらTrue。
    """
    if cmds.about(batch=True):
        return False
    commands.register()
    if bar.wasVisible():
        bar.show()
        return True
    return False
