"""Maya Code Editor の Python 側の入口。

画面・ドッキング・状態の保存はすべて C++(mayaCodeEditor.mll)が行う。ここにあるのは、C++ の ``mayaCodeEditor`` コマンドを
Python から呼ぶための薄い窓口(:func:`show`・:func:`restore`)だけ。

このファイルは mayaCodeEditor.mll に同梱され、プラグインのロード時に import フックから配られる
(src/plugin/embedded_python.cpp)。ディスク上の .py としては読み込まれない。
そのため ``import maya_code_editor`` は、``mayaCodeEditor`` プラグインをロードした後でないと使えない。

``__version__`` は、ロード時に C++ の ``src/version.h`` の値が設定される(版の定義は1か所だけ)。
"""


def _load():
    """Maya Code Editor プラグインが未ロードならロードする。

    Returns:
        module: ``maya.cmds``。``cmds.mayaCodeEditor`` を呼べる状態で返す。
    """
    from maya import cmds
    if 'mayaCodeEditor' not in (cmds.pluginInfo(query=True, listPlugins=True) or []):
        cmds.loadPlugin('mayaCodeEditor')
    return cmds


def show(floating=None):
    """編集画面を開く(MEL の ``mayaCodeEditor -show`` と同じ)。

    すでに開いていれば、タブを保存して一度閉じてから開き直す。未保存のタブ・ドッキング位置は保たれる。

    Args:
        floating (bool | None): True ならフローティング、False ならドッキングして開く。
            None なら今の配置のまま(初回はフローティング)。
    """
    cmds = _load()
    if floating is None:
        cmds.mayaCodeEditor(show=True)
    else:
        cmds.mayaCodeEditor(show=True, floating=bool(floating))


def restore():
    """Maya のワークスペース復元から、画面を作り直す(MEL の ``mayaCodeEditor -restore`` と同じ)。

    現在の uiScript は MEL の ``mayaCodeEditor -restore`` を直接呼ぶ。この関数は、旧版で保存された
    ワークスペースの uiScript(``import maya_code_editor; maya_code_editor.restore()``)のために残している。
    前回ユーザーが閉じていた場合は、画面を作らず非表示のままにする。
    """
    _load().mayaCodeEditor(restore=True)
