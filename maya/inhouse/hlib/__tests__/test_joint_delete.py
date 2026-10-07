"""未スキニング・スキニングjointの削除と失敗時の伝播。"""

import sys
import unittest
import uuid
from unittest.mock import patch

import hlib
import maya.cmds as cmds

hlib.reload()


class JointDeleteTest(unittest.TestCase):
    def delete_joint(self, name):
        hlib.nodes.Joints([name]).delete()

    def test_safe_keeps_skin_and_joint_hierarchy(self):
        root = self.getNode("safeRoot")
        child = self.getNode("safeChild", parent=root)
        mesh = cmds.polyCube(name=self.ns + ":mesh")[0]
        skin = cmds.skinCluster([root, child], mesh, name=self.ns + ":skin")[0]
        pose = hlib.getNode(skin).getBindPose()
        cmds.rename(pose.getFullName(), self.ns + ":pose")
        weights = cmds.skinPercent(skin, mesh + '.vtx[0]', query=True, value=True)
        hlib.getNode(child).delete(safe=True)
        self.assertTrue(cmds.objExists(child))
        isolated = self.getNode("isolated")
        self.assertIsNone(hlib.nodes.Joints([root, child, isolated]).delete(safe=True))
        self.assertTrue(cmds.objExists(root) and cmds.objExists(child))
        self.assertFalse(cmds.objExists(isolated))
        self.assertEqual(cmds.listRelatives(child, parent=True)[0], root)
        self.assertEqual(cmds.skinPercent(skin, mesh + '.vtx[0]', query=True, value=True), weights)
        cmds.undo()
        self.assertTrue(cmds.objExists(isolated))
        cmds.redo()
        self.assertFalse(cmds.objExists(isolated))

    def test_safe_joint_validation_and_inverse_scale_connection(self):
        root = hlib.getNode(self.getNode("safeRoot"))
        child = hlib.getNode(self.getNode("safeChild", parent=root.getFullName()))
        cmds.connectAttr(root.getFullName() + '.scale', child.getFullName() + '.inverseScale')
        for node in (root, child):
            node.delete(safe=True)
            self.assertTrue(node.isValid())
        for target in (root, hlib.nodes.Joints([root])):
            with self.assertRaises(TypeError):
                target.delete(safe=1)

    def setUp(self):
        self.ns = "hlibDelete_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def getNode(self, name, type="joint", parent=None):
        args = {"name": self.ns + ":" + name}
        if parent:
            args["parent"] = parent
        return cmds.createNode(type, **args)

    def test_unskinned_root_and_transform_children_undo(self):
        root = self.getNode("root")
        leaf = self.getNode("leaf", parent=root)
        ctrl = self.getNode("ctrl", "transform", parent=root)
        cmds.setAttr(root + ".translateX", 3)
        before = cmds.xform(leaf, query=True, worldSpace=True, matrix=True)
        self.delete_joint(root)
        self.assertFalse(cmds.objExists(root))
        self.assertTrue(cmds.objExists(ctrl))
        self.assertFalse(cmds.listRelatives(leaf, parent=True))
        self.assertEqual(cmds.xform(leaf, query=True, worldSpace=True, matrix=True), before)
        cmds.undo()
        self.assertTrue(cmds.objExists(root))
        self.assertEqual(cmds.listRelatives(leaf, parent=True), [root])
        cmds.redo()
        self.assertFalse(cmds.objExists(root))

    def test_multiple_unskinned_under_transform(self):
        group = self.getNode("group", "transform")
        root = self.getNode("root", parent=group)
        mid = self.getNode("mid", parent=root)
        leaf = self.getNode("leaf", parent=mid)
        hlib.nodes.Joints([root, mid]).delete()
        self.assertEqual(cmds.listRelatives(leaf, parent=True), [group])
        self.assertFalse(cmds.objExists(root))
        self.assertFalse(cmds.objExists(mid))

    def skin_state(self, skin, mesh):
        if not cmds.objExists(skin):
            return None
        influences = cmds.skinCluster(skin, query=True, influence=True) or []
        return (len(influences), [cmds.skinPercent(skin, f"{mesh}.vtx[{i}]", query=True, value=True)
                                 for i in range(8)])

    def test_no_parent_influence_matches_native_delete(self):
        for single in (True, False):
            for has_parent in (True, False):
                with self.subTest(single=single, has_parent=has_parent):
                    parent = self.getNode("parent") if has_parent else None
                    joint = self.getNode("remove", parent=parent)
                    influences = [joint] if single else [joint, self.getNode("other")]
                    mesh = cmds.polyCube(name=self.ns + ":mesh")[0]
                    skin = cmds.skinCluster(influences, mesh, toSelectedBones=True)[0]
                    if not single:
                        cmds.skinPercent(skin, mesh, transformValue=[(joint, 0.7), (influences[1], 0.3)])
                    original = self.skin_state(skin, mesh)
                    cmds.delete(joint)
                    expected = self.skin_state(skin, mesh)
                    cmds.undo()
                    self.delete_joint(joint)
                    self.assertFalse(cmds.objExists(joint))
                    self.assertEqual(self.skin_state(skin, mesh), expected)
                    cmds.undo()
                    self.assertTrue(cmds.objExists(joint))
                    self.assertEqual(self.skin_state(skin, mesh), original)
                    cmds.redo()
                    self.assertEqual(self.skin_state(skin, mesh), expected)

    def test_mixed_skin_clusters_transfer_only_where_parent_is_influence(self):
        parent = self.getNode("parent")
        joint = self.getNode("remove", parent=parent)
        other = self.getNode("other")
        meshes = [cmds.polyCube(name=self.ns + ":mesh")[0] for _ in range(2)]
        a = cmds.skinCluster([parent, joint], meshes[0], toSelectedBones=True)[0]
        b = cmds.skinCluster([joint, other], meshes[1], toSelectedBones=True)[0]
        cmds.skinPercent(a, meshes[0], transformValue=[(parent, 0.2), (joint, 0.8)])
        cmds.skinPercent(b, meshes[1], transformValue=[(joint, 0.7), (other, 0.3)])
        cmds.delete(joint)
        expected = self.skin_state(b, meshes[1])
        cmds.undo()
        self.delete_joint(joint)
        self.assertEqual(cmds.skinCluster(a, query=True, influence=True), [parent])
        self.assertAlmostEqual(cmds.skinPercent(a, meshes[0] + ".vtx[0]", query=True, transform=parent), 1)
        self.assertEqual(self.skin_state(b, meshes[1]), expected)

    def test_failure_propagates_with_context_and_undo_remains_available(self):
        root = self.getNode("root")
        leaf = self.getNode("leaf", parent=root)
        with patch.object(cmds, "delete", side_effect=RuntimeError("simulated failure")):
            with self.assertRaisesRegex(RuntimeError, "delete joint.*simulated failure"):
                self.delete_joint(root)
        self.assertTrue(cmds.objExists(root))
        self.assertFalse(cmds.listRelatives(leaf, parent=True))
        cmds.undo()
        self.assertEqual(cmds.listRelatives(leaf, parent=True), [root])


class SingleJointDeleteTest(JointDeleteTest):
    """単体入口にも同じ移送・標準削除比較・Undo・例外テストを適用する。"""

    def delete_joint(self, name):
        hlib.getNode(name).delete()

    def test_invalid_joint_raises(self):
        name = self.getNode("removed")
        joint = hlib.getNode(name)
        cmds.delete(name)
        with self.assertRaisesRegex(RuntimeError, "invalid joint"):
            joint.delete()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
