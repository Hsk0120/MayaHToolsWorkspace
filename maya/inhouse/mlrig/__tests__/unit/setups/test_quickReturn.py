"""QuickReturnのレバーの振れ・溝の距離・ラム・速さの比を、試験側で独立に書いた幾何とDGの数値微分で確かめる。"""

import math
import random
import unittest

from maya import cmds

from mlrig.setups import QuickReturn

RADIUS, DISTANCE, HEIGHT = 2.0, 5.0, 8.0


def _pin(degrees, radius=RADIUS, distance=DISTANCE):
    """試験側の独立な幾何。クランクの中心 (0, d) のまわりで、真上から θ 回したピンをピボットから見た位置。"""
    theta = math.radians(degrees)
    # 式の上の位置(rotateZ では x の正の向きが -X 側にあたる)。
    return radius * math.sin(theta), distance + radius * math.cos(theta)


def _leverDegrees(degrees, radius=RADIUS, distance=DISTANCE):
    """ピボットからピンを通る直線の傾き(度)。"""
    x, y = _pin(degrees, radius, distance)
    return math.degrees(math.atan2(x, y))


class QuickReturnTest(unittest.TestCase):
    """作成時・幾何との一致・Python版・速さの比と戻りの区間・振れと時間比・phase/ramHeight・軸と単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """クランクを rotateZ = 30 度、レバーを rotateZ = 10 度、ラムを translateX = 4cm に置いて生成する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.crank = cmds.createNode("joint", name="crank")
        cmds.setAttr(self.crank + ".rotateZ", 30.0)
        self.lever = cmds.createNode("joint", name="lever")
        cmds.setAttr(self.lever + ".rotateZ", 10.0)
        self.ram = cmds.createNode("transform", name="ram")
        cmds.setAttr(self.ram + ".translateX", 4.0)
        self.setup = QuickReturn.create(self.crank, self.lever, self.ram, RADIUS, DISTANCE, HEIGHT,
                                        name="quickReturn")
        self.owner = str(self.setup.container)

    def _turn(self, degrees):
        """生成時から degrees 度クランクを回し、(レバーの振れ(度)、ラムの移動(cm)) を返す。"""
        cmds.setAttr(self.crank + ".rotateZ", 30.0 + degrees)
        return (cmds.getAttr(self.lever + ".rotateZ") - 10.0, cmds.getAttr(self.ram + ".translateX") - 4.0)

    def test_rest(self):
        """生成時はレバーもラムも跳ねず、振れ・ラムの移動が0、溝の距離は d + r、速さの比は r / (d + r)。"""
        self.assertAlmostEqual(cmds.getAttr(self.lever + ".rotateZ"), 10.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.ram + ".translateX"), 4.0, places=6)
        for attribute in ("leverAngle", "ramOffset", "returnStroke"):
            with self.subTest(attribute=attribute):
                self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), 0.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".slotDistance"), DISTANCE + RADIUS, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".speedRatio"), RADIUS / (DISTANCE + RADIUS), places=6)

    def test_geometry(self):
        """正負・複数回転の角度で、レバーの振れ・溝の距離・ラムの移動が試験側の幾何と一致する。"""
        for degrees in (-725.0, -400.0, -90.0, 0.0, 45.0, 90.0, 113.578, 180.0, 246.422, 270.0, 359.0, 1000.0):
            with self.subTest(degrees=degrees):
                lean, ram = self._turn(degrees)
                x, y = _pin(degrees)
                self.assertAlmostEqual(lean, _leverDegrees(degrees), places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".leverAngle"), _leverDegrees(degrees), places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".slotDistance"), math.hypot(x, y), places=5)
                # ラムの溝(高さ H の水平線)とレバーの直線の交点の横の位置
                self.assertAlmostEqual(ram, HEIGHT * x / y, places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".ramOffset"), HEIGHT * x / y, places=5)

    def test_swing_and_time_ratio(self):
        """振れの最大は ±asin(r/d) で、ピンの線がレバーと接する角度 90° + α で起き、時間比は (180 + 2α) / (180 - 2α)。"""
        half = math.degrees(math.asin(RADIUS / DISTANCE))
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".swingAngle"), half, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".timeRatio"), (180.0 + 2.0 * half) / (180.0 - 2.0 * half),
                               places=6)
        self.assertAlmostEqual(self._turn(90.0 + half)[0], half, places=5)
        self.assertAlmostEqual(self._turn(-90.0 - half)[0], -half, places=5)
        samples = [self._turn(step * 0.5)[0] for step in range(720)]
        self.assertAlmostEqual(max(samples), half, places=3)
        self.assertAlmostEqual(min(samples), -half, places=3)

    def test_python_version_and_speed(self):
        """乱数の角度で Python 版と一致し、speedRatio は DG の振れの数値微分、returnStroke はその負の区間と一致する。"""
        rng = random.Random(11)
        for _ in range(30):
            degrees = rng.uniform(-720.0, 720.0)
            with self.subTest(degrees=degrees):
                lean, ram = self._turn(degrees)
                result = QuickReturn.motion(math.radians(degrees), RADIUS, DISTANCE, HEIGHT)
                self.assertAlmostEqual(lean, math.degrees(result["leverAngle"]), places=5)
                self.assertAlmostEqual(ram, result["ramOffset"], places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".slotDistance"), result["slotDistance"], places=5)
                speed = cmds.getAttr(self.owner + ".speedRatio")
                self.assertAlmostEqual(speed, result["speedRatio"], places=6)
                step = 1e-2
                slope = (self._turn(degrees + step)[0] - self._turn(degrees - step)[0]) / (2.0 * step)
                self.assertAlmostEqual(speed, slope, places=4)
                self._turn(degrees)
                self.assertEqual(cmds.getAttr(self.owner + ".returnStroke"), result["returnStroke"])
        # 戻りの区間はクランクの角度 180° - 2α ぶん(1度刻みで数える)
        half = math.degrees(math.asin(RADIUS / DISTANCE))
        count = 0
        for degrees in range(360):
            self._turn(degrees + 0.5)
            count += int(cmds.getAttr(self.owner + ".returnStroke"))
        self.assertAlmostEqual(count, 180.0 - 2.0 * half, delta=1.0)
        # 戻りの中央(180度)で最も速く、比は -r / (d - r)
        self._turn(180.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".speedRatio"), -RADIUS / (DISTANCE - RADIUS), places=6)

    def test_phase_and_ram_height(self):
        """phase はクランクの角度に足され、ramHeight の変更はラムの移動に比例する。"""
        cmds.setAttr(self.owner + ".phase", 40.0)
        self.assertAlmostEqual(self._turn(50.0)[0], _leverDegrees(90.0), places=5)
        cmds.setAttr(self.owner + ".ramHeight", -3.0)
        x, y = _pin(90.0)
        self.assertAlmostEqual(self._turn(50.0)[1], -3.0 * x / y, places=5)

    def test_axes_units_and_no_ram(self):
        """axis=x・ramAxis=y・UI単位 mm/rad・ラムなしでも幾何と一致し、外部に変換ノードを残さない。"""
        cmds.currentUnit(linear="mm", angle="rad")
        conversions = set(cmds.ls(type="unitConversion"))
        crank = cmds.createNode("transform", name="xCrank")
        lever = cmds.createNode("transform", name="xLever")
        ram = cmds.createNode("transform", name="yRam")
        setup = QuickReturn.create(crank, lever, ram, 1.0, 3.0, 5.0, name="xQuickReturn", axis="x", ramAxis="y")
        bare = QuickReturn.create(crank, cmds.createNode("transform", name="bareLever"), None, 1.0, 3.0,
                                  name="bareQuickReturn", axis="x")
        members = set(cmds.container(str(setup.container), query=True, nodeList=True) or [])
        members |= set(cmds.container(str(bare.container), query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        self.assertFalse(cmds.attributeQuery("ramTranslate", node=str(bare.container), exists=True))
        for degrees in (30.0, 100.0, 200.0, 300.0):
            with self.subTest(degrees=degrees):
                cmds.setAttr(crank + ".rotateX", math.radians(degrees))
                x, y = _pin(degrees, 1.0, 3.0)
                self.assertAlmostEqual(math.degrees(cmds.getAttr(lever + ".rotateX")),
                                       _leverDegrees(degrees, 1.0, 3.0), places=4)
                self.assertAlmostEqual(math.degrees(cmds.getAttr("bareLever.rotateX")),
                                       _leverDegrees(degrees, 1.0, 3.0), places=4)
                self.assertAlmostEqual(cmds.getAttr(ram + ".translateY"), 5.0 * x / y * 10.0, places=3)  # mm
                self.assertAlmostEqual(cmds.getAttr(str(setup.container) + ".slotDistance"),
                                       math.hypot(x, y) * 10.0, places=3)
        cmds.currentUnit(linear="cm", angle="deg")

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("quickReturn_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.file(new=True, force=True)
        crank = cmds.createNode("transform", name="undoCrank")
        lever = cmds.createNode("transform", name="undoLever")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        QuickReturn.create(crank, lever, name="undoQuickReturn")
        self.assertTrue(cmds.listConnections(lever + ".rotateZ", source=True, destination=False))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoQuickReturn"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoQuickReturn.rotate"))

    def test_arguments(self):
        """軸・半径・距離・数値以外・transform以外・同じノード・接続済み・名前の重複を拒否し、何も残さない。"""
        other = cmds.createNode("multiplyDivide")
        free = cmds.createNode("transform", name="free")
        spare = cmds.createNode("transform", name="spare")
        before = set(cmds.ls())
        cases = (
            ((self.crank, free), {"axis": "w"}),
            ((self.crank, free, spare), {"ramAxis": "q"}),
            ((self.crank, free, None, 0.0), {}),
            ((self.crank, free, None, 2.0, 2.0), {}),
            ((self.crank, free, None, 3.0, 2.0), {}),
            ((self.crank, free, None, True), {}),
            ((self.crank, free, None, 1.0, "5"), {}),
            ((other, free), {}),
            ((self.crank, self.crank), {}),
            ((self.crank, free, free), {}),
            ((self.crank, self.lever), {}),
            ((self.crank, free, self.ram), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                QuickReturn.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            QuickReturn.create(self.crank, free, name="quickReturn")
        self.assertEqual(set(cmds.ls()), before)
        QuickReturn.create(self.crank, self.lever, self.ram, name="unconnected", connect=False)
        self.assertTrue(cmds.objExists("unconnected.ramTranslate"))


if __name__ == "__main__":
    unittest.main()
