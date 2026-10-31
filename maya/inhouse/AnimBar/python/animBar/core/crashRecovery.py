"""アニメーションの退避(クラッシュに備えて、一定間隔でキーをファイルへ書き出す)と復元。

有効にすると、一定の時間ごとに、シーンの時間入力のアニメーションカーブのキーを JSON へ書き出す
(書き出すのはキーの時刻・値・接線の型・角度・ウェイト・ロック、インフィニティと、駆動先のアトリビュート名)。シーンを保存すると退避は消える。
Mayaが落ちた後に同じシーンを開いて :func:`restore` を呼ぶと、退避したキーで同名のアトリビュートを置き換える。
有効にした状態は覚え、次の起動でも有効にする。有効な間は、起動時とシーンを開いたときに、そのシーンの
シーンより新しい退避があれば戻すかを聞く(:func:`checkOnOpen`)。
"""

import hashlib
import json
import os
import tempfile
import time

import maya.cmds as cmds

import mlib
from mlib.common import ScriptJob
from mlib.decorator import undoChunk

from . import keys

#: 退避の間隔(秒)。
INTERVAL = 180

#: 退避の状態。
_state = {"jobs": [], "last": 0.0}

#: 有効にしたかを覚えるoptionVarの名前。
ENABLED_OPTION = "animBarRecoveryEnabled"


def backupPath(scene=None):
    """退避ファイルのパスを返す。シーンごとに別のファイルにする。

    Args:
        scene (str | None): シーンのパス。Noneは今のシーン。

    Returns:
        str: 退避ファイルのパス。
    """
    scene = cmds.file(query=True, sceneName=True) if scene is None else scene
    name = os.path.splitext(os.path.basename(scene))[0] if scene else "untitled"
    if scene:
        # 別のフォルダの同じ名前のシーンと退避が混ざらないよう、フルパスの短いハッシュを付ける。
        name += "_" + hashlib.sha1(os.path.normcase(os.path.abspath(scene)).encode("utf-8")).hexdigest()[:8]
    return os.path.join(tempfile.gettempdir(), "animBar_recovery", name + ".json")


def backup(path=None):
    """今のアニメーションのキーを退避ファイルへ書き出す。

    Args:
        path (str | None): 書き出すファイル。Noneは :func:`backupPath`。

    Returns:
        int: 書き出したカーブの数。
    """
    path = backupPath() if path is None else path
    data = {}
    for curve in mlib.ls(type="animCurve"):
        if not curve.isTimeInput() or curve.isFromReferencedFile():
            continue
        destinations = curve.getPlug("output").getDestinations(skipConversionNodes=True)
        if not destinations:
            continue
        data[destinations[0].getName()] = keys.curveSnapshot(curve)
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"time": time.time(), "curves": data}, handle)
    _state["last"] = time.time()
    return len(data)


def hasBackup(path=None):
    """退避ファイルがあるかを返す。

    Args:
        path (str | None): 退避ファイル。Noneは :func:`backupPath`。

    Returns:
        bool: あればTrue。
    """
    return os.path.isfile(backupPath() if path is None else path)


@undoChunk("animBarRestoreAnimation")
def restore(path=None):
    """退避したキーで、同名のアトリビュートのアニメーションを置き換える。

    Args:
        path (str | None): 退避ファイル。Noneは :func:`backupPath`。

    Returns:
        int: 置き換えたアトリビュートの数。見つからないアトリビュートは飛ばす。
    """
    with open(backupPath() if path is None else path, encoding="utf-8") as handle:
        data = json.load(handle)["curves"]
    count = 0
    for name, snapshot in data.items():
        if not mlib.objExists(name):
            continue
        plug = mlib.getPlug(name)
        if not keys.isEditable(plug):
            continue
        if isinstance(snapshot, list):
            # 1.0.0 の退避(時刻・値・接線型の並び)も読めるようにする。
            snapshot = {"keys": [[when, value, {"inTangentType": tangent_in, "outTangentType": tangent_out}]
                                 for when, value, tangent_in, tangent_out in snapshot]}
        if not snapshot["keys"]:
            continue
        curve = keys.animCurveOf(plug)
        if curve is None:
            # 退避した後にキーを消したアトリビュートは、カーブを作り直してから戻す。
            first = snapshot["keys"][0]
            plug.setKey(time=first[0], value=first[1])
            curve = keys.animCurveOf(plug)
        keys.applySnapshot(curve, snapshot, replace="all")
        count += 1
    return count

