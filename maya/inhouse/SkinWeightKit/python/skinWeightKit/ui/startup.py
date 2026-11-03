"""Maya の起動時に Skin Weight Kit を準備する(userSetup から遅延して呼ぶ)。"""

import maya.cmds as cmds

from . import commands, panel


def install():
    """runTimeCommand を登録し、前回表示していればパネルを表示する(初めての起動では表示しない)。

    Returns:
        bool: パネルを表示したらTrue。
    """
    if cmds.about(batch=True):
        return False
    commands.register()
    if panel.wasVisible():
        panel.show()
        return True
    return False
