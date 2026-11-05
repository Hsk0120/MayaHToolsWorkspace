"""GUIの準備後にチャンネルボックス操作の監視を登録する。"""


def initialize():
    """Maya 2025以降のGUIだけでmlrigの操作監視を起動する。"""
    import mlib

    if mlib.Environment.isBatch() or mlib.Environment.getApiVersion() < 20250000:
        return
    mlib.Deferred.call(_install)


def _install():
    """シーン読込後の監視と上部の実行メニューを登録する。"""
    from mlrig.channel_controls import install
    from mlrig.menu import Menu

    install()
    Menu.install()
