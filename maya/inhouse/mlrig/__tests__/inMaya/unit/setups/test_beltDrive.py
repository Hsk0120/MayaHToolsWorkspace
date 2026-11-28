"""BeltDriveのプーリー・ベルトの直線部の行列を、共通接線の式と幾何の条件(接点が円周上・半径に垂直)で確認する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import BeltDrive


def _matrix(owner, attribute):
    """containerの行列アトリビュートの値。"""
    return om.MMatrix(cmds.getAttr("{}.{}".format(owner, attribute)))


class BeltDriveTest(unittest.TestCase):
    """標準ノードの数値評価・接線の条件・範囲の端・単位・引数検査を確認する。"""

    def setUp(self):
        """移動・回転した土台を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.base = cmds.createNode("transform", name="beltBase")
        cmds.setAttr(self.base + ".translate", 3, 7, -2)
        cmds.setAttr(self.base + ".rotate", 20, -35, 12)

    def check(self, owner, distance, r1, r2, crossed=False, rotation=0.0, base=None, tolerance=1e-3):
        """値の出力を式と比べ、直線部が両方の円に接することを、角度の式から独立に確かめる。"""
        owner = str(owner)
        clamped, excess, tangent, span, driverWrap, drivenWrap, length, ratio = BeltDrive.evaluate(
            distance, r1, r2, crossed)
        for attribute, expected in (("clampedDistance", clamped), ("excess", excess), ("spanLength", span),
                                    ("beltLength", length), ("travel", math.radians(rotation) * r1)):
            self.assertAlmostEqual(cmds.getAttr(owner + "." + attribute), expected, delta=tolerance, msg=attribute)
        for attribute, expected in (("tangentAngle", tangent), ("driverWrap", driverWrap),
                                    ("drivenWrap", drivenWrap), ("drivenRotation", ratio * rotation)):
            self.assertAlmostEqual(cmds.getAttr(owner + "." + attribute), expected, delta=0.05, msg=attribute)
        self.assertAlmostEqual(cmds.getAttr(owner + ".ratio"), ratio, places=5)
        world = om.MMatrix(cmds.getAttr(base + ".worldMatrix[0]")) if base else om.MMatrix()
        inverse = world.inverse()
        # プーリーの中心と回転(土台の空間で、Z軸まわり)。
        for attribute, center, angle in (("driverMatrix", 0.0, rotation), ("drivenMatrix", clamped, ratio * rotation)):
            local = _matrix(owner, attribute) * inverse
            self.assertTrue((om.MPoint() * local).isEquivalent(om.MPoint(center, 0.0, 0.0), tolerance), attribute)
            arm = om.MVector(1.0, 0.0, 0.0) * local
            expected = om.MVector(math.cos(math.radians(angle)), math.sin(math.radians(angle)), 0.0)
            self.assertTrue(arm.isEquivalent(expected, 1e-3), attribute)
        sides = []
        for attribute, side in (("upperSpanMatrix", 1.0), ("lowerSpanMatrix", -1.0)):
            local = _matrix(owner, attribute) * inverse
            start = om.MPoint() * local
            end = om.MPoint(span, 0.0, 0.0) * local
            along = om.MVector(1.0, 0.0, 0.0) * local
            toStart = om.MVector(start)
            toEnd = end - om.MPoint(clamped, 0.0, 0.0)
            # 両端が円周上にあり、半径が直線部に垂直(=接線)で、回転軸に垂直な面内にある。
            self.assertAlmostEqual(toStart.length(), r1, delta=tolerance, msg=attribute)
            self.assertAlmostEqual(toEnd.length(), r2, delta=tolerance, msg=attribute)
            self.assertAlmostEqual(toStart * along, 0.0, delta=tolerance, msg=attribute)
            self.assertAlmostEqual(toEnd * along, 0.0, delta=tolerance, msg=attribute)
            self.assertAlmostEqual(start.z, 0.0, delta=tolerance)
            self.assertAlmostEqual(end.z, 0.0, delta=tolerance)
            if span > 1e-2:
                self.assertGreater(side * start.y, -tolerance, attribute)
            sides.append((start.y, end.y))
        if span > 1e-2:
            # 平行掛けは同じ側のまま、十字掛けは反対側へ渡る。
            for start, end in sides:
                self.assertGreater(-start * end if crossed else start * end, -tolerance)
            self.assertAlmostEqual(sides[0][0], -sides[1][0], delta=tolerance)
            self.assertAlmostEqual(sides[0][1], -sides[1][1], delta=tolerance)

    def test_open_belt(self):
        """平行掛け: r1=2, r2=1, d=6 で θ=acos(1/6)、L=sqrt(35)。従動プーリーは同じ向きに2倍で回る。"""
        owner = BeltDrive.create(self.base).container
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".spanLength"), math.sqrt(35.0), places=4)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".tangentAngle"), math.degrees(math.acos(1.0 / 6.0)),
                               places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".ratio"), 2.0, places=6)
        for rotation in (0.0, 45.0, -130.0, 540.0):
            with self.subTest(rotation=rotation):
                cmds.setAttr(str(owner) + ".rotation", rotation)
                self.assertAlmostEqual(cmds.getAttr(str(owner) + ".drivenRotation"), 2.0 * rotation, places=3)
                self.check(owner, 6.0, 2.0, 1.0, rotation=rotation, base=self.base)

    def test_crossed_belt(self):
        """十字掛け: k = r1 + r2。両方の巻き付け角が同じで180度より大きく、従動プーリーは逆に回る。"""
        owner = BeltDrive.create(self.base, driverRadius=2.0, drivenRadius=1.0, distance=6.0, crossed=True,
                                 name="crossed").container
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".tangentAngle"), 60.0, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".driverWrap"), 240.0, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".drivenWrap"), 240.0, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".ratio"), -2.0, places=6)
        cmds.setAttr(str(owner) + ".rotation", 30.0)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".drivenRotation"), -60.0, places=3)
        self.check(owner, 6.0, 2.0, 1.0, crossed=True, rotation=30.0, base=self.base)
        # 生成後に平行掛けへ切り替えられる。
        cmds.setAttr(str(owner) + ".crossed", False)
        self.check(owner, 6.0, 2.0, 1.0, rotation=30.0, base=self.base)

    def test_equal_and_larger_driven(self):
        """同じ半径なら直線部は軸間の線に平行(θ=90度・巻き付け180度)。従動側が大きい場合も接線になる。"""
        owner = BeltDrive.create(None, driverRadius=1.5, drivenRadius=1.5, distance=5.0, name="equal").container
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".tangentAngle"), 90.0, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".driverWrap"), 180.0, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".drivenWrap"), 180.0, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".spanLength"), 5.0, places=5)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".beltLength"), 10.0 + 3.0 * math.pi, places=4)
        self.check(owner, 5.0, 1.5, 1.5)
        for r1, r2, distance, crossed in ((1.0, 3.0, 5.0, False), (1.0, 3.0, 6.5, True), (0.5, 2.5, 3.0, False),
                                          (2.5, 0.75, 4.0, True)):
            with self.subTest(r1=r1, r2=r2, distance=distance, crossed=crossed):
                cmds.setAttr(str(owner) + ".driverRadius", r1)
                cmds.setAttr(str(owner) + ".drivenRadius", r2)
                cmds.setAttr(str(owner) + ".distance", distance)
                cmds.setAttr(str(owner) + ".crossed", crossed)
                self.check(owner, distance, r1, r2, crossed=crossed)

    def test_limits_and_excess(self):
        """共通接線が引けない近さ(平行掛け d < |r1-r2|、十字掛け d < r1+r2)は端で止まり、離すと元へ戻る。"""
        owner = BeltDrive.create(self.base, driverRadius=3.0, drivenRadius=1.0, distance=6.0).container
        for crossed, distance, clamped, excess in ((False, 6.0, 6.0, 0.0), (False, 1.5, 2.0, -0.5),
                                                   (False, 2.0, 2.0, 0.0), (True, 3.0, 4.0, -1.0),
                                                   (True, 4.0, 4.0, 0.0), (True, 0.0, 4.0, -4.0),
                                                   (True, 7.0, 7.0, 0.0), (False, 7.0, 7.0, 0.0)):
            with self.subTest(crossed=crossed, distance=distance):
                cmds.setAttr(str(owner) + ".crossed", crossed)
                cmds.setAttr(str(owner) + ".distance", distance)
                self.assertAlmostEqual(cmds.getAttr(str(owner) + ".clampedDistance"), clamped, places=5)
                self.assertAlmostEqual(cmds.getAttr(str(owner) + ".excess"), excess, places=5)
                self.check(owner, distance, 3.0, 1.0, crossed=crossed, base=self.base)
        # 端では直線部の長さが0になり、平行掛けは小さい円が大きい円に内接する(θ=0)。
        cmds.setAttr(str(owner) + ".distance", 1.0)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".spanLength"), 0.0, places=4)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".tangentAngle"), 0.0, places=2)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".driverWrap"), 360.0, places=2)

    def test_belt_length_matches_polyline(self):
        """beltLengthが、直線部2本と2つの弧を細かい折れ線で測った長さに一致する。"""
        for crossed in (False, True):
            with self.subTest(crossed=crossed):
                name = "length%d" % crossed
                owner = str(BeltDrive.create(None, driverRadius=2.0, drivenRadius=1.25, distance=7.0,
                                             crossed=crossed, name=name).container)
                span = cmds.getAttr(owner + ".spanLength")
                upper, lower = _matrix(owner, "upperSpanMatrix"), _matrix(owner, "lowerSpanMatrix")
                total = 2.0 * span
                # 駆動側の弧は上の接点から+X の反対側を通って下の接点まで、従動側は残りの側を回る。
                for center, radius, first, last, through in (
                        (om.MPoint(), 2.0, om.MPoint() * upper, om.MPoint() * lower, math.pi),
                        (om.MPoint(7.0, 0, 0), 1.25, om.MPoint(span, 0, 0) * upper, om.MPoint(span, 0, 0) * lower, 0.0)):
                    start = math.atan2(first.y - center.y, first.x - center.x)
                    end = math.atan2(last.y - center.y, last.x - center.x)
                    # start から through を通って end へ進む向きの角度の幅。
                    sweep = (end - start) % (2.0 * math.pi)
                    if not (through - start) % (2.0 * math.pi) <= sweep:
                        sweep -= 2.0 * math.pi
                    steps = 2000
                    chord = 2.0 * radius * math.sin(abs(sweep) / steps / 2.0)
                    total += chord * steps
                self.assertAlmostEqual(cmds.getAttr(owner + ".beltLength"), total, delta=2e-3)

    def test_ui_units(self):
        """UIの単位がradian・meterでも、内部の値(cm・radian)の計算は変わらず、unitConversionを作らない。"""
        before = set(cmds.ls(type="unitConversion"))
        cmds.currentUnit(angle="rad", linear="m")
        try:
            owner = BeltDrive.create(self.base, driverRadius=2.0, drivenRadius=1.0, distance=6.0, name="units").container
            self.assertEqual(set(cmds.ls(type="unitConversion")), before)
            expected = BeltDrive.evaluate(6.0, 2.0, 1.0)
            self.assertAlmostEqual(cmds.getAttr(str(owner) + ".distance"), 0.06, places=6)
            self.assertAlmostEqual(cmds.getAttr(str(owner) + ".tangentAngle"), math.radians(expected[2]), places=4)
            self.assertAlmostEqual(cmds.getAttr(str(owner) + ".beltLength"), expected[6] / 100.0, places=5)
        finally:
            cmds.currentUnit(angle="deg", linear="cm")
        self.assertEqual(set(cmds.ls(type="unitConversion")), before)
        cmds.setAttr(str(owner) + ".rotation", 75.0)
        self.check(owner, 6.0, 2.0, 1.0, rotation=75.0, base=self.base)

    def test_base_follow(self):
        """土台の移動・回転に、プーリーと直線部が追従する。"""
        owner = BeltDrive.create(self.base, driverRadius=1.0, drivenRadius=2.0, distance=5.0).container
        cmds.setAttr(self.base + ".translate", -4, 3, 6)
        cmds.setAttr(self.base + ".rotate", -70, 10, 130)
        cmds.setAttr(str(owner) + ".rotation", -40.0)
        self.check(owner, 5.0, 1.0, 2.0, rotation=-40.0, base=self.base)

    def test_invalid_arguments(self):
        """範囲外の半径・distance、boolでないcrossed、transformでない土台、既存の名前を拒否する。"""
        for kwargs in ({"driverRadius": 0}, {"drivenRadius": -1}, {"driverRadius": float("nan")},
                       {"drivenRadius": True}, {"distance": -1}, {"distance": float("inf")}, {"crossed": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                BeltDrive.create(self.base, **kwargs)
        with self.assertRaises(ValueError):
            BeltDrive.create("time1")
        self.assertFalse(cmds.objExists("beltDrive"))
        BeltDrive.create(self.base, name="taken")
        with self.assertRaises(ValueError):
            BeltDrive.create(self.base, name="taken")

    def test_undo_removes_graph(self):
        """生成を1回のUndoで取り消せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        BeltDrive.create(self.base, name="undoBelt")
        self.assertTrue(cmds.objExists("undoBelt"))
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main()
