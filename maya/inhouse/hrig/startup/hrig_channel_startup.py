"""GUIの準備後にチャンネルボックス操作の監視を登録する。"""


def initialize():
    """Maya 2025以降のGUIだけでhrigの操作監視を起動する。"""
    from maya import cmds, utils
    if cmds.about(batch=True) or int(cmds.about(apiVersion=True)) < 20250000:
        return
    utils.executeDeferred(_install)


def _install():
    """シーン読込後の操作に備えて監視を登録する。"""
    from hrig.channel_controls import install
    install()
