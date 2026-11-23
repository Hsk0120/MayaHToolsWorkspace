"""Maya GUI起動後にQPEのC++プラグインをロードする最小ブートストラップ(mlib版)。

Windowメニュー登録・画面復元・ファイル操作はmll側が担当する。
Plug-in Managerからのロードと同じ入口を使い、信頼設定は変更しない。
"""

from maya import cmds

from mlib.common import Deferred, Environment, Plugin


def _load_qpe():
    """GUIで未ロードのQPEだけをロードし、失敗は警告として通知する。"""
    if Environment.isBatch():
        return
    try:
        plugin = Plugin("quickPathExplorer")
        if plugin.isLoaded():
            return
        plugin.load()
    except Exception as exc:
        cmds.warning("QuickPathExplorer startup: {}".format(exc))


if not Environment.isBatch():
    Deferred.call(_load_qpe)
