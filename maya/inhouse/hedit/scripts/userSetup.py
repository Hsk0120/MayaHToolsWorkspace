""".mod経由のMaya GUI起動時にheditをロードし、前回開いていた画面を復元する。"""
from maya import cmds, utils
if not cmds.about(batch=True):
    utils.executeDeferred("from hedit.startup import initialize; initialize()")
