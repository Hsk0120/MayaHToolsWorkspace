"""hedit の Python 側の入口。

このファイルは hedit.mll に同梱され、プラグインのロード時に import フックから配られる
(src/plugin/embedded_python.cpp)。ディスク上の .py としては読み込まれない。

``__version__`` は、ロード時に C++ の ``src/version.h`` の値が設定される(版の定義は1か所だけ)。
"""


def _load():
    from maya import cmds
    if 'hedit' not in (cmds.pluginInfo(query=True, listPlugins=True) or []):
        cmds.loadPlugin('hedit')
    return cmds


def show(floating=None):
    """編集画面を開く(MELの hedit -show と同じ)。

    Args:
        floating (bool | None): 指定時だけフローティング状態を変更する。
    """
    cmds = _load()
    if floating is None:
        cmds.hedit(show=True)
    else:
        cmds.hedit(show=True, floating=bool(floating))


def restore():
    """旧版で保存されたworkspaceControlのuiScriptから呼ばれる(MELの hedit -restore と同じ)。"""
    _load().hedit(restore=True)
