"""BodyProportionの骨の移動・スケールを、独立に計算した値と比べて確かめる。"""

import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import BodyProportion


def _close(test, first, second, tolerance=1e-6):
    """2つの列の各成分が誤差の範囲で等しいことを確かめる。"""
    first, second = list(first), list(second)
    test.assertEqual(len(first), len(second))
    for a, b in zip(first, second):
        test.assertAlmostEqual(a, b, delta=tolerance)


def _world(node):
    return list(om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]")))


class BodyProportionTest(unittest.TestCase):
    """作成直後・独立計算との一致・clamp・正負の量・量と範囲の変更・接続なし・UI単位・所有とUndo・引数。"""

    def setUp(self):
        """回転・一様scale 2の胴の下に、肩・肘・手首の腕(joint、jointOrient付き)を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.body = cmds.createNode("transform", name="body")
        cmds.setAttr(self.body + ".translate", 1, 5, -2)
        cmds.setAttr(self.body + ".rotate", 10, 25, -15)
        cmds.setAttr(self.body + ".scale", 2, 2, 2)
        self.joints = []
        parent = self.body
        for name, translate, orient in (("shoulder", (1.5, 0.2, 0), (0, 0, -10)), ("elbow", (3.0, 0, -0.2), (0, 15, 0)),
                                        ("wrist", (2.5, 0.1, 0.1), (5, 0, 0))):
            joint = cmds.createNode("joint", name=name, parent=parent)
            cmds.setAttr(joint + ".translate", *translate)
            cmds.setAttr(joint + ".jointOrient", *orient)
            parent = joint
            self.joints.append(cmds.ls(joint, long=True)[0])
        cmds.setAttr(self.joints[0] + ".scale", 1.0, 1.1, 0.9)
        self.rest = {joint: (cmds.getAttr(joint + ".translate")[0], cmds.getAttr(joint + ".scale")[0])
                     for joint in self.joints}

    def _parameters(self):
        return [
            {"name": "armLength", "minimum": -0.5, "maximum": 1.0, "targets": {
                self.joints[1]: {"translate": (1.0, 0, 0)},
                self.joints[2]: {"translate": (0.8, 0, 0), "translateNegative": (-0.4, 0.1, 0)}}},
            {"name": "shoulderWidth", "targets": {self.joints[0]: {"translate": (0.6, 0.1, 0)}}},
            {"name": "armThickness", "minimum": -1.0, "maximum": 2.0, "targets": {
                self.joints[0]: {"scale": (0, 0.3, 0.3), "scaleNegative": (0, -0.2, -0.1)},
                self.joints[1]: {"scale": (0.05, 0.2, 0.2)}}},
        ]

    def _expected(self, values, parameters=None):
        """骨ごとの (translate, scale) を独立に求める。"""
        parameters = parameters or self._parameters()
        result = {}
        for joint in self.joints:
            translate, scale = [list(v) for v in self.rest[joint]]
            for parameter in parameters:
                value = values.get(parameter["name"], 0.0)
                low, high = parameter.get("minimum", -1.0), parameter.get("maximum", 1.0)
                value = min(max(value, low), high)
                amounts = parameter["targets"].get(joint)
                if amounts is None:
                    continue
                for role, target in (("translate", translate), ("scale", scale)):
                    positive = amounts.get(role, (0, 0, 0))
                    negative = amounts.get(role + "Negative", tuple(-v for v in positive))
                    for axis in range(3):
                        target[axis] += value * positive[axis] if value >= 0 else -value * negative[axis]
            result[joint] = (translate, scale)
        return result

    def _check(self, values):
        for joint, (translate, scale) in self._expected(values).items():
            _close(self, cmds.getAttr(joint + ".translate")[0], translate)
            _close(self, cmds.getAttr(joint + ".scale")[0], scale)

    def test_rest_is_unchanged(self):
        before = [_world(joint) for joint in self.joints]
        graph = BodyProportion.create(self._parameters(), name="proportion")
        for joint, matrix in zip(self.joints, before):
            _close(self, _world(joint), matrix, 1e-9)
        self.assertEqual(graph.getParameters(), ["armLength", "shoulderWidth", "armThickness"])
        for joint in self.joints:
            self.assertIsNotNone(cmds.listConnections(joint + ".translate", source=True, destination=False))

    def test_matches_independent_values_and_clamps(self):
        graph = BodyProportion.create(self._parameters(), name="proportion")
        owner = str(graph.container)
        generator = random.Random(4)
        for _ in range(15):
            values = {name: generator.uniform(-2.5, 2.5) for name in ("armLength", "shoulderWidth", "armThickness")}
            for name, value in values.items():
                cmds.setAttr(owner + "." + name, value)
            self._check(values)
            # Python版も同じ値になる(肘のtranslate)。
            elbow = self.joints[1]
            python = BodyProportion.evaluate(self.rest[elbow][0], [(values["armLength"], -0.5, 1.0)],
                                             [((1.0, 0, 0), (-1.0, 0, 0))])
            _close(self, cmds.getAttr(elbow + ".translate")[0], python)
        # 範囲の外は端の値と同じ。
        cmds.setAttr(owner + ".armLength", 5.0)
        far = cmds.getAttr(self.joints[1] + ".translate")[0]
        cmds.setAttr(owner + ".armLength", 1.0)
        _close(self, cmds.getAttr(self.joints[1] + ".translate")[0], far)

    def test_negative_side_uses_its_own_amount(self):
        graph = BodyProportion.create(self._parameters(), name="proportion")
        owner = str(graph.container)
        cmds.setAttr(owner + ".armLength", -0.5)
        wrist = self.joints[2]
        rest = self.rest[wrist][0]
        _close(self, cmds.getAttr(wrist + ".translate")[0], (rest[0] - 0.2, rest[1] + 0.05, rest[2]))
        # 負の量を省略した肘は、正の量と同じ傾きで反対へ動く。
        _close(self, cmds.getAttr(self.joints[1] + ".translate")[0],
               (self.rest[self.joints[1]][0][0] - 0.5,) + tuple(self.rest[self.joints[1]][0][1:]))

    def test_edit_amounts_and_limits(self):
        graph = BodyProportion.create(self._parameters(), name="proportion")
        owner = str(graph.container)
        cmds.setAttr(owner + ".armLengthTranslate0", 2.0, 0.5, 0.0)
        cmds.setAttr(owner + ".armLengthMaximum", 2.0)
        cmds.setAttr(owner + ".armLength", 1.5)
        rest = self.rest[self.joints[1]][0]
        _close(self, cmds.getAttr(self.joints[1] + ".translate")[0], (rest[0] + 3.0, rest[1] + 0.75, rest[2]))
        cmds.setAttr(owner + ".armLengthMinimum", 0.0)
        cmds.setAttr(owner + ".armLength", -1.0)
        _close(self, cmds.getAttr(self.joints[1] + ".translate")[0], rest)

    def test_values_round_trip(self):
        graph = BodyProportion.create(self._parameters(), name="proportion")
        graph.setValues({"armLength": 0.4, "armThickness": -0.6})
        self.assertEqual(graph.getValues(), {"armLength": 0.4, "shoulderWidth": 0.0, "armThickness": -0.6})
        self._check(graph.getValues())
        with self.assertRaises(ValueError):
            graph.setValues({"legLength": 1.0})

    def test_without_connect(self):
        graph = BodyProportion.create(self._parameters(), name="proportion", connect=False)
        owner = str(graph.container)
        cmds.setAttr(owner + ".shoulderWidth", 1.0)
        for joint in self.joints:
            self.assertFalse(cmds.listConnections(joint + ".translate", source=True, destination=False))
            _close(self, cmds.getAttr(joint + ".translate")[0], self.rest[joint][0])
        # 骨の番号は定義に最初に現れた順(肘・手首・肩)。
        order = [joint.getFullName() for joint in graph.getJoints()]
        self.assertEqual(order, [self.joints[1], self.joints[2], self.joints[0]])
        expected = self._expected({"shoulderWidth": 1.0})[self.joints[0]]
        _close(self, cmds.getAttr(owner + ".translate2")[0], expected[0])
        _close(self, cmds.getAttr(owner + ".scale2")[0], expected[1])

    def test_millimeters(self):
        cmds.currentUnit(linear="mm")
        before = [_world(joint) for joint in self.joints]
        conversions = set(cmds.ls(type="unitConversion"))
        graph = BodyProportion.create(self._parameters(), name="proportion")
        owner = str(graph.container)
        for joint, matrix in zip(self.joints, before):
            _close(self, _world(joint), matrix, 1e-9)
        members = set(cmds.ls(cmds.container(owner, query=True, nodeList=True), long=False))
        for node in set(cmds.ls(type="unitConversion")) - conversions:
            self.assertIn(node, members)
            self.assertEqual(cmds.getAttr(node + ".conversionFactor"), 1.0)
        cmds.setAttr(owner + ".armLength", 1.0)
        cmds.currentUnit(linear="cm")
        self._check({"armLength": 1.0})

    def test_ownership_and_undo(self):
        before = set(cmds.ls())
        cmds.undoInfo(stateWithoutFlush=True)
        graph = BodyProportion.create(self._parameters(), name="proportion")
        owner = str(graph.container)
        members = set(cmds.ls(cmds.container(owner, query=True, nodeList=True)))
        self.assertEqual(set(cmds.ls()) - before - {owner} - set(cmds.ls(type="hyperLayout")), members)
        cmds.undo()
        self.assertFalse(cmds.objExists(owner))
        self.assertEqual(set(cmds.ls()), before)
        for joint in self.joints:
            self.assertFalse(cmds.listConnections(joint + ".translate", source=True, destination=False))
        cmds.redo()
        cmds.setAttr(owner + ".armThickness", 1.0)
        self._check({"armThickness": 1.0})

    def test_arguments(self):
        joint = self.joints[1]
        cases = [
            [],
            [{"name": "1bad", "targets": {joint: {"translate": (1, 0, 0)}}}],
            [{"name": "translateLength", "targets": {joint: {"translate": (1, 0, 0)}}}],
            [{"name": "a", "targets": {joint: {"translate": (1, 0, 0)}}}, {"name": "a", "targets": {joint: {}}}],
            [{"name": "a", "minimum": 0.5, "targets": {joint: {}}}],
            [{"name": "a", "targets": {}}],
            [{"name": "a", "targets": {joint: {"rotate": (1, 0, 0)}}}],
            [{"name": "a", "targets": {joint: {"translate": (1, 0)}}}],
            [{"name": "a", "extra": 1, "targets": {joint: {}}}],
        ]
        for parameters in cases:
            with self.assertRaises(ValueError):
                BodyProportion.create(parameters, name="bad")
            self.assertFalse(cmds.objExists("bad"))
        cmds.connectAttr(self.body + ".translateX", joint + ".translateY")
        with self.assertRaises(ValueError):
            BodyProportion.create([{"name": "a", "targets": {joint: {"translate": (1, 0, 0)}}}], name="bad")
        BodyProportion.create([{"name": "a", "targets": {self.joints[0]: {"translate": (1, 0, 0)}}}], name="ok")
        with self.assertRaises(ValueError):
            BodyProportion.create([{"name": "a", "targets": {self.joints[2]: {"translate": (1, 0, 0)}}}], name="ok")


if __name__ == "__main__":
    unittest.main(argv=["BodyProportion"], exit=False, verbosity=2)
