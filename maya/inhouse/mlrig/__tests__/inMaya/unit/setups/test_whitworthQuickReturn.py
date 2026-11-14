"""WhitworthQuickReturnのレバーの回転・溝の距離・連接棒で押すラム・速さの比を、試験側で独立に書いた幾何とDGの数値微分で確かめる。"""

import math
import random
import unittest

from maya import cmds

from mlrig.setups import WhitworthQuickReturn

RADIUS, DISTANCE, ARM, ROD = 3.0, 1.5, 3.0, 8.0


def _pin(degrees, radius=RADIUS, distance=DISTANCE):
    """試験側の独立な幾何。クランクの中心 (0, d) のまわりで、真上から θ 回したピンをピボットから見た位置。"""
    theta = math.radians(degrees)
    return radius * math.sin(theta), distance + radius * math.cos(theta)


def _leverDegrees(degrees, radius=RADIUS, distance=DISTANCE):
    """ピボットからピンへの向き(度)。クランクの回転に最も近い値へ360度の倍数をそろえて、連続した角度にする。"""
    x, y = _pin(degrees, radius, distance)
    direction = math.degrees(math.atan2(x, y))
    return direction + 360.0 * round((degrees - direction) / 360.0)


def _ram(degrees, radius=RADIUS, distance=DISTANCE, arm=ARM, rod=ROD):
    """腕の先 (a sin φ, a cos φ) から長さ L の棒で届く、ピボットを通る横の直線上の点(生成時からの移動、cm)。"""
    phi = math.radians(_leverDegrees(degrees, radius, distance))
    end = (arm * math.sin(phi), arm * math.cos(phi))
    return end[0] + math.sqrt(rod * rod - end[1] * end[1]) - math.sqrt(rod * rod - arm * arm)


