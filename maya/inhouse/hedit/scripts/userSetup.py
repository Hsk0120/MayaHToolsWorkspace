""".mod経由のMaya GUI起動時にhedit.mllをロードするだけの最小ブートストラップ。

hedit本体のロジック(復元・Windowメニュー登録・補完・静的解析等)は一切ここに置かない。
それらはC++(src/)とPython(src/python/)で書かれてhedit.mllに同梱されており、
initializePlugin(C++)がロード時にMaya同梱のCPythonへimportフックとして登録する。このファイルの役割は
「Maya起動時にloadPluginを1回呼ぶ」ことだけで、Plug-in Managerでの明示ロードや
Mayaのプラグインautoloadと同じ入口(initializePlugin)へ合流する。
"""
from maya import cmds, utils


def _load_hedit():
    """GUI の Maya で、hedit プラグインが未ロードならロードする。失敗は警告に留める。"""
    if cmds.about(batch=True):
        return
    if 'hedit' in (cmds.pluginInfo(query=True, listPlugins=True) or []):
        return
    try:
        cmds.loadPlugin('hedit')
    except Exception as exc:
        cmds.warning('hedit startup: {}'.format(exc))


if not cmds.about(batch=True):
    utils.executeDeferred(_load_hedit)
