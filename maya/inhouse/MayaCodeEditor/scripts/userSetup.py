""".mod経由のMaya GUI起動時にmayaCodeEditor.mllをロードするだけの最小ブートストラップ。

Maya Code Editor本体のロジック(復元・Windowメニュー登録・補完・静的解析等)は一切ここに置かない。
それらはC++(src/)とPython(src/python/)で書かれてmayaCodeEditor.mllに同梱されており、
initializePlugin(C++)がロード時にMaya同梱のCPythonへimportフックとして登録する。このファイルの役割は
「Maya起動時にloadPluginを1回呼ぶ」ことだけで、Plug-in Managerでの明示ロードや
Mayaのプラグインautoloadと同じ入口(initializePlugin)へ合流する。
"""
from maya import cmds, utils


def _load_mce():
    """GUI の Maya で、Maya Code Editor プラグインが未ロードならロードする。失敗は警告に留める。"""
    if cmds.about(batch=True):
        return
    if 'mayaCodeEditor' in (cmds.pluginInfo(query=True, listPlugins=True) or []):
        return
    try:
        cmds.loadPlugin('mayaCodeEditor')
    except Exception as exc:
        cmds.warning('Maya Code Editor startup: {}'.format(exc))


if not cmds.about(batch=True):
    utils.executeDeferred(_load_mce)
