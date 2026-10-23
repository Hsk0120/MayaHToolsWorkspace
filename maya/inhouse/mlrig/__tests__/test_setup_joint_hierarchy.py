"""明示したジョイント整理のウェイト移送・階層保持・Undoを検証する。"""

from contextlib import ExitStack
import sys
import unittest
import uuid
from unittest.mock import patch

import mlib
from mlrig.setups import JointHierarchy
import maya.cmds as cmds

class JointDeleteTest(unittest.TestCase):
    def delete_joint(self, name):
        JointHierarchy.delete([name])

    def test_safe_keeps_skin_and_joint_hierarchy(self):
        root = self.getNode("safeRoot")
        child = self.getNode("safeChild", parent=root)
        mesh = cmds.polyCube(name=self.ns + ":mesh")[0]
        skin = cmds.skinCluster([root, child], mesh, name=self.ns + ":skin")[0]
        pose = mlib.getNode(skin).getBindPose()
        cmds.rename(pose.getFullName(), self.ns + ":pose")
        weights = cmds.skinPercent(skin, mesh + '.vtx[0]', query=True, value=True)
        JointHierarchy.delete(child, safe=True)
        self.assertTrue(cmds.objExists(child))
        isolated = self.getNode("isolated")
        self.assertIsNone(JointHierarchy.delete([root, child, isolated], safe=True))
        self.assertTrue(cmds.objExists(root) and cmds.objExists(child))
        self.assertFalse(cmds.objExists(isolated))
        self.assertEqual(cmds.listRelatives(child, parent=True)[0], root)
        self.assertEqual(cmds.skinPercent(skin, mesh + '.vtx[0]', query=True, value=True), weights)
        cmds.undo()
        self.assertTrue(cmds.objExists(isolated))
        cmds.redo()
        self.assertFalse(cmds.objExists(isolated))

    def test_safe_joint_validation_and_inverse_scale_connection(self):
        root = mlib.getNode(self.getNode("safeRoot"))
        child = mlib.getNode(self.getNode("safeChild", parent=root.getFullName()))
        cmds.connectAttr(root.getFullName() + '.scale', child.getFullName() + '.inverseScale')
        for node in (root, child):
            JointHierarchy.delete(node, safe=True)
            self.assertTrue(node.isValid())
        for target in (root, mlib.nodes.Joints([root])):
            with self.assertRaises(TypeError):
                JointHierarchy.delete(target, safe=1)

    def setUp(self):
        self.ns = "mlibDelete_" + uuid.uuid4().hex
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
        JointHierarchy.delete([root, mid])
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
        JointHierarchy.delete(mlib.getNode(name))

    def test_invalid_joint_raises(self):
        name = self.getNode("removed")
        joint = mlib.getNode(name)
        cmds.delete(name)
        with self.assertRaises((ValueError, RuntimeError)):
            JointHierarchy.delete(joint)


