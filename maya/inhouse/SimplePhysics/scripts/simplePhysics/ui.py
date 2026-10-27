"""Kawaii Physicsのカテゴリ構成を参考にしたMaya標準UI。"""

import json

from maya import cmds

from . import api
from .solver import PARAMETERS


WINDOW = "SimplePhysicsWindow"
_instance = None
LABELS = {
    "damping": "Damping", "stiffness": "Stiffness", "worldDampingLocation": "World Damping Location",
    "worldDampingRotation": "World Damping Rotation", "radius": "Radius (cm)", "limitAngle": "Limit Angle (deg)",
    "blend": "Alpha / Blend", "targetFramerate": "Target Framerate", "teleportDistance": "Teleport Distance (cm)",
    "iterationsBefore": "Iterations Before Collision", "iterationsAfter": "Iterations After Collision",
    "collisionIterations": "Collision Iterations", "warmupSteps": "Warmup Steps", "maxSteps": "Max Steps",
    "startFrame": "Start Frame", "planarConstraint": "Planar Constraint", "gravity": "Gravity (cm/s2)",
    "wind": "Wind Velocity (cm/s)", "residualPenetration": "Residual Penetration (cm)",
}


class PhysicsWindow:
    """設定をシーンのSolverアトリビュートへ直接接続する画面。"""

    def __init__(self):
        """選択・接続・操作のUI状態を作る。"""
        self.node = None
        self.fields = {}
        if cmds.window(WINDOW, exists=True):
            cmds.deleteUI(WINDOW)
        self.window = cmds.window(WINDOW, title="Simple Physics", widthHeight=(500, 820), sizeable=True)
        cmds.scrollLayout(childResizable=True)
        self.main = cmds.columnLayout(adjustableColumn=True, rowSpacing=7)
        cmds.text(label="Simple Physics  |  Bone Dynamics", height=35, font="boldLabelFont")
        cmds.text(label="入力アニメーションを残して、揺れた出力ジョイントを作成します。", align="left")
        cmds.frameLayout(label="1  Bones / Setup", collapsable=True, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        self.roots = cmds.textFieldButtonGrp(label="Root Bones", buttonLabel="選択から", buttonCommand=lambda *_: self._selection_to(self.roots))
        self.excluded = cmds.textFieldButtonGrp(label="Exclude Bones", buttonLabel="選択から", buttonCommand=lambda *_: self._selection_to(self.excluded))
        self.dummy = cmds.floatFieldGrp(label="Dummy Bone Length (cm)", value1=0, numberOfFields=1)
        self.axis = cmds.optionMenuGrp(label="Bone Forward Axis")
        for axis in ("X", "Y", "Z", "-X", "-Y", "-Z"):
            cmds.menuItem(label=axis)
        cmds.button(label="Create Simple Physics", height=32, command=lambda *_: self._run(self._create))
        cmds.text(label="Root/Exclude/Dummyは作成時の設定。変更時は新規作成してください。", align="left")
        cmds.setParent(self.main)
        cmds.separator(height=8)
        self.selector = cmds.optionMenuGrp(label="Solver", changeCommand=lambda value: self._run(lambda: self._edit(value)))
        cmds.button(label="Refresh / 選択したSolverを編集", command=lambda *_: self._refresh())
        self.editor = cmds.columnLayout(adjustableColumn=True)
        cmds.setParent(self.main)
        cmds.showWindow(self.window)
        self._refresh()

    def _run(self, callback):
        """UI入口の失敗を明示し、シーン変更はAPI側のUndo処理に任せる。"""
        try:
            return callback()
        except (ValueError, TypeError, RuntimeError, OSError) as error:
            cmds.confirmDialog(title="Simple Physics", message=str(error), button=["OK"], icon="warning")
            return None

    def _selection_to(self, field):
        """選択ジョイントをセミコロン区切りで入力欄へ反映する。"""
        selected = cmds.ls(selection=True, long=True, type="joint") or []
        cmds.textFieldButtonGrp(field, edit=True, text="; ".join(selected))

    def _create(self):
        """Bones欄の値からセットアップを作成する。"""
        roots = [name.strip() for name in cmds.textFieldButtonGrp(self.roots, query=True, text=True).split(";") if name.strip()]
        excluded = [name.strip() for name in cmds.textFieldButtonGrp(self.excluded, query=True, text=True).split(";") if name.strip()]
        self.node = api.create(roots, excluded, cmds.floatFieldGrp(self.dummy, query=True, value1=True), cmds.optionMenuGrp(self.axis, query=True, value=True))
        self._refresh()

    def _refresh(self):
        """存在するSolverを再列挙し、選択対象があれば優先して表示する。"""
        nodes = cmds.ls(type="simplePhysicsSolver") if "simplePhysicsSolver" in cmds.allNodeTypes() else []
        selected = [name for name in cmds.ls(selection=True) or [] if name in nodes]
        self.node = selected[0] if selected else self.node if self.node in nodes else nodes[0] if nodes else None
        items = cmds.optionMenuGrp(self.selector, query=True, itemListLong=True) or []
        for item in items:
            cmds.deleteUI(item)
        for node in nodes:
            cmds.menuItem(label=node, parent=self.selector + "|OptionMenu")
        if self.node:
            cmds.optionMenuGrp(self.selector, edit=True, value=self.node)
        self._edit(self.node)

    def _section(self, label, collapsed=False):
        """設定カテゴリを作り、その子の列を編集先にする。"""
        cmds.setParent(self.editor)
        cmds.frameLayout(label=label, collapsable=True, collapse=collapsed, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)

    def _attributes(self, names):
        """Maya標準のアトリビュート編集コントロールを配置する。"""
        for name in names:
            cmds.attrControlGrp(attribute=f"{self.node}.{name}", label=LABELS[name])

    def _edit(self, node):
        """Solverごとの設定、カーブ、コライダー一覧を作り直す。"""
        self.node = node
        for child in cmds.columnLayout(self.editor, query=True, childArray=True) or []:
            cmds.deleteUI(child)
        if not node or not cmds.objExists(node):
            return
        self._section("2  Physics Settings")
        self._attributes(("blend",) + PARAMETERS)
        cmds.text(label="Limit Angle = 0 は無制限。Radiusはボーン位置の接触半径。", align="left")
        self._section("3  Physics Settings Curves", True)
        cmds.text(label="横軸: 根元0 → 先端1 / 縦軸: 各設定値への倍率", align="left")
        for name in PARAMETERS:
            cmds.text(label=LABELS[name], align="left", font="boldLabelFont")
            cmds.gradientControl(attribute=f"{node}.{name}Curve", height=95)
        self._section("4  Forces / Simulation", True)
        self._attributes(("gravity", "wind", "planarConstraint", "startFrame", "targetFramerate", "warmupSteps", "teleportDistance", "maxSteps"))
        cmds.button(label="開始時刻を現在にしてリセット", command=lambda *_: self._run(self._reset))
        self._section("5  Collision Limits")
        self.attach = cmds.checkBox(label="選択した入力ジョイントに追従させる", value=True)
        cmds.rowLayout(numberOfColumns=3, adjustableColumn=3)
        for kind in ("sphere", "capsule", "plane"):
            cmds.button(label="Add " + kind.title(), command=lambda *_, value=kind: self._run(lambda: self._collider(value)))
        cmds.setParent("..")
        self.collider_list = cmds.textScrollList(height=80, selectCommand=self._select_collider)
        for collider in api.connections(node, "colliderObjects"):
            cmds.textScrollList(self.collider_list, edit=True, append=collider)
        cmds.button(label="選択したコライダーを削除", command=lambda *_: self._run(self._remove_collider))
        cmds.text(label="ガイドを移動・回転し、Channel BoxのphysicsRadius/Heightを調整。", align="left")
        self._attributes(("collisionIterations", "residualPenetration"))
        cmds.text(label="Residual > 0 は残留貫通。固定点・角度制限・衝突の両立を確認。", align="left")
        self._section("6  Bone Constraints", True)
        self._attributes(("iterationsBefore", "iterationsAfter"))
        self.compliance = cmds.floatFieldGrp(label="Compliance", value1=0.0001, precision=6)
        cmds.button(label="選択した出力ボーン2本を距離拘束", command=lambda *_: self._run(self._constraint))
        self.constraint_list = cmds.textScrollList(height=80)
        outputs = api.connections(node, "outputBones")
        for first, second, length, compliance in json.loads(cmds.getAttr(node + ".boneConstraints")):
            cmds.textScrollList(self.constraint_list, edit=True, append=f"{outputs[first]}  <>  {outputs[second]}  ({length:.2f}cm / {compliance:g})")
        cmds.button(label="選択した距離拘束を削除", command=lambda *_: self._run(self._remove_constraint))
        self._section("7  Preset / Bake")
        cmds.text(label="プリセットは係数・カーブを保存。骨とコライダーの接続はシーン保存。", align="left")
        cmds.rowLayout(numberOfColumns=2, adjustableColumn=2)
        cmds.button(label="Save Preset", command=lambda *_: self._run(lambda: self._preset(False)))
        cmds.button(label="Load Preset", command=lambda *_: self._run(lambda: self._preset(True)))
        cmds.setParent("..")
        self.range = cmds.intFieldGrp(label="Bake Start / End", numberOfFields=2,
                                      value1=int(cmds.playbackOptions(query=True, minTime=True)), value2=int(cmds.playbackOptions(query=True, maxTime=True)))
        cmds.button(label="Bake to New Joints", height=32, command=lambda *_: self._run(self._bake))
        cmds.button(label="このセットアップを削除（元の骨・ベイク結果は保持）", command=lambda *_: self._run(self._remove))

    def _reset(self):
        """現在時刻をシミュレーションの開始時刻にする。"""
        cmds.setAttr(self.node + ".startFrame", cmds.currentTime(query=True))

    def _collider(self, kind):
        """指定形状のガイドを作り、画面を再表示する。"""
        selected = cmds.ls(selection=True, long=True, type="joint") or []
        target = selected[0] if selected and cmds.checkBox(self.attach, query=True, value=True) else None
        api.addCollider(self.node, kind, target)
        self._edit(self.node)

    def _select_collider(self):
        """一覧からガイドを選択し、移動ツール等で編集できるようにする。"""
        selected = cmds.textScrollList(self.collider_list, query=True, selectItem=True) or []
        if selected:
            cmds.select(selected)

    def _remove_collider(self):
        """選択されたガイドだけを取り除く。"""
        selected = cmds.textScrollList(self.collider_list, query=True, selectItem=True) or []
        if selected:
            api.removeCollider(self.node, selected[0])
            self._edit(self.node)

    def _constraint(self):
        """出力ジョイント2本から距離拘束を作る。"""
        selected = cmds.ls(selection=True, long=True, type="joint") or []
        if len(selected) != 2:
            raise ValueError("出力ジョイントを2本選択してください")
        api.addConstraint(self.node, *selected, compliance=cmds.floatFieldGrp(self.compliance, query=True, value1=True))
        self._edit(self.node)

    def _remove_constraint(self):
        """一覧で選択した距離拘束を削除する。"""
        indices = cmds.textScrollList(self.constraint_list, query=True, selectIndexedItem=True) or []
        if indices:
            values = json.loads(cmds.getAttr(self.node + ".boneConstraints"))
            del values[indices[0] - 1]
            cmds.setAttr(self.node + ".boneConstraints", json.dumps(values), type="string")
            self._edit(self.node)

    def _preset(self, reading):
        """ユーザーが指定したファイルへ係数プリセットを読み書きする。"""
        paths = cmds.fileDialog2(fileMode=1 if reading else 0, fileFilter="Simple Physics (*.json)", caption="Simple Physics Preset")
        if paths:
            if reading:
                api.loadPreset(self.node, paths[0])
                self._edit(self.node)
            else:
                api.savePreset(self.node, paths[0])

    def _bake(self):
        """指定整数フレーム範囲を別階層へベイクする。"""
        api.bake(self.node, cmds.intFieldGrp(self.range, query=True, value1=True), cmds.intFieldGrp(self.range, query=True, value2=True))

    def _remove(self):
        """選択Solverの所有物を取り除いて一覧を更新する。"""
        api.remove(self.node)
        self.node = None
        self._refresh()


def show():
    """Simple Physicsの設定画面を表示して所有インスタンスを保持する。"""
    global _instance
    _instance = PhysicsWindow()
    return _instance
