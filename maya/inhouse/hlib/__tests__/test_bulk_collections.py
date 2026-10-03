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
        self.joints.setTranslation((1, 2, 3))
        self.assertEqual([tuple(p) for p in self.joints.getTranslation()], [(1, 2, 3)] * 2)
        cmds.undo()
        self.assertEqual([tuple(p) for p in self.joints.getTranslation()], [(0, 0, 0)] * 2)
        cmds.redo()
        self.assertEqual([tuple(p) for p in self.joints.getTranslation()], [(1, 2, 3)] * 2)
        self.joints.callEach("setTranslation", [((4, 5, 6),), ((7, 8, 9),)])
        self.assertEqual([tuple(p) for p in self.joints.getTranslation()], [(4, 5, 6), (7, 8, 9)])
        self.assertEqual(self.joints.isJoint(), [True, True])
        self.assertEqual(self.joints.fullName(), [item.fullName() for item in self.joints])
        self.assertEqual(self.joints[:1].names(), self.names[:1])
        self.assertEqual(len(self.joints), 2)
        self.assertFalse(hasattr(self.joints, "create"))
        self.assertEqual(hlib.nodes.Joints().getTranslation(), [])

    def test_argument_validation_and_failure_context(self):
        with self.assertRaises(ValueError):
            self.joints.callEach("setTranslation", [((1, 2, 3),)])
        with self.assertRaises(TypeError):
            self.joints.callEach("setTranslation", [((1, 2, 3),), ()])
        self.assertEqual([tuple(p) for p in self.joints.getTranslation()], [(0, 0, 0)] * 2)
        cmds.setAttr(self.names[1] + ".translateX", lock=True)
        try:
            with self.assertRaisesRegex(RuntimeError, "setTranslation failed at item 1"):
                self.joints.setTranslation((5, 0, 0))
            self.assertEqual(cmds.getAttr(self.names[0] + ".translateX"), 5)
            cmds.undo()
            self.assertEqual(cmds.getAttr(self.names[0] + ".translateX"), 0)
        finally:
            cmds.setAttr(self.names[1] + ".translateX", lock=False)

    def test_skin_methods_and_file_operations_are_explicit(self):
        meshes = [cmds.polyCube(name=self.ns + ":mesh")[0] for _ in range(2)]
        skins = hlib.nodes.SkinClusters([cmds.skinCluster(self.names, mesh, toSelectedBones=True)[0] for mesh in meshes])
        self.assertEqual(len(skins.influences()), 2)
        self.assertEqual(skins.hasInfluence(self.names[0]), [True, True])
        for skin, mesh in zip(skins, meshes):
            cmds.skinPercent(skin.fullName(), mesh, transformValue=[(self.names[0], 0.75), (self.names[1], 0.25)])
        skins.transferWeights([(self.names[0], self.names[1])])
        for skin, mesh in zip(skins, meshes):
            self.assertAlmostEqual(cmds.skinPercent(skin.fullName(), mesh + ".vtx[0]", query=True, transform=self.names[1]), 1)
        cmds.undo()
        for skin, mesh in zip(skins, meshes):
            self.assertAlmostEqual(cmds.skinPercent(skin.fullName(), mesh + ".vtx[0]", query=True, transform=self.names[0]), 0.75)
        self.assertFalse(hasattr(skins, "dumpWeights"))
        self.assertIn("dumpWeights", skins._bulk_methods)
        self.assertEqual(len(skins[:1]), 1)
        self.assertTrue(callable(skins.removeInfluences))

    def test_registration_coverage(self):
        for collection, single in ((self.joints, hlib.nodes.Joint), (hlib.nodes.SkinClusters(), hlib.nodes.SkinCluster)):
            for name in dir(single):
                if not name.startswith("_") and inspect.isfunction(inspect.getattr_static(single, name)):
                    self.assertIn(name, collection._bulk_methods)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
