"""GearTrainの歯車の回転を、歯数の比から独立に求めた値と、かみ合う歯の送り量(歯数×角度)で確かめる。"""

import math
import unittest

from maya import cmds

from mlrig.setups import GearTrain

TEETH = (32, 16, 16, 8, 20)
LINKS = ("mesh", "shaft", "mesh", "mesh")


def _ratios(teeth, links):
    """駆動側に対する各歯車の比(試験側の独立計算。歯車ごとに前との関係を積み上げる)。"""
    values, current = [], 1.0
    for index, link in enumerate(links, 1):
        current = current * (-teeth[index - 1] / teeth[index] if link == "mesh" else 1.0)
        values.append(current)
    return values


class GearTrainTest(unittest.TestCase):
    """比・作成時に跳ねない・送り量・歯数/phaseの変更・軸と接続しない場合・UI単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """駆動側と4つの歯車(2つ目は1つ目と同じ軸)を、それぞれ初期の回転を持たせて作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.driver = cmds.createNode("transform", name="driverGear")
        cmds.setAttr(self.driver + ".rotateZ", 12)
        self.gears = []
        for index in range(4):
            gear = cmds.createNode("transform", name="gear{}".format(index + 1))
            cmds.setAttr(gear + ".rotateZ", 5 * index - 3)
            self.gears.append(gear)
        self.rest = [cmds.getAttr(gear + ".rotateZ") for gear in self.gears]
        self.setup = GearTrain.create(self.driver, self.gears, TEETH, name="train", links=LINKS)
        self.owner = str(self.setup.container)

    def _assertRotations(self, delta, teeth=TEETH, phases=(0, 0, 0, 0), tolerance=1e-4):
        for index, (gear, ratio) in enumerate(zip(self.gears, _ratios(teeth, LINKS))):
            expected = ratio * delta + self.rest[index] + phases[index]
            self.assertAlmostEqual(cmds.getAttr(gear + ".rotateZ"), expected, delta=tolerance, msg=gear)
            self.assertAlmostEqual(cmds.getAttr("{}.ratio{}".format(self.owner, index + 1)), ratio, delta=1e-6)

    def test_rest(self):
        """作成直後は各歯車の回転が作成前のまま(跳ねない)。"""
        self._assertRotations(0.0)

    def test_driver_rotation(self):
        """駆動側を回すと、比どおりに回り、かみ合う歯車は逆向き、同じ軸の歯車は同じ角度で回る。"""
        for angle in (90.0, -45.0, 400.0, 12.5):
            with self.subTest(angle=angle):
                cmds.setAttr(self.driver + ".rotateZ", 12 + angle)
                self._assertRotations(angle)
        self.assertEqual(GearTrain.ratios(TEETH, LINKS), _ratios(TEETH, LINKS))

    def test_teeth_travel(self):
        """かみ合う2つの歯車は、送った歯の数(歯数×回転)が同じで向きが逆になる。"""
        cmds.setAttr(self.driver + ".rotateZ", 12 + 75)
        angles = [75.0] + [cmds.getAttr(gear + ".rotateZ") - rest for gear, rest in zip(self.gears, self.rest)]
        for index, link in enumerate(LINKS, 1):
            with self.subTest(gear=index):
                if link == "mesh":
                    self.assertAlmostEqual(TEETH[index - 1] * angles[index - 1], -TEETH[index] * angles[index],
                                           delta=1e-3)
                else:
                    self.assertAlmostEqual(angles[index - 1], angles[index], delta=1e-4)

    def test_teeth_and_phase(self):
        """歯数を変えると比がすぐに変わり、phaseで角度を足せる。"""
        cmds.setAttr(self.owner + ".teeth0", 24)
        cmds.setAttr(self.owner + ".teeth4", 12)
        cmds.setAttr(self.owner + ".phase3", 7.5)
        cmds.setAttr(self.driver + ".rotateZ", 12 + 60)
        teeth = (24, 16, 16, 8, 12)
        self._assertRotations(60.0, teeth=teeth, phases=(0, 0, 7.5, 0))

    def test_axis_and_without_connect(self):
        """axis=xと先頭がshaftのつながりを使え、connect=Falseなら出力だけを持ち歯車は接続しない。"""
        cmds.file(new=True, force=True)
        driver = cmds.createNode("transform", name="crank")
        gear = cmds.createNode("transform", name="pulley")
        cmds.setAttr(gear + ".rotateX", 30)
        setup = GearTrain.create(driver, [gear], (10, 40), name="crankTrain", axis="x", links=["shaft"],
                                 connect=False)
        owner = str(setup.container)
        self.assertIsNone(cmds.listConnections(gear + ".rotateX", source=True, destination=False))
        cmds.setAttr(driver + ".rotateX", 50)
        self.assertAlmostEqual(cmds.getAttr(owner + ".ratio1"), 1.0, delta=1e-9)
        self.assertAlmostEqual(cmds.getAttr(owner + ".rotate1"), 80.0, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(gear + ".rotateX"), 30.0, delta=1e-9)

    def test_ui_units(self):
        """UI単位がラジアンでも、角度のまま比が掛かる(単位変換の係数が入らない)。"""
        cmds.currentUnit(angle="rad")
        cmds.setAttr(self.driver + ".rotateZ", math.radians(12 + 30))
        cmds.currentUnit(angle="deg")
        self._assertRotations(30.0)
        self.assertEqual(cmds.ls(type="unitConversion"), [])

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消えて接続も戻り、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.gears[-1] + ".rotateZ") or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        driver = cmds.createNode("transform", name="undoDriver")
        gear = cmds.createNode("transform", name="undoGear")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        GearTrain.create(driver, [gear], (10, 20), name="undoTrain")
        self.assertTrue(cmds.objExists("undoTrain"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoTrain"))
        self.assertEqual(set(cmds.ls()), before)
        self.assertIsNone(cmds.listConnections(gear + ".rotateZ", source=True, destination=False))
        cmds.redo()
        self.assertTrue(cmds.objExists("undoTrain.rotate1"))

    def test_arguments(self):
        """軸・歯数の個数と値・つながり方・歯車無し・transform以外・重複・接続済み・名前の重複を拒否する。"""
        gears = self.gears[:2]
        cases = (
            ((self.driver, gears, (10, 20, 30)), {"axis": "w"}),
            ((self.driver, gears, (10, 20)), {}),
            ((self.driver, gears, (10, 0, 30)), {}),
            ((self.driver, gears, (10, 20, float("nan"))), {}),
            ((self.driver, gears, (10, 20, 30)), {"links": ["mesh", "belt"]}),
            ((self.driver, gears, (10, 20, 30)), {"links": ["mesh"]}),
            ((self.driver, [], (10,)), {}),
            ((self.driver, [self.driver], (10, 20)), {}),
            ((cmds.createNode("multiplyDivide"), gears, (10, 20, 30)), {}),
            ((self.driver, gears, (10, 20, 30)), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                GearTrain.create(*args, name="bad", **kwargs)
        free = cmds.createNode("transform", name="freeGear")
        with self.assertRaises(ValueError):
            GearTrain.create(self.driver, [free], (10, 20), name="train")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
