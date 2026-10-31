"""再生範囲の保存・切替、選んだキーへの移動、プレイブラスト。

保存した範囲とプレイブラストの設定は、Mayaのユーザー設定(optionVar)へ JSON で残す。
"""

import json
import os
import tempfile

import maya.cmds as cmds
import maya.mel as mel

import mlib
from mlib.common import ScriptJob, Selection, Time
from mlib.decorator import undoChunk

from . import keys

#: 保存した範囲を置くoptionVarの名前。
RANGES_OPTION = "animBarTimelineRanges"

#: 直前のプレイブラストのファイル名を置くoptionVarの名前。
LAST_PLAYBLAST_OPTION = "animBarLastPlayblast"

#: プレイブラストの設定を置くoptionVarの名前。
PLAYBLAST_OPTION = "animBarPlayblastSettings"

#: プレイブラストの設定の既定。sound はタイムスライダーの音声を入れるか、overscan は撮る間のカメラの
#: オーバースキャン(Noneは変えない)、percent は大きさ(%)、showOrnaments はHUD等を映すか、
#: useRange はタイムスライダーで選んだ範囲があればそこだけ撮るか。
PLAYBLAST_DEFAULTS = {"sound": True, "overscan": None, "percent": 100, "showOrnaments": True, "useRange": True}


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
    """現在時刻を、選んだキーの平均の時刻(direction=0)、または前後のキー(-1・1)へ動かす。

    direction=0 で Graph Editor のキーを選んでいなければ、選んだノードの最初のキーへ移る。

    Args:
        direction (int): 0は選んだキーの平均の時刻、-1は前のキー、1は後ろのキー。

    Returns:
        float | None: 移った時刻。キーが無ければNone。
    """
    now = Time.getCurrent()
    if direction == 0:
        selected = keys.graphEditorKeys()
        chosen = [time for curve, indices in selected.items()
                  for time in curve.getKeyframes(indices).getTimes()]
        if chosen:
            # 複数のカーブで選んだキーの真ん中あたりを見られるよう、平均の時刻へ移る(aTools と同じ)。
            return Time.setCurrent(sum(chosen) / len(chosen))
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


#: 選んだキーへ自動で移る scriptJob。
_jump = {"job": None}


def setJumpToSelectedKey(enabled):
    """選択が変わるたびに、選んだキーの平均の時刻へ移るかを切り替える(GUI のみ)。

    Args:
        enabled (bool): Trueは有効にする。

    Returns:
        bool: 有効ならTrue。
    """
    if _jump["job"] is not None:
        _jump["job"].stop()
        _jump["job"] = None
    if enabled:
        _jump["job"] = ScriptJob(event="SelectionChanged", callback=_jump_if_keys, killWithScene=False)
        _jump_if_keys()
    return isJumpToSelectedKey()


def isJumpToSelectedKey():
    """選んだキーへ自動で移る設定かを返す。

    Returns:
        bool: 有効ならTrue。
    """
    return _jump["job"] is not None and _jump["job"].exists()


def _jump_if_keys():
    """キーを選んでいるときだけ、その平均の時刻へ移る(scriptJob から呼ぶ)。"""
    if len(Selection.getKeyframes()):
        jumpToKey(0)


def playblastSettings():
    """プレイブラストの設定を返す。

    Returns:
        dict: :data:`PLAYBLAST_DEFAULTS` と同じ鍵の辞書。
    """
    settings = dict(PLAYBLAST_DEFAULTS)
    if cmds.optionVar(exists=PLAYBLAST_OPTION):
        try:
            stored = json.loads(cmds.optionVar(query=PLAYBLAST_OPTION))
        except ValueError:
            stored = {}
        settings.update({key: value for key, value in stored.items() if key in PLAYBLAST_DEFAULTS})
    return settings


def setPlayblastSettings(**settings):
    """プレイブラストの設定を変えて覚える。

    Args:
        **settings: :data:`PLAYBLAST_DEFAULTS` の鍵と値。

    Returns:
        dict: 変えた後の設定。

    Raises:
        KeyError: 知らない鍵を渡した場合。
        ValueError: percent が 1〜200 でない、overscan が 1 未満の場合。
    """
    unknown = set(settings) - set(PLAYBLAST_DEFAULTS)
    if unknown:
        raise KeyError("Unknown playblast settings: " + ", ".join(sorted(unknown)))
    if "percent" in settings and not 1 <= int(settings["percent"]) <= 200:
        raise ValueError("percent must be between 1 and 200")
    if settings.get("overscan") is not None and float(settings["overscan"]) < 1.0:
        raise ValueError("overscan must be 1.0 or more")
    current = playblastSettings()
    current.update(settings)
    cmds.optionVar(stringValue=(PLAYBLAST_OPTION, json.dumps(current)))
    return current


def resetPlayblastSettings():
    """プレイブラストの設定を既定へ戻す。

    Returns:
        dict: 既定の設定。
    """
    if cmds.optionVar(exists=PLAYBLAST_OPTION):
        cmds.optionVar(remove=PLAYBLAST_OPTION)
    return playblastSettings()


