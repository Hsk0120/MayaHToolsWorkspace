"""GUIの準備後にチャンネルボックス操作の監視を登録する。"""


def initialize():
    """Maya 2025以降のGUIだけでmlrigの操作監視を起動する。"""
    import mlib

    if mlib.common.Environment.isBatch() or mlib.common.Environment.getApiVersion() < 20250000:
        return
    mlib.common.Deferred.call(_install)


def _install():
    """シーン読込後の監視と上部の実行メニューを登録する。"""
    from mlrig.channel_controls import install
    from mlrig.menu import Menu

    install()
    Menu.install()
