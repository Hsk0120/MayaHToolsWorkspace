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
        plug = node.plug("translate")
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
        before = [(node.plug(a).isLocked(), node.plug(a).isKeyable()) for a in attrs]
        self.assertIs(node.setAttributeFlags(attrs, locked=True, keyable=False), node)
        for a in attrs:
            self.assertTrue(node.plug(a).isLocked())
            self.assertFalse(node.plug(a).isKeyable())
        cmds.undo()
        self.assertEqual([(node.plug(a).isLocked(), node.plug(a).isKeyable()) for a in attrs], before)
        cmds.redo()
        self.assertTrue(all(node.plug(a).isLocked() for a in attrs))
        node.setAttributeFlags(attrs, locked=False, channelBox=True)
        self.assertTrue(cmds.getAttr(node.plug(attrs[0]).fullName(), channelBox=True))
        with self.assertRaises(TypeError):
            node.setAttributeFlags(attrs, locked="false")

    def test_center_pivot_preserves_geometry_and_undo(self):
        name = cmds.polyCube(name=self.namespace + ":pivotMesh")[0]
        node = hlib.getNode(name)
        cmds.move(3, 1, -2, name + ".vtx[*]", relative=True)
        cmds.setAttr(name + ".rotateY", 30)
        cmds.setAttr(name + ".scaleX", 2)
        points = cmds.xform(name + ".vtx[*]", query=True, translation=True, worldSpace=True)
        before = cmds.xform(name, query=True, pivots=True)
        self.assertIs(node.centerPivot(), node)
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
                cmds.addAttr(node.fullName(), longName=name, attributeType=kind, defaultValue=default)
                value_before = cmds.getAttr(node.fullName() + "." + name)
                plug = node.plug(name)
                plug.set(99)
                plug.reset()
                self.assertAlmostEqual(cmds.getAttr(plug.fullName()), value_before)
            cmds.addAttr(node.fullName(), longName="choice", attributeType="enum",
                         enumName="A:B:C", defaultValue=2)
            node.plug("choice").set(0)
            node.plug("choice").reset()
            self.assertEqual(node.plug("choice").get(), 2)
        finally:
            cmds.currentUnit(linear=linear, angle=angle)

    def test_reset_attrs_skips_locked_and_connected_channels(self):
        node, source = self.create("control"), self.create("driver")
        node.plug("translate").set((2, 3, 4))
        node.plug("translateX").setFlags(locked=True)
        source.plug("translateY").connectTo(node.plug("translateY"))
        changed = node.resetAttributes()
        names = [plug.fullName() for plug in changed]
        self.assertNotIn(node.plug("translateX").fullName(), names)
        self.assertNotIn(node.plug("translateY").fullName(), names)
        self.assertEqual(node.plug("translateZ").get(), 0)
        cmds.undo()
        self.assertEqual(node.plug("translateZ").get(), 4)
        with self.assertRaises(RuntimeError):
            node.resetAttributes("translateX")
        cmds.addAttr(node.fullName(), longName="text", dataType="string")
        with self.assertRaises(TypeError):
            node.plug("text").reset()

    def test_match_transform_matches_maya_and_undo(self):
        parent = self.create("parent")
        parent.plug("translate").set((4, 2, -1))
        target = self.create("target")
        actual = self.create("actual", parent=parent.fullName())
        expected = self.create("expected", parent=parent.fullName())
        target.plug("translate").set((10, 3, -5))
        target.plug("rotate").set((20, 30, 10))
        target.plug("scale").set((2, 3, 4))
        before = cmds.xform(actual.fullName(), query=True, matrix=True, worldSpace=True)
        cmds.matchTransform(expected.fullName(), target.fullName(), position=True, rotation=True, scale=True, pivots=False)
        self.assertIs(actual.matchTransform(target), actual)
        after = cmds.xform(actual.fullName(), query=True, matrix=True, worldSpace=True)
        for a, b in zip(after, cmds.xform(expected.fullName(), query=True, matrix=True, worldSpace=True)):
            self.assertAlmostEqual(a, b)
        cmds.undo()
        for a, b in zip(before, cmds.xform(actual.fullName(), query=True, matrix=True, worldSpace=True)):
            self.assertAlmostEqual(a, b)
        cmds.redo()
        for a, b in zip(after, cmds.xform(actual.fullName(), query=True, matrix=True, worldSpace=True)):
            self.assertAlmostEqual(a, b)

    def test_match_position_only_and_noop(self):
        actual, target = self.create("actual"), self.create("target")
        cmds.setAttr(actual.fullName() + ".rotate", 15, 0, 0)
        target.plug("translate").set((7, 8, 9))
        actual.matchTransform(target.fullName(), rotation=False, scale=False)
        self.assertEqual(tuple(actual.plug("translate").get()), (7, 8, 9))
        self.assertAlmostEqual(actual.plug("rotateX").get(), __import__("math").radians(15))
        undo_name = cmds.undoInfo(query=True, undoName=True)
        actual.matchTransform(target, position=False, rotation=False, scale=False)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        with self.assertRaises(TypeError):
            actual.matchTransform(self.create("network", type="network"))

    def skin(self):
        joints = [self.create("joint" + str(i), type="joint") for i in range(3)]
        mesh = cmds.polyCube(name=self.namespace + ":mesh")[0]
        skin = hlib.getNode(cmds.skinCluster([j.fullName() for j in joints], mesh)[0])
        return joints, hlib.getNode(mesh), skin

    def test_history_filtered_and_empty(self):
        joints, mesh, skin = self.skin()
        self.assertIn(skin.uuid(), [node.uuid() for node in mesh.history(type="skinCluster")])
        self.assertIn(skin.uuid(), [node.uuid() for node in mesh.history(type="geometryFilter")])
        native = cmds.listHistory(mesh.fullName()) or []
        expected = list(dict.fromkeys(hlib.getNode(name).uuid() for name in native if hlib.getNode(name).uuid() != mesh.uuid()))
        self.assertEqual([node.uuid() for node in mesh.history()], expected)
        self.assertEqual(self.create("empty").history(type="skinCluster"), [])

    def test_unused_influences_undo_and_joint_survival(self):
        joints, mesh, skin = self.skin()
        names = [joint.fullName() for joint in joints]
        skin.setWeights(names, [1, 0, 0])
        self.assertEqual([node.uuid() for node in skin.unusedInfluences()], [j.uuid() for j in joints[1:]])
        before = list(skin.getWeights(names))
        removed = skin.removeUnusedInfluences()
        self.assertEqual([node.uuid() for node in removed], [j.uuid() for j in joints[1:]])
        self.assertTrue(all(j.isValid() for j in joints))
        self.assertEqual(len(skin.influences()), 1)
        cmds.undo()
        self.assertEqual(list(skin.getWeights(names)), before)
        cmds.redo()
        self.assertEqual(len(skin.influences()), 1)
        self.assertEqual(skin.removeUnusedInfluences(), [])

    def test_unused_influences_keep_small_weights_and_reject_empty_binding(self):
        joints, mesh, skin = self.skin()
        names = [joint.fullName() for joint in joints]
        skin.setWeights(names, [1 - 1e-8, 1e-8, 0])
        self.assertEqual([node.uuid() for node in skin.unusedInfluences()], [joints[2].uuid()])
        skin.setWeights(names, [0, 0, 0])
        with self.assertRaises(ValueError):
            skin.removeUnusedInfluences()
        self.assertEqual(len(skin.influences()), 3)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
