"""共通メソッドのMaya結果・単位・Undo/Redoを検証する。"""

import sys
import unittest
import uuid

import maya.cmds as cmds
import hlib

hlib.reload()


class CommonMethodsTest(unittest.TestCase):
    def setUp(self):
        self.namespace = "hlibCommon_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)

    def tearDown(self):
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def create(self, name, type="transform", **kwargs):
        return hlib.createNode(type, name=self.namespace + ":" + name, **kwargs)

    def test_reset_compound_and_undo(self):
        node = self.create("control")
        plug = node.attr("translate")
        plug.set((2, 3, 4))
        self.assertIs(plug.reset(), plug)
        self.assertEqual(tuple(plug.get()), (0, 0, 0))
        cmds.undo()
        self.assertEqual(tuple(plug.get()), (2, 3, 4))
        cmds.redo()
        self.assertEqual(tuple(plug.get()), (0, 0, 0))

    def test_attr_flags_batch_undo(self):
        node = self.create("flags")
        attrs = ["translateX", "translateY"]
        before = [(node.attr(a).is_locked, node.attr(a).is_keyable) for a in attrs]
        self.assertIs(node.set_attr_flags(attrs, locked=True, keyable=False), node)
        for a in attrs:
            self.assertTrue(node.attr(a).is_locked)
            self.assertFalse(node.attr(a).is_keyable)
        cmds.undo()
        self.assertEqual([(node.attr(a).is_locked, node.attr(a).is_keyable) for a in attrs], before)
        cmds.redo()
        self.assertTrue(all(node.attr(a).is_locked for a in attrs))
        node.set_attr_flags(attrs, locked=False, channel_box=True)
        self.assertTrue(cmds.getAttr(node.attr(attrs[0]).full_name, channelBox=True))
        with self.assertRaises(TypeError):
            node.set_attr_flags(attrs, locked="false")

    def test_center_pivot_preserves_geometry_and_undo(self):
        name = cmds.polyCube(name=self.namespace + ":pivotMesh")[0]
        node = hlib.node(name)
        cmds.move(3, 1, -2, name + ".vtx[*]", relative=True)
        cmds.setAttr(name + ".rotateY", 30)
        cmds.setAttr(name + ".scaleX", 2)
        points = cmds.xform(name + ".vtx[*]", query=True, translation=True, worldSpace=True)
        before = cmds.xform(name, query=True, pivots=True)
        self.assertIs(node.center_pivot(), node)
        after = cmds.xform(name, query=True, pivots=True)
        self.assertNotEqual(after, before)
        for a, b in zip(points, cmds.xform(name + ".vtx[*]", query=True, translation=True, worldSpace=True)):
            self.assertAlmostEqual(a, b)
        cmds.undo()
        self.assertEqual(cmds.xform(name, query=True, pivots=True), before)
        cmds.redo()
        self.assertEqual(cmds.xform(name, query=True, pivots=True), after)

    def test_reset_custom_defaults_and_units(self):
        node = self.create("defaults")
        linear = cmds.currentUnit(query=True, linear=True)
        angle = cmds.currentUnit(query=True, angle=True)
        try:
            cmds.currentUnit(linear="m", angle="rad")
            for name, kind, default in (("distance", "doubleLinear", 2.5),
                                        ("angle", "doubleAngle", 0.75),
                                        ("time", "time", 12.0),
                                        ("amount", "double", 1.25)):
                cmds.addAttr(node.full_name, longName=name, attributeType=kind, defaultValue=default)
                value_before = cmds.getAttr(node.full_name + "." + name)
                plug = node.attr(name)
                plug.set(99)
                plug.reset()
                self.assertAlmostEqual(cmds.getAttr(plug.full_name), value_before)
            cmds.addAttr(node.full_name, longName="choice", attributeType="enum",
                         enumName="A:B:C", defaultValue=2)
            node.attr("choice").set(0)
            node.attr("choice").reset()
            self.assertEqual(node.attr("choice").get(), 2)
        finally:
            cmds.currentUnit(linear=linear, angle=angle)

    def test_reset_attrs_skips_locked_and_connected_channels(self):
        node, source = self.create("control"), self.create("driver")
        node.attr("translate").set((2, 3, 4))
        node.attr("translateX").set_locked(True)
        source.attr("translateY").connect(node.attr("translateY"))
        changed = node.reset_attrs()
        names = [plug.full_name for plug in changed]
        self.assertNotIn(node.attr("translateX").full_name, names)
        self.assertNotIn(node.attr("translateY").full_name, names)
        self.assertEqual(node.attr("translateZ").get(), 0)
        cmds.undo()
        self.assertEqual(node.attr("translateZ").get(), 4)
        with self.assertRaises(RuntimeError):
            node.reset_attrs("translateX")
        cmds.addAttr(node.full_name, longName="text", dataType="string")
        with self.assertRaises(TypeError):
            node.attr("text").reset()

    def test_match_transform_matches_maya_and_undo(self):
        parent = self.create("parent")
        parent.attr("translate").set((4, 2, -1))
        target = self.create("target")
        actual = self.create("actual", parent=parent.full_name)
        expected = self.create("expected", parent=parent.full_name)
        target.attr("translate").set((10, 3, -5))
        target.attr("rotate").set((20, 30, 10))
        target.attr("scale").set((2, 3, 4))
        before = cmds.xform(actual.full_name, query=True, matrix=True, worldSpace=True)
        cmds.matchTransform(expected.full_name, target.full_name, position=True, rotation=True, scale=True, pivots=False)
        self.assertIs(actual.match_transform(target), actual)
        after = cmds.xform(actual.full_name, query=True, matrix=True, worldSpace=True)
        for a, b in zip(after, cmds.xform(expected.full_name, query=True, matrix=True, worldSpace=True)):
            self.assertAlmostEqual(a, b)
        cmds.undo()
        for a, b in zip(before, cmds.xform(actual.full_name, query=True, matrix=True, worldSpace=True)):
            self.assertAlmostEqual(a, b)
        cmds.redo()
        for a, b in zip(after, cmds.xform(actual.full_name, query=True, matrix=True, worldSpace=True)):
            self.assertAlmostEqual(a, b)

    def test_match_position_only_and_noop(self):
        actual, target = self.create("actual"), self.create("target")
        cmds.setAttr(actual.full_name + ".rotate", 15, 0, 0)
        target.attr("translate").set((7, 8, 9))
        actual.match_transform(target.full_name, rotation=False, scale=False)
        self.assertEqual(tuple(actual.attr("translate").get()), (7, 8, 9))
        self.assertAlmostEqual(actual.attr("rotateX").get(), 15)
        undo_name = cmds.undoInfo(query=True, undoName=True)
        actual.match_transform(target, position=False, rotation=False, scale=False)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        with self.assertRaises(TypeError):
            actual.match_transform(self.create("network", type="network"))

    def skin(self):
        joints = [self.create("joint" + str(i), type="joint") for i in range(3)]
        mesh = cmds.polyCube(name=self.namespace + ":mesh")[0]
        skin = hlib.node(cmds.skinCluster([j.full_name for j in joints], mesh)[0])
        return joints, hlib.node(mesh), skin

    def test_history_filtered_and_empty(self):
        joints, mesh, skin = self.skin()
        self.assertIn(skin.uuid, [node.uuid for node in mesh.history(type="skinCluster")])
        self.assertIn(skin.uuid, [node.uuid for node in mesh.history(type="geometryFilter")])
        native = cmds.listHistory(mesh.full_name) or []
        expected = list(dict.fromkeys(hlib.node(name).uuid for name in native if hlib.node(name).uuid != mesh.uuid))
        self.assertEqual([node.uuid for node in mesh.history()], expected)
        self.assertEqual(self.create("empty").history(type="skinCluster"), [])

    def test_unused_influences_undo_and_joint_survival(self):
        joints, mesh, skin = self.skin()
        names = [joint.full_name for joint in joints]
        skin.set_weights(names, [1, 0, 0])
        self.assertEqual([node.uuid for node in skin.unused_influences()], [j.uuid for j in joints[1:]])
        before = list(skin.get_weights(names))
        removed = skin.remove_unused_influences()
        self.assertEqual([node.uuid for node in removed], [j.uuid for j in joints[1:]])
        self.assertTrue(all(j.is_valid() for j in joints))
        self.assertEqual(len(skin.influences()), 1)
        cmds.undo()
        self.assertEqual(list(skin.get_weights(names)), before)
        cmds.redo()
        self.assertEqual(len(skin.influences()), 1)
        self.assertEqual(skin.remove_unused_influences(), [])

    def test_unused_influences_keep_small_weights_and_reject_empty_binding(self):
        joints, mesh, skin = self.skin()
        names = [joint.full_name for joint in joints]
        skin.set_weights(names, [1 - 1e-8, 1e-8, 0])
        self.assertEqual([node.uuid for node in skin.unused_influences()], [joints[2].uuid])
        skin.set_weights(names, [0, 0, 0])
        with self.assertRaises(ValueError):
            skin.remove_unused_influences()
        self.assertEqual(len(skin.influences()), 3)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
