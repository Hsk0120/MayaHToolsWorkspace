"""同じガイドを使い、標準IKソルバーで末端・長さ・姿勢を比較する。"""

import math

from maya import cmds, mel
from maya.api import OpenMaya as om2
from mlib.decorator import undoTransaction


_SOLVERS = {"単一チェーン": "ikSCsolver", "スプリング": "ikSpringSolver", "2ボーン": "ikRPsolver", "スプライン": "ikSplineSolver"}


def _points(guides):
    if len(guides) < 3 or any(not cmds.objectType(n, isAType="transform") for n in guides):
        raise ValueError("根元から末端に向かって3点以上のガイドを選択してください")
    points = [cmds.xform(n, query=True, worldSpace=True, translation=True) for n in guides]
    if any(math.dist(a, b) < 1e-7 for a, b in zip(points, points[1:])):
        raise ValueError("隣り合うガイドの位置が重複しています")
    return points


def _chain(points, solver, target, twist):
    group = cmds.createNode("transform", name="ikComparison#")
    cmds.select(group)
    joints = [cmds.joint(position=p, name="ikComparisonBone#") for p in points]
    cmds.joint(joints[0], edit=True, orientJoint="xyz", secondaryAxisOrient="yup", children=True, zeroScaleOrient=True)
    if solver == "ikSpringSolver":
        mel.eval("ikSpringSolver")
    args = {}
    curve = None
    if solver == "ikSplineSolver":
        curve = cmds.curve(degree=1, point=points)
        curve = cmds.parent(curve, group)[0]
        args.update(curve=curve, createCurve=False, parentCurve=False)
    handle = cmds.ikHandle(startJoint=joints[0], endEffector=joints[-1], solver=solver, **args)[0]
    handle = cmds.parent(handle, group)[0]
    if curve:
        cmds.xform("{}.cv[{}]".format(curve, len(points) - 1), worldSpace=True, translation=target)
    else:
        cmds.xform(handle, worldSpace=True, translation=target)
    cmds.setAttr(handle + ".twist", twist)
    return group, joints


@undoTransaction("mlrigCompareIK")
def compare(guides, delta, twist=0, keep=None):
    """同じ末端目標とねじりを各鎖に適用し、先頭の解から切り替えた場合の差を返す。"""
    points = _points(guides)
    if keep is not None and keep not in _SOLVERS:
        raise ValueError("作成するIK方式を選択してください")
    target = [v + d for v, d in zip(points[-1], delta)]
    if len(target) != 3 or not all(math.isfinite(v) for v in target + [twist]):
        raise ValueError("有限の移動量3成分とねじり角を指定してください")
    saved = cmds.ls(selection=True, long=True) or []
    reference = None
    rows = {}
    for label, solver in _SOLVERS.items():
        if keep and label != keep:
            continue
        if solver == "ikRPsolver" and len(points) != 3:
            if keep:
                raise ValueError("2ボーンには3点を指定してください")
            continue
        group, joints = _chain(points, solver, target, twist)
        solved = [cmds.xform(n, query=True, worldSpace=True, translation=True) for n in joints]
        quats = [
            om2.MTransformationMatrix(om2.MMatrix(cmds.xform(n, query=True, worldSpace=True, matrix=True))).rotation(asQuaternion=True)
            for n in joints
        ]
        if reference is None:
            reference = solved, quats
        steps = [abs(math.dist(a, b) - math.dist(c, d)) for a, b, c, d in zip(solved, solved[1:], points, points[1:])]
        angles = [
            math.degrees(2 * math.acos(min(1.0, abs(a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w)))) for a, b in zip(quats, reference[1])
        ]
        rows[label] = dict(
            endError=math.dist(solved[-1], target),
            lengthError=max(steps),
            switchDistance=max(math.dist(a, b) for a, b in zip(solved, reference[0])),
            switchDegrees=max(angles),
        )
        if keep:
            cmds.select(group)
            return group
        cmds.delete(group)
    if saved:
        cmds.select(saved, replace=True)
    else:
        cmds.select(clear=True)
    return rows


def show():
    """選択ガイドの試験条件を入力して結果を表示し、選んだ方式の鎖を作成する。"""
    guides = cmds.ls(selection=True, long=True) or []
    _points(guides)
    window = "mlrigIKComparison"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="IKの作成・差し替え診断")
    cmds.columnLayout(adjustableColumn=True)
    move = cmds.floatFieldGrp(numberOfFields=3, label="末端の移動量")
    angle = cmds.floatFieldGrp(label="ねじり（シーン角度単位）")
    menu = cmds.optionMenu(label="作成する方式")
    for name in _SOLVERS:
        cmds.menuItem(label=name, parent=menu)
    report = cmds.scrollField(editable=False, height=140)

    def run(keep=None):
        delta = cmds.floatFieldGrp(move, query=True, value=True)
        result = compare(guides, delta, cmds.floatFieldGrp(angle, query=True, value1=True), keep)
        if not keep:
            rows = ["方式 / 末端誤差 / 骨長の最大差 / 切替位置差 / 切替角度(度)"]
            for name, v in result.items():
                rows.append("{}  {:.5g}  {:.5g}  {:.5g}  {:.5g}".format(name, *v.values()))
            cmds.scrollField(report, edit=True, text="\n".join(rows))

    cmds.button(label="同じ目標で比較", command=lambda *_: run())
    cmds.button(label="選択方式の鎖を作成", command=lambda *_: run(cmds.optionMenu(menu, query=True, value=True)))
    cmds.showWindow(window)
    return window
