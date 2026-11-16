"""EllipticTrammelのスライダー・棒・棒の上の点を、試験側で独立に書いた棒の幾何(長さ一定・溝の上)と楕円の式で確かめる。"""

import math
import random
import unittest

from maya import cmds

from mlrig.setups import EllipticTrammel

LENGTH = 4.0
PEN = 6.0


def _midpoint(degrees, length=LENGTH):
    """試験側の独立な幾何。溝の交点から +X に置いたクランク(長さ L/2)を degrees 度回した棒の中点 (x, y)。"""
    theta = math.radians(degrees)
    return 0.5 * length * math.cos(theta), 0.5 * length * math.sin(theta)


class EllipticTrammelTest(unittest.TestCase):
    """作成時・棒の長さと溝・Python版・楕円と半軸・棒の回転・phase・軸と単位と向き・所有とUndo・引数を確認する。"""

    def setUp(self):
        """クランクを rotateZ = 30 度、スライダーAを translateX = L + 1、Bを translateY = 2 に置き、棒をAの子にして生成する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.crank = cmds.createNode("joint", name="crank")
        cmds.setAttr(self.crank + ".rotateZ", 30.0)
        self.sliderA = cmds.createNode("transform", name="sliderA")
        cmds.setAttr(self.sliderA + ".translateX", LENGTH + 1.0)
        self.sliderB = cmds.createNode("transform", name="sliderB")
        cmds.setAttr(self.sliderB + ".translateY", 2.0)
        self.rod = cmds.createNode("transform", name="rod", parent=self.sliderA)
        cmds.setAttr(self.rod + ".rotateZ", 180.0)
        self.pen = cmds.createNode("transform", name="pen", parent=self.rod)
        cmds.setAttr(self.pen + ".translateX", PEN)
        self.setup = EllipticTrammel.create(self.crank, self.sliderA, self.sliderB, self.rod, LENGTH, PEN,
                                            name="trammelRig")
        self.owner = str(self.setup.container)

    def _turn(self, degrees):
        """生成時から degrees 度クランクを回し、(Aの位置 x、Bの位置 y) を溝の交点を原点として返す。"""
        cmds.setAttr(self.crank + ".rotateZ", 30.0 + degrees)
        return cmds.getAttr(self.sliderA + ".translateX") - 1.0, cmds.getAttr(self.sliderB + ".translateY") - 2.0

    def test_rest(self):
        """生成時はスライダーも棒も跳ねず、移動・回転が0、固定値は L・d・|L - d|・|d|。"""
        self.assertAlmostEqual(cmds.getAttr(self.sliderA + ".translateX"), LENGTH + 1.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.sliderB + ".translateY"), 2.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.rod + ".rotateZ"), 180.0, places=5)
        for attribute in ("aOffset", "bOffset", "rodAngle", "penX", "penY"):
            with self.subTest(attribute=attribute):
                self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), 0.0, places=6)
        expected = {"rodLength": LENGTH, "penDistance": PEN, "semiAxisA": abs(LENGTH - PEN), "semiAxisB": PEN}
        for attribute, value in expected.items():
            with self.subTest(attribute=attribute):
                self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), value, places=6)

    def test_rod_keeps_length_and_midpoint(self):
        """正負・複数回転の角度で、A・Bは溝の上、|AB| = L、ABの中点はクランクの先に一致する。"""
        for degrees in (-725.0, -400.0, -90.0, 0.0, 45.0, 90.0, 135.0, 180.0, 270.0, 359.0, 1000.0):
            with self.subTest(degrees=degrees):
                a, b = self._turn(degrees)
                self.assertAlmostEqual(math.hypot(a, b), LENGTH, places=5)
                mx, my = _midpoint(degrees)
                self.assertAlmostEqual(0.5 * a, mx, places=5)
                self.assertAlmostEqual(0.5 * b, my, places=5)

    def test_rod_direction_and_pen_on_ellipse(self):
        """棒(Aの子)の先はBを通り、棒の上の点のワールド位置は楕円の上にあり、DGの penX・penY と一致する。"""
        for degrees in (0.0, 20.0, 75.0, 160.0, 200.0, 290.0, -45.0):
            with self.subTest(degrees=degrees):
                a, b = self._turn(degrees)
                pen = cmds.xform(self.pen, query=True, worldSpace=True, translation=True)
                # 棒は A (ワールド (a + 1, 0)) から、溝の交点 (ワールド (1, 0)) を基準にした B (0, b) へ向く
                direction = (-a / LENGTH, b / LENGTH)
                self.assertAlmostEqual(pen[0], a + 1.0 + PEN * direction[0], places=4)
                self.assertAlmostEqual(pen[1], PEN * direction[1], places=4)
                x, y = pen[0] - 1.0, pen[1]
                self.assertAlmostEqual((x / (LENGTH - PEN)) ** 2 + (y / PEN) ** 2, 1.0, places=4)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".penX"), x - (LENGTH - PEN), places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".penY"), y, places=5)

    def test_python_version(self):
        """乱数の角度で Python 版と一致し、棒の回転はクランクと逆向きに同じ量。"""
        rng = random.Random(17)
        for _ in range(25):
            degrees = rng.uniform(-720.0, 720.0)
            with self.subTest(degrees=degrees):
                a, b = self._turn(degrees)
                result = EllipticTrammel.motion(math.radians(degrees), LENGTH, PEN)
                self.assertAlmostEqual(a - LENGTH, result["aOffset"], places=5)
                self.assertAlmostEqual(b, result["bOffset"], places=5)
                for attribute in ("aOffset", "bOffset", "penX", "penY"):
                    self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), result[attribute], places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".rodAngle"), math.degrees(result["rodAngle"]),
                                       places=4)
                self.assertAlmostEqual(cmds.getAttr(self.rod + ".rotateZ"), 180.0 - degrees, places=4)

    def test_ellipse_extent_and_default_pen(self):
        """1回転で棒の上の点の移動の幅は 2|L - d| と 2|d|。penDistance を省くと 1.5 L、中点 (d = L/2) は円。"""
        xs, ys = [], []
        for index in range(360):
            self._turn(index)
            xs.append(cmds.getAttr(self.owner + ".penX"))
            ys.append(cmds.getAttr(self.owner + ".penY"))
        self.assertAlmostEqual(max(xs) - min(xs), 2.0 * abs(LENGTH - PEN), places=4)
        self.assertAlmostEqual(max(ys) - min(ys), 2.0 * PEN, places=4)
        crank = cmds.createNode("transform", name="defaultCrank")
        free = [cmds.createNode("transform", name="free" + str(index)) for index in range(4)]
        default = EllipticTrammel.create(crank, free[0], free[1], rodLength=2.0, name="defaultRig")
        self.assertAlmostEqual(cmds.getAttr(str(default.container) + ".penDistance"), 3.0, places=6)
        circle = EllipticTrammel.create(crank, free[2], free[3], rodLength=2.0, penDistance=1.0, name="circleRig")
        cmds.setAttr(crank + ".rotateZ", 123.0)
        owner = str(circle.container)
        self.assertAlmostEqual(cmds.getAttr(owner + ".semiAxisA"), cmds.getAttr(owner + ".semiAxisB"), places=6)
        x = cmds.getAttr(owner + ".penX") + 1.0
        self.assertAlmostEqual(math.hypot(x, cmds.getAttr(owner + ".penY")), 1.0, places=5)

    def test_phase(self):
        """phase はクランクの角度に足される。"""
        cmds.setAttr(self.owner + ".phase", 40.0)
        a, b = self._turn(50.0)
        self.assertAlmostEqual(a, 0.0, places=5)
        self.assertAlmostEqual(b, LENGTH, places=5)

    def test_axes_units_direction_and_no_rod(self):
        """axis=x・aAxis=y・bAxis=z・向き -1・UI単位 mm/rad・棒なしでも一致し、外部に変換ノードを残さない。"""
        cmds.currentUnit(linear="mm", angle="rad")
        conversions = set(cmds.ls(type="unitConversion"))
        crank = cmds.createNode("transform", name="xCrank")
        sliderA = cmds.createNode("transform", name="ySlider")
        cmds.setAttr(sliderA + ".translateY", 20.0)  # mm
        sliderB = cmds.createNode("transform", name="zSlider")
        rod = cmds.createNode("transform", name="xRod")
        setup = EllipticTrammel.create(crank, sliderA, sliderB, rod, 2.0, 1.0, name="xTrammel", axis="x", aAxis="y",
                                       bAxis="z", aDirection=-1.0, bDirection=-1.0, rodDirection=-1.0)
        bare = EllipticTrammel.create(crank, cmds.createNode("transform", name="bareA"),
                                      cmds.createNode("transform", name="bareB"), rodLength=2.0, name="bareRig",
                                      axis="x")
        members = set(cmds.container(str(setup.container), query=True, nodeList=True) or [])
        members |= set(cmds.container(str(bare.container), query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        self.assertFalse(cmds.attributeQuery("rodRotate", node=str(bare.container), exists=True))
        for degrees in (0.0, 30.0, 100.0, 200.0, 300.0, 500.0):
            with self.subTest(degrees=degrees):
                theta = math.radians(degrees)
                cmds.setAttr(crank + ".rotateX", theta)
                self.assertAlmostEqual(cmds.getAttr(sliderA + ".translateY"), 20.0 - 20.0 * (math.cos(theta) - 1.0),
                                       places=3)
                self.assertAlmostEqual(cmds.getAttr(sliderB + ".translateZ"), -20.0 * math.sin(theta), places=3)
                self.assertAlmostEqual(cmds.getAttr(rod + ".rotateX"), theta, places=5)
                self.assertAlmostEqual(cmds.getAttr("bareA.translateX"), 20.0 * (math.cos(theta) - 1.0), places=3)
                self.assertAlmostEqual(cmds.getAttr("bareB.translateY"), 20.0 * math.sin(theta), places=3)
        cmds.currentUnit(linear="cm", angle="deg")

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("trammelRig_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.file(new=True, force=True)
        crank = cmds.createNode("transform", name="undoCrank")
        sliderA = cmds.createNode("transform", name="undoA")
        sliderB = cmds.createNode("transform", name="undoB")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        EllipticTrammel.create(crank, sliderA, sliderB, name="undoTrammel")
        self.assertTrue(cmds.listConnections(sliderA + ".translateX", source=True, destination=False))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoTrammel"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoTrammel.bTranslate"))

    def test_arguments(self):
        """軸・長さ・距離・向き・数値以外・transform以外・同じノード・接続済み・名前の重複を拒否し、何も残さない。"""
        other = cmds.createNode("multiplyDivide")
        free = cmds.createNode("transform", name="free")
        spare = cmds.createNode("transform", name="spare")
        extra = cmds.createNode("transform", name="extra")
        before = set(cmds.ls())
        cases = (
            ((self.crank, free, spare), {"axis": "w"}),
            ((self.crank, free, spare), {"aAxis": "q"}),
            ((self.crank, free, spare), {"bAxis": "q"}),
            ((self.crank, free, spare, None, 0.0), {}),
            ((self.crank, free, spare, None, -1.0), {}),
            ((self.crank, free, spare, None, True), {}),
            ((self.crank, free, spare, None, "2"), {}),
            ((self.crank, free, spare), {"penDistance": "1"}),
            ((self.crank, free, spare), {"aDirection": 0.5}),
            ((self.crank, free, spare), {"bDirection": 2.0}),
            ((self.crank, free, spare), {"rodDirection": 0.0}),
            ((other, free, spare), {}),
            ((self.crank, free, free), {}),
            ((self.crank, free, spare, free), {}),
            ((self.crank, self.sliderA, spare), {}),
            ((self.crank, free, self.sliderB), {}),
            ((self.crank, free, spare, self.rod), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                EllipticTrammel.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            EllipticTrammel.create(self.crank, free, spare, name="trammelRig")
        self.assertEqual(set(cmds.ls()), before)
        EllipticTrammel.create(self.crank, self.sliderA, self.sliderB, extra, name="unconnected", connect=False)
        self.assertTrue(cmds.objExists("unconnected.rodRotate"))


if __name__ == "__main__":
    unittest.main()
