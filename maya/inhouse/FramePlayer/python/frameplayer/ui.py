"""FramePlayerとの連携を操作する、Maya標準の部品(maya.cmds)で作った小さな画面。

接続・切断、FramePlayerの起動、番号の対応(ずらし・倍率)、連携の向き、再生範囲を合わせるかを設定する。
設定はMayaの設定(optionVar)に保存し、次に開いたときも使う。
"""

import threading

import maya.cmds as cmds
import maya.utils

import frameplayer
from frameplayer.sync import DEFAULT_PORT

WINDOW = "framePlayerSyncWindow"
_OPTION_PREFIX = "framePlayerSync_"
_DEFAULTS = {
    "port": DEFAULT_PORT,
    "offset": 0,
    "multiplier": 1.0,
    "syncRange": 1,
    "mayaToPlayer": 1,
    "playerToMaya": 1,
}
_controls = {}


def _load(name):
    """保存した設定を読む。

    Args:
        name (str): 設定の名前(_DEFAULTSのキー)。

    Returns:
        int or float: 値。保存していなければ既定値。
    """
    key = _OPTION_PREFIX + name
    if cmds.optionVar(exists=key):
        return cmds.optionVar(query=key)
    return _DEFAULTS[name]


def _save(name, value):
    """設定を保存する。

    Args:
        name (str): 設定の名前。
        value (int or float): 値。
    """
    key = _OPTION_PREFIX + name
    if isinstance(value, float):
        cmds.optionVar(floatValue=(key, value))
    else:
        cmds.optionVar(intValue=(key, int(value)))


def _options():
    """画面の値から、接続に渡す設定を作る(あわせて保存する)。

    Returns:
        dict: FramePlayerSync に渡す設定。
    """
    values = {
        "port": cmds.intField(_controls["port"], query=True, value=True),
        "offset": cmds.intField(_controls["offset"], query=True, value=True),
        "multiplier": cmds.floatField(_controls["multiplier"], query=True, value=True) or 1.0,
        "syncRange": cmds.checkBox(_controls["syncRange"], query=True, value=True),
        "mayaToPlayer": cmds.checkBox(_controls["mayaToPlayer"], query=True, value=True),
        "playerToMaya": cmds.checkBox(_controls["playerToMaya"], query=True, value=True),
    }
    for name, value in values.items():
        _save(name, value)
    return values


def _apply_options(*_):
    """画面で変えた設定を、つながっている接続にすぐ反映する。"""
    values = _options()
    sync = frameplayer.current()
    if sync is None:
        return
    sync.offset = int(values["offset"])
    sync.multiplier = float(values["multiplier"])
    sync.sync_range = bool(values["syncRange"])
    sync.maya_to_player = bool(values["mayaToPlayer"])
    sync.player_to_maya = bool(values["playerToMaya"])
    if sync.maya_to_player:
        sync.push_state()


def _update_status():
    """接続状態の表示とボタンを更新する。"""
    if not cmds.window(WINDOW, exists=True):
        return
    sync = frameplayer.current()
    if sync is not None and sync.connected:
        text = "接続中 (ポート %d)%s" % (sync.port, "  FramePlayer再生中" if sync.player_playing else "")
        color = (0.35, 0.6, 0.35)
    else:
        text = "未接続"
        color = (0.35, 0.35, 0.35)
    cmds.text(_controls["status"], edit=True, label=text, backgroundColor=color)
    connected = sync is not None and sync.connected
    cmds.button(_controls["connect"], edit=True, label="切断" if connected else "接続")
    cmds.button(_controls["play"], edit=True, enable=connected)
    cmds.button(_controls["stop"], edit=True, enable=connected)


def _connect(warn):
    """画面の設定でFramePlayerへ接続する。

    Args:
        warn (bool): 接続できなかったときに警告を出すか。

    Returns:
        bool: 接続できた場合True。
    """
    values = _options()
    result = frameplayer.connect(
        port=int(values["port"]),
        offset=int(values["offset"]),
        multiplier=float(values["multiplier"]),
        sync_range=bool(values["syncRange"]),
        maya_to_player=bool(values["mayaToPlayer"]),
        player_to_maya=bool(values["playerToMaya"]),
        on_status=_update_status,
    )
    if result is None and warn:
        cmds.warning("FramePlayerに接続できません。FramePlayerを起動してから接続してください(ポート %d)。"
                     % int(values["port"]))
    _update_status()
    return result is not None


