"""PeaucellierLinkageのペン・腕・クランクの先を、試験側で独立に書いたリンクの幾何(棒の長さが一定・直線の上)で確かめる。"""

import math
import random
import unittest

from maya import cmds

from mlrig.setups import PeaucellierLinkage

RADIUS = 2.0
ARM = 5.0
SIDE = 2.0
CONSTANT = ARM * ARM - SIDE * SIDE
LINE = CONSTANT / (2.0 * RADIUS)
LIMIT = math.degrees(2.0 * math.acos((ARM - SIDE) / (2.0 * RADIUS)))


def _world(node):
    """ノードのワールド位置 (x, y)。"""
    position = cmds.xform(node, query=True, worldSpace=True, translation=True)
    return position[0], position[1]


def _distance(first, second):
    """2点の距離。"""
    return math.hypot(first[0] - second[0], first[1] - second[1])


class PeaucellierLinkageTest(unittest.TestCase):
    """作成時・棒の長さ・直線・反転・範囲の止め・Python版・phase・軸と単位と向き・所有とUndo・引数を確認する。"""

    def setUp(self):
        """固定点 O を原点に、クランクを (r, 0) の -15 度回した親の下で rotateZ = 15 度(ワールドでは +u 向き)に置き、
        腕を θ = 0 の向き ±α0 に、ペンを直線の上に置いて生成する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        space = cmds.createNode("transform", name="crankSpace")
        cmds.setAttr(space + ".translateX", RADIUS)
        cmds.setAttr(space + ".rotateZ", -15.0)
        self.crank = cmds.createNode("joint", name="crank", parent=space)
        cmds.setAttr(self.crank + ".rotateZ", 15.0)
        self.crankTip = cmds.createNode("transform", name="crankTip", parent=self.crank)
        cmds.setAttr(self.crankTip + ".translateX", RADIUS)
        self.pen = cmds.createNode("transform", name="pen")
        cmds.setAttr(self.pen + ".translateX", LINE)
        cmds.setAttr(self.pen + ".translateY", 1.0)
        self.rest = PeaucellierLinkage.motion(0.0, RADIUS, ARM, SIDE)
        self.arms = []
        for label in ("A", "B"):
            arm = cmds.createNode("joint", name="arm" + label)
            cmds.setAttr(arm + ".rotateZ", math.degrees(self.rest["armAngle" + label]))
            tip = cmds.createNode("transform", name="arm" + label + "Tip", parent=arm)
            cmds.setAttr(tip + ".translateX", ARM)
            self.arms.append((arm, tip))
        self.setup = PeaucellierLinkage.create(self.crank, self.pen, self.arms[0][0], self.arms[1][0], RADIUS, ARM,
                                               SIDE, name="peaucellierRig")
        self.owner = str(self.setup.container)

    def _turn(self, degrees):
        """生成時から degrees 度クランクを回す。"""
        cmds.setAttr(self.crank + ".rotateZ", 15.0 + degrees)

    def _points(self):
        """DGの出力から O・A・B・P・Q を返す(固定点を原点とする u・v)。"""
        def get(attribute):
            """containerの出力の値。"""
            return cmds.getAttr(self.owner + "." + attribute)

        return {"O": (0.0, 0.0), "A": (get("aX"), get("aY")), "B": (get("bX"), get("bY")),
                "P": (get("pX"), get("pY")), "Q": (get("qX"), get("qY"))}

    def test_rest(self):
        """生成時はペンも腕も跳ねず、固定値は r・a・b・k・k/(2r)・θmax。"""
        self.assertAlmostEqual(cmds.getAttr(self.pen + ".translateY"), 1.0, places=6)
        for (arm, _), label in zip(self.arms, ("A", "B")):
            self.assertAlmostEqual(cmds.getAttr(arm + ".rotateZ"), math.degrees(self.rest["armAngle" + label]),
                                   places=5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".qY"), 0.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".excessAngle"), 0.0, places=6)
        expected = {"crankLength": RADIUS, "armLength": ARM, "sideLength": SIDE, "inversionConstant": CONSTANT,
                    "lineDistance": LINE, "maxAngle": LIMIT}
        for attribute, value in expected.items():
            with self.subTest(attribute=attribute):
                self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), value, places=5)

    def test_bar_lengths_and_straight_line(self):
        """範囲の中の角度で、腕 OA・OB = a、菱形の4辺 = b、|CP| = r、Q は直線 x = k/(2r) の上、O・P・Q は一直線。"""
        for degrees in (-80.0, -60.0, -30.0, -5.0, 0.0, 12.0, 45.0, 70.0, 82.0):
            with self.subTest(degrees=degrees):
                self._turn(degrees)
                points = self._points()
                for arm in ("A", "B"):
                    self.assertAlmostEqual(_distance(points["O"], points[arm]), ARM, places=4)
                    for joint in ("P", "Q"):
                        self.assertAlmostEqual(_distance(points[arm], points[joint]), SIDE, places=4)
                self.assertAlmostEqual(_distance((RADIUS, 0.0), points["P"]), RADIUS, places=5)
                self.assertAlmostEqual(points["Q"][0], LINE, places=5)
                cross = points["P"][0] * points["Q"][1] - points["P"][1] * points["Q"][0]
                self.assertAlmostEqual(cross, 0.0, places=4)
                self.assertGreater(points["A"][1], points["B"][1])

    def test_inversion_and_scene(self):
        """|OP|·|OQ| = k、クランクの先(シーン)は P と一致し、ペンは直線の上を qY だけ動き、腕の先は A・B と一致する。"""
        for degrees in (-70.0, -20.0, 0.0, 33.0, 77.0):
            with self.subTest(degrees=degrees):
                self._turn(degrees)
                points = self._points()
                near = cmds.getAttr(self.owner + ".opDistance")
                far = cmds.getAttr(self.owner + ".oqDistance")
                self.assertAlmostEqual(near * far, CONSTANT, places=4)
                self.assertAlmostEqual(_distance(points["O"], points["P"]), near, places=5)
                self.assertAlmostEqual(_distance(points["O"], points["Q"]), far, places=4)
                # 試験側の P: 中心 (r, 0)・半径 r の円の上で θ 回した点。シーンのクランクの先とDGの P が一致する
                tip = _world(self.crankTip)
                theta = math.radians(degrees)
                expected = (RADIUS + RADIUS * math.cos(theta), RADIUS * math.sin(theta))
                for actual in (tip, points["P"]):
                    self.assertAlmostEqual(actual[0], expected[0], places=4)
                    self.assertAlmostEqual(actual[1], expected[1], places=4)
                self.assertAlmostEqual(cmds.getAttr(self.pen + ".translateY"), 1.0 + points["Q"][1], places=5)
                self.assertAlmostEqual(cmds.getAttr(self.pen + ".translateX"), LINE, places=6)
                # 腕は生成時に ±α0 の向きなので、シーンの腕の先が A・B に一致する
                for (_, armTip), label in zip(self.arms, ("A", "B")):
                    position = _world(armTip)
                    self.assertAlmostEqual(position[0], points[label][0], places=4)
                    self.assertAlmostEqual(position[1], points[label][1], places=4)

    def test_limit_excess_and_return(self):
        """±θmax を超えると P・Q は端で止まり excessAngle に超過量が出て、戻すと同じ経路に戻る(NaNを出さない)。"""
        self._turn(60.0)
        before = self._points()
        for degrees in (LIMIT, LIMIT + 30.0, 400.0, -LIMIT - 50.0):
            with self.subTest(degrees=degrees):
                self._turn(degrees)
                clamped = max(min(degrees, LIMIT), -LIMIT)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".crankAngle"), clamped, places=4)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".excessAngle"), degrees - clamped, places=4)
                points = self._points()
                self.assertTrue(all(not math.isnan(value) for point in points.values() for value in point))
                self.assertAlmostEqual(points["Q"][0], LINE, places=4)
                # 端では O・A・P・B が一直線になり、腕と P の距離は a - b
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".opDistance"), ARM - SIDE, places=4)
                self.assertAlmostEqual(_distance(points["A"], points["B"]), 0.0, places=2)
        self._turn(60.0)
        after = self._points()
        for key in before:
            self.assertAlmostEqual(_distance(before[key], after[key]), 0.0, places=5)

    def test_python_version(self):
        """乱数の角度(範囲の外を含む)で Python 版と一致する。"""
        rng = random.Random(23)
        for _ in range(25):
            degrees = rng.uniform(-150.0, 150.0)
            with self.subTest(degrees=degrees):
                self._turn(degrees)
                result = PeaucellierLinkage.motion(math.radians(degrees), RADIUS, ARM, SIDE)
                for attribute in ("pX", "pY", "qX", "qY", "aX", "aY", "bX", "bY", "opDistance", "oqDistance"):
                    self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), result[attribute], places=4)
                for attribute in ("crankAngle", "excessAngle", "armAngleA", "armAngleB"):
                    self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute),
                                           math.degrees(result[attribute]), places=3)

    def test_phase(self):
        """phase はクランクの角度に足される。"""
        cmds.setAttr(self.owner + ".phase", 40.0)
        self._turn(-40.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".qY"), 0.0, places=5)
        self._turn(0.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".qY"), LINE * math.tan(math.radians(20.0)), places=4)

    def test_axes_units_direction_and_no_arms(self):
        """axis=x・penAxis=z・向き -1・UI単位 mm/rad・腕なしでも一致し、外部に変換ノードを残さない。"""
        cmds.currentUnit(linear="mm", angle="rad")
        conversions = set(cmds.ls(type="unitConversion"))
        crank = cmds.createNode("transform", name="xCrank")
        pen = cmds.createNode("transform", name="zPen")
        cmds.setAttr(pen + ".translateZ", 30.0)  # mm
        arm = cmds.createNode("transform", name="xArm")
        setup = PeaucellierLinkage.create(crank, pen, arm, None, 1.5, 3.0, 1.0, name="xLinkage", axis="x",
                                          penAxis="z", penDirection=-1.0, armDirection=-1.0)
        members = set(cmds.container(str(setup.container), query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        owner = str(setup.container)
        self.assertFalse(cmds.attributeQuery("armBRotate", node=owner, exists=True))
        rest = PeaucellierLinkage.motion(0.0, 1.5, 3.0, 1.0)["armAngleA"]
        for degrees in (-60.0, -10.0, 0.0, 25.0, 70.0):
            with self.subTest(degrees=degrees):
                theta = math.radians(degrees)
                cmds.setAttr(crank + ".rotateX", theta)
                result = PeaucellierLinkage.motion(theta, 1.5, 3.0, 1.0)
                self.assertAlmostEqual(cmds.getAttr(pen + ".translateZ"), 30.0 - 10.0 * result["qY"], places=3)
                self.assertAlmostEqual(cmds.getAttr(arm + ".rotateX"), -(result["armAngleA"] - rest), places=5)
                self.assertAlmostEqual(cmds.getAttr(owner + ".qX"), 10.0 * (9.0 - 1.0) / 3.0, places=3)
        cmds.currentUnit(linear="cm", angle="deg")

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("peaucellierRig_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.file(new=True, force=True)
        crank = cmds.createNode("transform", name="undoCrank")
        pen = cmds.createNode("transform", name="undoPen")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        PeaucellierLinkage.create(crank, pen, name="undoLinkage")
        self.assertTrue(cmds.listConnections(pen + ".translateY", source=True, destination=False))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoLinkage"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoLinkage.penTranslate"))

    def test_arguments(self):
        """軸・長さ(2r の範囲を含む)・向き・数値以外・transform以外・同じノード・接続済み・名前の重複を拒否し、何も残さない。"""
        other = cmds.createNode("multiplyDivide")
        free = cmds.createNode("transform", name="free")
        spare = cmds.createNode("transform", name="spare")
        extra = cmds.createNode("transform", name="extra")
        before = set(cmds.ls())
        cases = (
            ((self.crank, free), {"axis": "w"}),
            ((self.crank, free), {"penAxis": "q"}),
            ((self.crank, free), {"crankLength": 0.0}),
            ((self.crank, free), {"sideLength": -1.0}),
            ((self.crank, free), {"armLength": 2.0, "sideLength": 2.0}),
            ((self.crank, free), {"crankLength": 1.4}),
            ((self.crank, free), {"crankLength": 3.6}),
            ((self.crank, free), {"crankLength": True}),
            ((self.crank, free), {"armLength": "5"}),
            ((self.crank, free), {"penDirection": 0.5}),
            ((self.crank, free), {"armDirection": 2.0}),
            ((other, free), {}),
            ((self.crank, self.crank), {}),
            ((self.crank, free, free), {}),
            ((self.crank, free, spare, spare), {}),
            ((self.crank, self.pen), {}),
            ((self.crank, free, self.arms[0][0]), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                PeaucellierLinkage.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            PeaucellierLinkage.create(self.crank, free, name="peaucellierRig")
        self.assertEqual(set(cmds.ls()), before)
        PeaucellierLinkage.create(self.crank, self.pen, extra, name="unconnected", connect=False)
        self.assertTrue(cmds.objExists("unconnected.armARotate"))
        PeaucellierLinkage.create(self.crank, spare, crankLength=3.25, armLength=5.0, sideLength=1.5, name="edge")
        self.assertAlmostEqual(cmds.getAttr("edge.maxAngle"), math.degrees(2.0 * math.acos(3.5 / 6.5)), places=5)


if __name__ == "__main__":
    unittest.main()
