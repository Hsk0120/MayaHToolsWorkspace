"""Umbrellaの親骨・受け骨・ランナーの行列を、三角形の式と位置の一致(骨の先がつながること)で確認する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import Umbrella


def _matrix(owner, attribute):
    """containerの行列アトリビュートの値。"""
    return om.MMatrix(cmds.getAttr("{}.{}".format(owner, attribute)))


def _point(matrix, x=0.0):
    """行列のローカルX上の点のワールド位置。"""
    return om.MPoint(x, 0.0, 0.0) * matrix


class UmbrellaTest(unittest.TestCase):
    """標準ノードの数値評価・骨のつながり・範囲の端・単位・引数検査を確認する。"""

    def setUp(self):
        """移動・回転した土台を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.base = cmds.createNode("transform", name="umbrellaBase")
        cmds.setAttr(self.base + ".translate", 2, 9, -1)
        cmds.setAttr(self.base + ".rotate", 15, 40, -10)

    def check(self, owner, count, slide, a, b, base=None, startAngle=0.0, tolerance=1e-3):
        """値の出力と、全部の骨の位置・向きを式から求めた期待値と比べる。"""
        clamped, excess, rib, stretcher, radius = Umbrella.evaluate(slide, a, b)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".clampedSlide"), clamped, places=4)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".excess"), excess, places=4)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".radius"), radius, delta=tolerance)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".ribAngle"), rib, delta=0.05)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".stretcherAngle"), stretcher, delta=0.05)
        world = om.MMatrix(cmds.getAttr(base + ".worldMatrix[0]")) if base else om.MMatrix()
        runner = om.MPoint(0.0, -clamped, 0.0) * world
        self.assertTrue(_point(_matrix(owner, "runnerMatrix")).isEquivalent(runner, tolerance))
        depth = (a * a + clamped * clamped - b * b) / (2.0 * clamped)
        for index in range(count):
            azimuth = math.radians(startAngle) + 2.0 * math.pi * index / count
            # 中棒まわりの向きは +X から -Z へ回る(Y軸まわりの右ねじ)。
            joint = om.MPoint(radius * math.cos(azimuth), -depth, -radius * math.sin(azimuth)) * world
            ribMatrix = _matrix(owner, "rib%dMatrix" % index)
            stretcherMatrix = _matrix(owner, "stretcher%dMatrix" % index)
            self.assertTrue(_point(ribMatrix).isEquivalent(om.MPoint() * world, tolerance), index)
            self.assertTrue(_point(stretcherMatrix).isEquivalent(runner, tolerance), index)
            # 親骨の先(a)と受け骨の先(b)が、同じつなぎ目に来る。
            self.assertTrue(_point(ribMatrix, a).isEquivalent(joint, tolerance), index)
            self.assertTrue(_point(stretcherMatrix, b).isEquivalent(joint, tolerance), index)
            # 蝶番(Z)は中棒(土台のY)に垂直で、2本の骨で同じ向き。
            hinge = om.MVector(0.0, 0.0, 1.0) * ribMatrix
            self.assertAlmostEqual(hinge * (om.MVector(0.0, 1.0, 0.0) * world), 0.0, places=5)
            self.assertTrue(hinge.isEquivalent(om.MVector(0.0, 0.0, 1.0) * stretcherMatrix, 1e-5))

    def test_closed_by_default(self):
        """既定のslide(a + b)では閉じていて、親骨と受け骨が中棒に沿う。"""
        owner = Umbrella.create(self.base, count=6, ribLength=6.0, stretcherLength=4.0).container
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".slide"), 10.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".ribAngle"), 0.0, places=4)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".stretcherAngle"), 0.0, places=4)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".radius"), 0.0, places=5)
        self.check(owner, 6, 10.0, 6.0, 4.0, base=self.base)

    def test_opens_as_runner_rises(self):
        """slideを小さくすると開き、全部の骨が式どおりの位置でつながる。"""
        graph = Umbrella.create(self.base, count=8, ribLength=4.0, stretcherLength=5.0, startAngle=20.0)
        owner = graph.container
        self.assertEqual(graph.getCount(), 8)
        previous = -1.0
        for slide in (8.75, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.25):
            with self.subTest(slide=slide):
                cmds.setAttr(str(owner) + ".slide", slide)
                self.check(owner, 8, slide, 4.0, 5.0, base=self.base, startAngle=20.0)
                angle = cmds.getAttr(str(owner) + ".ribAngle")
                self.assertGreater(angle, previous)
                previous = angle

    def test_horizontal_rib(self):
        """b > a のとき、s = sqrt(b^2 - a^2) で親骨が水平(90度)になる。"""
        owner = Umbrella.create(None, count=4, ribLength=3.0, stretcherLength=5.0, slide=4.0, name="flat").container
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".ribAngle"), 90.0, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".radius"), 3.0, places=5)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".stretcherAngle"), math.degrees(math.atan2(3.0, 4.0)),
                               places=3)
        self.check(owner, 4, 4.0, 3.0, 5.0)
        # さらに押し上げると水平を超えて反り返る(おちょこ)。
        cmds.setAttr(str(owner) + ".slide", 3.0)
        self.assertGreater(cmds.getAttr(str(owner) + ".ribAngle"), 90.0)
        self.check(owner, 4, 3.0, 3.0, 5.0)

    def test_limits_and_excess(self):
        """三角形ができる範囲 |a - b| 〜 a + b の外は端で止まり、超えた量がexcessに出て、戻すと元へ戻る。"""
        owner = Umbrella.create(self.base, count=3, ribLength=6.0, stretcherLength=4.0).container
        for slide, clamped, excess in ((12.5, 10.0, 2.5), (10.0, 10.0, 0.0), (0.5, 2.0, -1.5), (2.0, 2.0, 0.0),
                                       (7.0, 7.0, 0.0)):
            with self.subTest(slide=slide):
                cmds.setAttr(str(owner) + ".slide", slide)
                self.assertAlmostEqual(cmds.getAttr(str(owner) + ".clampedSlide"), clamped, places=5)
                self.assertAlmostEqual(cmds.getAttr(str(owner) + ".excess"), excess, places=5)
                self.check(owner, 3, slide, 6.0, 4.0, base=self.base)
        # 下の端では、受け骨が中棒に沿って下を向く(180度)。
        cmds.setAttr(str(owner) + ".slide", 0.0)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".stretcherAngle"), 180.0, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".ribAngle"), 0.0, places=3)
        # a > b では親骨は水平まで開かず、s = sqrt(a^2 - b^2) のとき最大の asin(b / a) になる。
        cmds.setAttr(str(owner) + ".slide", math.sqrt(20.0))
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".ribAngle"), math.degrees(math.asin(4.0 / 6.0)), places=2)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".stretcherAngle"), 90.0, places=2)

    def test_length_attributes_and_base(self):
        """生成後の長さの変更(a < b への入れ替えを含む)と、土台の移動・回転に追従する。"""
        owner = Umbrella.create(self.base, count=5, ribLength=6.0, stretcherLength=4.0, slide=7.0).container
        for a, b, slide in ((6.0, 4.0, 7.0), (5.5, 3.25, 6.0), (3.0, 5.0, 4.5), (4.0, 4.0, 3.0), (4.0, 4.0, -1.0)):
            with self.subTest(a=a, b=b, slide=slide):
                cmds.setAttr(str(owner) + ".ribLength", a)
                cmds.setAttr(str(owner) + ".stretcherLength", b)
                cmds.setAttr(str(owner) + ".slide", slide)
                self.check(owner, 5, slide, a, b, base=self.base)
        cmds.setAttr(str(owner) + ".ribLength", 6.0)
        cmds.setAttr(str(owner) + ".slide", 6.0)
        cmds.setAttr(self.base + ".translate", -4, 3, 6)
        cmds.setAttr(self.base + ".rotate", -70, 10, 130)
        self.check(owner, 5, 6.0, 6.0, 4.0, base=self.base)

    def test_ui_units(self):
        """UIの単位がradian・meterでも、内部の値(cm・radian)の計算は変わらず、unitConversionを作らない。"""
        before = set(cmds.ls(type="unitConversion"))
        cmds.currentUnit(angle="rad", linear="m")
        try:
            owner = Umbrella.create(self.base, count=4, ribLength=6.0, stretcherLength=4.0, slide=7.0,
                                    name="units").container
            self.assertEqual(set(cmds.ls(type="unitConversion")), before)
            self.assertAlmostEqual(cmds.getAttr(str(owner) + ".slide"), 0.07, places=6)
            expected = Umbrella.evaluate(7.0, 6.0, 4.0)
            self.assertAlmostEqual(cmds.getAttr(str(owner) + ".ribAngle"), math.radians(expected[2]), places=4)
            self.assertAlmostEqual(cmds.getAttr(str(owner) + ".radius"), expected[4] / 100.0, places=5)
        finally:
            cmds.currentUnit(angle="deg", linear="cm")
        self.check(owner, 4, 7.0, 6.0, 4.0, base=self.base)

    def test_invalid_arguments(self):
        """範囲外の本数・長さ・slide、transformでない土台、既存の名前を拒否する。"""
        for kwargs in ({"count": 0}, {"count": 2.5}, {"count": True}, {"count": 65}, {"ribLength": 0},
                       {"stretcherLength": -1}, {"ribLength": float("nan")}, {"slide": -1},
                       {"slide": float("inf")}, {"startAngle": float("nan")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Umbrella.create(self.base, **kwargs)
        with self.assertRaises(ValueError):
            Umbrella.create("time1")
        self.assertFalse(cmds.objExists("umbrella"))
        Umbrella.create(self.base, name="taken")
        with self.assertRaises(ValueError):
            Umbrella.create(self.base, name="taken")

    def test_undo_removes_graph(self):
        """生成を1回のUndoで取り消せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        Umbrella.create(self.base, name="undoUmbrella", count=3)
        self.assertTrue(cmds.objExists("undoUmbrella"))
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main()