def _toggle_connect(*_):
    """接続していなければ接続し、接続していれば切る。"""
    sync = frameplayer.current()
    if sync is not None and sync.connected:
        frameplayer.disconnect()
        _update_status()
        return
    _connect(warn=True)


def _launch(*_):
    """FramePlayerを起動し、起動を待ってから接続する。"""
    try:
        frameplayer.launch()
    except RuntimeError as error:
        cmds.warning(str(error))
        return
    _retry_connect(20)


def _retry_connect(remaining):
    """起動直後のFramePlayerへ、つながるまで約0.25秒ごとに接続を試す。

    Mayaの画面を止めないよう、待つのは別のスレッドのタイマーに任せ、接続はメインスレッドで行う。

    Args:
        remaining (int): 残りの試行回数。
    """
    sync = frameplayer.current()
    if (sync is not None and sync.connected) or _connect(warn=remaining <= 0) or remaining <= 0:
        return
    timer = threading.Timer(0.25, lambda: maya.utils.executeDeferred(_retry_connect, remaining - 1))
    timer.daemon = True
    timer.start()


def _play(*_):
    """FramePlayerで再生を始める。"""
    sync = frameplayer.current()
    if sync is not None:
        sync.play()


def _stop(*_):
    """FramePlayerの再生を止める。"""
    sync = frameplayer.current()
    if sync is not None:
        sync.stop()


def show():
    """連携の画面を開く(既に開いていれば前に出す)。

    Returns:
        str: 画面(window)の名前。
    """
    if cmds.window(WINDOW, exists=True):
        cmds.showWindow(WINDOW)
        _update_status()
        return WINDOW
    cmds.window(WINDOW, title="FramePlayer連携", widthHeight=(320, 300), sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAttach=("both", 8))
    _controls["status"] = cmds.text(label="未接続", height=24, backgroundColor=(0.35, 0.35, 0.35))
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1, columnAttach2=("both", "both"))
    _controls["connect"] = cmds.button(label="接続", command=_toggle_connect)
    cmds.button(label="FramePlayerを起動", command=_launch)
    cmds.setParent("..")

    cmds.separator(style="in")
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(150, 140))
    cmds.text(label="ポート", align="left")
    _controls["port"] = cmds.intField(value=int(_load("port")), minValue=1, maxValue=65535,
                                      changeCommand=_apply_options)
    cmds.setParent("..")
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(150, 140))
    cmds.text(label="ずらし (FramePlayer - Maya)", align="left")
    _controls["offset"] = cmds.intField(value=int(_load("offset")), changeCommand=_apply_options)
    cmds.setParent("..")
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(150, 140))
    cmds.text(label="倍率 (FramePlayer / Maya)", align="left")
    _controls["multiplier"] = cmds.floatField(value=float(_load("multiplier")), minValue=0.001, precision=3,
                                              changeCommand=_apply_options)
    cmds.setParent("..")
    _controls["mayaToPlayer"] = cmds.checkBox(label="Maya → FramePlayer", value=bool(_load("mayaToPlayer")),
                                              changeCommand=_apply_options)
    _controls["playerToMaya"] = cmds.checkBox(label="FramePlayer → Maya", value=bool(_load("playerToMaya")),
                                              changeCommand=_apply_options)
    _controls["syncRange"] = cmds.checkBox(label="再生範囲も合わせる", value=bool(_load("syncRange")),
                                           changeCommand=_apply_options)

    cmds.separator(style="in")
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1, columnAttach2=("both", "both"))
    _controls["play"] = cmds.button(label="FramePlayerで再生", command=_play)
    _controls["stop"] = cmds.button(label="停止", command=_stop)
    cmds.setParent("..")
    cmds.showWindow(WINDOW)
    _update_status()
    return WINDOW
