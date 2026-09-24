"""複合編集・選択復元・タイムライン範囲のUndo/Redoを検証する。"""

import sys
import unittest

import maya.cmds as cmds
import hlib

hlib.reload()
from hlib.decorators import preserved_selection, undo_chunk


class EditUndoTest(unittest.TestCase):
    def setUp(self):
        self.node = cmds.createNode("transform", name="hlibEditUndo")

    def tearDown(self):
        if cmds.objExists(self.node):
            cmds.delete(self.node)

    def test_compound_set_is_one_step(self):
        cmds.addAttr(self.node, longName="pair", attributeType="compound", numberOfChildren=2)
        for name in ("first", "second"):
            cmds.addAttr(self.node, longName=name, attributeType="double", parent="pair")
        plug = hlib.node(self.node).attr("pair")
        plug.set((3, 7))
        self.assertEqual(plug.get(), (3, 7))
        cmds.undo()
        self.assertEqual(plug.get(), (0, 0))
        cmds.redo()
        self.assertEqual(plug.get(), (3, 7))

    def test_selection_restored_on_redo_and_exception(self):
        cmds.select(self.node)
        with self.assertRaises(ValueError):
            with preserved_selection():
                cmds.select(clear=True)
                hlib.node(self.node).attr("visibility").set(False)
                raise ValueError("test")
        self.assertEqual(cmds.ls(selection=True), [self.node])
        cmds.undo()
        self.assertTrue(cmds.getAttr(self.node + ".visibility"))
        self.assertEqual(cmds.ls(selection=True), [self.node])
        cmds.redo()
        self.assertFalse(cmds.getAttr(self.node + ".visibility"))
        self.assertEqual(cmds.ls(selection=True), [self.node])

    def test_selection_skips_deleted_object(self):
        cmds.select(self.node)
        with preserved_selection():
            cmds.delete(self.node)
        self.assertEqual(cmds.ls(selection=True), [])
        cmds.undo()
        self.assertTrue(cmds.objExists(self.node))
        self.assertEqual(cmds.ls(selection=True), [self.node])
        cmds.redo()
        self.assertFalse(cmds.objExists(self.node))

    def test_component_selection_survives_redo(self):
        mesh = cmds.polyCube()[0]
        try:
            cmds.select(mesh + ".vtx[0:3]", replace=True)
            before = cmds.ls(selection=True, flatten=True, long=True)
            with preserved_selection():
                cmds.select(self.node, replace=True)
                hlib.node(self.node).attr("visibility").set(False)
            self.assertEqual(cmds.ls(selection=True, flatten=True, long=True), before)
            cmds.undo()
            self.assertEqual(cmds.ls(selection=True, flatten=True, long=True), before)
            cmds.redo()
            self.assertEqual(cmds.ls(selection=True, flatten=True, long=True), before)
        finally:
            cmds.delete(mesh)

    def test_ranges_group_with_tool(self):
        slider = hlib.timeSlider()
        playback, animation = slider.playback_range(), slider.animation_range()
        try:
            with undo_chunk("rangeTool"):
                slider.set_animation_range(-20, 200)
                slider.set_playback_range(-10, 100)
            cmds.undo()
            self.assertEqual(slider.playback_range(), playback)
            self.assertEqual(slider.animation_range(), animation)
            cmds.redo()
            self.assertEqual(slider.playback_range(), (-10, 100))
            self.assertEqual(slider.animation_range(), (-20, 200))
        finally:
            slider.set_animation_range(*animation)
            slider.set_playback_range(*playback)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
