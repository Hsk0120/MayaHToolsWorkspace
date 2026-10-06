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
        b.setColor(1, (1, 0, 0)).setColor(2, (0, 0, 1))
        b.setBlender(0)
        self.assertEqual(b.getResult(), (0, 0, 1))
        b.setBlender(1)
        self.assertEqual(b.getResult(), (1, 0, 0))
        b.setBlender(0.25)
        self.assertEqual(b.getResult(), (0.25, 0, 0.75))
        cmds.undo()
        self.assertEqual(b.getResult(), (1, 0, 0))
        cmds.redo()
        self.assertEqual(b.getResult(), (0.25, 0, 0.75))
        b.setColor(1, (2, -1, 3))
        cmds.undo()
        self.assertEqual(tuple(b.getColorPlug(1).get()), (1, 0, 0))
        cmds.redo()
        self.assertEqual(tuple(b.getColorPlug(1).get()), (2, -1, 3))

    def test_connections(self):
        b = self.blend
        source = hlib.createNode("blendColors", name=self.ns + ":source")
        source.setColor(1, (0, 1, 0)).setBlender(1)
        control = hlib.createNode("transform", name=self.ns + ":control")
        control.getPlug("tx").set(1)
        b.connectColor(1, source.getOutputPlug()).connectBlender(control.getPlug("tx"))
        self.assertEqual(b.getResult(), (0, 1, 0))
        cmds.undo()
        self.assertFalse(cmds.listConnections(b.getBlenderPlug().getFullName(), source=True, destination=False))
        cmds.redo()
        self.assertEqual(b.getResult(), (0, 1, 0))
        replacement = hlib.createNode("blendColors", name=self.ns + ":replacement")
        with self.assertRaises(RuntimeError):
            b.connectColor(1, replacement.getOutputPlug())
        b.connectColor(1, replacement.getOutputPlug(), force=True)
        self.assertTrue(cmds.isConnected(replacement.getOutputPlug().getFullName(), b.getColorPlug(1).getFullName()))
        cmds.undo()
        self.assertTrue(cmds.isConnected(source.getOutputPlug().getFullName(), b.getColorPlug(1).getFullName()))
        with self.assertRaises(RuntimeError):
            b.setColor(1, (1, 1, 1))

    def test_invalid_values_do_not_change_inputs(self):
        before = self.blend.getColorPlug(1).get()
        for value in ((1, 2), (1, float("nan"), 3)):
            with self.assertRaises(ValueError):
                self.blend.setColor(1, value)
        for index in (0, 3, True, 1.0):
            with self.assertRaises(ValueError):
                self.blend.getColorPlug(index)
        for value in (-1, 2, float("inf")):
            with self.assertRaises(ValueError):
                self.blend.setBlender(value)
        self.assertEqual(self.blend.getColorPlug(1).get(), before)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
