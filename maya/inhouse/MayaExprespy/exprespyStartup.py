"""ユーザー設定を変更せず、GUI起動時にexprespyを遅延ロードする。

バイナリの選択は ``maya/modules/exprespy.mod`` のバージョン別パスに任せる。
HTools・hlib・Qtには依存せず、ロード失敗は警告して他の起動処理を続行する。
"""

from maya import cmds, utils


_scheduled = False


def _loadDeferred():
    """未ロードのexprespyをロードし、成功・失敗にかかわらず予約を解除する。"""
    global _scheduled
    try:
        if cmds.about(batch=True):
            return
        if "exprespy" in (cmds.pluginInfo(query=True, listPlugins=True) or []):
            return
        cmds.loadPlugin("exprespy", quiet=True)
    except Exception as error:
        cmds.warning("[MayaExprespy] exprespyのロードに失敗しました: {}".format(error))
    finally:
        _scheduled = False


def initialize():
    """GUIセッションでexprespyのロードを遅延予約する。

    予約中とバッチ実行時は何もしない。ロードや予約が失敗した場合は警告し、
    再度呼び出して再試行できる。プラグインのautoloadや信頼済みパスは変更しない。
    """
    global _scheduled
    if _scheduled or cmds.about(batch=True):
        return
    _scheduled = True
    try:
        utils.executeDeferred(_loadDeferred)
    except Exception as error:
        _scheduled = False
        cmds.warning("[MayaExprespy] 起動処理の予約に失敗しました: {}".format(error))
