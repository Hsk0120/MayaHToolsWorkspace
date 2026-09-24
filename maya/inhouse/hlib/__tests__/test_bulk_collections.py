"""同種コレクションの一括API、要素別引数、失敗とUndoを検証する。"""
import inspect
import sys
import unittest
import uuid
from unittest.mock import patch
import maya.cmds as cmds
import hlib

hlib.reload()


class BulkCollectionsTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibBulk_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.names = [cmds.createNode("joint", name=self.ns + ":j" + str(i)) for i in range(2)]
        self.joints = hlib.nodes.Joints(self.names)

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_common_and_per_item_transform_undo(self):
        self.joints.set_translate((1, 2, 3))
        self.assertEqual([tuple(p) for p in self.joints.get_translate()], [(1, 2, 3)] * 2)
        cmds.undo()
        self.assertEqual([tuple(p) for p in self.joints.get_translate()], [(0, 0, 0)] * 2)
        cmds.redo()
        self.assertEqual([tuple(p) for p in self.joints.get_translate()], [(1, 2, 3)] * 2)
        self.joints.call_each("set_translate", [((4, 5, 6),), ((7, 8, 9),)])
        self.assertEqual([tuple(p) for p in self.joints.get_translate()], [(4, 5, 6), (7, 8, 9)])
        self.assertEqual(self.joints.is_joint(), [True, True])
        self.assertEqual(self.joints.full_name, [item.full_name for item in self.joints])
        self.assertEqual(self.joints[:1].names, self.names[:1])
        self.assertEqual(len(self.joints), 2)
        self.assertFalse(hasattr(self.joints, "create"))
        self.assertEqual(hlib.nodes.Joints().get_translate(), [])

    def test_argument_validation_and_failure_context(self):
        with self.assertRaises(ValueError):
            self.joints.call_each("set_translate", [((1, 2, 3),)])
        with self.assertRaises(TypeError):
            self.joints.call_each("set_translate", [((1, 2, 3),), ()])
        self.assertEqual([tuple(p) for p in self.joints.get_translate()], [(0, 0, 0)] * 2)
        cmds.setAttr(self.names[1] + ".translateX", lock=True)
        try:
            with self.assertRaisesRegex(RuntimeError, "set_translate failed at item 1"):
                self.joints.set_translate((5, 0, 0))
            self.assertEqual(cmds.getAttr(self.names[0] + ".translateX"), 5)
            cmds.undo()
            self.assertEqual(cmds.getAttr(self.names[0] + ".translateX"), 0)
        finally:
            cmds.setAttr(self.names[1] + ".translateX", lock=False)

    def test_skin_methods_and_file_operations_are_explicit(self):
        meshes = [cmds.polyCube(name=self.ns + ":mesh")[0] for _ in range(2)]
        skins = hlib.nodes.SkinClusters([cmds.skinCluster(self.names, mesh, toSelectedBones=True)[0] for mesh in meshes])
        self.assertEqual(len(skins.influences()), 2)
        self.assertEqual(skins.has_influence(self.names[0]), [True, True])
        for skin, mesh in zip(skins, meshes):
            cmds.skinPercent(skin.full_name, mesh, transformValue=[(self.names[0], 0.75), (self.names[1], 0.25)])
        skins.transfer_weight(self.names[0], self.names[1])
        for skin, mesh in zip(skins, meshes):
            self.assertAlmostEqual(cmds.skinPercent(skin.full_name, mesh + ".vtx[0]", query=True, transform=self.names[1]), 1)
        cmds.undo()
        for skin, mesh in zip(skins, meshes):
            self.assertAlmostEqual(cmds.skinPercent(skin.full_name, mesh + ".vtx[0]", query=True, transform=self.names[0]), 0.75)
        self.assertFalse(hasattr(skins, "dump_weights"))
        self.assertIn("dump_weights", skins._bulk_methods)
        self.assertEqual(len(skins[:1]), 1)
        self.assertTrue(callable(skins.remove_joints))

    def test_plugins_and_registration_coverage(self):
        from hlib.plugins import Plugin, Plugins
        plugins = Plugins(["hlibMissingA", "hlibMissingB"])
        self.assertEqual(plugins.name(), ["hlibMissingA", "hlibMissingB"])
        self.assertEqual(plugins.is_loaded(), [False, False])
        calls = []
        def fake_load(item, **kwargs):
            calls.append((item.name(), kwargs))
            return item
        with patch.object(Plugin, "load", fake_load):
            self.assertEqual(len(plugins.load(quiet=True)), 2)
        self.assertEqual(calls, [("hlibMissingA", {"quiet": True}), ("hlibMissingB", {"quiet": True})])
        for collection, single in ((self.joints, hlib.nodes.Joint), (hlib.nodes.SkinClusters(), hlib.nodes.SkinCluster), (plugins, Plugin)):
            for name in dir(single):
                if not name.startswith("_") and inspect.isfunction(inspect.getattr_static(single, name)):
                    self.assertIn(name, collection._bulk_methods)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
