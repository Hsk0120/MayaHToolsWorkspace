"""Aim軸変換が所有する設定保存の選定と単位を検証する。"""

import unittest
import uuid

import maya.cmds as cmds

from mlib.nodes import AimConstraint, Node
from mlrig.setups.aimAxisConversion import AimAxisConversion


class AimAxisConversionSettingsTest(unittest.TestCase):
    """専用namespaceで設定値の保存対象と入力接続の除外を確認する。"""

    def setUp(self):
        """回転を駆動するAimと独立した設定入力元を作成する。"""
        self.previous_namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.previous_angle_unit = cmds.currentUnit(query=True, angle=True)
        self.namespace = cmds.namespace(add="aimAxisSettings_" + uuid.uuid4().hex)
        cmds.namespace(set=self.namespace)
        target = cmds.createNode("transform")
        driven = cmds.createNode("transform")
        cmds.setAttr(target + ".translateX", 10)
        self.aim = AimConstraint(cmds.aimConstraint(target, driven)[0])
        self.driver = Node(cmds.createNode("transform"))

    def tearDown(self):
        """専用ノードを削除し、UI単位とnamespaceを復元する。"""
        cmds.currentUnit(angle=self.previous_angle_unit)
        cmds.namespace(set=self.previous_namespace)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def test_settings_selection_order_and_internal_angles(self):
        """18設定とweight aliasを従来の順で選び、角度はradで保存する。"""
        attrs = [
            "restRotateX", "restRotateY", "restRotateZ",
            "offsetX", "offsetY", "offsetZ",
            "aimVectorX", "aimVectorY", "aimVectorZ",
            "upVectorX", "upVectorY", "upVectorZ",
            "worldUpVectorX", "worldUpVectorY", "worldUpVectorZ",
            "worldUpType", "enableRestPosition", "useOldOffsetCalculation",
        ]
        values = (0.1, -0.2, 0.3)
        for unit in ("deg", "rad"):
            cmds.currentUnit(angle=unit)
            self.aim.setRestRotate(values).setOffset(values)
            settings = AimAxisConversion._captureSettings(self.aim)
            self.assertEqual(list(settings), attrs + self.aim.getWeightAliases())
            self.assertNotIn("worldUpMatrix", settings)
            for prefix in ("restRotate", "offset"):
                for axis, expected in zip("XYZ", values):
                    self.assertAlmostEqual(settings[prefix + axis], expected)

    def test_connected_child_and_parent_settings_are_not_saved(self):
        """子または複合親が駆動された設定を復元値として記録しない。"""
        self.driver.getPlug("rotateX").connectTo(self.aim.getPlug("offsetX"))
        self.driver.getPlug("translate").connectTo(self.aim.getPlug("aimVector"))
        settings = AimAxisConversion._captureSettings(self.aim)
        self.assertNotIn("offsetX", settings)
        self.assertIn("offsetY", settings)
        self.assertIn("offsetZ", settings)
        for axis in "XYZ":
            self.assertNotIn("aimVector" + axis, settings)
        self.assertIn("worldUpType", settings)

    def test_connected_weight_is_not_saved(self):
        """weight aliasも直接の入力接続がある場合は保存対象から外す。"""
        weight = self.aim.getWeightPlugs()[0]
        self.driver.getPlug("scaleX").connectTo(weight)
        settings = AimAxisConversion._captureSettings(self.aim)
        self.assertNotIn(self.aim.getWeightAliases()[0], settings)
        self.assertEqual(len(settings), 18)


if __name__ == "__main__":
    unittest.main()
