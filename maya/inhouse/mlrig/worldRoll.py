"""ワールド上方向を基準に、チェーンの向きに沿ったロールとローカルツイストを比較する。"""

import math

import mlib
from maya import cmds
from mlib import getNode
from mlib.maths import Transformation, Vector


def measure(node, reverse=False):
    """ローカル±Xを長手、+Yを上としてワールドロールと親空間のXツイストを度で返す。"""
    sign = -1 if reverse else 1
    transform = getNode(node)
    world = transform.getMatrix(ws=True)
    forward = world.transformVector((sign, 0, 0))
    if forward.length() < 1e-9:
        raise ValueError("長手方向の長さが不足しています")
    forward.normalize()
    up = world.transformVector((0, 1, 0))
    scene_up = Vector(0, 1, 0) if cmds.upAxis(query=True, axis=True) == "y" else Vector(0, 0, 1)
    baseline = scene_up - forward * (scene_up * forward)
    guide_up = up - forward * (up * forward)
    if min(baseline.length(), guide_up.length()) < 1e-9:
        raise ValueError("上方向と長手方向が平行なためロールを決定できません")
    baseline.normalize()
    guide_up.normalize()
    roll = math.degrees(math.atan2(forward * (baseline ^ guide_up), baseline * guide_up))
    local = transform.getPlug("matrix").get() * transform.getPlug("offsetParentMatrix").get()
    quat = Transformation(local).quaternion
    if math.hypot(quat.w, quat.x) < 1e-9:
        raise ValueError("このローカル回転ではXツイストを決定できません")
    twist = (math.degrees(2 * math.atan2(sign * quat.x, quat.w)) + 180) % 360 - 180
    return roll, twist


def show():
    """選択した各ガイドの角度を、指定した軸方向で読み取る。"""
    window = "mlrigWorldRoll"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="チェーンのワールドロール")
    cmds.columnLayout(adjustableColumn=True)
    reverse = cmds.checkBox(label="長手方向を−Xにする")
    output = cmds.scrollField(editable=False, height=130)

    def refresh(*_):
        rows = []
        for node in mlib.ls(selection=True, long=True, transforms=True).getNames(full=True):
            try:
                roll, twist = measure(node, cmds.checkBox(reverse, query=True, value=True))
                rows.append("{}  ワールド {:.4f}°  ローカル {:.4f}°".format(node, roll, twist))
            except ValueError as exc:
                rows.append("{}  {}".format(node, exc))
        cmds.scrollField(output, edit=True, text="\n".join(rows))

    cmds.checkBox(reverse, edit=True, changeCommand=refresh)
    cmds.button(label="現在の選択で計測", command=refresh)
    refresh()
    cmds.showWindow(window)
    return window
