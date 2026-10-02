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
        relation = hlib.getDrivenKey(self.a + ".ry", hlib.getNode(self.b).plug("rz"))
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
        self.assertIn("renamed", relation.driver_plug().full_name())
        self.assertEqual(len(relation.curves()), 1)

    def test_multiple_drivers_and_find(self):
        one = hlib.getDrivenKey(self.a + ".tx", self.b + ".ty")
        two = hlib.getDrivenKey(self.c + ".tx", self.b + ".ty")
        one.set_key(0, 0).set_key(10, 10)
        two.set_key(0, 0).set_key(10, 20)
        self.assertEqual(len(one.curves()), 1)
        self.assertEqual(len(two.curves()), 1)
        self.assertNotEqual(one.curves()[0].full_name(), two.curves()[0].full_name())
        found = hlib.scene.DrivenKey.find(self.b + ".ty")
        self.assertEqual(len(found), 2)
        cmds.setAttr(self.a + ".tx", 5)
        cmds.setAttr(self.c + ".tx", 5)
        self.assertAlmostEqual(cmds.getAttr(self.b + ".ty"), 15)
        self.assertIsInstance(found, list)
        from hlib.decorators.undo import undo_chunk
        with undo_chunk("testDrivenKeys"):
            for relation in found:
                relation.set_key(10, 30)
        self.assertAlmostEqual(cmds.getAttr(self.b + ".ty"), 30)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(self.b + ".ty"), 15)
        cmds.redo()
        self.assertAlmostEqual(cmds.getAttr(self.b + ".ty"), 30)
        self.assertEqual(len(found[:1]), 1)
        self.assertEqual(len([relation.driver_plug() for relation in found]), 2)

    def test_existing_maya_keys_and_weight_branch(self):
        cmds.setDrivenKeyframe(self.b + ".ty", currentDriver=self.a + ".tx", driverValue=0, value=0)
        cmds.setDrivenKeyframe(self.b + ".ty", currentDriver=self.c + ".tx", driverValue=0, value=0)
        blend = cmds.listConnections(self.b + ".ty", source=True, destination=False,
                                     type="blendWeighted", skipConversionNodes=True)[0]
        cmds.setDrivenKeyframe(blend + ".weight[0]", currentDriver=self.a + ".tz", driverValue=0, value=1)
        found = hlib.scene.DrivenKey.find(self.b + ".ty")
        self.assertEqual(len(found), 2)
        self.assertEqual({p.full_name() for p in [relation.driver_plug() for relation in found]},
                         {hlib.getNode(self.a).plug("tx").full_name(), hlib.getNode(self.c).plug("tx").full_name()})
        relation = hlib.getDrivenKey(self.a + ".tx", self.b + ".ty")
        self.assertEqual(len(relation.curves()), 1)
        relation.set_key(10, 10)
        self.assertEqual(relation.curves()[0].key_count(), 2)

    def test_time_animation_is_not_replaced(self):
        cmds.setKeyframe(self.b + ".tx", time=1, value=2)
        before = cmds.listConnections(self.b + ".tx", source=True, destination=False, plugs=True)
        relation = hlib.getDrivenKey(self.a + ".tx", self.b + ".tx")
        with self.assertRaises(RuntimeError):
            relation.set_key(0, 0)
        self.assertEqual(cmds.listConnections(self.b + ".tx", source=True, destination=False, plugs=True), before)

    def test_validation_and_unsupported_connections(self):
        with self.assertRaises(ValueError):
            hlib.getDrivenKey(self.a + ".translate", self.b + ".ty")
        with self.assertRaises(ValueError):
            hlib.getDrivenKey(self.a + ".tx", self.a + ".translateX")
        relation = hlib.getDrivenKey(self.a + ".tx", self.b + ".ty")
        with self.assertRaises(ValueError):
            relation.set_key(float("nan"), 0)
        cmds.connectAttr(self.c + ".ty", self.b + ".ty")
        with self.assertRaises(RuntimeError):
            relation.set_key(0, 0)
        self.assertTrue(cmds.isConnected(self.c + ".ty", self.b + ".ty"))
        self.assertFalse(relation.exists())
        self.assertEqual(len(hlib.scene.DrivenKey.find(self.b + ".ty")), 0)
        cmds.delete(self.a)
        with self.assertRaises(RuntimeError):
            relation.set_key(0, 0)

    def test_instanced_shape_driver_is_matched_by_plug_identity(self):
        # インスタンス化されたシェイプのアトリビュートは、どのインスタンスのパスから指定しても同じプラグ。
        # 2つ目のインスタンスのパスで指定したドライバーも、作成したカーブと照合できること。
        box = cmds.polyCube(name=self.ns + ":box", constructionHistory=False)[0]
        first_group = cmds.group(box, name=self.ns + ":ga")
        second_group = cmds.createNode("transform", name=self.ns + ":gb")
        instance = cmds.instance(cmds.listRelatives(first_group, children=True, fullPath=True)[0],
                                 name=self.ns + ":box1")[0]
        instance = cmds.parent(instance, second_group)[0]
        first_shape = cmds.listRelatives(cmds.ls(first_group, long=True)[0], allDescendents=True,
                                         type="mesh", fullPath=True)[0]
        second_shape = cmds.listRelatives(cmds.ls(instance, long=True)[0], shapes=True, fullPath=True)[0]
        self.assertNotEqual(first_shape, second_shape)
        cmds.addAttr(first_shape, longName="drv", attributeType="double", keyable=True)
        driver = hlib.getNode(second_shape).plug("drv")
        relation = hlib.getDrivenKey(driver, self.c + ".tx")
        relation.set_key(0, 0)
        relation.set_key(1, 10)
        self.assertEqual(len(relation.curves()), 1)
        self.assertTrue(relation.exists())
        # 1つ目のインスタンスのパスで指定しても同じ関係として見つかる。
        same = hlib.getDrivenKey(hlib.getNode(first_shape).plug("drv"), self.c + ".tx")
        self.assertEqual([curve.full_name() for curve in same.curves()],
                         [curve.full_name() for curve in relation.curves()])
        found = hlib.scene.DrivenKey.find(self.c + ".tx")
        self.assertEqual(len(found), 1)
        cmds.setAttr(first_shape + ".drv", 1)
        self.assertAlmostEqual(cmds.getAttr(self.c + ".tx"), 10.0)
        with self.assertRaises(ValueError):
            hlib.getDrivenKey(hlib.getNode(first_shape).plug("drv"), hlib.getNode(second_shape).plug("drv"))

    def test_find_skips_non_numeric_drivers(self):
        # 値によって型が変わる generic アトリビュート(choice.output)のドライバーは対象外として除外し、
        # 例外にしない。同じ駆動先の数値ドライバーは見つかる。
        relation = hlib.getDrivenKey(self.a + ".tx", self.b + ".ty")
        relation.set_key(0, 0).set_key(10, 10)
        choice = cmds.createNode("choice", name=self.ns + ":choice")
        cmds.connectAttr(self.c + ".tx", choice + ".input[0]")
        curve = cmds.createNode("animCurveUU", name=self.ns + ":genericCurve")
        cmds.setKeyframe(curve, float=0.0, value=0.0)
        cmds.setKeyframe(curve, float=1.0, value=1.0)
        cmds.connectAttr(choice + ".output", curve + ".input")
        cmds.connectAttr(curve + ".output", self.b + ".tz")
        self.assertEqual(len(hlib.scene.DrivenKey.find(self.b + ".tz")), 0)
        self.assertEqual(len(hlib.scene.DrivenKey.find(self.b + ".ty")), 1)
        self.assertEqual(len(hlib.scene.DrivenKey.find(hlib.getNode(self.b).plug("ty").mplug())), 1)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