def playblast(camera=None, play=True, folder=None):
    """今の再生範囲(タイムスライダーで範囲を選んでいればその範囲)をプレイブラストする。

    音声・オーバースキャン・大きさ等は :func:`playblastSettings` に従う。

    Args:
        camera (str | Node | None): 撮るカメラ。Noneは今のビューポート。
        play (bool): Trueは撮った後に再生する。
        folder (str | None): 保存先のフォルダ。Noneは一時フォルダ。

    Returns:
        str: 保存したファイルのパス。
    """
    settings = playblastSettings()
    # mlib にはビューポートとプレイブラストの入口が無いため、Mayaのコマンドを使う。
    panel = cmds.getPanel(withFocus=True)
    if not panel or cmds.getPanel(typeOf=panel) != "modelPanel":
        panels = cmds.getPanel(type="modelPanel") or []
        panel = panels[0] if panels else None
    previous = None
    if camera is not None and panel:
        previous = cmds.modelPanel(panel, query=True, camera=True)
        cmds.modelPanel(panel, edit=True, camera=mlib.nodes.Node(camera).getFullName())
    overscan = None
    if settings["overscan"] is not None and panel:
        shape = mlib.nodes.Node(cmds.modelPanel(panel, query=True, camera=True))
        shape = shape.getShape() if isinstance(shape, mlib.nodes.Transform) else shape
        if shape is not None and shape.hasAttr("overscan") and keys.isEditable(shape.getPlug("overscan")):
            overscan = (shape.getPlug("overscan"), shape.getPlug("overscan").get())
            overscan[0].set(float(settings["overscan"]))
    try:
        start, end = Time.getPlaybackRange()
        span = keys.timelineRange() if settings["useRange"] else None
        if span is not None:
            start, end = span
        flags = {}
        sound = _timeline_sound() if settings["sound"] else None
        if sound:
            flags["sound"] = sound
        path = os.path.join(folder or tempfile.gettempdir(), "animBar_playblast")
        result = cmds.playblast(filename=path, startTime=start, endTime=end, forceOverwrite=True,
                                viewer=play, showOrnaments=bool(settings["showOrnaments"]),
                                percent=int(settings["percent"]), offScreen=True, **flags)
    finally:
        if overscan is not None:
            overscan[0].set(overscan[1])
        if previous is not None:
            cmds.modelPanel(panel, edit=True, camera=previous)
    cmds.optionVar(stringValue=(LAST_PLAYBLAST_OPTION, result or ""))
    return result


def _timeline_sound():
    """タイムスライダーで鳴らしている音声のノード名を返す。

    Returns:
        str | None: 音声のノード名。無い・GUIが無ければNone。
    """
    if cmds.about(batch=True):
        return None
    # mlib にはタイムスライダーの音声の入口が無いため、Mayaのコマンドを使う。
    slider = mel.eval("$animBarTmp = $gPlayBackSlider")
    if not cmds.timeControl(slider, query=True, displaySound=True):
        return None
    return cmds.timeControl(slider, query=True, sound=True) or None


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

    複製した子のコンストレイント等は消し、移動・回転・拡大のロックと入力接続を外してから、
    再生範囲の各フレームでワールドのマトリクスを焼く(終わりにオイラーフィルタ)。焦点距離など
    カメラのシェイプのアニメーションのあるアトリビュートも同じフレームで焼く。

    Args:
        camera (str | Node | None): 元のカメラ(Transform)。Noneは選択の最初。

    Returns:
        Node: 複製したカメラのTransform。
    """
    source = mlib.nodes.Node(camera) if camera is not None else keys.selectedNodes()[0]
    copy = mlib.duplicate(source, name=source.getNodeName(removeNamespace=True) + "_copy")
    extras = [child for child in copy.getChildren()]
    if extras:
        mlib.delete(extras)
    if copy.getParent() is not None:
        copy.setParent(None)
    channels = [copy.getPlug(name) for name in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz")]
    for plug in channels:
        plug.setLocked(False)
        if plug.getSource() is not None:
            plug.disconnect()
    shape, copy_shape = source.getShape(), copy.getShape()
    animated = []
    if shape is not None and copy_shape is not None:
        for plug in shape.getPlugs(keyable=True, scalar=True):
            if plug.getSource() is not None and copy_shape.hasAttr(plug.getLongName()):
                target = copy_shape.getPlug(plug.getLongName())
                target.setLocked(False)
                if target.getSource() is not None:
                    target.disconnect()
                animated.append((plug, target))
    start, end = Time.getPlaybackRange()
    with Time.preserved():
        for frame in range(int(start), int(end) + 1):
            Time.setCurrent(frame)
            copy.setMatrix(source.getMatrix(worldSpace=True), worldSpace=True)
            copy.setKey(["translate", "rotate"], time=frame)
            for plug, target in animated:
                target.set(plug.get())
                target.setKey(time=frame)
    curves = [curve.getFullName() for curve in (copy.getPlug(name).getAnimCurve() for name in ("rx", "ry", "rz"))
              if curve is not None]
    if curves:
        # mlib にはオイラーフィルタの入口が無いため、Mayaのコマンドを使う。
        cmds.filterCurve(curves, filter="euler")
    return copy