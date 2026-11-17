"""OldhamCouplingの出力軸・円板を、試験側で独立に書いた溝の幾何(2本の直交する溝の線の交点)で確かめる。"""

import math
import random
import unittest

from maya import cmds

from mlrig.setups import OldhamCoupling

OFFSET = 2.0


def _center(degrees, offset=OFFSET):
    """試験側の独立な幾何。入力軸 O1 = (0, 0)、出力軸 O2 = (e, 0)。入力の溝は生成時に +Y (偏心に直交)で、degrees 度
    回った溝の線 (O1 を通る) と、それに直交して O2 を通る出力の溝の線の交点 (x, y) を2本の直線の連立方程式で解く。"""
    theta = math.radians(degrees)
    sx, sy = -math.sin(theta), math.cos(theta)  # 入力の溝の向き
    tx, ty = sy, -sx  # 出力の溝の向き(直交)
    # O1 + s (sx, sy) = O2 + t (tx, ty) をクラメルの公式で解く
    det = sx * (-ty) - (-tx) * sy
    s = (offset * (-ty) - (-tx) * 0.0) / det
    return s * sx, s * sy


class OldhamCouplingTest(unittest.TestCase):
    """作成時・円板の中心の幾何・公転の円と速さ・等速・Python版・phase・軸と単位と向き・所有とUndo・引数を確認する。"""

    def setUp(self):
        """入力軸を rotateZ = 30 度、出力軸を translateX = e・rotateZ = 10 度、円板を (1, 2) に置いて生成する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.input = cmds.createNode("joint", name="inputShaft")
        cmds.setAttr(self.input + ".rotateZ", 30.0)
        self.output = cmds.createNode("transform", name="outputShaft")
        cmds.setAttr(self.output + ".translateX", OFFSET)
        cmds.setAttr(self.output + ".rotateZ", 10.0)
        self.disc = cmds.createNode("transform", name="disc")
        cmds.setAttr(self.disc + ".translate", 1.0, 2.0, 0.0)
        cmds.setAttr(self.disc + ".rotateZ", 5.0)
        self.setup = OldhamCoupling.create(self.input, self.output, self.disc, OFFSET, name="oldhamRig")
        self.owner = str(self.setup.container)

    def _turn(self, degrees):
        """生成時から degrees 度入力軸を回し、円板の中心 (x, y) を入力軸の中心を原点として返す。"""
        cmds.setAttr(self.input + ".rotateZ", 30.0 + degrees)
        return cmds.getAttr(self.disc + ".translateX") - 1.0, cmds.getAttr(self.disc + ".translateY") - 2.0

    def test_rest(self):
        """生成時は跳ねず、移動・回転が0、溝の位置は (0, -e)、固定値は e・e/2。"""
        self.assertAlmostEqual(cmds.getAttr(self.disc + ".translateX"), 1.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.disc + ".translateY"), 2.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.disc + ".rotateZ"), 5.0, places=5)
        self.assertAlmostEqual(cmds.getAttr(self.output + ".rotateZ"), 10.0, places=5)
        for attribute in ("discOffsetU", "discOffsetV", "inputSlide", "orbitAngle"):
            with self.subTest(attribute=attribute):
                self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), 0.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".outputSlide"), -OFFSET, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".offset"), OFFSET, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".orbitRadius"), 0.5 * OFFSET, places=6)

    def test_disc_on_both_slots(self):
        """正負・複数回転の角度で、円板の中心は2本の溝の線の交点にあり、∠O1 C O2 は直角(|C - M| = e/2)。"""
        for degrees in (-725.0, -400.0, -90.0, -10.0, 0.0, 45.0, 90.0, 135.0, 180.0, 270.0, 359.0, 1000.0):
            with self.subTest(degrees=degrees):
                x, y = self._turn(degrees)
                ex, ey = _center(degrees)
                self.assertAlmostEqual(x, ex, places=5)
                self.assertAlmostEqual(y, ey, places=5)
                self.assertAlmostEqual(x * (x - OFFSET) + y * y, 0.0, places=5)
                self.assertAlmostEqual(math.hypot(x - 0.5 * OFFSET, y), 0.5 * OFFSET, places=5)

    def test_slides_match_slot_distances(self):
        """inputSlide・outputSlide は円板の中心の、入力軸・出力軸の中心から溝に沿った符号付きの距離。"""
        for degrees in (0.0, 20.0, 75.0, 160.0, 200.0, 290.0, -45.0):
            with self.subTest(degrees=degrees):
                x, y = self._turn(degrees)
                theta = math.radians(degrees)
                inputSlot = (-math.sin(theta), math.cos(theta))
                outputSlot = (math.cos(theta), math.sin(theta))
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".inputSlide"),
                                       x * inputSlot[0] + y * inputSlot[1], places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".outputSlide"),
                                       (x - OFFSET) * outputSlot[0] + y * outputSlot[1], places=5)

    def test_constant_velocity_and_double_orbit(self):
        """出力軸と円板は入力軸と同じ角度で回り、中心の公転は 2θ (半回転で1周)、1回転の移動の幅は u: e、v: e。"""
        xs, ys = [], []
        for index in range(0, 360, 2):
            x, y = self._turn(index)
            xs.append(x)
            ys.append(y)
            self.assertAlmostEqual(cmds.getAttr(self.output + ".rotateZ"), 10.0 + index, places=4)
            self.assertAlmostEqual(cmds.getAttr(self.disc + ".rotateZ"), 5.0 + index, places=4)
            orbit = math.degrees(math.atan2(y, x - 0.5 * OFFSET))
            delta = (orbit - (2.0 * index + 180.0) + 180.0) % 360.0 - 180.0
            self.assertAlmostEqual(delta, 0.0, places=3)
            self.assertAlmostEqual(cmds.getAttr(self.owner + ".orbitAngle"), 2.0 * index, places=4)
        self.assertAlmostEqual(max(xs) - min(xs), OFFSET, places=4)
        self.assertAlmostEqual(max(ys) - min(ys), OFFSET, places=2)
        x0, y0 = self._turn(37.0)
        x1, y1 = self._turn(217.0)
        self.assertAlmostEqual(x0, x1, places=5)
        self.assertAlmostEqual(y0, y1, places=5)

    def test_python_version(self):
        """乱数の角度で Python 版と一致する。"""
        rng = random.Random(18)
        for _ in range(25):
            degrees = rng.uniform(-720.0, 720.0)
            with self.subTest(degrees=degrees):
                x, y = self._turn(degrees)
                result = OldhamCoupling.motion(math.radians(degrees), OFFSET)
                self.assertAlmostEqual(x, result["discOffsetU"], places=5)
                self.assertAlmostEqual(y, result["discOffsetV"], places=5)
                for attribute in ("discOffsetU", "discOffsetV", "inputSlide", "outputSlide"):
                    self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), result[attribute], places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".orbitAngle"), math.degrees(result["orbitAngle"]),
                                       places=3)

    def test_phase(self):
        """phase は入力軸の角度に足される。"""
        cmds.setAttr(self.owner + ".phase", 40.0)
        x, y = self._turn(50.0)
        self.assertAlmostEqual(x, OFFSET, places=5)
        self.assertAlmostEqual(y, 0.0, places=5)
        self.assertAlmostEqual(cmds.getAttr(self.output + ".rotateZ"), 10.0 + 90.0, places=4)

    def test_axes_units_and_direction(self):
        """axis=x・offsetAxis=z (面内のもう1つは -y)・出力の向き -1・UI単位 mm/rad でも一致し、外部に変換ノードを残さない。"""
        cmds.currentUnit(linear="mm", angle="rad")
        conversions = set(cmds.ls(type="unitConversion"))
        shaft = cmds.createNode("transform", name="xInput")
        output = cmds.createNode("transform", name="xOutput")
        disc = cmds.createNode("transform", name="xDisc")
        cmds.setAttr(disc + ".translateY", 30.0)  # mm
        setup = OldhamCoupling.create(shaft, output, disc, 2.0, name="xOldham", axis="x", offsetAxis="z",
                                      outputDirection=-1.0)
        members = set(cmds.container(str(setup.container), query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        for degrees in (0.0, 30.0, 100.0, 200.0, 300.0, 500.0):
            with self.subTest(degrees=degrees):
                theta = math.radians(degrees)
                cmds.setAttr(shaft + ".rotateX", theta)
                # x × z = -y なので、面内のもう1つの軸は -Y
                self.assertAlmostEqual(cmds.getAttr(disc + ".translateZ"), 20.0 * math.sin(theta) ** 2, places=3)
                self.assertAlmostEqual(cmds.getAttr(disc + ".translateY"),
                                       30.0 + 20.0 * math.sin(theta) * math.cos(theta), places=3)
                self.assertAlmostEqual(cmds.getAttr(disc + ".rotateX"), theta, places=5)
                self.assertAlmostEqual(cmds.getAttr(output + ".rotateX"), -theta, places=5)
        cmds.currentUnit(linear="cm", angle="deg")

    def test_world_geometry_other_planes(self):
        """どの (axis, offsetAxis) でも、円板の中心は出力軸の溝の線の上(出力軸の中心から入力の溝の向きの成分が0)。"""
        for axis, offsetAxis in (("z", "y"), ("y", "z"), ("y", "x"), ("x", "y")):
            with self.subTest(axis=axis, offsetAxis=offsetAxis):
                prefix = axis + offsetAxis
                shaft = cmds.createNode("transform", name=prefix + "In")
                output = cmds.createNode("transform", name=prefix + "Out")
                disc = cmds.createNode("transform", name=prefix + "Disc")
                OldhamCoupling.create(shaft, output, disc, 3.0, name=prefix + "Rig", axis=axis, offsetAxis=offsetAxis)
                cmds.setAttr(shaft + ".rotate" + axis.upper(), 70.0)
                # 入力の溝の向き: 生成時の溝(axis × offsetAxis の向き)を入力軸と同じだけ回した向き
                slot = cmds.xform(shaft, query=True, worldSpace=True, matrix=True)
                rest = {"x": 0, "y": 1, "z": 2}
                perpendicular = [0.0, 0.0, 0.0]
                a, o = rest[axis], rest[offsetAxis]
                p = 3 - a - o
                perpendicular[p] = 1.0 if (a, o) in ((2, 0), (0, 1), (1, 2)) else -1.0
                direction = [sum(perpendicular[r] * slot[r * 4 + c] for r in range(3)) for c in range(3)]
                center = cmds.getAttr(disc + ".translate")[0]
                target = [0.0, 0.0, 0.0]
                target[o] = 3.0
                along = sum((center[i] - target[i]) * direction[i] for i in range(3))
                self.assertAlmostEqual(along, 0.0, places=5)
                cross = [center[(i + 1) % 3] * direction[(i + 2) % 3] - center[(i + 2) % 3] * direction[(i + 1) % 3]
                         for i in range(3)]
                self.assertAlmostEqual(math.sqrt(sum(value * value for value in cross)), 0.0, places=5)

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("oldhamRig_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.file(new=True, force=True)
        shaft = cmds.createNode("transform", name="undoInput")
        output = cmds.createNode("transform", name="undoOutput")
        disc = cmds.createNode("transform", name="undoDisc")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        OldhamCoupling.create(shaft, output, disc, name="undoOldham")
        self.assertTrue(cmds.listConnections(disc + ".translateX", source=True, destination=False))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoOldham"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoOldham.outputRotate"))

    def test_arguments(self):
        """軸・距離・向き・数値以外・transform以外・同じノード・接続済み・名前の重複を拒否し、何も残さない。"""
        other = cmds.createNode("multiplyDivide")
        free = cmds.createNode("transform", name="free")
        spare = cmds.createNode("transform", name="spare")
        before = set(cmds.ls())
        cases = (
            ((self.input, free, spare), {"axis": "w"}),
            ((self.input, free, spare), {"offsetAxis": "q"}),
            ((self.input, free, spare), {"axis": "x", "offsetAxis": "x"}),
            ((self.input, free, spare, 0.0), {}),
            ((self.input, free, spare, -1.0), {}),
            ((self.input, free, spare, True), {}),
            ((self.input, free, spare, "2"), {}),
            ((self.input, free, spare), {"outputDirection": 0.5}),
            ((self.input, free, spare), {"outputDirection": True}),
            ((other, free, spare), {}),
            ((self.input, free, free), {}),
            ((self.input, self.input, spare), {}),
            ((self.input, self.output, spare), {}),
            ((self.input, free, self.disc), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                OldhamCoupling.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            OldhamCoupling.create(self.input, free, spare, name="oldhamRig")
        self.assertEqual(set(cmds.ls()), before)
        OldhamCoupling.create(self.input, self.output, self.disc, name="unconnected", connect=False)
        self.assertTrue(cmds.objExists("unconnected.discV"))


if __name__ == "__main__":
    unittest.main()
