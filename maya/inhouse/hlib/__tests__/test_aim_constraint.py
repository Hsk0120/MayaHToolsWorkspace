"""Aimの照会・設定操作を専用namespaceで検証する。"""

import math
import unittest

import maya.cmds as cmds

from hlib.nodes import AimConstraint


class AimConstraintTest(unittest.TestCase):
    """接続・回転順序・単位と編集拒否を確認する。"""

    def setUp(self):
        """専用namespaceにAimを作成する。"""
        self.previous = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.unit = cmds.currentUnit(query=True, angle=True)
        self.ns = cmds.namespace(add="aimMethodTest")
        cmds.namespace(set=self.ns)
        self.target = cmds.createNode("transform")
        self.driven = cmds.createNode("transform")
        cmds.setAttr(self.target + ".translate", 10, 4, 3)
        self.aim = AimConstraint(cmds.aimConstraint(self.target, self.driven)[0])

    def tearDown(self):
        """テストノードを削除して単位を戻す。"""
        cmds.currentUnit(angle=self.unit)
        cmds.namespace(set=self.previous)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_connections(self):
        """子接続・複合接続・演算ノード宛ての直接接続を区別する。"""
        pairs = self.aim.getRotateConnections()
        self.assertEqual(len(pairs), 3)
        for source, destination in pairs:
            cmds.disconnectAttr(source.getFullName(), destination.getFullName())
        cmds.connectAttr(self.aim.getFullName() + ".constraintRotate", self.driven + ".rotate")
        self.assertEqual(len(self.aim.getRotateConnections()), 1)
        extra = cmds.createNode("composeMatrix")
        cmds.connectAttr(self.aim.getFullName() + ".constraintRotateX", extra + ".inputRotateX")
        pairs = self.aim.getRotateConnections()
        self.assertEqual(len(pairs), 2)
        self.assertEqual({destination.getNode().getType() for _, destination in pairs}, {"transform", "composeMatrix"})

    def test_settings_and_units(self):
        """設定値はUI単位に依存せず、接続付き設定も列挙される。"""
        values = (0.1, -0.2, 0.3)
        for unit in ("deg", "rad"):
            cmds.currentUnit(angle=unit)
            self.aim.setRestRotate(values)
            self.aim.setOffset(values)
            for result in (self.aim.getRestRotate(), self.aim.getOffset()):
                for actual, expected in zip(result, values):
                    self.assertAlmostEqual(actual, expected)
        self.assertEqual(len(self.aim.settingPlugs()), 18)
        cmds.connectAttr(self.target + ".rotateX", self.aim.getFullName() + ".offsetX")
        self.assertIn(self.aim.getPlug("offsetX"), self.aim.settingPlugs())
        with self.assertRaises(ValueError):
            self.aim.setOffset((1, 2, 3))
        self.assertAlmostEqual(self.aim.getOffset()[1], values[1])

    def test_locked_invalid_and_undo(self):
        """後半のロックでも部分更新せず、更新はUndoできる。"""
        self.aim.setRestRotate((0, 0, 0))
        cmds.setAttr(self.aim.getFullName() + ".restRotateZ", lock=True)
        try:
            with self.assertRaises(ValueError):
                self.aim.setRestRotate((1, 2, 3))
            self.assertEqual(self.aim.getRestRotate(), (0, 0, 0))
        finally:
            cmds.setAttr(self.aim.getFullName() + ".restRotateZ", lock=False)
        for invalid in ((1, 2), (0, math.nan, 0)):
            with self.assertRaises(ValueError):
                self.aim.setRestRotate(invalid)
        self.aim.setRestRotate((1, 2, 3))
        cmds.undo()
        self.assertEqual(self.aim.getRestRotate(), (0, 0, 0))

    def test_output_orders(self):
        """全回転順の出力値を取得し、Transform回転とは区別する。"""
        cmds.currentUnit(angle="rad")
        for order in range(6):
            cmds.setAttr(self.driven + ".rotateOrder", order)
            rotation = self.aim.getOutputRotate()
            self.assertEqual(rotation.order, order)
            expected = cmds.getAttr(self.aim.getFullName() + ".constraintRotate")[0]
            for actual, value in zip(rotation, expected):
                self.assertAlmostEqual(actual, value)
        self.assertNotEqual(tuple(self.aim.getOutputRotate()), tuple(self.aim.getRotate()))


if __name__ == "__main__":
    unittest.main()
