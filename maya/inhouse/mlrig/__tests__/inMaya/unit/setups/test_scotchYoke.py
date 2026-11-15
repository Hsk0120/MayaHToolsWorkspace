"""ScotchYokeのヨークの往復・溝の中のブロック・速さと加速度を、試験側で独立に書いたピンの位置とDGの数値微分で確かめる。"""

import math
import random
import unittest

from maya import cmds

from mlrig.setups import ScotchYoke

RADIUS = 3.0


def _pin(degrees, radius=RADIUS):
    """試験側の独立な幾何。クランクの中心から +X に置いたピンを degrees 度回した位置 (x, y)。"""
    theta = math.radians(degrees)
    return radius * math.cos(theta), radius * math.sin(theta)


class ScotchYokeTest(unittest.TestCase):
    """作成時・ピンとの一致・Python版・速さと加速度・行程と戻りの区間・phase・軸と単位と向き・所有とUndo・引数を確認する。"""

    def setUp(self):
        """クランクを rotateZ = 30 度、ヨークを translateX = 5cm、子のブロックを translateY = 0.5cm に置いて生成する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.crank = cmds.createNode("joint", name="crank")
        cmds.setAttr(self.crank + ".rotateZ", 30.0)
        self.yoke = cmds.createNode("transform", name="yoke")
        cmds.setAttr(self.yoke + ".translateX", 5.0)
        self.block = cmds.createNode("transform", name="block", parent=self.yoke)
        cmds.setAttr(self.block + ".translateY", 0.5)
        self.setup = ScotchYoke.create(self.crank, self.yoke, self.block, RADIUS, name="yokeRig")
        self.owner = str(self.setup.container)

    def _turn(self, degrees):
        """生成時から degrees 度クランクを回し、(ヨークの移動(cm)、ブロックの移動(cm)) を返す。"""
        cmds.setAttr(self.crank + ".rotateZ", 30.0 + degrees)
        return (cmds.getAttr(self.yoke + ".translateX") - 5.0, cmds.getAttr(self.block + ".translateY") - 0.5)

    def test_rest(self):
        """生成時はヨークもブロックも跳ねず、移動・travel・速さが0、加速度は -r、行程は 2r。"""
        self.assertAlmostEqual(cmds.getAttr(self.yoke + ".translateX"), 5.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.block + ".translateY"), 0.5, places=6)
        for attribute in ("yokeOffset", "blockOffset", "velocity", "travel", "returnStroke"):
            with self.subTest(attribute=attribute):
                self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), 0.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".acceleration"), -RADIUS, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".stroke"), 2.0 * RADIUS, places=6)

    def test_pin_stays_in_the_slot(self):
        """正負・複数回転の角度で、ヨークの溝の位置がピンのxに、ブロックの位置がピンのyに一致する。"""
        for degrees in (-725.0, -400.0, -90.0, 0.0, 45.0, 90.0, 135.0, 180.0, 270.0, 359.0, 1000.0):
            with self.subTest(degrees=degrees):
                yoke, block = self._turn(degrees)
                x, y = _pin(degrees)
                self.assertAlmostEqual(yoke, x - RADIUS, places=5)
                self.assertAlmostEqual(block, y, places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".yokeOffset"), x - RADIUS, places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".blockOffset"), y, places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".travel"), (RADIUS - x) / (2.0 * RADIUS), places=5)

    def test_python_version_velocity_and_acceleration(self):
        """乱数の角度で Python 版と一致し、velocity・acceleration はDGのヨークの位置の1階・2階の数値微分と一致する。"""
        rng = random.Random(11)
        step = 0.5
        for _ in range(25):
            degrees = rng.uniform(-720.0, 720.0)
            with self.subTest(degrees=degrees):
                yoke, block = self._turn(degrees)
                result = ScotchYoke.motion(math.radians(degrees), RADIUS)
                self.assertAlmostEqual(yoke, result["yokeOffset"], places=5)
                self.assertAlmostEqual(block, result["blockOffset"], places=5)
                velocity = cmds.getAttr(self.owner + ".velocity")
                acceleration = cmds.getAttr(self.owner + ".acceleration")
                stroke = cmds.getAttr(self.owner + ".returnStroke")
                self.assertAlmostEqual(velocity, result["velocity"], places=5)
                self.assertAlmostEqual(acceleration, result["acceleration"], places=5)
                self.assertEqual(stroke, result["returnStroke"])
                ahead, behind = self._turn(degrees + step)[0], self._turn(degrees - step)[0]
                h = math.radians(step)
                self.assertAlmostEqual(velocity, (ahead - behind) / (2.0 * h), places=3)
                self.assertAlmostEqual(acceleration, (ahead - 2.0 * yoke + behind) / (h * h), places=2)
                if abs(velocity) > 1e-3:
                    # 戻り(生成時の +端 へ向かう)の間は位置が増える
                    self.assertEqual(stroke == 1.0, ahead > behind)

    def test_stroke_and_return_half(self):
        """1回転でヨークの行程はちょうど 2r、戻りの区間はクランクの半周、端は θ = 0・180 度。"""
        samples, count = [], 0
        for index in range(720):
            samples.append(self._turn(index * 0.5)[0])
            count += int(cmds.getAttr(self.owner + ".returnStroke"))
        self.assertAlmostEqual(max(samples) - min(samples), 2.0 * RADIUS, places=5)
        self.assertAlmostEqual(count * 0.5, 180.0, delta=1.0)
        self.assertAlmostEqual(self._turn(180.0)[0], -2.0 * RADIUS, places=5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".travel"), 1.0, places=6)

    def test_phase(self):
        """phase はクランクの角度に足される。"""
        cmds.setAttr(self.owner + ".phase", 40.0)
        yoke, block = self._turn(50.0)
        x, y = _pin(90.0)
        self.assertAlmostEqual(yoke, x - RADIUS, places=5)
        self.assertAlmostEqual(block, y, places=5)

    def test_axes_units_direction_and_no_block(self):
        """axis=x・yokeAxis=y・blockAxis=z・向き -1・UI単位 mm/rad・初期位置あり・ブロックなしでも一致し、外部に変換ノードを残さない。"""
        cmds.currentUnit(linear="mm", angle="rad")
        conversions = set(cmds.ls(type="unitConversion"))
        crank = cmds.createNode("transform", name="xCrank")
        yoke = cmds.createNode("transform", name="yYoke")
        cmds.setAttr(yoke + ".translateY", 20.0)  # mm
        block = cmds.createNode("transform", name="zBlock", parent=yoke)
        cmds.setAttr(block + ".translateZ", -10.0)  # mm
        setup = ScotchYoke.create(crank, yoke, block, 2.0, name="xYoke", axis="x", yokeAxis="y", blockAxis="z",
                                  yokeDirection=-1.0, blockDirection=-1.0)
        bare = ScotchYoke.create(crank, cmds.createNode("transform", name="bareYoke"), None, 2.0, name="bareYokeRig",
                                 axis="x")
        members = set(cmds.container(str(setup.container), query=True, nodeList=True) or [])
        members |= set(cmds.container(str(bare.container), query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        self.assertFalse(cmds.attributeQuery("blockTranslate", node=str(bare.container), exists=True))
        for degrees in (0.0, 30.0, 100.0, 200.0, 300.0, 500.0):
            with self.subTest(degrees=degrees):
                cmds.setAttr(crank + ".rotateX", math.radians(degrees))
                x, y = _pin(degrees, 2.0)
                self.assertAlmostEqual(cmds.getAttr(yoke + ".translateY"), 20.0 - (x - 2.0) * 10.0, places=3)
                self.assertAlmostEqual(cmds.getAttr(block + ".translateZ"), -10.0 - y * 10.0, places=3)
                self.assertAlmostEqual(cmds.getAttr("bareYoke.translateX"), (x - 2.0) * 10.0, places=3)
        cmds.currentUnit(linear="cm", angle="deg")

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("yokeRig_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.file(new=True, force=True)
        crank = cmds.createNode("transform", name="undoCrank")
        yoke = cmds.createNode("transform", name="undoYoke")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        ScotchYoke.create(crank, yoke, name="undoYokeRig")
        self.assertTrue(cmds.listConnections(yoke + ".translateX", source=True, destination=False))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoYokeRig"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoYokeRig.yokeTranslate"))

    def test_arguments(self):
        """軸・半径・向き・数値以外・transform以外・同じノード・接続済み・名前の重複を拒否し、何も残さない。"""
        other = cmds.createNode("multiplyDivide")
        free = cmds.createNode("transform", name="free")
        spare = cmds.createNode("transform", name="spare")
        before = set(cmds.ls())
        cases = (
            ((self.crank, free), {"axis": "w"}),
            ((self.crank, free), {"yokeAxis": "q"}),
            ((self.crank, free, spare), {"blockAxis": "q"}),
            ((self.crank, free, None, 0.0), {}),
            ((self.crank, free, None, -1.0), {}),
            ((self.crank, free, None, True), {}),
            ((self.crank, free, None, "2"), {}),
            ((self.crank, free), {"yokeDirection": 0.5}),
            ((self.crank, free), {"blockDirection": 2.0}),
            ((other, free), {}),
            ((self.crank, self.crank), {}),
            ((self.crank, free, free), {}),
            ((self.crank, self.yoke), {}),
            ((self.crank, free, self.block), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                ScotchYoke.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            ScotchYoke.create(self.crank, free, name="yokeRig")
        self.assertEqual(set(cmds.ls()), before)
        ScotchYoke.create(self.crank, self.yoke, self.block, name="unconnected", connect=False)
        self.assertTrue(cmds.objExists("unconnected.blockTranslate"))


if __name__ == "__main__":
    unittest.main()