def isBackupNewer(path=None, scene=None):
    """退避ファイルが、シーンを保存したときより新しいかを返す。

    Args:
        path (str | None): 退避ファイル。Noneは :func:`backupPath`。
        scene (str | None): シーンのパス。Noneは今のシーン。

    Returns:
        bool: 退避があり、シーンのファイルより新しい(シーンが未保存なら退避があるだけで)ならTrue。
    """
    scene = cmds.file(query=True, sceneName=True) if scene is None else scene
    path = backupPath(scene) if path is None else path
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as handle:
            stamp = float(json.load(handle).get("time", 0.0))
    except (OSError, ValueError):
        return False
    return not scene or not os.path.isfile(scene) or stamp > os.path.getmtime(scene)


def checkOnOpen(ask=None):
    """今のシーンに新しい退避があれば、戻すかを聞いて戻す・消す。

    Args:
        ask (callable | None): 答えを返す関数 ``f(path) -> "restore" | "discard" | "keep"``。
            Noneは Maya のダイアログで聞く(GUI が無ければ聞かずに残す)。

    Returns:
        str | None: 選んだ答え。退避が無ければNone。
    """
    if not isBackupNewer():
        return None
    path = backupPath()
    if ask is None:
        if cmds.about(batch=True):
            return "keep"
        button = cmds.confirmDialog(title="Anim Bar", button=["Restore", "Discard", "Later"],
                                    message="An animation backup newer than this scene was found.\n"
                                            "Restore the backed up keys?",
                                    defaultButton="Restore", cancelButton="Later", dismissString="Later")
        answer = {"Restore": "restore", "Discard": "discard"}.get(button, "keep")
    else:
        answer = ask(path)
    if answer == "restore":
        mlib.logger.info("Restored {} curves from the animation backup".format(restore(path)))
    elif answer == "discard":
        discard(path)
    return answer


def wasEnabled():
    """前回、退避を有効にしていたかを返す。

    Returns:
        bool: 有効にしていたらTrue。
    """
    return cmds.optionVar(exists=ENABLED_OPTION) and bool(cmds.optionVar(query=ENABLED_OPTION))


def discard(path=None):
    """退避ファイルを消す。

    Args:
        path (str | None): 退避ファイル。Noneは :func:`backupPath`。

    Returns:
        None: 値を返さない。
    """
    path = backupPath() if path is None else path
    if os.path.isfile(path):
        os.remove(path)


def isEnabled():
    """退避が有効かを返す。

    Returns:
        bool: 有効ならTrue。
    """
    return any(job.exists() for job in _state["jobs"])


def setEnabled(enabled, remember=True):
    """退避を有効・無効にする。

    有効な間は、Mayaが暇なときに INTERVAL 秒ごとに退避し、シーンを保存したら退避ファイルを消す。
    シーンを開いたときは :func:`checkOnOpen` で新しい退避を戻すかを聞く。

    Args:
        enabled (bool): Trueは有効にする。
        remember (bool): Trueは状態を覚え、次の起動でも同じにする。

    Returns:
        bool: 有効ならTrue。
    """
    for job in _state["jobs"]:
        job.stop()
    _state["jobs"] = []
    if enabled:
        _state["last"] = time.time()
        _state["jobs"] = [ScriptJob(event="idle", callback=_tick), ScriptJob(event="SceneSaved", callback=discard),
                          ScriptJob(event="SceneOpened", callback=checkOnOpen)]
    if remember:
        cmds.optionVar(intValue=(ENABLED_OPTION, int(bool(enabled))))
    return bool(enabled)


def _tick():
    """前回の退避から INTERVAL 秒たっていれば退避する(scriptJob の idle から呼ぶ)。

    Returns:
        None: 値を返さない。
    """
    if time.time() - _state["last"] >= INTERVAL:
        try:
            backup()
        except (OSError, RuntimeError) as error:
            mlib.logger.warning("Animation backup failed: {}".format(error))
            _state["last"] = time.time()
