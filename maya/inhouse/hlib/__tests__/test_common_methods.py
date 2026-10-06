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
        plug = node.getPlug("translate")
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
        before = [(node.getPlug(a).isLocked(), node.getPlug(a).isKeyable()) for a in attrs]
        self.assertIs(node.setAttrFlags(attrs, locked=True, keyable=False), node)
        for a in attrs:
            self.assertTrue(node.getPlug(a).isLocked())
            self.assertFalse(node.getPlug(a).isKeyable())
        cmds.undo()
        self.assertEqual([(node.getPlug(a).isLocked(), node.getPlug(a).isKeyable()) for a in attrs], before)
        cmds.redo()
        self.assertTrue(all(node.getPlug(a).isLocked() for a in attrs))
        node.setAttrFlags(attrs, locked=False, channelBox=True)
        self.assertTrue(cmds.getAttr(node.getPlug(attrs[0]).getFullName(), channelBox=True))
        with self.assertRaises(TypeError):
            node.setAttrFlags(attrs, locked="false")

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
                cmds.addAttr(node.getFullName(), longName=name, attributeType=kind, defaultValue=default)
                value_before = cmds.getAttr(node.getFullName() + "." + name)
                plug = node.getPlug(name)
                plug.set(99)
                plug.reset()
                self.assertAlmostEqual(cmds.getAttr(plug.getFullName()), value_before)
            cmds.addAttr(node.getFullName(), longName="choice", attributeType="enum",
                         enumName="A:B:C", defaultValue=2)
            node.getPlug("choice").set(0)
            node.getPlug("choice").reset()
            self.assertEqual(node.getPlug("choice").get(), 2)
        finally:
            cmds.currentUnit(linear=linear, angle=angle)

    def test_reset_attrs_skips_locked_and_connected_channels(self):
        node, source = self.create("control"), self.create("driver")
        node.getPlug("translate").set((2, 3, 4))
        node.getPlug("translateX").setFlags(locked=True)
        source.getPlug("translateY").connectTo(node.getPlug("translateY"))
        changed = node.resetAttrs()
        names = [plug.getFullName() for plug in changed]
        self.assertNotIn(node.getPlug("translateX").getFullName(), names)
        self.assertNotIn(node.getPlug("translateY").getFullName(), names)
        self.assertEqual(node.getPlug("translateZ").get(), 0)
        cmds.undo()
        self.assertEqual(node.getPlug("translateZ").get(), 4)
        with self.assertRaises(RuntimeError):
            node.resetAttrs("translateX")
        cmds.addAttr(node.getFullName(), longName="text", dataType="string")
        with self.assertRaises(TypeError):
            node.getPlug("text").reset()

    def test_match_transform_matches_maya_and_undo(self):
        parent = self.create("parent")
        parent.getPlug("translate").set((4, 2, -1))
        target = self.create("target")
        actual = self.create("actual", parent=parent.getFullName())
        expected = self.create("expected", parent=parent.getFullName())
        target.getPlug("translate").set((10, 3, -5))
        target.getPlug("rotate").set((20, 30, 10))
        target.getPlug("scale").set((2, 3, 4))
        before = cmds.xform(actual.getFullName(), query=True, matrix=True, worldSpace=True)
        cmds.matchTransform(expected.getFullName(), target.getFullName(), position=True, rotation=True, scale=True, pivots=False)
        self.assertIs(actual.matchTransform(target), actual)
        after = cmds.xform(actual.getFullName(), query=True, matrix=True, worldSpace=True)
        for a, b in zip(after, cmds.xform(expected.getFullName(), query=True, matrix=True, worldSpace=True)):
            self.assertAlmostEqual(a, b)
        cmds.undo()
        for a, b in zip(before, cmds.xform(actual.getFullName(), query=True, matrix=True, worldSpace=True)):
            self.assertAlmostEqual(a, b)
        cmds.redo()
        for a, b in zip(after, cmds.xform(actual.getFullName(), query=True, matrix=True, worldSpace=True)):
            self.assertAlmostEqual(a, b)

    def test_match_position_only_and_noop(self):
        actual, target = self.create("actual"), self.create("target")
        cmds.setAttr(actual.getFullName() + ".rotate", 15, 0, 0)
        target.getPlug("translate").set((7, 8, 9))
        actual.matchTransform(target.getFullName(), rotation=False, scale=False)
        self.assertEqual(tuple(actual.getPlug("translate").get()), (7, 8, 9))
        self.assertAlmostEqual(actual.getPlug("rotateX").get(), __import__("math").radians(15))
        undo_name = cmds.undoInfo(query=True, undoName=True)
        actual.matchTransform(target, position=False, rotation=False, scale=False)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        with self.assertRaises(TypeError):
            actual.matchTransform(self.create("network", type="network"))

    def skin(self):
        joints = [self.create("joint" + str(i), type="joint") for i in range(3)]
        mesh = cmds.polyCube(name=self.namespace + ":mesh")[0]
        skin = hlib.getNode(cmds.skinCluster([j.getFullName() for j in joints], mesh)[0])
        return joints, hlib.getNode(mesh), skin

    def test_history_filtered_and_empty(self):
        joints, mesh, skin = self.skin()
        self.assertIn(skin.getUuid(), [node.getUuid() for node in mesh.getHistory(type="skinCluster")])
        self.assertIn(skin.getUuid(), [node.getUuid() for node in mesh.getHistory(type="geometryFilter")])
        native = cmds.listHistory(mesh.getFullName()) or []
        expected = list(dict.fromkeys(hlib.getNode(name).getUuid() for name in native if hlib.getNode(name).getUuid() != mesh.getUuid()))
        self.assertEqual([node.getUuid() for node in mesh.getHistory()], expected)
        self.assertEqual(self.create("empty").getHistory(type="skinCluster"), [])

    def test_unused_influences_undo_and_joint_survival(self):
        joints, mesh, skin = self.skin()
        names = [joint.getFullName() for joint in joints]
        skin.setWeights(names, [1, 0, 0])
        self.assertEqual([node.getUuid() for node in skin.getUnusedInfluences()], [j.getUuid() for j in joints[1:]])
        before = list(skin.getWeights(names))
        removed = skin.removeUnusedInfluences()
        self.assertEqual([node.getUuid() for node in removed], [j.getUuid() for j in joints[1:]])
        self.assertTrue(all(j.isValid() for j in joints))
        self.assertEqual(len(skin.getInfluences()), 1)
        cmds.undo()
        self.assertEqual(list(skin.getWeights(names)), before)
        cmds.redo()
        self.assertEqual(len(skin.getInfluences()), 1)
        self.assertEqual(skin.removeUnusedInfluences(), [])

    def test_unused_influences_keep_small_weights_and_reject_empty_binding(self):
        joints, mesh, skin = self.skin()
        names = [joint.getFullName() for joint in joints]
        skin.setWeights(names, [1 - 1e-8, 1e-8, 0])
        self.assertEqual([node.getUuid() for node in skin.getUnusedInfluences()], [joints[2].getUuid()])
        skin.setWeights(names, [0, 0, 0])
        with self.assertRaises(ValueError):
            skin.removeUnusedInfluences()
        self.assertEqual(len(skin.getInfluences()), 3)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
