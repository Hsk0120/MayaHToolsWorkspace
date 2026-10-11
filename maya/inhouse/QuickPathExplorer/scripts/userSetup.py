"""GUI起動後にQuickPathExplorerをWindowメニューへ登録する。"""
from maya import cmds, utils
if not cmds.about(batch=True):
    import qpeHost
    utils.executeDeferred(qpeHost.installMenu)
