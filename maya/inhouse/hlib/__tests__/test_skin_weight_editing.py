"""親への移送、正規化、十進丸め、最大influence数を実Mayaで検証する。"""
import sys
import unittest
import uuid
from decimal import Decimal
from unittest.mock import patch
import maya.cmds as cmds
import hlib

hlib.reload()


class SkinWeightEditingTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibWeights_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.parent = cmds.createNode("joint", name=self.ns + ":parent")
        self.child = cmds.createNode("joint", name=self.ns + ":child", parent=self.parent)
        self.other = cmds.createNode("joint", name=self.ns + ":other")
        self.mesh = cmds.polyCube(name=self.ns + ":mesh", constructionHistory=False)[0]
        self.skin = hlib.node(cmds.skinCluster([self.parent, self.child, self.other], self.mesh, toSelectedBones=True, name=self.ns + ":skin")[0])
        pose = self.skin.bind_pose()
        if pose:
            cmds.rename(pose.full_name, self.ns + ":pose")
        self.names = [self.parent, self.child, self.other]
        cmds.setAttr(self.skin.full_name + ".normalizeWeights", 0)
        self.skin.set_weights(self.names, [.2, .5, .3])

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def weights(self):
        return list(self.skin.get_weights(self.names))

    def test_remove_influence_transfers_and_keeps_joint(self):
        self.skin.remove_influence(hlib.node(self.child))
        self.assertTrue(cmds.objExists(self.child))
        self.assertFalse(self.skin.has_influence(self.child))
        values = list(self.skin.get_weights([self.parent, self.other]))
        self.assertAlmostEqual(values[0], .7)
        self.assertAlmostEqual(values[1], .3)
        cmds.undo()
        self.assertTrue(self.skin.has_influence(self.child))
        self.assertAlmostEqual(self.weights()[1], .5)
        cmds.redo()
        self.assertFalse(self.skin.has_influence(self.child))

    def test_joint_entry_and_last_influence_guard(self):
        joint = hlib.node(self.child)
        self.assertIs(joint.remove_influence(self.skin), joint)
        self.assertFalse(self.skin.has_influence(self.child))
        cmds.undo()
        joint.remove_influence()
        self.assertFalse(self.skin.has_influence(self.child))
        self.skin.remove_influence(self.other)
        with self.assertRaises(ValueError):
            self.skin.remove_influence(self.parent)
        self.assertTrue(cmds.objExists(self.parent))
        self.assertTrue(cmds.objExists(self.skin.full_name))

    def test_normalize_undo_and_decimal_sum(self):
        self.skin.set_weights(self.names, [1, 1, 1])
        self.skin.normalize_weights()
        self.assertAlmostEqual(sum(self.weights()[:3]), 1)
        cmds.undo()
        self.assertEqual(self.weights()[:3], [1, 1, 1])
        self.skin.normalize_weights(decimals=2)
        self.assertEqual(self.weights()[:3], [.34, .33, .33])
        self.assertEqual(sum(Decimal(str(v)) for v in self.weights()[:3]), Decimal(1))
        self.assertEqual(cmds.getAttr(self.skin.full_name + ".normalizeWeights"), 0)
        cmds.undo()
        self.assertEqual(self.weights()[:3], [1, 1, 1])
        cmds.redo()
        self.assertEqual(self.weights()[:3], [.34, .33, .33])

    def test_zero_and_locked_rejected_before_changes(self):
        self.skin.set_weights(self.names, [0, 0, 0])
        with self.assertRaises(ValueError):
            self.skin.normalize_weights()
        self.skin.set_weights(self.names, [.2, .5, .3])
        cmds.setAttr(self.child + ".lockInfluenceWeights", True)
        before = self.weights()
        with self.assertRaises(RuntimeError):
            self.skin.normalize_weights(decimals=2)
        self.assertEqual(self.weights(), before)

    def test_max_setting_preserves_weights_and_prune(self):
        before, old_max = self.weights(), self.skin.max_influences()
        self.skin.set_max_influences(2)
        self.assertEqual(self.skin.max_influences(), 2)
        self.assertEqual(self.weights(), before)
        cmds.undo()
        self.assertEqual(self.skin.max_influences(), old_max)
        self.skin.set_max_influences(2, prune=True)
        row = self.weights()[:3]
        self.assertEqual(row[0], 0)
        self.assertAlmostEqual(row[1], .625)
        self.assertAlmostEqual(row[2], .375)
        cmds.undo()
        self.assertEqual(self.weights(), before)

    def test_invalid_arguments_and_failure_propagation(self):
        before = self.weights()
        for decimals in (-1, 16, 1.5, True):
            with self.assertRaises(ValueError):
                self.skin.normalize_weights(decimals)
        for count in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                self.skin.set_max_influences(count)
        self.assertEqual(self.weights(), before)
        with patch.object(type(self.skin), "set_weights", side_effect=RuntimeError("transfer failed")):
            with self.assertRaisesRegex(RuntimeError, "transfer failed"):
                hlib.node(self.child).remove_influence()
        self.assertTrue(self.skin.has_influence(self.child))

    def test_transfer_preserves_non_normalized_totals(self):
        self.skin.set_weights(self.names, [.4, 1, .6])
        self.skin.remove_influence(self.child)
        values = list(self.skin.get_weights([self.parent, self.other]))
        self.assertAlmostEqual(values[0], 1.4)
        self.assertAlmostEqual(values[1], .6)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
