"""Maya用heditの起動窓口。エディタ本体はC++/Qtで実装する。"""
from pathlib import Path

__version__ = '0.2.10'


def _plugin_path(version):
    return Path(__file__).resolve().parents[2] / 'release' / 'plug-ins' / 'windows' / version / __version__ / 'hedit.mll'


def show(floating=None):
    """現在のMayaに対応したプラグインをロードしてエディタを表示する。"""
    from maya import cmds
    version = str(cmds.about(version=True)).split()[0]
    plugin = _plugin_path(version)
    if not plugin.is_file():
        raise RuntimeError("heditをこのMaya用にビルドしてください: {}".format(plugin))
    if 'hedit' not in (cmds.pluginInfo(query=True, listPlugins=True) or []):
        cmds.loadPlugin(str(plugin))
    from . import docking
    host = docking.show(floating=floating)
    from . import startup
    startup.opened()
    return host


def restore():
    """Mayaのワークスペース復元から呼び出す。"""
    from maya import cmds, utils
    from . import startup
    reopen = startup.previous_open()
    if not reopen:
        # 閉じたドックは必要になるまでQt本体を生成しない。
        utils.executeDeferred(startup.hide_if_closed)
        return None
    plugin = _plugin_path(str(cmds.about(version=True)).split()[0])
    if 'hedit' not in (cmds.pluginInfo(query=True, listPlugins=True) or []):
        cmds.loadPlugin(str(plugin))
    from . import docking
    host = docking.show(restore=True)
    startup.opened()
    return host

