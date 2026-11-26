"""参照リグの時刻変更とワールドマトリクス評価にかかる時間を測る。"""

from statistics import median
from time import perf_counter

import maya.cmds as cmds


def measure(nodes, frames):
    """順再生と逆順ジャンプの同時刻のマトリクス差・評価時間を測る。"""
    if not nodes or len(frames) < 2:
        raise ValueError("Choose transforms and at least two frames.")
    previous = cmds.currentTime(query=True)
    refs = {cmds.referenceQuery(node, referenceNode=True) for node in nodes if cmds.referenceQuery(node, isNodeReferenced=True)}
    clock = []
    expected = {}
    error = 0.0
    try:
        for frame in frames:
            start = perf_counter()
            cmds.currentTime(frame)
            expected[frame] = [cmds.xform(node, query=True, worldSpace=True, matrix=True) for node in nodes]
            clock.append((perf_counter()-start)*1000)
        for frame in reversed(frames):
            cmds.currentTime(frame)
            for node, before in zip(nodes, expected[frame]):
                actual = cmds.xform(node, query=True, worldSpace=True, matrix=True)
                error = max(error, max(abs(a-b) for a,b in zip(before, actual)))
    finally:
        cmds.currentTime(previous)
    return {"references": len(refs), "transforms": len(nodes), "frames": len(frames),
            "evaluation": cmds.evaluationManager(query=True, mode=True)[0],
            "medianMilliseconds": median(clock), "maxMatrixDifference": error}


def run():
    """選択した評価対象と指定したフレームで負荷を測定する。"""
    window = "HToolsReferenceRigLoad"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Measure Referenced Rig Evaluation")
    cmds.columnLayout(adjustableColumn=True)
    start = cmds.intFieldGrp(label="First frame", value1=1)
    length = cmds.intFieldGrp(label="Sample count", value1=12)
    stride = cmds.intFieldGrp(label="Frame increment", value1=1)
    output = cmds.scrollField(editable=False, height=120)

    def inspect(*_):
        first, count, step = (cmds.intFieldGrp(field, query=True, value1=True) for field in (start,length,stride))
        if count < 2 or step < 1:
            raise ValueError("Choose at least two samples and a positive increment.")
        nodes = cmds.ls(selection=True, long=True, transforms=True) or []
        result = measure(nodes, range(first, first+count*step, step))
        cmds.scrollField(output, edit=True, text="\n".join(f"{key}: {value}" for key,value in result.items()))

    cmds.button(label="Measure selected transforms", command=inspect)
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
