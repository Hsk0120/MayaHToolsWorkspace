"""blendColorsの登録・補間・接続とUndo/Redoを検証する。"""
import sys
import unittest
import uuid
import maya.cmds as cmds
import hlib

hlib.reload()


class BlendColorsTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibColor_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.blend = hlib.createNode("blendColors", name=self.ns + ":blend")

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_values_and_undo(self):
        b = self.blend
        self.assertIsInstance(b, hlib.nodes.BlendColors)
        b.set_color(1, (1, 0, 0)).set_color(2, (0, 0, 1))
        b.set_blender(0)
        self.assertEqual(b.result(), (0, 0, 1))
        b.set_blender(1)
        self.assertEqual(b.result(), (1, 0, 0))
        b.set_blender(0.25)
        self.assertEqual(b.result(), (0.25, 0, 0.75))
        cmds.undo()
        self.assertEqual(b.result(), (1, 0, 0))
        cmds.redo()
        self.assertEqual(b.result(), (0.25, 0, 0.75))
        b.set_color(1, (2, -1, 3))
        cmds.undo()
        self.assertEqual(tuple(b.color(1).get()), (1, 0, 0))
        cmds.redo()
        self.assertEqual(tuple(b.color(1).get()), (2, -1, 3))

    def test_connections(self):
        b = self.blend
        source = hlib.createNode("blendColors", name=self.ns + ":source")
        source.set_color(1, (0, 1, 0)).set_blender(1)
        control = hlib.createNode("transform", name=self.ns + ":control")
        control.plug("tx").set(1)
        b.connect_color(1, source.output()).connect_blender(control.plug("tx"))
        self.assertEqual(b.result(), (0, 1, 0))
        cmds.undo()
        self.assertFalse(cmds.listConnections(b.blender().full_name, source=True, destination=False))
        cmds.redo()
        self.assertEqual(b.result(), (0, 1, 0))
        replacement = hlib.createNode("blendColors", name=self.ns + ":replacement")
        with self.assertRaises(RuntimeError):
            b.connect_color(1, replacement.output())
        b.connect_color(1, replacement.output(), force=True)
        self.assertTrue(cmds.isConnected(replacement.output().full_name, b.color(1).full_name))
        cmds.undo()
        self.assertTrue(cmds.isConnected(source.output().full_name, b.color(1).full_name))
        with self.assertRaises(RuntimeError):
            b.set_color(1, (1, 1, 1))

    def test_invalid_values_do_not_change_inputs(self):
        before = self.blend.color(1).get()
        for value in ((1, 2), (1, float("nan"), 3)):
            with self.assertRaises(ValueError):
                self.blend.set_color(1, value)
        for index in (0, 3, True, 1.0):
            with self.assertRaises(ValueError):
                self.blend.color(index)
        for value in (-1, 2, float("inf")):
            with self.assertRaises(ValueError):
                self.blend.set_blender(value)
        self.assertEqual(self.blend.color(1).get(), before)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
