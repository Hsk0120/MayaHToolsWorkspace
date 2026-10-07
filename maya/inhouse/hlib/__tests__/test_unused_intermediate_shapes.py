"""未使用中間Shapeの選別とUndo可能な削除を検証する。"""

import sys
import unittest
import uuid
from unittest import mock

import hlib
import maya.cmds as cmds

hlib.reload()


class UnusedIntermediateShapesTest(unittest.TestCase):
    def setUp(self):
        self.ns = "unusedShape_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.transform = hlib.getNode(cmds.polyCube(name=self.ns + ":mesh")[0])

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def intermediate(self, node_type="mesh"):
        shape = cmds.createNode(node_type, name=self.ns + ":unused",
                                parent=self.transform.getFullName())
        cmds.setAttr(shape + ".intermediateObject", True)
        return hlib.getNode(shape)

    def test_delete_multiple_types_undo_redo_and_parent_survives(self):
        shapes = [self.intermediate(t) for t in ("mesh", "nurbsCurve", "nurbsSurface")]
        names = [s.getFullName() for s in shapes]
        self.assertEqual(self.transform.getUnusedIntermediateShapes(), shapes)
        visible = self.transform.getShape().getFullName()
        self.assertIs(self.transform.deleteUnusedIntermediateShapes(), self.transform)
        self.assertTrue(cmds.objExists(visible))
        self.assertTrue(all(not cmds.objExists(n) for n in names))
        cmds.undo()
        self.assertTrue(all(cmds.objExists(n) for n in names))
        cmds.redo()
        self.assertTrue(all(not cmds.objExists(n) for n in names))
        parent = cmds.createNode("transform", name=self.ns + ":empty")
        only = cmds.createNode("mesh", parent=parent, name=self.ns + ":only")
        cmds.setAttr(only + ".intermediateObject", True)
        hlib.getNode(parent).deleteUnusedIntermediateShapes()
        self.assertTrue(cmds.objExists(parent))

    def test_keeps_skin_history_and_custom_consumers(self):
        joint = cmds.createNode("joint", name=self.ns + ":joint")
        skin = hlib.getNode(cmds.skinCluster(joint, self.transform.getFullName(),
                                           name=self.ns + ":skin")[0])
        cmds.rename(skin.getBindPose().getFullName(), self.ns + ":pose")
        unused = self.intermediate()
        message_used = self.intermediate()
        consumer = cmds.createNode("network", name=self.ns + ":consumer")
        cmds.addAttr(consumer, longName="sourceShape", attributeType="message")
        cmds.connectAttr(message_used.getFullName() + ".message", consumer + ".sourceShape")
        self.assertEqual(self.transform.getUnusedIntermediateShapes(), [unused])
        self.transform.deleteUnusedIntermediateShapes()
        self.assertTrue(message_used.isValid())
        self.assertEqual(self.transform.getSkinClusters(), [skin])

    def test_shading_membership_input_history_and_upstream_survive(self):
        other = cmds.polyCube(name=self.ns + ":other")[0]
        shape = cmds.listRelatives(other, shapes=True, fullPath=True)[0]
        generator = cmds.listConnections(shape + ".inMesh", source=True, destination=False)[0]
        cmds.rename(generator, self.ns + ":generator")
        generator = self.ns + ":generator"
        shape = cmds.parent(shape, self.transform.getFullName(), shape=True, relative=True)[0]
        cmds.setAttr(shape + ".intermediateObject", True)
        self.assertEqual(self.transform.getUnusedIntermediateShapes(), [hlib.getNode(shape)])
        self.transform.deleteUnusedIntermediateShapes()
        self.assertTrue(cmds.objExists(generator))
        cmds.undo()
        self.assertTrue(cmds.objExists(shape))
        self.assertTrue(cmds.isConnected(generator + ".output", shape + ".inMesh"))

    def test_keeps_custom_set_membership_and_indirect_instances(self):
        member = self.intermediate()
        object_set = cmds.sets(empty=True, name=self.ns + ":set")
        cmds.sets(member.getFullName(), add=object_set)
        self.assertEqual(self.transform.getUnusedIntermediateShapes(), [])
        unused = self.intermediate()
        cmds.instance(self.transform.getFullName(), name=self.ns + ":instance")
        self.assertEqual(self.transform.getUnusedIntermediateShapes(), [])
        self.transform.deleteUnusedIntermediateShapes()
        self.assertTrue(unused.isValid())

    def test_skips_locks_instances_and_descendants(self):
        locked = self.intermediate()
        cmds.lockNode(locked.getFullName(), lock=True)
        instanced = self.intermediate()
        other = cmds.createNode("transform", name=self.ns + ":other")
        cmds.parent(instanced.getFullName(), other, add=True, shape=True)
        child = cmds.createNode("transform", name=self.ns + ":child", parent=self.transform.getFullName())
        descendant = cmds.createNode("mesh", name=self.ns + ":descendant", parent=child)
        cmds.setAttr(descendant + ".intermediateObject", True)
        try:
            self.assertEqual(self.transform.getUnusedIntermediateShapes(), [])
            undo_name = cmds.undoInfo(query=True, undoName=True)
            self.transform.deleteUnusedIntermediateShapes()
            self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
            self.assertTrue(cmds.objExists(descendant))
        finally:
            cmds.lockNode(locked.getFullName(), lock=False)

    def test_failure_rolls_back(self):
        first, second = self.intermediate(), self.intermediate()
        names = [first.getFullName(), second.getFullName()]
        original = cmds.delete

        def fail_after_first(nodes, **kwargs):
            if isinstance(nodes, list) and nodes == names:
                original(nodes[0])
                raise RuntimeError("Injected deletion failure")
            return original(nodes, **kwargs)

        with mock.patch("maya.cmds.delete", side_effect=fail_after_first):
            with self.assertRaisesRegex(RuntimeError, "Injected"):
                self.transform.deleteUnusedIntermediateShapes()
        self.assertTrue(all(cmds.objExists(n) for n in names))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
