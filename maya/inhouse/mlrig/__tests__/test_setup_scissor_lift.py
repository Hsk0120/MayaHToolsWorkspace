"""ScissorLiftの腕・台・滑る足の行列を、支点の位置(腕の両端・交点)の幾何と独立計算で確かめる。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import ScissorLift

LENGTH = 8.0
STAGES = 3
#: 位置の許容(cm)。multiplyDivide・clamp は単精度で、腕が垂直に近いと w = sqrt(L^2 - h^2) の誤差が増える
#: (実測: h=7.9997 で 1.9e-6 cm)。倍精度で組む他のモジュールの 1e-9 ではなく、単精度の誤差の範囲で確かめる。
TOLERANCE = 1e-5


def _matrix(plug):
    return om2.MMatrix(cmds.getAttr(plug))


def _point(matrix, x=0.0, y=0.0):
    """行列のローカルの点 (x, y, 0) をワールドへ送る。"""
    return om2.MPoint(x, y, 0.0) * matrix


class ScissorLiftTest(unittest.TestCase):
    """支点の幾何・Python版・範囲の端・土台への追従・base無し・UI単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """回転・移動・一様でない縮尺の無い土台を作り、その上に3段のシザーリフトを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.base = cmds.createNode("transform", name="liftBase")
        cmds.setAttr(self.base + ".translate", 3, 1, -2)
        cmds.setAttr(self.base + ".rotate", 10, 40, -5)
        self.setup = ScissorLift.create(self.base, LENGTH, STAGES, name="lift")
        self.owner = str(self.setup.container)

    def _expected(self, height, length=LENGTH, stages=STAGES):
        """試験側の独立計算: 1段の高さ h と滑る側の距離 w(三平方)。"""
        stage = min(max(height / stages, 0.0), length)
        return stage, math.sqrt(max(length * length - stage * stage, 0.0))

    def _check(self, height, base=None, length=LENGTH, stages=STAGES):
        base = _matrix(self.base + ".worldMatrix[0]") if base is None else base
        stage, spread = self._expected(height, length, stages)
        local = lambda x, y: om2.MPoint(x, y, 0.0) * base
        for index in range(stages):
            arm_a = _matrix(self.owner + ".arm%dAMatrix" % index)
            arm_b = _matrix(self.owner + ".arm%dBMatrix" % index)
            pairs = (
                (_point(arm_a), local(0.0, index * stage)),
                (_point(arm_a, length), local(spread, (index + 1) * stage)),
                (_point(arm_b), local(0.0, (index + 1) * stage)),
                (_point(arm_b, length), local(spread, index * stage)),
                (_point(arm_a, length * 0.5), _point(arm_b, length * 0.5)),
            )
            for actual, expected in pairs:
                self.assertLess((actual - expected).length(), TOLERANCE, (height, index))
            # 腕のZは土台のZ(腕は土台のXY面の中で回る)。
            z_axis = om2.MVector(0, 0, 1) * base
            for arm in (arm_a, arm_b):
                self.assertLess((om2.MVector(0, 0, 1) * arm - z_axis).length(), 1e-9)
        for attribute, point in (("platform", (0.0, stages * stage)), ("baseSlider", (spread, 0.0)),
                                 ("topSlider", (spread, stages * stage))):
            matrix = _matrix(self.owner + "." + attribute + "Matrix")
            self.assertLess((_point(matrix) - local(*point)).length(), TOLERANCE, attribute)
            self.assertTrue(om2.MTransformationMatrix(matrix * base.inverse()).rotation().isEquivalent(
                om2.MEulerRotation(), 1e-9), attribute)

    def test_geometry(self):
        """高さを変えても、腕の両端が段の支点に乗り、2本の腕が中点で交わり、台・滑る足が支点の上にある。"""
        default = LENGTH * STAGES * 0.5
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".height"), default, places=9)
        for height in (default, 0.0, 1.0, 9.5, 17.3, LENGTH * STAGES - 1e-3):
            cmds.setAttr(self.owner + ".height", height)
            self._check(height)

    def test_evaluate_and_outputs(self):
        """containerの stageHeight・spread・angle がPython版と独立計算に一致する。"""
        for height in (0.0, 2.0, 12.0, 23.0, 30.0, 100.0):
            cmds.setAttr(self.owner + ".height", height)
            stage, spread, angle = ScissorLift.evaluate(height, LENGTH, STAGES)
            expected = self._expected(height)
            self.assertAlmostEqual(stage, expected[0], places=12)
            self.assertAlmostEqual(spread, expected[1], places=12)
            self.assertAlmostEqual(angle, math.degrees(math.asin(expected[0] / LENGTH)), places=9)
            self.assertAlmostEqual(cmds.getAttr(self.owner + ".stageHeight"), stage, delta=TOLERANCE)
            self.assertAlmostEqual(cmds.getAttr(self.owner + ".spread"), spread, delta=TOLERANCE)
            self.assertAlmostEqual(cmds.getAttr(self.owner + ".angle"), angle, delta=1e-4)  # 位置の許容 / L の角度(度)

    def test_limits(self):
        """高さが n*L を超えると腕は垂直(w=0)、0なら水平(w=L)で止まる。"""
        cmds.setAttr(self.owner + ".height", 1000.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".spread"), 0.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".angle"), 90.0, places=5)
        self._check(1000.0)
        cmds.setAttr(self.owner + ".height", 0.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".spread"), LENGTH, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".angle"), 0.0, places=6)
        self._check(0.0)

    def test_arm_length_and_base_follow(self):
        """腕の長さを書き換えても、土台を動かしても、支点の幾何を保つ。"""
        cmds.setAttr(self.owner + ".armLength", 6.0)
        cmds.setAttr(self.owner + ".height", 10.0)
        self._check(10.0, length=6.0)
        cmds.setAttr(self.base + ".translate", -4, 2, 7)
        cmds.setAttr(self.base + ".rotate", -30, 5, 60)
        self._check(10.0, length=6.0)

    def test_without_base_and_one_stage(self):
        """baseを省略するとワールド原点、1段でも同じ幾何になる。"""
        setup = ScissorLift.create(None, 5.0, 1, height=3.0, name="single")
        self.assertEqual(setup.getStages(), 1)
        self.assertEqual(self.setup.getStages(), STAGES)
        self.owner = str(setup.container)
        self._check(3.0, base=om2.MMatrix(), length=5.0, stages=1)
        self.assertAlmostEqual(cmds.getAttr("single.spread"), 4.0, places=9)

    def test_ui_units(self):
        """UI単位 mm/rad で作っても自動の単位変換が入らず、行列は内部単位(cm)で正しい。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="mm", angle="rad")
        try:
            before = set(cmds.ls(type="unitConversion"))
            self.base = cmds.createNode("transform", name="liftBase")
            setup = ScissorLift.create(self.base, LENGTH, STAGES, height=12.0, name="lift")
            self.owner = str(setup.container)
            self.assertEqual(set(cmds.ls(type="unitConversion")), before)
            cmds.currentUnit(linear="cm", angle="deg")
            self.assertAlmostEqual(cmds.getAttr(self.owner + ".height"), 12.0, places=9)
            self._check(12.0)
            cmds.setAttr(self.owner + ".height", 20.0)
            self._check(20.0)
        finally:
            cmds.currentUnit(linear="cm", angle="deg")

    def test_container_and_undo(self):
        """生成ノードはcontainerが所有し、作成はUndoで消えRedoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = set(cmds.ls("lift_*"))
        created = {node for node in created if cmds.nodeType(node) != "hyperLayout"}
        self.assertTrue(created)
        self.assertTrue(created <= members)
        cmds.file(new=True, force=True)
        base = cmds.createNode("transform", name="liftBase")
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        ScissorLift.create(base, LENGTH, 2, name="lift")
        self.assertTrue(cmds.objExists("lift"))
        cmds.undo()
        self.assertFalse(cmds.objExists("lift"))
        self.assertFalse(cmds.ls("lift_*"))
        cmds.redo()
        self.assertTrue(cmds.objExists("lift.arm1BMatrix"))

    def test_arguments(self):
        """段数・長さ・高さ・transform以外のbase・名前の重複を拒否する。"""
        cases = (
            {"stages": 0}, {"stages": 2.0}, {"stages": True}, {"armLength": 0.0}, {"armLength": float("nan")},
            {"height": -1.0}, {"height": float("inf")}, {"base": cmds.createNode("multiplyDivide")},
        )
        for kwargs in cases:
            arguments = {"base": self.base, "armLength": 4.0, "stages": 2}
            arguments.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ScissorLift.create(name="bad", **arguments)
        with self.assertRaises(ValueError):
            ScissorLift.create(self.base, name="lift")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
