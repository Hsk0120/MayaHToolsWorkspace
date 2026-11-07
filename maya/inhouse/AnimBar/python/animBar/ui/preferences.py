"""Anim Bar の画面の設定(区切りの表示・ボタンの大きさ)を Maya のユーザー設定(optionVar)へ覚える。

プレイブラスト・退避・細かい移動の設定は、それぞれの処理のモジュールが覚える。
:func:`resetAll` はそれらもまとめて既定へ戻す。
"""

import json

import maya.cmds as cmds

from ..core import crashRecovery, timeline, viewTools

#: バーの区切りの見出し(左から順)。
SECTIONS = ("Tween", "Keys", "Tangents", "Time", "Pose", "Space", "View", "Sets")

#: 隠す区切りを覚えるoptionVarの名前。
HIDDEN_SECTIONS_OPTION = "animBarHiddenSections"

#: ボタンの大きさを覚えるoptionVarの名前。
SIZE_OPTION = "animBarSize"

#: ボタンの大きさ: (名前, 表示名, アイコンの大きさ(px), バーの高さ(px))。
SIZES = (("small", "Small", 18, 30), ("medium", "Medium", 22, 34), ("large", "Large", 28, 40))

#: ボタンの大きさの既定。
DEFAULT_SIZE = "medium"


def hiddenSections():
    """隠す区切りの見出しを返す。

    Returns:
        list[str]: 隠す区切りの見出し(:data:`SECTIONS` の順)。
    """
    stored = []
    if cmds.optionVar(exists=HIDDEN_SECTIONS_OPTION):
        try:
            stored = json.loads(cmds.optionVar(query=HIDDEN_SECTIONS_OPTION))
        except (TypeError, ValueError):
            stored = []
    return [name for name in SECTIONS if name in stored]


def setSectionVisible(name, visible):
    """区切りの表示・非表示を覚える。

    Args:
        name (str): :data:`SECTIONS` の見出し。
        visible (bool): Trueなら表示する。

    Returns:
        list[str]: 変えた後の隠す区切り。

    Raises:
        KeyError: 知らない見出しを渡した場合。
    """
    if name not in SECTIONS:
        raise KeyError("Unknown Anim Bar section: {}".format(name))
    hidden = set(hiddenSections())
    if visible:
        hidden.discard(name)
    else:
        hidden.add(name)
    names = [section for section in SECTIONS if section in hidden]
    cmds.optionVar(stringValue=(HIDDEN_SECTIONS_OPTION, json.dumps(names)))
    return names


def size():
    """ボタンの大きさの名前を返す。

    Returns:
        str: :data:`SIZES` の名前。
    """
    stored = cmds.optionVar(query=SIZE_OPTION) if cmds.optionVar(exists=SIZE_OPTION) else None
    return stored if stored in [entry[0] for entry in SIZES] else DEFAULT_SIZE


def setSize(name):
    """ボタンの大きさを覚える(バーを作り直すまで画面には反映されない)。

    Args:
        name (str): :data:`SIZES` の名前。

    Returns:
        str: 覚えた名前。

    Raises:
        KeyError: 知らない名前を渡した場合。
    """
    if name not in [entry[0] for entry in SIZES]:
        raise KeyError("Unknown Anim Bar size: {}".format(name))
    cmds.optionVar(stringValue=(SIZE_OPTION, name))
    return name


def iconSize():
    """今の大きさのアイコンの一辺を返す。

    Returns:
        int: アイコンの大きさ(px)。
    """
    return next(entry[2] for entry in SIZES if entry[0] == size())


def barHeight():
    """今の大きさのバーの高さを返す。

    Returns:
        int: バーの高さ(px)。
    """
    return next(entry[3] for entry in SIZES if entry[0] == size())


def resetAll():
    """Anim Bar の設定をすべて既定へ戻す。

    区切りの表示・ボタンの大きさ・プレイブラストの設定・退避の有効/無効・細かい移動の倍率を戻す。
    保存した再生範囲・選択セット・退避のファイルはデータなので残す。

    Returns:
        None: 値を返さない。
    """
    for option in (HIDDEN_SECTIONS_OPTION, SIZE_OPTION):
        if cmds.optionVar(exists=option):
            cmds.optionVar(remove=option)
    timeline.resetPlayblastSettings()
    viewTools.resetMicroFactor()
    crashRecovery.setEnabled(False)
