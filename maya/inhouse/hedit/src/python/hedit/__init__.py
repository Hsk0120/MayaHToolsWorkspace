"""hedit の Python 側の入口。

画面・ドッキング・状態の保存はすべて C++(hedit.mll)が行う。ここにあるのは、C++ の ``hedit`` コマンドを
Python から呼ぶための薄い窓口(:func:`show`・:func:`restore`)だけ。

このファイルは hedit.mll に同梱され、プラグインのロード時に import フックから配られる
(src/plugin/embedded_python.cpp)。ディスク上の .py としては読み込まれない。
そのため ``import hedit`` は、``hedit`` プラグインをロードした後でないと使えない。

``__version__`` は、ロード時に C++ の ``src/version.h`` の値が設定される(版の定義は1か所だけ)。
"""


def _load():
    """hedit プラグインが未ロードならロードする。

    Returns:
        module: ``maya.cmds``。``cmds.hedit`` を呼べる状態で返す。
    """
    from maya import cmds
    if 'hedit' not in (cmds.pluginInfo(query=True, listPlugins=True) or []):
        cmds.loadPlugin('hedit')
    return cmds


def show(floating=None):
    """編集画面を開く(MEL の ``hedit -show`` と同じ)。

    すでに開いていれば、タブを保存して一度閉じてから開き直す。未保存のタブ・ドッキング位置は保たれる。

    Args:
        floating (bool | None): True ならフローティング、False ならドッキングして開く。
            None なら今の配置のまま(初回はフローティング)。
    """
    cmds = _load()
    if floating is None:
        cmds.hedit(show=True)
    else:
        cmds.hedit(show=True, floating=bool(floating))


def restore():
    """Maya のワークスペース復元から、画面を作り直す(MEL の ``hedit -restore`` と同じ)。

    現在の uiScript は MEL の ``hedit -restore`` を直接呼ぶ。この関数は、旧版で保存された
    ワークスペースの uiScript(``import hedit; hedit.restore()``)のために残している。
    前回ユーザーが閉じていた場合は、画面を作らず非表示のままにする。
    """
    _load().hedit(restore=True)
