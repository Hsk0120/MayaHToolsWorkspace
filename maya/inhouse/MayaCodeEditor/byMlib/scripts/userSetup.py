""".mod経由のMaya GUI起動時にmayaCodeEditor.mllをロードするだけの最小ブートストラップ(mlib版)。

Maya Code Editor本体のロジック(復元・Windowメニュー登録・補完・静的解析等)は一切ここに置かない。
それらはC++(src/)とPython(src/python/)で書かれてmayaCodeEditor.mllに同梱されており、
initializePlugin(C++)がロード時にMaya同梱のCPythonへimportフックとして登録する。このファイルの役割は
「Maya起動時にloadPluginを1回呼ぶ」ことだけで、Plug-in Managerでの明示ロードや
Mayaのプラグインautoloadと同じ入口(initializePlugin)へ合流する。
"""
from maya import cmds

from mlib.common import Deferred, Environment, Plugin


def _load_mce():
    """GUI の Maya で、Maya Code Editor プラグインが未ロードならロードする。失敗は警告に留める。"""
    if Environment.isBatch():
        return
    plugin = Plugin('mayaCodeEditor')
    if plugin.isLoaded():
        return
    try:
        plugin.load()
    except Exception as exc:
        cmds.warning('Maya Code Editor startup: {}'.format(exc))


if not Environment.isBatch():
    Deferred.call(_load_mce)
