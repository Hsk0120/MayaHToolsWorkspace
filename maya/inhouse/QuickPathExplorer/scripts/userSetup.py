"""Maya GUI起動後にQPEのC++プラグインをロードする最小ブートストラップ。

Windowメニュー登録・画面復元・ファイル操作はmll側が担当する。
Plug-in Managerからのロードと同じ入口を使い、信頼設定は変更しない。
"""

from maya import cmds, utils


def _load_qpe():
    """GUIで未ロードのQPEだけをロードし、失敗は警告として通知する。"""
    if cmds.about(batch=True):
        return
    try:
        if "quickPathExplorer" in (cmds.pluginInfo(query=True, listPlugins=True) or []):
            return
        cmds.loadPlugin("quickPathExplorer")
    except Exception as exc:
        cmds.warning("QuickPathExplorer startup: {}".format(exc))


if not cmds.about(batch=True):
    utils.executeDeferred(_load_qpe)
