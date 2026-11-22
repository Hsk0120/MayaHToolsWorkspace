"""StewartPlatformの脚の長さ・超過・シリンダーの向き・ロッドの位置を、試験側で独立に求めたワールド位置で確かめる。"""

import math
import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import StewartPlatform

BASE_RADIUS = 3.0
TOP_RADIUS = 2.0
HEIGHT = 4.0
MINIMUM = 3.0
MAXIMUM = 6.0
BASE_ANGLES = (15, 105, 135, 225, 255, 345)
TOP_ANGLES = (45, 75, 165, 195, 285, 315)


def _matrix(node):
    """ノードのワールドマトリクス。"""
    return om2.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))


def _point(node):
    """ノードのワールド位置。"""
    return om2.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))


class StewartPlatformTest(unittest.TestCase):
    """作成時・脚の長さ・シリンダーとロッド・止めと復帰・minimum/maximum・Python版・台座の移動・Undo・引数を確認する。"""

    def setUp(self):
        """少し回して動かした親の下に、台座(6つの取り付け点)と天板(6つの取り付け点)、6本のシリンダーとロッドを置く。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.space = cmds.createNode("transform", name="simulator")
        cmds.setAttr(self.space + ".translate", 4.0, 1.0, -2.0)
        cmds.setAttr(self.space + ".rotate", 10.0, 25.0, -5.0)
        self.base = cmds.createNode("transform", name="base", parent=self.space)
        self.platform = cmds.createNode("transform", name="platform", parent=self.space)
        cmds.setAttr(self.platform + ".translateY", HEIGHT)
        self.bases, self.tops, self.cylinders, self.rods = [], [], [], []
        for index, (low, high) in enumerate(zip(BASE_ANGLES, TOP_ANGLES)):
            low, high = math.radians(low), math.radians(high)
            anchor = cmds.createNode("transform", name="baseAnchor%d" % index, parent=self.base)
            cmds.setAttr(anchor + ".translate", BASE_RADIUS * math.cos(low), 0.0, -BASE_RADIUS * math.sin(low))
            cmds.setAttr(anchor + ".rotateY", 20.0 * index)
            self.bases.append(anchor)
            anchor = cmds.createNode("transform", name="topAnchor%d" % index, parent=self.platform)
            cmds.setAttr(anchor + ".translate", TOP_RADIUS * math.cos(high), 0.0, -TOP_RADIUS * math.sin(high))
            self.tops.append(anchor)
            cylinder = cmds.createNode("transform", name="cylinder%d" % index, parent=self.space)
            cmds.setAttr(cylinder + ".rotateOrder", index % 6)
            self.cylinders.append(cylinder)
            self.rods.append(cmds.createNode("transform", name="rod%d" % index, parent=cylinder))
        self.setup = StewartPlatform.create(self.bases, self.tops, self.cylinders, self.rods, MINIMUM, MAXIMUM,
                                            name="stewartRig")
        self.owner = str(self.setup.container)

    def _get(self, attribute, index=None):
        """containerの出力の値。"""
        return cmds.getAttr(self.owner + "." + attribute + ("" if index is None else "[%d]" % index))

    def _pose(self, translate=(0.0, HEIGHT, 0.0), rotate=(0.0, 0.0, 0.0)):
        """天板の位置と回転(度)を入れる。"""
        cmds.setAttr(self.platform + ".translate", *translate)
        cmds.setAttr(self.platform + ".rotate", *rotate)

    def _lengths(self):
        """試験側で独立に求めた、取り付け点どうしのワールドの距離。"""
        return [(_point(top) - _point(base)).length() for base, top in zip(self.bases, self.tops)]

    def test_rest(self):
        """生成時は extension が0、超過0、reachable = 1、固定値は脚の数と生成時の長さ。"""
        expected = self._lengths()
        self.assertEqual(self._get("legCount"), 6)
        self.assertAlmostEqual(self._get("minimum"), MINIMUM, places=6)
        self.assertAlmostEqual(self._get("maximum"), MAXIMUM, places=6)
        self.assertAlmostEqual(self._get("maxExcess"), 0.0, places=9)
        self.assertEqual(self._get("reachable"), 1.0)
        for index in range(6):
            self.assertAlmostEqual(self._get("restLength", index), expected[index], places=6)
            self.assertAlmostEqual(self._get("length", index), expected[index], places=6)
            self.assertAlmostEqual(self._get("extension", index), 0.0, places=6)
            self.assertAlmostEqual(self._get("excess", index), 0.0, places=9)
        # 対称な配置なので、生成時の脚はすべて同じ長さ。
        self.assertAlmostEqual(max(expected) - min(expected), 0.0, places=6)

    def test_lengths(self):
        """天板を6自由度で動かしても、length は取り付け点のワールドの距離、stroke は範囲の中の割合。"""
        random.seed(5)
        for _ in range(12):
            self._pose((random.uniform(-1, 1), HEIGHT + random.uniform(-0.6, 0.8), random.uniform(-1, 1)),
                       (random.uniform(-15, 15), random.uniform(-25, 25), random.uniform(-15, 15)))
            expected = self._lengths()
            for index in range(6):
                self.assertAlmostEqual(self._get("length", index), expected[index], places=6)
                self.assertAlmostEqual(self._get("extension", index), expected[index] - self._get("restLength", index),
                                       places=6)
                self.assertAlmostEqual(self._get("stroke", index), (expected[index] - MINIMUM) / (MAXIMUM - MINIMUM),
                                       places=6)

    def test_cylindersAndRods(self):
        """シリンダーは台座側の取り付け点にあり +Y が天板側の取り付け点を向き、+X は取り付け点の +X に寄る。
        範囲内ではロッドの原点が天板側の取り付け点に重なる。"""
        random.seed(8)
        for _ in range(10):
            self._pose((random.uniform(-0.8, 0.8), HEIGHT + random.uniform(-0.4, 0.6), random.uniform(-0.8, 0.8)),
                       (random.uniform(-12, 12), random.uniform(-20, 20), random.uniform(-12, 12)))
            self.assertEqual(self._get("reachable"), 1.0)
            for index in range(6):
                base, top = _point(self.bases[index]), _point(self.tops[index])
                matrix = _matrix(self.cylinders[index])
                self.assertAlmostEqual((_point(self.cylinders[index]) - base).length(), 0.0, places=6)
                direction = (top - base).normal()
                axisY = om2.MVector(matrix[4], matrix[5], matrix[6])
                self.assertAlmostEqual((axisY - direction).length(), 0.0, places=6)
                # +X は、取り付け点の +X から脚の向きの成分を除いた向き。
                anchor = _matrix(self.bases[index])
                reference = om2.MVector(anchor[0], anchor[1], anchor[2])
                expected = (reference - direction * (reference * direction)).normal()
                axisX = om2.MVector(matrix[0], matrix[1], matrix[2])
                self.assertAlmostEqual((axisX - expected).length(), 0.0, places=6)
                self.assertTrue(matrix.isEquivalent(om2.MMatrix(self._get("cylinderMatrix", index)), 1e-8))
                self.assertAlmostEqual((_point(self.rods[index]) - top).length(), 0.0, places=6)
                self.assertAlmostEqual(cmds.getAttr(self.rods[index] + ".translateY"), self._get("length", index),
                                       places=6)

    def test_limitAndRecover(self):
        """脚が maximum を超えるとロッドは maximum で止まり、取り付け点から excess だけ離れる。戻すと超過0に戻る。"""
        self._pose((0.0, HEIGHT + 3.0, 0.0))
        expected = self._lengths()
        self.assertGreater(min(expected), MAXIMUM)
        for index in range(6):
            excess = expected[index] - MAXIMUM
            self.assertAlmostEqual(self._get("clampedLength", index), MAXIMUM, places=6)
            self.assertAlmostEqual(self._get("excess", index), excess, places=6)
            self.assertAlmostEqual(cmds.getAttr(self.rods[index] + ".translateY"), MAXIMUM, places=6)
            self.assertAlmostEqual((_point(self.rods[index]) - _point(self.tops[index])).length(), excess, places=6)
            self.assertGreater(self._get("stroke", index), 1.0)
        self.assertAlmostEqual(self._get("maxExcess"), max(expected) - MAXIMUM, places=6)
        self.assertEqual(self._get("reachable"), 0.0)
        # 縮みすぎ: 負の超過。
        self._pose((0.0, 1.5, 0.0))
        expected = self._lengths()
        self.assertLess(max(expected), MINIMUM)
        for index in range(6):
            self.assertAlmostEqual(self._get("clampedLength", index), MINIMUM, places=6)
            self.assertAlmostEqual(self._get("excess", index), expected[index] - MINIMUM, places=6)
            self.assertLess(self._get("stroke", index), 0.0)
        self.assertAlmostEqual(self._get("maxExcess"), MINIMUM - min(expected), places=6)
        self.assertEqual(self._get("reachable"), 0.0)
        # 一部の脚だけが超える傾き: maxExcess はその最大。
        self._pose((3.5, HEIGHT + 0.5, 0.0), (0.0, 0.0, 6.0))
        excess = [max(value - MAXIMUM, 0.0) - max(MINIMUM - value, 0.0) for value in self._lengths()]
        self.assertTrue(any(value == 0.0 for value in excess) and any(value != 0.0 for value in excess))
        for index in range(6):
            self.assertAlmostEqual(self._get("excess", index), excess[index], places=6)
        self.assertAlmostEqual(self._get("maxExcess"), max(abs(value) for value in excess), places=6)
        self.assertEqual(self._get("reachable"), 0.0)
        self._pose()
        self.assertEqual(self._get("reachable"), 1.0)
        for index in range(6):
            self.assertAlmostEqual(self._get("excess", index), 0.0, places=9)
            self.assertAlmostEqual((_point(self.rods[index]) - _point(self.tops[index])).length(), 0.0, places=6)

    def test_limitAttributes(self):
        """containerの minimum・maximum を変えると、止める長さと超過がそれに従う。"""
        rest = self._get("restLength", 0)
        cmds.setAttr(self.owner + ".maximum", rest - 0.5)
        cmds.setAttr(self.owner + ".minimum", 1.0)
        for index in range(6):
            self.assertAlmostEqual(self._get("clampedLength", index), rest - 0.5, places=6)
            self.assertAlmostEqual(self._get("excess", index), 0.5, places=6)
            self.assertAlmostEqual(self._get("stroke", index), (rest - 1.0) / (rest - 1.5), places=6)
        self.assertEqual(self._get("reachable"), 0.0)

    def test_pythonMatchesGraph(self):
        """legs はDGと同じ値を返す。"""
        random.seed(13)
        for _ in range(10):
            self._pose((random.uniform(-2, 2), HEIGHT + random.uniform(-2.5, 3), random.uniform(-2, 2)),
                       (random.uniform(-30, 30), random.uniform(-40, 40), random.uniform(-30, 30)))
            result = StewartPlatform.legs([tuple(_point(node)) for node in self.bases],
                                          [tuple(_point(node)) for node in self.tops], MINIMUM, MAXIMUM)
            for key in ("length", "clampedLength", "excess", "stroke"):
                for index in range(6):
                    self.assertAlmostEqual(result[key][index], self._get(key, index), places=6)
            self.assertAlmostEqual(result["maxExcess"], self._get("maxExcess"), places=6)
            self.assertEqual(result["reachable"], self._get("reachable"))

    def test_baseMoves(self):
        """台座や全体の親を動かしても、天板との相対が同じなら長さは変わらず、シリンダーは取り付け点に付いていく。"""
        self._pose((0.5, HEIGHT + 0.4, -0.3), (5.0, 10.0, -4.0))
        before = [self._get("length", index) for index in range(6)]
        cmds.setAttr(self.space + ".translate", -3.0, 2.0, 5.0)
        cmds.setAttr(self.space + ".rotate", -30.0, 80.0, 15.0)
        for index in range(6):
            self.assertAlmostEqual(self._get("length", index), before[index], places=6)
            self.assertAlmostEqual((_point(self.cylinders[index]) - _point(self.bases[index])).length(), 0.0, places=6)
            self.assertAlmostEqual((_point(self.rods[index]) - _point(self.tops[index])).length(), 0.0, places=6)
        # 台座だけを下げると、すべての脚が伸びる。
        cmds.setAttr(self.base + ".translateY", -0.5)
        for index in range(6):
            self.assertGreater(self._get("length", index), before[index])

    def test_axesAndWithoutParts(self):
        """aimAxis = x・upAxis = z ではシリンダーの +X が相手を向きロッドは translateX。シリンダー無し・接続なしでも出力する。"""
        cmds.file(new=True, force=True)
        bases = [cmds.createNode("transform", name="b%d" % index) for index in range(3)]
        tops = [cmds.createNode("transform", name="t%d" % index) for index in range(3)]
        cylinders = [cmds.createNode("transform", name="c%d" % index) for index in range(3)]
        rods = [cmds.createNode("transform", name="r%d" % index, parent=cylinders[index]) for index in range(3)]
        for index in range(3):
            cmds.setAttr(bases[index] + ".translate", 2.0 * index, 0.0, 0.0)
            cmds.setAttr(tops[index] + ".translate", 2.0 * index + 1.0, 3.0, 0.5)
        setup = StewartPlatform.create(bases, tops, cylinders, rods, name="stewartX", aimAxis="x", upAxis="z")
        owner = str(setup.container)
        rest = math.sqrt(1.0 + 9.0 + 0.25)
        self.assertAlmostEqual(cmds.getAttr(owner + ".minimum"), rest * 0.75, places=6)
        self.assertAlmostEqual(cmds.getAttr(owner + ".maximum"), rest * 1.25, places=6)
        for index in range(3):
            matrix = _matrix(cylinders[index])
            direction = (_point(tops[index]) - _point(bases[index])).normal()
            self.assertAlmostEqual((om2.MVector(matrix[0], matrix[1], matrix[2]) - direction).length(), 0.0, places=6)
            self.assertAlmostEqual(cmds.getAttr(rods[index] + ".translateX"), rest, places=6)
            self.assertEqual(cmds.getAttr(rods[index] + ".translateY"), 0.0)
        free = cmds.createNode("transform", name="freeCylinder")
        plain = StewartPlatform.create(bases[:1], tops[:1], [free], name="stewartPlain", connect=False)
        self.assertFalse(cmds.listConnections(free, source=True, destination=False))
        self.assertAlmostEqual(cmds.getAttr(str(plain.container) + ".length[0]"), rest, places=6)
        bare = StewartPlatform.create(bases[:2], tops[:2], name="stewartBare")
        self.assertEqual(cmds.getAttr(str(bare.container) + ".legCount"), 2)

    def test_ownershipAndUndo(self):
        """演算ノードはcontainerが所有し、1回のUndoで作成全体とシリンダー・ロッドの接続が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {node for node in cmds.ls() if node.startswith("stewartRig_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        self.assertEqual(sum(cmds.nodeType(member) == "aimMatrix" for member in members), 6)
        cmds.file(new=True, force=True)
        base = cmds.createNode("transform", name="undoBase")
        top = cmds.createNode("transform", name="undoTop")
        cmds.setAttr(top + ".translateY", 2.0)
        cylinder = cmds.createNode("transform", name="undoCylinder")
        rod = cmds.createNode("transform", name="undoRod", parent=cylinder)
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        StewartPlatform.create([base], [top], [cylinder], [rod], name="stewartUndo")
        self.assertTrue(cmds.listConnections(rod + ".translateY", source=True, destination=False))
        cmds.undo()
        self.assertFalse(cmds.objExists("stewartUndo"))
        self.assertEqual(set(cmds.ls()), before)
        self.assertFalse(cmds.listConnections(cylinder, source=True, destination=False))
        self.assertFalse(cmds.listConnections(rod + ".translateY", source=True, destination=False))
        cmds.redo()
        self.assertTrue(cmds.objExists("stewartUndo.length[0]"))

    def test_invalidArguments(self):
        """不正な引数は ValueError で、containerを残さない。"""
        base = cmds.createNode("transform", name="newBase")
        top = cmds.createNode("transform", name="newTop")
        cmds.setAttr(top + ".translateY", 2.0)
        cylinder = cmds.createNode("transform", name="newCylinder")
        rod = cmds.createNode("transform", name="newRod", parent=cylinder)
        loose = cmds.createNode("transform", name="looseRod")
        joint = cmds.createNode("joint", name="jointCylinder")
        same = cmds.createNode("transform", name="sameTop")
        cases = [
            {"baseAnchors": []},
            {"baseAnchors": base},
            {"platformAnchors": [top, same]},
            {"platformAnchors": [base]},
            {"platformAnchors": [same]},
            {"cylinders": [cylinder, loose]},
            {"cylinders": [joint]},
            {"cylinders": [cylinder], "rods": [loose]},
            {"rods": [rod]},
            {"cylinders": [self.cylinders[0]]},
            {"baseAnchors": [joint.replace("jointCylinder", "newCylinder")], "cylinders": [cylinder]},
            {"minimum": 0.0},
            {"minimum": 3.0, "maximum": 3.0},
            {"maximum": True},
            {"maximum": float("inf")},
            {"aimAxis": "w"},
            {"aimAxis": "x", "upAxis": "x"},
            {"name": self.owner},
        ]
        for case in cases:
            arguments = {"baseAnchors": [base], "platformAnchors": [top], "name": "stewartBad"}
            arguments.update(case)
            with self.subTest(case=case), self.assertRaises(ValueError):
                StewartPlatform.create(**arguments)
        self.assertFalse(cmds.objExists("stewartBad"))
        with self.assertRaises(ValueError):
            StewartPlatform.legs([(0, 0, 0)], [], 1.0, 2.0)


if __name__ == "__main__":
    unittest.main()
