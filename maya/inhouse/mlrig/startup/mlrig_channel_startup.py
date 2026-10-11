"""GUIの準備後にチャンネルボックス操作の監視を登録する。"""

from maya import cmds


def initialize():
    """Maya 2025以降のGUIだけでmlrigの操作監視を起動する。"""
    import mlib

    if cmds.about(batch=True) or int(cmds.about(apiVersion=True)) < 20250000:
        return
    mlib.executeDeferred(_install)


def _install():
    """シーン読込後の監視と上部の実行メニューを登録する。"""
    from mlrig.channel_controls import install
    from mlrig.menu import Menu

    install()
    Menu.install()
