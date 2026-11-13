"""HipSwingの腰の振りと上体の安定化を、支点の枠とオイラー角から独立に組んだ行列で確かめる。"""

import math
import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import HipSwing

#: 行列の成分の許容(行列のノードは倍精度なので丸めの範囲)。
TOLERANCE = 1e-6


def _world(node):
    return om2.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _matrix(plug):
    return om2.MMatrix(cmds.getAttr(plug))


def _point(matrix):
    return om2.MVector(matrix[12], matrix[13], matrix[14])


def _quat(matrix):
    return om2.MTransformationMatrix(matrix).rotation(asQuaternion=True)


def _angle(a, b):
    """2つの行列の回転の差の角度(rad)。"""
    q = _quat(a).conjugate() * _quat(b)
    return 2.0 * math.acos(min(1.0, abs(q.w)))


class HipSwingTest(unittest.TestCase):
    """作成時の不変、独立な式との一致、割合、評価の方式、単位、所有・Undo・引数を確認する。"""

    def setUp(self):
        """COG の下の腰・背骨の根元・胸と、COG の下の振りのコントロールを作る。"""
        cmds.file(new=True, force=True)
        self.cog = cmds.createNode("transform", name="cog")
        cmds.setAttr(self.cog + ".translate", 3, 95, -2)
        cmds.setAttr(self.cog + ".rotate", 5, 25, -4)
        self.hips = cmds.ls(cmds.createNode("joint", name="hips", parent=self.cog), long=True)[0]
        cmds.setAttr(self.hips + ".translate", 0, -2, 0.5)
        cmds.setAttr(self.hips + ".jointOrient", 0, 0, 90)
        self.spine = cmds.ls(cmds.createNode("joint", name="spine", parent=self.hips), long=True)[0]
        cmds.setAttr(self.spine + ".translate", 8, 0, 0)
        cmds.setAttr(self.spine + ".rotate", 0, 0, -7)
        self.chest = cmds.ls(cmds.createNode("joint", name="chest", parent=self.spine), long=True)[0]
        cmds.setAttr(self.chest + ".translate", 20, 0, 0)
        self.control = cmds.ls(cmds.createNode("transform", name="swingCtrl", parent=self.cog), long=True)[0]
        offset = om2.MTransformationMatrix()
        offset.setTranslation(om2.MVector(0.5, 1.0, 0.2), om2.MSpace.kTransform)
        offset.setRotation(om2.MEulerRotation(0.1, -0.3, 0.2))
        cmds.setAttr(self.control + ".offsetParentMatrix", list(offset.asMatrix()), type="matrix")
        self.setup = HipSwing.create(self.hips, self.spine, self.control, name="hs")
        self.owner = str(self.setup.container)

    def _swing(self):
        """支点の枠 Q(translate・offsetParentMatrix・親)と rotate・rotateOrder から独立に組んだ S = Q^-1 · R · Q。"""
        move = om2.MTransformationMatrix()
        move.setTranslation(om2.MVector(*cmds.getAttr(self.control + ".translate")[0]), om2.MSpace.kTransform)
        frame = move.asMatrix() * om2.MMatrix(cmds.getAttr(self.control + ".offsetParentMatrix")) * _world(self.cog)
        angles = [math.radians(value) for value in cmds.getAttr(self.control + ".rotate")[0]]
        order = cmds.getAttr(self.control + ".rotateOrder")
        rotation = om2.MEulerRotation(angles[0], angles[1], angles[2], order).asMatrix()
        return frame.inverse() * rotation * frame, _point(frame)

    def _assertMatrix(self, actual, expected, msg=""):
        for index in range(16):
            self.assertAlmostEqual(actual[index], expected[index], delta=TOLERANCE, msg="{} [{}]".format(msg, index))

    def _check(self, msg=""):
        """出力を独立な式・Python版と比べる(swing=1・stabilize=1 のとき)。"""
        swing, pivot = self._swing()
        hips, spine = _world(self.hips), _world(self.spine)
        out = _matrix(self.owner + ".hipsMatrix")
        self._assertMatrix(out, hips * swing, msg + " hips")
        self._assertMatrix(_matrix(self.owner + ".swingMatrix"), swing, msg + " swing")
        # 支点は S で動かない。
        moved = om2.MPoint(pivot) * swing
        self.assertLess((om2.MVector(moved) - pivot).length(), TOLERANCE, msg)
        # 背骨の根元: 位置は B·S、向きは元の B のまま。
        result = _matrix(self.owner + ".spineMatrix")
        self.assertLess((_point(result) - _point(spine * swing)).length(), TOLERANCE, msg)
        self.assertLess(_angle(result, spine), TOLERANCE, msg)
        # 胸に spineOffset を掛けると、胸の向きは変わらず根元と同じだけ平行に動く。
        chest = _world(self.chest) * _matrix(self.owner + ".spineOffset")
        self.assertLess(_angle(chest, _world(self.chest)), TOLERANCE, msg)
        shift = _point(result) - _point(spine)
        self.assertLess((_point(chest) - _point(_world(self.chest)) - shift).length(), TOLERANCE, msg)
        # Python版。
        python = HipSwing.matrices(hips, spine, _world(self.control), _matrix(self.control + ".matrix"))
        self._assertMatrix(python["hips"], out, msg + " python hips")
        self._assertMatrix(python["spine"], result, msg + " python spine")
        self._assertMatrix(python["spineOffset"], _matrix(self.owner + ".spineOffset"), msg + " python offset")

    def test_rest_keeps_inputs(self):
        """rotate が0なら出力は入力と同じ(作成時に跳ねない)。既定の割合は1。"""
        self._assertMatrix(_matrix(self.owner + ".hipsMatrix"), _world(self.hips), "hips")
        self._assertMatrix(_matrix(self.owner + ".spineMatrix"), _world(self.spine), "spine")
        self._assertMatrix(_matrix(self.owner + ".spineOffset"), om2.MMatrix(), "offset")
        self.assertEqual(cmds.getAttr(self.owner + ".swing"), 1.0)
        self.assertEqual(cmds.getAttr(self.owner + ".stabilize"), 1.0)

    def test_random_swings_match_independent_formula(self):
        """乱数25通り(COG・コントロールの移動と回転の順序も変える)で独立な式・Python版と一致する。"""
        generator = random.Random(32)
        for index in range(25):
            cmds.setAttr(self.cog + ".translate", *[generator.uniform(-20, 20) for _ in range(3)])
            cmds.setAttr(self.cog + ".rotate", *[generator.uniform(-60, 60) for _ in range(3)])
            cmds.setAttr(self.hips + ".rotate", *[generator.uniform(-20, 20) for _ in range(3)])
            cmds.setAttr(self.control + ".translate", *[generator.uniform(-2, 2) for _ in range(3)])
            cmds.setAttr(self.control + ".rotateOrder", generator.randrange(6))
            cmds.setAttr(self.control + ".rotate", *[generator.uniform(-45, 45) for _ in range(3)])
            self._check("case {}".format(index))

    def test_weights(self):
        """swing=0.5 で振りの角度が半分、stabilize=0 で上体も腰と一緒に回り、0.5 で半分戻る。"""
        cmds.setAttr(self.control + ".rotate", 10, 30, -20)
        full, _ = self._swing()
        spine = _world(self.spine)
        whole = _angle(om2.MMatrix(), full)
        cmds.setAttr(self.owner + ".swing", 0.5)
        self.assertAlmostEqual(_angle(om2.MMatrix(), _matrix(self.owner + ".swingMatrix")), whole / 2, delta=1e-6)
        cmds.setAttr(self.owner + ".swing", 0.0)
        self._assertMatrix(_matrix(self.owner + ".hipsMatrix"), _world(self.hips), "swing 0")
        cmds.setAttr(self.owner + ".swing", 1.0)
        cmds.setAttr(self.owner + ".stabilize", 0.0)
        self._assertMatrix(_matrix(self.owner + ".spineMatrix"), spine * full, "stabilize 0")
        cmds.setAttr(self.owner + ".stabilize", 0.5)
        result = _matrix(self.owner + ".spineMatrix")
        self.assertAlmostEqual(_angle(spine, result), whole / 2, delta=1e-6)
        self.assertLess((_point(result) - _point(spine * full)).length(), TOLERANCE)
        python = HipSwing.matrices(_world(self.hips), spine, _world(self.control),
                                   _matrix(self.control + ".matrix"), swing=1.0, stabilize=0.5)
        self._assertMatrix(python["spine"], result, "python stabilize 0.5")

    def test_evaluation_modes(self):
        """off・serial・parallel の評価で同じ結果になる。"""
        original = cmds.evaluationManager(query=True, mode=True)[0]
        try:
            for mode, angle in (("off", 15.0), ("serial", -25.0), ("parallel", 35.0)):
                cmds.evaluationManager(mode=mode)
                cmds.setAttr(self.control + ".rotate", angle, -angle / 2, angle / 3)
                cmds.setAttr(self.cog + ".rotateY", angle)
                self._check(mode)
        finally:
            cmds.evaluationManager(mode=original)

    def test_ui_units(self):
        """UI単位 mm・rad で作っても自動の単位変換の係数は1で、式と一致する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="mm", angle="rad")
        try:
            cog = cmds.createNode("transform", name="cog")
            cmds.setAttr(cog + ".translate", 30, 950, -20)
            hips = cmds.ls(cmds.createNode("joint", name="hips", parent=cog), long=True)[0]
            spine = cmds.ls(cmds.createNode("joint", name="spine", parent=hips), long=True)[0]
            cmds.setAttr(spine + ".translate", 0, 80, 0)
            control = cmds.ls(cmds.createNode("transform", name="swingCtrl", parent=cog), long=True)[0]
            owner = str(HipSwing.create(hips, spine, control, name="hsUnits").container)
            cmds.setAttr(control + ".translate", 5, 60, 10)
            cmds.setAttr(control + ".rotate", 0.3, -0.2, 0.4)
            for conversion in cmds.ls(type="unitConversion"):
                self.assertEqual(cmds.getAttr(conversion + ".conversionFactor"), 1.0)
            expected = HipSwing.matrices(_world(hips), _world(spine), _world(control), _matrix(control + ".matrix"))
            self._assertMatrix(_matrix(owner + ".hipsMatrix"), expected["hips"], "mm hips")
            self._assertMatrix(_matrix(owner + ".spineMatrix"), expected["spine"], "mm spine")
            pivot = _point(_world(control))
            self.assertLess((om2.MVector(om2.MPoint(pivot) * _matrix(owner + ".swingMatrix")) - pivot).length(),
                            TOLERANCE)
        finally:
            cmds.currentUnit(linear="cm", angle="deg")

    def test_ownership_and_undo(self):
        """生成ノードはcontainerが所有し、入力へは接続しない。1回のUndoで消えRedoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        self.assertGreaterEqual(len(members), 9)
        for node in (self.hips, self.spine, self.control, self.chest):
            self.assertFalse(cmds.listConnections(node, source=True, destination=False, plugs=True,
                                                  skipConversionNodes=True), node)
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True, infinity=True)
        hips = cmds.createNode("joint", name="hips")
        spine = cmds.createNode("joint", name="spine", parent=hips)
        control = cmds.createNode("transform", name="swingCtrl")
        cmds.undoInfo(closeChunk=True)
        before = set(cmds.ls())
        HipSwing.create(hips, spine, control, name="hsUndo")
        self.assertTrue(cmds.objExists("hsUndo"))
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("hsUndo"))
        cmds.setAttr(control + ".rotateZ", 30)
        self.assertGreater(_angle(_world(hips), _matrix("hsUndo.hipsMatrix")), 0.5)

    def test_invalid_arguments(self):
        """不正な引数は ValueError で、何も作らない。"""
        before = set(cmds.ls())
        base = dict(hips=self.hips, spine=self.spine, control=self.control, name="bad")
        cases = [
            dict(base, hips="missing"),
            dict(base, spine=self.hips),
            dict(base, control=self.spine),
            dict(base, control="hs"),
            dict(base, swing=1.5),
            dict(base, swing=True),
            dict(base, stabilize=-0.1),
            dict(base, stabilize=float("nan")),
            dict(base, name="hs"),
        ]
        for case in cases:
            with self.assertRaises(ValueError, msg=str(case)):
                HipSwing.create(**case)
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main(argv=["hip_swing"], exit=False, verbosity=2)
