"""ドリブンキーの接続解決・単位変換・複数入力・Undoを検証する。"""
import sys
import unittest
import uuid
import maya.cmds as cmds
import hlib

hlib.reload()


class DrivenKeyTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibSDK_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.a = cmds.createNode("transform", name=self.ns + ":a")
        self.b = cmds.createNode("transform", name=self.ns + ":b")
        self.c = cmds.createNode("transform", name=self.ns + ":c")

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_creation_units_undo_and_rename(self):
        relation = hlib.drivenKey(self.a + ".ry", hlib.node(self.b).plug("rz"))
        before = cmds.ls(type="animCurve") or []
        self.assertFalse(relation.exists())
        self.assertEqual(cmds.ls(type="animCurve") or [], before)
        relation.set_key(0, 0)
        cmds.undo()
        self.assertFalse(relation.exists())
        cmds.redo()
        self.assertTrue(relation.exists())
        relation.set_key(90, 45)
        self.assertEqual(len(relation.curves()), 1)
        cmds.setAttr(self.a + ".ry", 45)
        self.assertAlmostEqual(cmds.getAttr(self.b + ".rz"), 22.5, places=4)
        relation.set_key(90, 60)
        self.assertAlmostEqual(cmds.getAttr(self.a + ".ry"), 45)
        self.assertAlmostEqual(cmds.getAttr(self.b + ".rz"), 30, places=4)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(self.b + ".rz"), 22.5, places=4)
        self.a = cmds.rename(self.a, self.ns + ":renamed")
        self.assertIn("renamed", relation.driver().full_name)
        self.assertEqual(len(relation.curves()), 1)

    def test_multiple_drivers_and_find(self):
        one = hlib.drivenKey(self.a + ".tx", self.b + ".ty")
        two = hlib.drivenKey(self.c + ".tx", self.b + ".ty")
        one.set_key(0, 0).set_key(10, 10)
        two.set_key(0, 0).set_key(10, 20)
        self.assertEqual(len(one.curves()), 1)
        self.assertEqual(len(two.curves()), 1)
        self.assertNotEqual(one.curves()[0].full_name, two.curves()[0].full_name)
        found = hlib.animation.DrivenKeys.find(self.b + ".ty")
        self.assertEqual(len(found), 2)
        cmds.setAttr(self.a + ".tx", 5)
        cmds.setAttr(self.c + ".tx", 5)
        self.assertAlmostEqual(cmds.getAttr(self.b + ".ty"), 15)
        found.set_key(10, 30)
        self.assertAlmostEqual(cmds.getAttr(self.b + ".ty"), 30)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(self.b + ".ty"), 15)
        cmds.redo()
        self.assertAlmostEqual(cmds.getAttr(self.b + ".ty"), 30)
        self.assertEqual(len(found[:1]), 1)
        self.assertEqual(len(found.driver()), 2)

    def test_existing_maya_keys_and_weight_branch(self):
        cmds.setDrivenKeyframe(self.b + ".ty", currentDriver=self.a + ".tx", driverValue=0, value=0)
        cmds.setDrivenKeyframe(self.b + ".ty", currentDriver=self.c + ".tx", driverValue=0, value=0)
        blend = cmds.listConnections(self.b + ".ty", source=True, destination=False,
                                     type="blendWeighted", skipConversionNodes=True)[0]
        cmds.setDrivenKeyframe(blend + ".weight[0]", currentDriver=self.a + ".tz", driverValue=0, value=1)
        found = hlib.animation.DrivenKeys.find(self.b + ".ty")
        self.assertEqual(len(found), 2)
        self.assertEqual({p.full_name for p in found.driver()},
                         {hlib.node(self.a).plug("tx").full_name, hlib.node(self.c).plug("tx").full_name})
        relation = hlib.drivenKey(self.a + ".tx", self.b + ".ty")
        self.assertEqual(len(relation.curves()), 1)
        relation.set_key(10, 10)
        self.assertEqual(relation.curves()[0].key_count(), 2)

    def test_time_animation_is_not_replaced(self):
        cmds.setKeyframe(self.b + ".tx", time=1, value=2)
        before = cmds.listConnections(self.b + ".tx", source=True, destination=False, plugs=True)
        relation = hlib.drivenKey(self.a + ".tx", self.b + ".tx")
        with self.assertRaises(RuntimeError):
            relation.set_key(0, 0)
        self.assertEqual(cmds.listConnections(self.b + ".tx", source=True, destination=False, plugs=True), before)

    def test_validation_and_unsupported_connections(self):
        with self.assertRaises(ValueError):
            hlib.drivenKey(self.a + ".translate", self.b + ".ty")
        with self.assertRaises(ValueError):
            hlib.drivenKey(self.a + ".tx", self.a + ".translateX")
        relation = hlib.drivenKey(self.a + ".tx", self.b + ".ty")
        with self.assertRaises(ValueError):
            relation.set_key(float("nan"), 0)
        cmds.connectAttr(self.c + ".ty", self.b + ".ty")
        with self.assertRaises(RuntimeError):
            relation.set_key(0, 0)
        self.assertTrue(cmds.isConnected(self.c + ".ty", self.b + ".ty"))
        self.assertFalse(relation.exists())
        self.assertEqual(len(hlib.animation.DrivenKeys.find(self.b + ".ty")), 0)
        cmds.delete(self.a)
        with self.assertRaises(RuntimeError):
            relation.set_key(0, 0)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
