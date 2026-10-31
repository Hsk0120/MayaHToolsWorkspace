"""Maya の起動時に Anim Bar を準備する(userSetup から遅延して呼ぶ)。"""

import maya.cmds as cmds

from ..core import commands, crashRecovery
from . import bar


def install():
    """runTimeCommand を登録し、前回有効にしていれば退避を有効にして新しい退避を戻すかを聞き、
    前回表示していればバーを表示する。

    Returns:
        bool: バーを表示したらTrue。
    """
    if cmds.about(batch=True):
        return False
    commands.register()
    if crashRecovery.wasEnabled():
        crashRecovery.setEnabled(True)
        crashRecovery.checkOnOpen()
    if bar.wasVisible():
        bar.show()
        return True
    return False
