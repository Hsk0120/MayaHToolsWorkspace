"""Pantographのペン・腕・棒を、試験側で独立に書いたリンクの幾何(棒の長さが一定・平行四辺形・k 倍)で確かめる。"""

import math
import random
import unittest

from maya import cmds

from mlrig.setups import Pantograph

ARM = 4.0
LINK = 3.0
RATIO = 2.5
PIVOT = (1.0, -0.5)
OFFSET = (3.0, 1.0)
START = (5.0, 2.0)
NEAREST = ARM - LINK
FARTHEST = ARM + LINK


def _local(node):
    """ノードの、親の空間 (space) での位置 (x, y)。"""
    position = cmds.xform(node, query=True, worldSpace=True, translation=True)
    return position[0] - OFFSET[0], position[1] - OFFSET[1]


def _distance(first, second):
    """2点の距離。"""
    return math.hypot(first[0] - second[0], first[1] - second[1])


class PantographTest(unittest.TestCase):
    """作成時・k 倍と棒の長さ・シーンとの一致・範囲の止め・Python版・平面と単位と向き・所有とUndo・引数を確認する。"""

    def setUp(self):
        """動かした親 (space) の下に、固定点 PIVOT の腕(joint)・その子の棒(joint)・なぞる点・ペンを置いて生成する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.space = cmds.createNode("transform", name="space")
        cmds.setAttr(self.space + ".translate", OFFSET[0], OFFSET[1], 0.0)
        self.tracer = cmds.createNode("transform", name="tracer", parent=self.space)
        cmds.setAttr(self.tracer + ".translate", START[0], START[1], 0.0)
        self.rest = Pantograph.motion(START[0] - PIVOT[0], START[1] - PIVOT[1], ARM, LINK, RATIO)
        self.pen = cmds.createNode("transform", name="pen", parent=self.space)
        cmds.setAttr(self.pen + ".translate", PIVOT[0] + self.rest["qU"], PIVOT[1] + self.rest["qV"], 0.0)
        self.arm = cmds.createNode("joint", name="arm", parent=self.space)
        cmds.setAttr(self.arm + ".translate", PIVOT[0], PIVOT[1], 0.0)
        cmds.setAttr(self.arm + ".rotateZ", math.degrees(self.rest["armAngle"]))
        self.link = cmds.createNode("joint", name="link", parent=self.arm)
        cmds.setAttr(self.link + ".translateX", ARM)
        cmds.setAttr(self.link + ".rotateZ", math.degrees(self.rest["linkAngle"] - self.rest["armAngle"]))
        self.linkTip = cmds.createNode("transform", name="linkTip", parent=self.link)
        cmds.setAttr(self.linkTip + ".translateX", LINK)
        self.setup = Pantograph.create(self.tracer, self.pen, self.arm, self.link, ARM, LINK, RATIO,
                                       name="pantographRig", pivot=PIVOT, linkRelative=True)
        self.owner = str(self.setup.container)

    def _move(self, u, v):
        """なぞる点を、固定点から見た (u, v) へ動かす。"""
        cmds.setAttr(self.tracer + ".translate", PIVOT[0] + u, PIVOT[1] + v, 0.0)

    def _points(self):
        """DGの出力から O・P・Q・A・B・C を返す(固定点を原点とする u・v)。"""
        points = {"O": (0.0, 0.0)}
        for name in "PQABC":
            points[name] = tuple(cmds.getAttr("{}.{}{}".format(self.owner, name.lower(), axis)) for axis in "UV")
        return points

    def test_rest(self):
        """生成時はペンも腕も棒も跳ねず、固定値は a・b・k・範囲・固定点。"""
        position = cmds.getAttr(self.pen + ".translate")[0]
        self.assertAlmostEqual(position[0], PIVOT[0] + self.rest["qU"], places=6)
        self.assertAlmostEqual(position[1], PIVOT[1] + self.rest["qV"], places=6)
        self.assertAlmostEqual(cmds.getAttr(self.arm + ".rotateZ"), math.degrees(self.rest["armAngle"]), places=5)
        self.assertAlmostEqual(cmds.getAttr(self.link + ".rotateZ"),
                               math.degrees(self.rest["linkAngle"] - self.rest["armAngle"]), places=5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".excess"), 0.0, places=6)
        expected = {"armLength": ARM, "linkLength": LINK, "ratio": RATIO, "minimumDistance": NEAREST,
                    "maximumDistance": FARTHEST, "pivotU": PIVOT[0], "pivotV": PIVOT[1]}
        for attribute, value in expected.items():
            with self.subTest(attribute=attribute):
                self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), value, places=6)

    def test_scaled_copy_and_bar_lengths(self):
        """範囲の中の位置で、Q = k P、|OA| = a、|AP| = b、|OB| = k a、|BQ| = k b、A-P-C-B は平行四辺形、C は BQ の上。"""
        for u, v in ((4.0, 2.5), (1.2, 0.0), (0.0, 6.9), (-3.0, 4.0), (-5.0, -2.0), (2.0, -5.5), (6.99, 0.1)):
            with self.subTest(u=u, v=v):
                self._move(u, v)
                points = self._points()
                self.assertAlmostEqual(points["P"][0], u, places=4)
                self.assertAlmostEqual(points["P"][1], v, places=4)
                self.assertAlmostEqual(points["Q"][0], RATIO * u, places=4)
                self.assertAlmostEqual(points["Q"][1], RATIO * v, places=4)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".excess"), 0.0, places=5)
                lengths = (("O", "A", ARM), ("A", "P", LINK), ("O", "B", RATIO * ARM), ("B", "Q", RATIO * LINK),
                           ("P", "C", (RATIO - 1.0) * ARM), ("B", "C", LINK), ("C", "Q", (RATIO - 1.0) * LINK))
                for first, second, length in lengths:
                    self.assertAlmostEqual(_distance(points[first], points[second]), length, places=4)
                # A は O→P の線の u→v へ回る側(elbow = 1)
                cross = points["P"][0] * points["A"][1] - points["P"][1] * points["A"][0]
                self.assertGreaterEqual(cross, -1e-6)

    def test_scene(self):
        """シーンのペンは pivot + k p、腕の子の棒の先は P、棒の付け根(腕の先)は A に一致する。"""
        for u, v in ((4.0, 2.5), (0.5, 1.5), (-2.0, 5.0), (-4.0, -4.0), (3.0, -3.0)):
            with self.subTest(u=u, v=v):
                self._move(u, v)
                points = self._points()
                pen = _local(self.pen)
                self.assertAlmostEqual(pen[0], PIVOT[0] + RATIO * u, places=4)
                self.assertAlmostEqual(pen[1], PIVOT[1] + RATIO * v, places=4)
                for node, point in ((self.linkTip, "P"), (self.link, "A")):
                    position = _local(node)
                    self.assertAlmostEqual(position[0], PIVOT[0] + points[point][0], places=4)
                    self.assertAlmostEqual(position[1], PIVOT[1] + points[point][1], places=4)
                # なぞる点(入力)とも一致する
                tracer = _local(self.tracer)
                self.assertAlmostEqual(_distance(tracer, _local(self.linkTip)), 0.0, places=4)

    def test_limit_excess_and_return(self):
        """範囲の外では向きを保って端で止まり excess に超過量が出て、戻すと同じ姿勢に戻る(NaNを出さない)。"""
        self._move(3.0, 1.0)
        before = self._points()
        cases = (((7.0, 0.0), FARTHEST), ((9.0, 12.0), FARTHEST), ((-40.0, 3.0), FARTHEST), ((0.3, 0.4), NEAREST),
                 ((0.0, -0.2), NEAREST), ((0.0, 0.0), NEAREST))
        for (u, v), clamped in cases:
            with self.subTest(u=u, v=v):
                self._move(u, v)
                distance = math.hypot(u, v)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".tracerDistance"), distance, places=4)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".clampedDistance"), clamped, places=4)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".excess"), distance - clamped, places=4)
                points = self._points()
                self.assertTrue(all(not math.isnan(value) for point in points.values() for value in point))
                self.assertAlmostEqual(_distance(points["O"], points["P"]), clamped, places=4)
                self.assertAlmostEqual(_distance(points["O"], points["Q"]), RATIO * clamped, places=4)
                if distance > 0.0:
                    cross = points["P"][0] * v - points["P"][1] * u
                    self.assertAlmostEqual(cross, 0.0, places=3)
                    self.assertGreater(points["P"][0] * u + points["P"][1] * v, 0.0)
                # 端では腕と棒が一直線(遠い端)か折り重なる(近い端)。棒の長さは保つ
                self.assertAlmostEqual(_distance(points["O"], points["A"]), ARM, places=4)
                self.assertAlmostEqual(_distance(points["A"], points["P"]), LINK, places=2)
        self._move(3.0, 1.0)
        after = self._points()
        for key in before:
            self.assertAlmostEqual(_distance(before[key], after[key]), 0.0, places=5)

    def test_python_version(self):
        """乱数の位置(範囲の外を含む)で Python 版と一致する。"""
        rng = random.Random(26)
        names = ("tracerDistance", "clampedDistance", "excess", "pU", "pV", "qU", "qV", "aU", "aV", "bU", "bV",
                 "cU", "cV")
        for _ in range(25):
            u, v = rng.uniform(-9.0, 9.0), rng.uniform(-9.0, 9.0)
            with self.subTest(u=u, v=v):
                self._move(u, v)
                result = Pantograph.motion(u, v, ARM, LINK, RATIO)
                for attribute in names:
                    self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), result[attribute], places=4)
                for attribute in ("tracerAngle", "armAngle", "linkAngle"):
                    self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute),
                                           math.degrees(result[attribute]), places=3)

    def test_plane_units_elbow_and_negative_ratio(self):
        """plane=zx・肘の向き -1・負の倍率・minimumDistance・UI単位 mm/rad・腕の子でない棒でも一致し、変換ノードを残さない。"""
        cmds.currentUnit(linear="mm", angle="rad")
        conversions = set(cmds.ls(type="unitConversion"))
        tracer = cmds.createNode("transform", name="zTracer")
        cmds.setAttr(tracer + ".translate", 10.0, 0.0, 30.0)  # mm。u = z = 3cm、v = x = 1cm
        pen = cmds.createNode("transform", name="zPen")
        cmds.setAttr(pen + ".translate", 5.0, 7.0, -20.0)
        arm = cmds.createNode("transform", name="zArm")
        armTip = cmds.createNode("transform", name="zArmTip", parent=arm)
        cmds.setAttr(armTip + ".translateZ", 20.0)
        link = cmds.createNode("transform", name="zLink")
        rest = Pantograph.motion(3.0, 1.0, 2.0, 2.0, -1.5, -1.0, 0.5)
        cmds.setAttr(arm + ".rotateY", rest["armAngle"])
        cmds.setAttr(link + ".rotateY", 0.25)
        setup = Pantograph.create(tracer, pen, arm, link, 2.0, 2.0, -1.5, name="zPantograph", plane="zx",
                                  elbow=-1.0, minimumDistance=0.5)
        owner = str(setup.container)
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        self.assertAlmostEqual(cmds.getAttr(owner + ".minimumDistance"), 5.0, places=5)
        for u, v in ((3.0, 1.0), (1.0, -2.0), (-2.5, 2.5), (0.1, 0.2), (6.0, 1.0)):
            with self.subTest(u=u, v=v):
                cmds.setAttr(tracer + ".translate", 10.0 * v, 0.0, 10.0 * u)
                result = Pantograph.motion(u, v, 2.0, 2.0, -1.5, -1.0, 0.5)
                position = cmds.getAttr(pen + ".translate")[0]
                self.assertAlmostEqual(position[2], -20.0 + 10.0 * (result["qU"] - rest["qU"]), places=3)
                self.assertAlmostEqual(position[0], 5.0 + 10.0 * (result["qV"] - rest["qV"]), places=3)
                self.assertAlmostEqual(position[1], 7.0, places=6)
                self.assertAlmostEqual(cmds.getAttr(owner + ".qU"), -15.0 * result["pU"], places=3)
                self.assertAlmostEqual(cmds.getAttr(arm + ".rotateY"), result["armAngle"], places=5)
                self.assertAlmostEqual(cmds.getAttr(link + ".rotateY"),
                                       0.25 + result["linkAngle"] - rest["linkAngle"], places=5)
                # 腕の先(ローカル +Z へ 2cm)は A。u = z、v = x
                world = cmds.xform(armTip, query=True, worldSpace=True, translation=True)
                self.assertAlmostEqual(world[2], 10.0 * result["aU"], places=3)
                self.assertAlmostEqual(world[0], 10.0 * result["aV"], places=3)
                # 肘は O→P の線の v→u へ回る側(elbow = -1)
                self.assertLessEqual(result["pU"] * result["aV"] - result["pV"] * result["aU"], 1e-9)
        cmds.currentUnit(linear="cm", angle="deg")

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("pantographRig_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.file(new=True, force=True)
        tracer = cmds.createNode("transform", name="undoTracer")
        cmds.setAttr(tracer + ".translateX", 5.0)
        pen = cmds.createNode("transform", name="undoPen")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        Pantograph.create(tracer, pen, name="undoPantograph")
        self.assertTrue(cmds.listConnections(pen + ".translateX", source=True, destination=False))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoPantograph"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoPantograph.penTranslateU"))

    def test_arguments(self):
        """平面・長さ・倍率・固定点・向き・範囲・数値以外・transform以外・同じノード・接続済み・名前の重複を拒否し、何も残さない。"""
        other = cmds.createNode("multiplyDivide")
        free = cmds.createNode("transform", name="free")
        spare = cmds.createNode("transform", name="spare")
        driven = cmds.createNode("transform", name="driven")
        cmds.connectAttr(free + ".rotate", driven + ".rotate")
        before = set(cmds.ls())
        cases = (
            ((self.tracer, free), {"plane": "xz"}),
            ((self.tracer, free), {"plane": "w"}),
            ((self.tracer, free), {"armLength": 0.0}),
            ((self.tracer, free), {"linkLength": -1.0}),
            ((self.tracer, free), {"ratio": 0.0}),
            ((self.tracer, free), {"ratio": True}),
            ((self.tracer, free), {"armLength": "4"}),
            ((self.tracer, free), {"pivot": (1.0,)}),
            ((self.tracer, free), {"pivot": 1.0}),
            ((self.tracer, free), {"pivot": (0.0, "a")}),
            ((self.tracer, free), {"elbow": 0.5}),
            ((self.tracer, free), {"minimumDistance": 8.0}),
            ((self.tracer, free), {"armLength": 4.0, "linkLength": 3.0, "minimumDistance": 0.5}),
            ((self.tracer, free), {"linkRelative": 1}),
            ((self.tracer, free), {"connect": "yes"}),
            ((other, free), {}),
            ((self.tracer, self.tracer), {}),
            ((self.tracer, free, free), {}),
            ((self.tracer, free, spare, spare), {}),
            ((self.tracer, self.pen), {}),
            ((self.tracer, free, self.arm), {}),
            ((self.tracer, free, driven), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                Pantograph.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            Pantograph.create(self.tracer, free, name="pantographRig")
        self.assertEqual(set(cmds.ls()), before)
        Pantograph.create(self.tracer, self.pen, spare, name="unconnected", connect=False)
        self.assertTrue(cmds.objExists("unconnected.armRotate"))
        self.assertFalse(cmds.attributeQuery("linkRotate", node="unconnected", exists=True))
        self.assertFalse(cmds.listConnections(spare + ".rotateZ", source=True, destination=False))


if __name__ == "__main__":
    unittest.main()
