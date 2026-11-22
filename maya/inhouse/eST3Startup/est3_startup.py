"""MayaのGUI起動時にeST3を開始し、eSTのメニューバーを表示する。

eST3の配布物(``maya/external/eST3``)には手を入れず、配布物が用意しているMELの
``eST3menuBar`` を呼ぶだけにしている。配布物を取得していない環境では何もしない。
"""
import maya.cmds as cmds
import maya.mel as mel
import maya.utils as maya_utils

START_COMMAND = "eST3menuBar"
_scheduled = False


def start():
    """eST3を開始してメニューバーを表示する。

    Returns:
        bool: 開始できたらTrue。配布物が無い、または開始に失敗したらFalse。
    """
    if not mel.eval('exists "{}"'.format(START_COMMAND)):
        print("[eST3Startup] eST3 is not installed (maya/external/eST3 is missing). Skipped.")
        return False
    try:
        mel.eval(START_COMMAND)
    except Exception as error:
        cmds.warning("[eST3Startup] Failed to start eST3: {}".format(error))
        return False
    print("[eST3Startup] eST3 started")
    return True


def _start_deferred():
    """遅延実行でeST3を開始し、成功・失敗にかかわらず予約状態を解除する。"""
    global _scheduled
    try:
        start()
    finally:
        _scheduled = False


def initialize():
    """GUIセッションでeST3の開始を遅延予約する。予約中とバッチ実行時は何もしない。

    Mayaのメインウィンドウができる前にメニューバーを作れないため、起動処理が
    終わった後(アイドル時)に実行する。
    """
    global _scheduled
    if _scheduled or cmds.about(batch=True):
        return
    _scheduled = True
    try:
        maya_utils.executeDeferred(_start_deferred)
    except Exception:
        _scheduled = False
        raise
