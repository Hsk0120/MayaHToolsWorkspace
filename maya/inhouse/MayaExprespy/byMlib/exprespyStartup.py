"""ユーザー設定を変更せず、GUI起動時にexprespyを遅延ロードする。

バイナリの選択は ``maya/modules/exprespy.mod`` のバージョン別パスに任せる。
HTools・Qtには依存せず(この版はmlibでMayaの状態を調べる)、ロード失敗は警告して他の起動処理を続行する。
"""

from maya import cmds

from mlib.common import Deferred, Environment, Plugin


_scheduled = False


def _loadDeferred():
    """未ロードのexprespyをロードし、成功・失敗にかかわらず予約を解除する。"""
    global _scheduled
    try:
        if Environment.isBatch():
            return
        plugin = Plugin("exprespy")
        if plugin.isLoaded():
            return
        plugin.load(quiet=True)
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
    if _scheduled or Environment.isBatch():
        return
    _scheduled = True
    try:
        Deferred.call(_loadDeferred)
    except Exception as error:
        _scheduled = False
        cmds.warning("[MayaExprespy] 起動処理の予約に失敗しました: {}".format(error))