class WhitworthQuickReturnTest(unittest.TestCase):
    """作成時・幾何との一致・Python版・速さの比と戻りの区間・時間比と行程・phase・軸と単位・所有とUndo・引数を確認する。"""

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
        self.setup = WhitworthQuickReturn.create(self.crank, self.lever, self.ram, RADIUS, DISTANCE, ARM, ROD,
                                                 name="whitworth")
        self.owner = str(self.setup.container)

    def _turn(self, degrees):
        """生成時から degrees 度クランクを回し、(レバーの回転(度)、ラムの移動(cm)) を返す。"""
        cmds.setAttr(self.crank + ".rotateZ", 30.0 + degrees)
        return (cmds.getAttr(self.lever + ".rotateZ") - 10.0, cmds.getAttr(self.ram + ".translateX") - 4.0)

    def test_rest(self):
        """生成時はレバーもラムも跳ねず、角度の差・ラムの移動が0、溝の距離は d + r、速さの比は r / (r + d)。"""
        self.assertAlmostEqual(cmds.getAttr(self.lever + ".rotateZ"), 10.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.ram + ".translateX"), 4.0, places=6)
        for attribute in ("leverAngle", "lag", "ramOffset", "returnStroke"):
            with self.subTest(attribute=attribute):
                self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), 0.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".slotDistance"), DISTANCE + RADIUS, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".speedRatio"), RADIUS / (RADIUS + DISTANCE), places=6)

    def test_geometry_and_full_turns(self):
        """正負・複数回転の角度で、連続したレバーの角度・溝の距離・ラムの移動が試験側の幾何と一致する。"""
        for degrees in (-725.0, -400.0, -120.0, -90.0, 0.0, 45.0, 90.0, 120.0, 179.0, 180.0, 181.0, 240.0,
                        270.0, 359.0, 1000.0):
            with self.subTest(degrees=degrees):
                lean, ram = self._turn(degrees)
                x, y = _pin(degrees)
                self.assertAlmostEqual(lean, _leverDegrees(degrees), places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".leverAngle"), _leverDegrees(degrees), places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".lag"), _leverDegrees(degrees) - degrees, places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".slotDistance"), math.hypot(x, y), places=5)
                self.assertAlmostEqual(ram, _ram(degrees), places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".ramOffset"), _ram(degrees), places=5)
        # クランクが1回転するとレバーもちょうど1回転し、途中で跳ばない(1度刻みの差が180度より十分小さい)
        previous = self._turn(0.0)[0]
        for degrees in range(1, 721):
            current = self._turn(float(degrees))[0]
            self.assertLess(abs(current - previous), 3.0)
            previous = current
        self.assertAlmostEqual(previous, 720.0, places=5)

    def test_python_version_and_speed(self):
        """乱数の角度で Python 版と一致し、speedRatio は DG の回転の数値微分、returnStroke はラムが戻る区間と一致する。"""
        rng = random.Random(7)
        for _ in range(30):
            degrees = rng.uniform(-720.0, 720.0)
            with self.subTest(degrees=degrees):
                lean, ram = self._turn(degrees)
                result = WhitworthQuickReturn.motion(math.radians(degrees), RADIUS, DISTANCE, ARM, ROD)
                self.assertAlmostEqual(lean, math.degrees(result["leverAngle"]), places=5)
                self.assertAlmostEqual(ram, result["ramOffset"], places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".slotDistance"), result["slotDistance"], places=5)
                speed = cmds.getAttr(self.owner + ".speedRatio")
                self.assertAlmostEqual(speed, result["speedRatio"], places=6)
                step = 1e-2
                slope = (self._turn(degrees + step)[0] - self._turn(degrees - step)[0]) / (2.0 * step)
                self.assertAlmostEqual(speed, slope, places=4)
                ramSlope = self._turn(degrees + step)[1] - self._turn(degrees - step)[1]
                self._turn(degrees)
                stroke = cmds.getAttr(self.owner + ".returnStroke")
                self.assertEqual(stroke, result["returnStroke"])
                if abs(ramSlope) > 1e-6:
                    self.assertEqual(stroke == 1.0, ramSlope < 0.0)
        # 速さの比は往きの中央で最小 r / (r + d)、戻りの中央で最大 r / (r - d)
        self._turn(180.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".speedRatio"), RADIUS / (RADIUS - DISTANCE), places=6)

    def test_time_ratio_and_stroke(self):
        """戻りはクランクの 2β (β = acos(d/r))、時間比 (180 - β) / β、ラムの行程は 2a で、端はレバーが横向きの角度。"""
        half = math.degrees(math.acos(DISTANCE / RADIUS))
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".returnAngle"), 2.0 * half, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".timeRatio"), (180.0 - half) / half, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".stroke"), 2.0 * ARM, places=6)
        count = 0
        samples = []
        for step in range(720):
            samples.append(self._turn(step * 0.5)[1])
            count += int(cmds.getAttr(self.owner + ".returnStroke"))
        self.assertAlmostEqual(count * 0.5, 2.0 * half, delta=1.0)
        self.assertAlmostEqual(max(samples) - min(samples), 2.0 * ARM, places=3)
        # ラムの端: クランクが 180 - β でレバーが 90 度(前の端)、180 + β で 270 度(後ろの端)
        self.assertAlmostEqual(self._turn(180.0 - half)[0], 90.0, places=5)
        self.assertAlmostEqual(self._turn(180.0 - half)[1], max(samples), places=3)
        self.assertAlmostEqual(self._turn(180.0 + half)[0], 270.0, places=5)
        self.assertAlmostEqual(self._turn(180.0 + half)[1], min(samples), places=3)

    def test_phase(self):
        """phase はクランクの角度に足される。"""
        cmds.setAttr(self.owner + ".phase", 40.0)
        lean, ram = self._turn(50.0)
        self.assertAlmostEqual(lean, _leverDegrees(90.0), places=5)
        self.assertAlmostEqual(ram, _ram(90.0), places=5)

    def test_axes_units_direction_and_no_ram(self):
        """axis=x・ramAxis=y・ramDirection=-1・d=0・UI単位 mm/rad・ラムなしでも幾何と一致し、外部に変換ノードを残さない。"""
        cmds.currentUnit(linear="mm", angle="rad")
        conversions = set(cmds.ls(type="unitConversion"))
        crank = cmds.createNode("transform", name="xCrank")
        lever = cmds.createNode("transform", name="xLever")
        ram = cmds.createNode("transform", name="yRam")
        setup = WhitworthQuickReturn.create(crank, lever, ram, 2.0, 1.0, 1.5, 5.0, name="xWhitworth", axis="x",
                                            ramAxis="y", ramDirection=-1.0)
        bare = WhitworthQuickReturn.create(crank, cmds.createNode("transform", name="bareLever"), None, 2.0, 0.0,
                                           name="bareWhitworth", axis="x")
        members = set(cmds.container(str(setup.container), query=True, nodeList=True) or [])
        members |= set(cmds.container(str(bare.container), query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        self.assertFalse(cmds.attributeQuery("ramTranslate", node=str(bare.container), exists=True))
        for degrees in (30.0, 100.0, 200.0, 300.0, 500.0):
            with self.subTest(degrees=degrees):
                cmds.setAttr(crank + ".rotateX", math.radians(degrees))
                self.assertAlmostEqual(math.degrees(cmds.getAttr(lever + ".rotateX")),
                                       _leverDegrees(degrees, 2.0, 1.0), places=4)
                # d = 0 ではレバーはクランクと同じ角度で回る
                self.assertAlmostEqual(math.degrees(cmds.getAttr("bareLever.rotateX")), degrees, places=4)
                self.assertAlmostEqual(cmds.getAttr(ram + ".translateY"),
                                       -_ram(degrees, 2.0, 1.0, 1.5, 5.0) * 10.0, places=3)  # mm
        cmds.currentUnit(linear="cm", angle="deg")

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("whitworth_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.file(new=True, force=True)
        crank = cmds.createNode("transform", name="undoCrank")
        lever = cmds.createNode("transform", name="undoLever")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        WhitworthQuickReturn.create(crank, lever, name="undoWhitworth")
        self.assertTrue(cmds.listConnections(lever + ".rotateZ", source=True, destination=False))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoWhitworth"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoWhitworth.rotate"))

    def test_arguments(self):
        """軸・半径・距離・長さ・向き・数値以外・transform以外・同じノード・接続済み・名前の重複を拒否し、何も残さない。"""
        other = cmds.createNode("multiplyDivide")
        free = cmds.createNode("transform", name="free")
        spare = cmds.createNode("transform", name="spare")
        before = set(cmds.ls())
        cases = (
            ((self.crank, free), {"axis": "w"}),
            ((self.crank, free, spare), {"ramAxis": "q"}),
            ((self.crank, free, None, 0.0), {}),
            ((self.crank, free, None, 2.0, 2.0), {}),
            ((self.crank, free, None, 2.0, 3.0), {}),
            ((self.crank, free, None, 2.0, -0.5), {}),
            ((self.crank, free, None, 2.0, 1.0, 0.0), {}),
            ((self.crank, free, None, 2.0, 1.0, 3.0, 3.0), {}),
            ((self.crank, free), {"ramDirection": 0.5}),
            ((self.crank, free, None, True), {}),
            ((self.crank, free, None, 2.0, "1"), {}),
            ((other, free), {}),
            ((self.crank, self.crank), {}),
            ((self.crank, free, free), {}),
            ((self.crank, self.lever), {}),
            ((self.crank, free, self.ram), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                WhitworthQuickReturn.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            WhitworthQuickReturn.create(self.crank, free, name="whitworth")
        self.assertEqual(set(cmds.ls()), before)
        WhitworthQuickReturn.create(self.crank, self.lever, self.ram, name="unconnected", connect=False)
        self.assertTrue(cmds.objExists("unconnected.ramTranslate"))


if __name__ == "__main__":
    unittest.main()
