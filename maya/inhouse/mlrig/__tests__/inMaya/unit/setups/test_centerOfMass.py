"""CenterOfMassの重心・床への投影・支えとのずれを、各ノードのワールド位置から独立に計算した値で確かめる。"""

import math
import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import CenterOfMass

#: 位置(cm)の許容。wtAddMatrix・decomposeMatrix・composeMatrix は倍精度なので丸めの範囲で確かめる。
TOLERANCE = 1e-6


def _position(node):
    return om2.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))


def _translation(owner, attribute):
    matrix = om2.MMatrix(cmds.getAttr(owner + "." + attribute))
    return om2.MVector(matrix[12], matrix[13], matrix[14])


class CenterOfMassTest(unittest.TestCase):
    """式との一致、質量・割合の変更、床と支え、回転・スケールした親、所有とUndo・引数を確認する。"""

    def setUp(self):
        """回転・スケールした親の下に、3つの体節(根元と先)と先の無い体節、2つの支えを作る。"""
        cmds.file(new=True, force=True)
        self.parent = cmds.createNode("transform", name="body")
        cmds.setAttr(self.parent + ".translate", 2, 5, -1)
        cmds.setAttr(self.parent + ".rotate", 20, -35, 10)
        cmds.setAttr(self.parent + ".scale", 1.5, 0.8, 1.2)
        self.nodes = []
        for index, position in enumerate(((0, 0, 0), (0, 4, 0), (3, 4, 1), (5, 2, 1), (-1, -4, 0), (-1, -8, 1))):
            cmds.select(clear=True)
            joint = cmds.joint(name="j" + str(index))
            cmds.parent(joint, self.parent if index == 0 else self.nodes[0])
            cmds.xform(joint, objectSpace=True, translation=position)
            cmds.setAttr(joint + ".rotate", 10 * index, -5 * index, 7 * index)
            self.nodes.append(joint)
        self.segments = [
            dict(start=self.nodes[0], end=self.nodes[1], mass=50.0, ratio=0.5),
            dict(start=self.nodes[1], end=self.nodes[2], mass=3.0, ratio=0.436),
            dict(start=self.nodes[4], end=self.nodes[5], mass=10.0, ratio=0.25),
            dict(start=self.nodes[3], mass=1.5),
        ]
        self.feet = [cmds.createNode("transform", name=name, parent=self.parent) for name in ("footL", "footR")]
        cmds.setAttr(self.feet[0] + ".translate", 1, -9, 2)
        cmds.setAttr(self.feet[1] + ".translate", -2, -9, -1)
        self.owner = str(CenterOfMass.create(self.segments, name="com", support=self.feet, groundHeight=0.5)
                         .container)

    def _expected(self):
        """containerの現在の質量・割合と各ノードのワールド位置から重心を求める。"""
        points, masses = [], []
        for index, segment in enumerate(self.segments):
            mass = cmds.getAttr("{}.mass{}".format(self.owner, index))
            start = _position(segment["start"])
            if segment.get("end") is None:
                point = start
            else:
                ratio = cmds.getAttr("{}.ratio{}".format(self.owner, index))
                point = start * (1.0 - ratio) + _position(segment["end"]) * ratio
            points.append(point)
            masses.append(mass)
        total = sum(masses)
        center = om2.MVector()
        for point, mass in zip(points, masses):
            center += point * (mass / total)
        return center, total

    def _check(self, message=None):
        center, total = self._expected()
        ground = cmds.getAttr(self.owner + ".groundHeight")
        self.assertLess((_translation(self.owner, "centerMatrix") - center).length(), TOLERANCE, message)
        self.assertLess((_translation(self.owner, "groundMatrix") - om2.MVector(center.x, ground, center.z)).length(),
                        TOLERANCE, message)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".totalMass"), total, 9, message)
        support = (_position(self.feet[0]) + _position(self.feet[1])) * 0.5
        support.y = ground
        self.assertLess((_translation(self.owner, "supportMatrix") - support).length(), TOLERANCE, message)
        expected = math.hypot(center.x - support.x, center.z - support.z)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".balance"), expected, 6, message)
        rotation = om2.MMatrix(cmds.getAttr(self.owner + ".centerMatrix"))
        for row in range(3):
            for column in range(3):
                self.assertAlmostEqual(rotation[row * 4 + column], 1.0 if row == column else 0.0, 9)

    def test_matches_formula(self):
        """作成直後と、ランダムな姿勢10通りで、重心・床の点・支え・balanceが式と一致する。"""
        self._check("rest")
        generator = random.Random(26)
        for trial in range(10):
            for node in self.nodes:
                cmds.setAttr(node + ".rotate", *[generator.uniform(-90, 90) for _ in range(3)])
            cmds.setAttr(self.parent + ".translate", *[generator.uniform(-5, 5) for _ in range(3)])
            cmds.setAttr(self.feet[0] + ".translateX", generator.uniform(-3, 3))
            self._check(trial)

    def test_mass_and_ratio_changes(self):
        """質量・割合・床の高さを変えても式と一致し、1つの体節だけに質量があれば重心はその点になる。"""
        cmds.setAttr(self.owner + ".mass1", 40.0)
        cmds.setAttr(self.owner + ".ratio0", 0.9)
        cmds.setAttr(self.owner + ".ratio2", 0.0)
        cmds.setAttr(self.owner + ".groundHeight", -3.0)
        self._check("changed")
        for index in (0, 1, 3):
            cmds.setAttr("{}.mass{}".format(self.owner, index), 0.0)
        cmds.setAttr(self.owner + ".ratio2", 1.0)
        self.assertLess((_translation(self.owner, "centerMatrix") - _position(self.nodes[5])).length(), TOLERANCE)
        self._check("single")

    def test_python_center(self):
        """Python版の center() がDGの重心と一致する。"""
        points, masses = [], []
        for segment in self.segments:
            start = _position(segment["start"])
            point = start if segment.get("end") is None else (
                start * (1 - segment["ratio"]) + _position(segment["end"]) * segment["ratio"])
            points.append((point.x, point.y, point.z))
            masses.append(segment["mass"])
        expected = CenterOfMass.center(points, masses)
        result = _translation(self.owner, "centerMatrix")
        for axis in range(3):
            self.assertAlmostEqual(result[axis], expected[axis], 6)
        with self.assertRaises(ValueError):
            CenterOfMass.center(points, masses[:-1])
        with self.assertRaises(ValueError):
            CenterOfMass.center(points, [0.0] * len(points))

    def test_dempster_table(self):
        """人体の体節の表は、左右の腕・脚を2回数えると合計がほぼ1になる。"""
        table = CenterOfMass.DEMPSTER
        total = table["headNeck"][0] + table["trunk"][0] + 2 * sum(
            table[key][0] for key in ("upperArm", "forearm", "hand", "thigh", "shank", "foot"))
        self.assertAlmostEqual(total, 1.0, 6)
        self.assertTrue(all(0.0 <= ratio <= 1.0 for _, ratio in table.values()))

    def test_without_support(self):
        """支えを渡さなければ supportMatrix・balance は作らない。"""
        owner = str(CenterOfMass.create(self.segments[:1], name="com2").container)
        self.assertFalse(cmds.attributeQuery("balance", node=owner, exists=True))
        center = (_position(self.nodes[0]) + _position(self.nodes[1])) * 0.5
        self.assertLess((_translation(owner, "centerMatrix") - center).length(), TOLERANCE)
        self.assertAlmostEqual(_translation(owner, "groundMatrix").y, 0.0, 9)

    def test_container_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消えRedoで戻る。"""
        nodes = cmds.container(self.owner, query=True, nodeList=True) or []
        self.assertTrue(any(cmds.nodeType(node) == "wtAddMatrix" for node in nodes))
        allowed = ("plusMinusAverage", "clamp", "wtAddMatrix", "multiplyDivide", "reverse", "decomposeMatrix",
                   "composeMatrix", "distanceBetween")
        self.assertTrue(all(cmds.nodeType(node) in allowed for node in nodes), sorted(set(map(cmds.nodeType, nodes))))
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        CenterOfMass.create(self.segments, name="com3", support=self.feet)
        self.assertTrue(cmds.objExists("com3"))
        cmds.undo()
        self.assertFalse(cmds.objExists("com3"))
        cmds.redo()
        self.assertTrue(cmds.objExists("com3.balance"))

    def test_arguments(self):
        """不正な引数は ValueError。"""
        cases = [
            dict(segments=[]),
            dict(segments=[dict(start="missing")]),
            dict(segments=[dict(end=self.nodes[0])]),
            dict(segments=[dict(start=self.nodes[0], end=self.nodes[0])]),
            dict(segments=[dict(start=self.nodes[0], mass=-1.0)]),
            dict(segments=[dict(start=self.nodes[0], mass=0.0)]),
            dict(segments=[dict(start=self.nodes[0], end=self.nodes[1], ratio=1.5)]),
            dict(segments=[dict(start=self.nodes[0], weight=1.0)]),
            dict(segments=[dict(start=self.nodes[0])], support=["missing"]),
            dict(segments=[dict(start=self.nodes[0])], groundHeight=float("nan")),
            dict(segments=[dict(start=self.nodes[0])], name="com"),
        ]
        for case in cases:
            with self.assertRaises(ValueError, msg=str(case)):
                CenterOfMass.create(**case)


if __name__ == "__main__":
    unittest.main(argv=["center_of_mass"], exit=False, verbosity=2)
