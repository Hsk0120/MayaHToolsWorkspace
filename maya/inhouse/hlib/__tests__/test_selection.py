"""選択の分類・名前変更追跡・欠落・Undo/RedoをMayaで検証する。"""

import sys
import unittest
import uuid
import maya.cmds as cmds
import hlib

hlib.reload()
from hlib.selection import Selection


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibSelection_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.mesh = cmds.polyCube(name=self.ns + ":mesh")[0]
        self.joint = cmds.createNode("joint", name=self.ns + ":joint")

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_capture_mixed_and_snapshot(self):
        cmds.select([self.joint, self.mesh + ".vtx[1:3]"], replace=True)
        selection = hlib.captureSelection()
        cmds.select(clear=True)
        self.assertEqual(len(selection), 4)
        self.assertEqual(len(selection.nodes(type="joint")), 1)
        self.assertEqual(selection.components()[0].indices, (1, 2, 3))
        self.assertEqual(len(selection.owners()), 2)
        self.assertEqual(len(selection.filter(type="vtx")), 3)
        selection.restore()
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 4)
        cmds.undo()
        self.assertEqual(cmds.ls(selection=True), [])
        cmds.redo()
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 4)

    def test_rename_and_missing_validation(self):
        selection = Selection([self.joint, self.mesh + ".f[0]"])
        renamed = cmds.rename(self.joint, self.ns + ":renamed")
        selection.restore()
        self.assertIn(renamed, cmds.ls(selection=True))
        cmds.delete(self.mesh)
        cmds.select(clear=True)
        with self.assertRaises(RuntimeError):
            selection.restore(missing="error")
        self.assertEqual(cmds.ls(selection=True), [])
        selection.restore()
        self.assertEqual(cmds.ls(selection=True), [renamed])
        with self.assertRaises(ValueError):
            selection.restore(missing="invalid")

    def test_plug_reference_and_delete(self):
        cmds.addAttr(self.joint, longName="amount", attributeType="double")
        selection = Selection([self.joint + ".amount"])
        self.assertEqual(len(selection.plugs()), 1)
        self.assertEqual(len(selection.filter(type="plug")), 1)
        cmds.renameAttr(self.joint + ".amount", "renamed")
        self.assertTrue(selection.plugs()[0].full_name().endswith(".renamed"))
        cmds.deleteAttr(self.joint + ".renamed")
        self.assertEqual(selection.plugs(), [])
        with self.assertRaises(RuntimeError):
            selection.restore(missing="error")

    def test_add_remove_and_empty(self):
        selection = Selection(self.joint)
        cmds.select(self.mesh)
        selection.add_to_selection()
        self.assertIn(self.joint, cmds.ls(selection=True))
        cmds.undo()
        self.assertEqual(cmds.ls(selection=True), [self.mesh])
        cmds.redo()
        selection.remove_from_selection()
        self.assertEqual(cmds.ls(selection=True), [self.mesh])
        cmds.undo()
        self.assertIn(self.joint, cmds.ls(selection=True))
        Selection().restore()
        self.assertEqual(cmds.ls(selection=True), [])

    def test_component_kinds_and_objectset(self):
        curve = cmds.curve(name=self.ns + ":curve", degree=1, point=[(0, 0, 0), (1, 0, 0)])
        for suffix in ("e[0:1]", "f[0:1]", "map[0:1]"):
            selection = Selection(self.mesh + "." + suffix)
            self.assertEqual(len(selection), 2)
            self.assertEqual(len(selection.components()), 1)
        self.assertEqual(len(Selection(curve + ".cv[*]")), 2)
        name = cmds.sets(self.mesh, name=self.ns + ":set")
        Selection(name).restore()
        self.assertEqual(cmds.ls(selection=True), [name])

    def test_instanced_path_preserved(self):
        instance = cmds.instance(self.mesh, name=self.ns + ":instance")[0]
        selection = Selection(instance + ".vtx[0]")
        selection.restore()
        self.assertIn(instance, cmds.ls(selection=True, long=True)[0])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
