"""再生範囲の保存・切替、選んだキーへの移動、プレイブラスト。

保存した範囲は、Mayaのユーザー設定(optionVar ``animBarTimelineRanges``)へ JSON で残す。
"""

import json
import os
import tempfile

import maya.cmds as cmds

import mlib
from mlib.common import Time
from mlib.decorator import undoChunk

from . import keys

#: 保存した範囲を置くoptionVarの名前。
RANGES_OPTION = "animBarTimelineRanges"

#: 直前のプレイブラストのファイル名を置くoptionVarの名前。
LAST_PLAYBLAST_OPTION = "animBarLastPlayblast"


def savedRanges():
    """保存した再生範囲を、名前から (開始, 終了) への辞書で返す。

    Returns:
        dict[str, tuple[float, float]]: 保存した範囲。
    """
    # mlib には設定の保存先が無いため、Mayaの optionVar を使う。
    if not cmds.optionVar(exists=RANGES_OPTION):
        return {}
    try:
        data = json.loads(cmds.optionVar(query=RANGES_OPTION))
    except ValueError:
        return {}
    return {name: (float(start), float(end)) for name, (start, end) in data.items()}


def saveRange(name=None):
    """今の再生範囲を名前を付けて保存する。

    Args:
        name (str | None): 名前。Noneは ``"開始-終了"``。

    Returns:
        str: 保存した名前。
    """
    start, end = Time.getPlaybackRange()
    name = name or "{:g}-{:g}".format(start, end)
    ranges = savedRanges()
    ranges[name] = (start, end)
    cmds.optionVar(stringValue=(RANGES_OPTION, json.dumps(ranges)))
    return name


def removeRange(name=None):
    """保存した範囲を消す。

    Args:
        name (str | None): 名前。Noneは全部。

    Returns:
        None: 値を返さない。
    """
    ranges = {} if name is None else {key: value for key, value in savedRanges().items() if key != name}
    cmds.optionVar(stringValue=(RANGES_OPTION, json.dumps(ranges)))


def useRange(name):
    """保存した範囲を再生範囲にする。

    Args:
        name (str): 名前。

    Returns:
        tuple[float, float]: 設定した範囲。

    Raises:
        KeyError: その名前の範囲が無い場合。
    """
    start, end = savedRanges()[name]
    return Time.setPlaybackRange(start, end)


def frameSelectedKeys(nodes=None):
    """選んだキー(無ければ選んだノードの全キー)の範囲を再生範囲にする。

    Args:
        nodes (Iterable[Node] | None): 対象。Noneは選択。

    Returns:
        tuple[float, float] | None: 設定した範囲。キーが無ければNone(変えない)。
    """
    times = keys.keyTimesOf([], selectedOnly=True) or keys.keyTimesOf(
        keys.selectedNodes() if nodes is None else nodes)
    if not times:
        return None
    end = times[-1] if times[-1] > times[0] else times[0] + 1
    return Time.setPlaybackRange(times[0], end)


def jumpToKey(direction=0):
    """現在時刻を、選んだキーの最初(direction=0)、または前後のキー(-1・1)へ動かす。

    Args:
        direction (int): 0は選んだキーの最初、-1は前のキー、1は後ろのキー。

    Returns:
        float | None: 移った時刻。キーが無ければNone。
    """
    now = Time.getCurrent()
    times = keys.keyTimesOf([], selectedOnly=True) if direction == 0 else []
    if not times:
        times = keys.keyTimesOf(keys.selectedNodes())
    if not times:
        return None
    if direction < 0:
        candidates = [time for time in times if time < now - keys.TIME_EPSILON]
        time = candidates[-1] if candidates else times[-1]
    elif direction > 0:
        candidates = [time for time in times if time > now + keys.TIME_EPSILON]
        time = candidates[0] if candidates else times[0]
    else:
        time = times[0]
    return Time.setCurrent(time)


def playblast(camera=None, play=True, folder=None):
    """今の再生範囲をプレイブラストする。

    Args:
        camera (str | Node | None): 撮るカメラ。Noneは今のビューポート。
        play (bool): Trueは撮った後に再生する。
        folder (str | None): 保存先のフォルダ。Noneは一時フォルダ。

    Returns:
        str: 保存したファイルのパス。
    """
    # mlib にはビューポートとプレイブラストの入口が無いため、Mayaのコマンドを使う。
    panel = cmds.getPanel(withFocus=True)
    if not panel or cmds.getPanel(typeOf=panel) != "modelPanel":
        panels = cmds.getPanel(type="modelPanel") or []
        panel = panels[0] if panels else None
    previous = None
    if camera is not None and panel:
        previous = cmds.modelPanel(panel, query=True, camera=True)
        cmds.modelPanel(panel, edit=True, camera=mlib.nodes.Node(camera).getFullName())
    try:
        start, end = Time.getPlaybackRange()
        path = os.path.join(folder or tempfile.gettempdir(), "animBar_playblast")
        result = cmds.playblast(filename=path, startTime=start, endTime=end, forceOverwrite=True,
                                viewer=play, showOrnaments=True, percent=100, offScreen=True)
    finally:
        if previous is not None:
            cmds.modelPanel(panel, edit=True, camera=previous)
    cmds.optionVar(stringValue=(LAST_PLAYBLAST_OPTION, result or ""))
    return result


def playLastPlayblast():
    """直前のプレイブラストを再生する。

    Returns:
        str | None: 再生したファイル。無ければNone。
    """
    path = cmds.optionVar(query=LAST_PLAYBLAST_OPTION) if cmds.optionVar(exists=LAST_PLAYBLAST_OPTION) else ""
    if not path:
        return None
    cmds.launch(movie=path)
    return path


@undoChunk("animBarDuplicateCamera")
def duplicateCamera(camera=None):
    """カメラを、アニメーションを焼いた独立したカメラとして複製する(レイアウト確認用)。

    Args:
        camera (str | Node | None): 元のカメラ(Transform)。Noneは選択の最初。

    Returns:
        Node: 複製したカメラのTransform。
    """
    source = mlib.nodes.Node(camera) if camera is not None else keys.selectedNodes()[0]
    copy = mlib.duplicate(source, name=source.getNodeName(removeNamespace=True) + "_copy")[0]
    if copy.getParent() is not None:
        copy.setParent(None)
    start, end = Time.getPlaybackRange()
    with Time.preserved():
        for frame in range(int(start), int(end) + 1):
            Time.setCurrent(frame)
            copy.setMatrix(source.getMatrix(worldSpace=True), worldSpace=True)
            copy.setKey(["translate", "rotate"], time=frame)
    return copy
