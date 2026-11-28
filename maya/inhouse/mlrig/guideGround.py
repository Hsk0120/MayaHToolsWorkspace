"""両足のガイドのうち低い方を指定した地面の高さに合わせる。"""

import math

import mlib
from maya import cmds
from mlib.decorator import undoTransaction


@undoTransaction("mlrigGroundGuides")
def align(root, left, right, height):
    """ワールドの上方向だけにルートを移動し、子のローカル姿勢を保持する。"""
    nodes = []
    for name in (root, left, right):
        matches = mlib.ls(name, long=True, transforms=True).getNames(full=True)
        if len(matches) != 1:
            raise ValueError("ルートと左右の接地点を一意に指定してください")
        nodes.append(matches[0])
    root, left, right = nodes
    if left == right or not all(node.startswith(root + "|") for node in (left, right)):
        raise ValueError("異なる左右の接地点をルート配下から選択してください")
    if not math.isfinite(height):
        raise ValueError("地面の高さには有限の数値を指定してください")
    if cmds.autoKeyframe(query=True, state=True) or any(
        not cmds.getAttr(root + ".t" + axis, settable=True) or cmds.connectionInfo(root + ".t" + axis, isDestination=True)
        for axis in "xyz"
    ):
        raise ValueError("自動キーを無効にし、移動にロックや入力のないガイドを選択してください")
    up = "xyz".index(cmds.upAxis(query=True, axis=True))
    delta = height - min(cmds.xform(node, query=True, translation=True, worldSpace=True)[up] for node in (left, right))
    movement = [0.0, 0.0, 0.0]
    movement[up] = delta
    cmds.move(*movement, root, worldSpace=True, relative=True)
    return delta


def show():
    """ルート・左・右の順に選択したガイドの地面の高さを指定する。"""
    selected = mlib.ls(selection=True, long=True, transforms=True).getNames(full=True)
    if len(selected) != 3:
        raise ValueError("ガイドのルート、左、右の接地点を順に選んでください")
    window = "mlrigGuideGround"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="ガイドの接地位置")
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label="\n".join(selected))
    field = cmds.floatFieldGrp(numberOfFields=1, label="地面の高さ")
    cmds.button(label="低い接地点を合わせる", command=lambda *_: align(*selected, cmds.floatFieldGrp(field, query=True, value1=True)))
    cmds.showWindow(window)
    return window