class JointHierarchyFastTest(unittest.TestCase):
    """fast整理も通常経路と同じ結果・事前検証を保つ。"""

    def setUp(self):
        """他の検証に影響しない新規シーンを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)


    def api_only(self):
        """fast実行中にMayaコマンドによるシーン更新を禁止する。"""
        stack = ExitStack()
        for name in ("setAttr", "delete", "deleteAttr", "addAttr", "createNode", "group", "parent",
                     "rename", "connectAttr", "disconnectAttr", "skinCluster", "skinPercent", "undoInfo"):
            stack.enter_context(patch.object(cmds, name, side_effect=AssertionError(name)))
        return stack


    def assertMatrixEqual(self, actual, expected):
        """Mayaの分解に伴う丸め差だけを許容する。"""
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, delta=1e-6)


    def test_fast_joint_delete_preserves_children(self):
        """Joint削除時の子の姿勢・SSC・inverseScaleを通常経路と比較する。"""
        parent = mlib.createNode("joint", name="root")
        middle = mlib.createNode("joint", parent=parent, name="middle")
        child = mlib.createNode("joint", parent=middle, name="leaf")
        ctrl = mlib.createNode("transform", parent=middle, name="control")
        parent.setTranslate((3, 2, 1))
        middle.setTranslate((4, 0, 0))
        middle.getPlug("jointOrient").set((.2, .3, .1))
        child.setTranslate((2, 0, 0))
        middle.connectInverseScale()
        child.connectInverseScale()
        matrices = [list(n.getMatrix(worldSpace=True)) for n in (child, ctrl)]
        JointHierarchy.delete(middle)
        expected_orient = tuple(mlib.getNode("leaf").getPlug("jointOrient").get())
        cmds.undo()
        middle = mlib.getNode("middle")
        with self.api_only():
            JointHierarchy.delete(middle, fast=True)
        self.assertFalse(middle.isValid())
        child, ctrl = mlib.getNode("leaf"), mlib.getNode("control")
        self.assertEqual(child.getParent(), parent)
        self.assertEqual(ctrl.getParent(), parent)
        self.assertEqual(child.getPlug("inverseScale").getSource(skipConversionNodes=False), parent.getPlug("scale"))
        for node, matrix in zip((child, ctrl), matrices):
            self.assertMatrixEqual(node.getMatrix(worldSpace=True), matrix)
        for actual, expected in zip(child.getPlug("jointOrient").get(), expected_orient):
            self.assertAlmostEqual(actual, expected, delta=1e-6)


    def skin_fixture(self):
        """単一meshと3influenceの最小スキンを作る。"""
        mesh = cmds.polyPlane(ch=False, sx=1, sy=1)[0]
        root = mlib.createNode("joint", name="root")
        middle = mlib.createNode("joint", parent=root, name="middle")
        other = mlib.createNode("joint", name="other")
        skin = mlib.getNode(cmds.skinCluster([root.getFullName(), middle.getFullName(), other.getFullName()],
                                           mesh, toSelectedBones=True)[0])
        skin.setWeights([root.getFullName(), middle.getFullName(), other.getFullName()], [.2, .3, .5])
        return skin, root, middle, other


    def test_fast_joint_delete_transfers_weights(self):
        """祖先influenceへの移送後、Mayaの削除通知で接続を解除する。"""
        skin, root, middle, other = self.skin_fixture()
        JointHierarchy.delete(middle)
        expected = list(skin.getWeights([root.getFullName(), other.getFullName()]))
        cmds.undo()
        middle = mlib.getNode("middle")
        with self.api_only():
            JointHierarchy.delete(middle, fast=True)
        self.assertEqual(list(skin.getWeights([root.getFullName(), other.getFullName()])), expected)
        self.assertFalse(middle.isValid())


    def test_fast_joint_root_delete_and_ssc(self):
        """スケール補正のある未スキニング階層でも子のワールド姿勢を保つ。"""
        root = mlib.createNode("joint", name="root")
        middle = mlib.createNode("joint", parent=root, name="middle")
        child = mlib.createNode("joint", parent=middle, name="child")
        root.getPlug("scale").set((2, 3, 4))
        middle.getPlug("scale").set((1.5, 1.5, 1.5))
        middle.connectInverseScale()
        child.connectInverseScale()
        child.getPlug("translate").set((4, 2, 1))
        matrix = list(child.getMatrix(worldSpace=True))
        with self.api_only():
            JointHierarchy.delete(middle, fast=True)
        self.assertTrue(root.isValid())
        self.assertMatrixEqual(child.getMatrix(worldSpace=True), matrix)
        self.assertEqual(child.getParent(), root)


    def test_fast_joint_child_failure_precedes_weight_transfer(self):
        """子Transformの入力接続を、Jointウェイト移送より前に拒否する。"""
        skin, root, middle, other = self.skin_fixture()
        child = mlib.createNode("transform", parent=middle)
        root.getPlug("translateX").connectTo(child.getPlug("translateX"))
        names = [n.getFullName() for n in (root, middle, other)]
        weights = list(skin.getWeights(names))
        with self.api_only(), self.assertRaises(RuntimeError):
            JointHierarchy.delete(middle, fast=True)
        self.assertTrue(middle.isValid())
        self.assertEqual(child.getParent(), middle)
        self.assertEqual(list(skin.getWeights(names)), weights)



if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
