"""同一ソルバーの固定刻み状態を保存し、同じ入力姿勢から再開する。"""

import json
import math
from pathlib import Path
from tempfile import NamedTemporaryFile

from maya import cmds
from maya.api import OpenMaya as om

from . import api


def _context(node):
    """対象ID・時間単位・設定と固定刻みの計算ノードを取得する。"""
    api._solver(node)
    selection = om.MSelectionList()
    selection.add(node)
    instance = om.MFnDependencyNode(selection.getDependNode(0)).userNode()
    # 通常DGで設定変更を反映する。現在の時刻は移動しない。
    cmds.getAttr(node + ".peakParticleSpeed")
    metadata = {
        "solver": cmds.ls(node, uuid=True)[0],
        "input": cmds.ls(api.getConnection(node, "sourceMesh"), uuid=True)[0],
        "colliders": [cmds.ls(name, uuid=True)[0] for name in api.getColliders(node)],
        "timeUnit": cmds.currentUnit(query=True, time=True),
        "fps": 1.0 / om.MTime(1, om.MTime.uiUnit()).asUnits(om.MTime.kSeconds),
        "signature": instance._signature,
    }
    return instance, metadata


def saveState(node, path):
    """現在の固定刻み上の位置・速度と入力形状をUTF-8 JSONへ保存する。"""
    instance, metadata = _context(node)
    unit = om.MTime.uiUnit()
    frame = cmds.getAttr(node + ".time")
    elapsed = om.MTime(frame - cmds.getAttr(node + ".startFrame"), unit).asUnits(om.MTime.kSeconds)
    offset = elapsed * cmds.getAttr(node + ".solverRate")
    step = round(offset)
    if offset < 0 or abs(step - offset) > 1e-7:
        raise ValueError("開始時刻以降の固定刻み上で状態を保存してください")
    key, state = instance._cache[step - instance._cache_origin[0]]
    payload = dict(metadata, format="SimpleClothState", version=1, step=step, frame=frame, sample=json.dumps(key),
                   state=[[list(point) for point in values] for values in state])
    contents = json.dumps(payload, allow_nan=False, ensure_ascii=False)
    target = Path(path)
    with NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_text(contents, encoding="utf-8")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_state(node, path):
    """対象、設定、保存時刻の入力と状態配列を検証する。"""
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(saved, dict) or saved.get("format") != "SimpleClothState" or saved.get("version") != 1:
        raise ValueError("Simple Clothの途中再開ファイルを指定してください")
    instance, metadata = _context(node)
    if any(saved.get(key) != value for key, value in metadata.items()):
        raise ValueError("対象・設定・時間単位が保存時と異なります")
    step = saved.get("step")
    if type(step) is not int or not 0 <= step <= cmds.getAttr(node + ".maxSteps"):
        raise ValueError("保存ステップが不正です")
    reference = json.loads(cmds.getAttr(node + ".referenceData"))
    kinds = json.loads(cmds.getAttr(node + ".colliderTypes"))
    seconds = om.MTime(cmds.getAttr(node + ".startFrame"), om.MTime.uiUnit()).asUnits(om.MTime.kSeconds)
    moment = om.MTime(seconds + step / cmds.getAttr(node + ".solverRate"), om.MTime.kSeconds)
    frame = saved.get("frame")
    if type(frame) not in (int, float) or not math.isclose(moment.asUnits(om.MTime.uiUnit()), frame, rel_tol=0, abs_tol=1e-6):
        raise ValueError("保存フレームとステップが一致しません")
    _, _, _, key = instance._sample(moment.asUnits(om.MTime.kSeconds), reference, kinds)
    if json.dumps(key) != saved.get("sample"):
        raise ValueError("保存時の入力姿勢またはコライダーが異なります")
    arrays = saved.get("state")
    if not isinstance(arrays, list) or len(arrays) != 2 or any(
        not isinstance(array, list) or len(array) != len(reference["points"]) or any(
            not isinstance(point, list) or len(point) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)
            for point in array) for array in arrays
    ):
        raise ValueError("保存した位置または速度が不正です")
    return instance, saved


def compareState(node, path):
    """保存フレームで現在評価と保存状態の最大位置差(cm)・速度差(cm/s)を返す。"""
    instance, saved = _read_state(node, path)
    if abs(cmds.getAttr(node + ".time") - saved["frame"]) > 1e-7:
        raise ValueError("比較には保存フレームを表示してください")
    current, velocities = instance._cache[saved["step"] - instance._cache_origin[0]][1]
    positions = [om.MVector(point) for point in saved["state"][0]]
    saved_velocities = [om.MVector(point) for point in saved["state"][1]]
    return {
        "maxPositionDifference": max((a - b).length() for a, b in zip(current, positions)),
        "maxVelocityDifference": max((a - b).length() for a, b in zip(velocities, saved_velocities)),
    }


def loadState(node, path):
    """同一ソルバーの固定刻み状態を復元する。1回のUndoで解除できる。"""
    _, saved = _read_state(node, path)
    cmds.setAttr(node + ".resumeState", json.dumps(saved, allow_nan=False), type="string")
