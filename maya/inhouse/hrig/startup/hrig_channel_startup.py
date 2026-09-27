"""GUIの準備後にチャンネルボックス操作の監視を登録する。"""

from maya import cmds


def initialize():
    """Maya 2025以降のGUIだけでhrigの操作監視を起動する。"""
    import hlib

    if cmds.about(batch=True) or int(cmds.about(apiVersion=True)) < 20250000:
        return
    hlib.executeDeferred(_install)


def _install():
    """シーン読込後の監視と上部の実行メニューを登録する。"""
    from hrig.channel_controls import install
    from hrig.menu import Menu

    install()
    Menu.install()
