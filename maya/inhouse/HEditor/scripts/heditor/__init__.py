"""Maya用HEditorの起動窓口。エディタ本体はC++/Qtで実装する。"""
from pathlib import Path

__version__ = '0.1.2'


def _plugin_path(version):
    return Path(__file__).resolve().parents[2] / 'release' / 'plug-ins' / 'windows' / version / __version__ / 'HEditor.mll'


def show():
    """現在のMayaに対応したプラグインをロードしてエディタを表示する。"""
    from maya import cmds
    version = str(cmds.about(version=True)).split()[0]
    plugin = _plugin_path(version)
    if not plugin.is_file():
        raise RuntimeError("HEditorをこのMaya用にビルドしてください: {}".format(plugin))
    if 'HEditor' not in (cmds.pluginInfo(query=True, listPlugins=True) or []):
        cmds.loadPlugin(str(plugin))
    cmds.heditor()

