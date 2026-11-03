"""Maya の起動時に Skin Weight Kit を準備する(userSetup から遅延して呼ぶ)。"""

from mlib.common import Environment

from . import commands, panel


def install():
    """runTimeCommand を登録し、前回表示していればパネルを表示する(初めての起動では表示しない)。

    Returns:
        bool: パネルを表示したらTrue。
    """
    if Environment.isBatch():
        return False
    commands.register()
    if panel.wasVisible():
        panel.show()
        return True
    return False
