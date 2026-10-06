"""複合編集・選択復元・タイムライン範囲のUndo/Redoを検証する。"""

import sys
import unittest

import maya.cmds as cmds
import hlib

hlib.reload()
from hlib.decorators import preservedSelection, undoChunk


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
        plug = hlib.getNode(self.node).getPlug("pair")
        plug.set((3, 7))
        self.assertEqual(plug.get(), (3, 7))
        cmds.undo()
        self.assertEqual(plug.get(), (0, 0))
        cmds.redo()
        self.assertEqual(plug.get(), (3, 7))

    def test_selection_restored_on_redo_and_exception(self):
        cmds.select(self.node)
        with self.assertRaises(ValueError):
            with preservedSelection():
                cmds.select(clear=True)
                hlib.getNode(self.node).getPlug("visibility").set(False)
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
        with preservedSelection():
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
            with preservedSelection():
                cmds.select(self.node, replace=True)
                hlib.getNode(self.node).getPlug("visibility").set(False)
            self.assertEqual(cmds.ls(selection=True, flatten=True, long=True), before)
            cmds.undo()
            self.assertEqual(cmds.ls(selection=True, flatten=True, long=True), before)
            cmds.redo()
            self.assertEqual(cmds.ls(selection=True, flatten=True, long=True), before)
        finally:
            cmds.delete(mesh)

    def test_ranges_group_with_tool(self):
        slider = hlib.getTimeSlider()
        playback, animation = slider.getPlaybackRange(), slider.getAnimationRange()
        try:
            if str(cmds.about(version=True)).startswith(("2022", "2023")):
                # 空のUndoチャンクではネイティブの非Undo操作を補えない。
                before = cmds.undoInfo(query=True, undoName=True)
                with undoChunk("rangeTool"):
                    slider.setAnimationRange(-20, 200)
                    slider.setPlaybackRange(-10, 100)
                self.assertEqual(slider.getPlaybackRange(), (-10, 100))
                self.assertEqual(slider.getAnimationRange(), (-20, 200))
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), before)
                return
            with undoChunk("rangeTool"):
                slider.setAnimationRange(-20, 200)
                slider.setPlaybackRange(-10, 100)
            cmds.undo()
            self.assertEqual(slider.getPlaybackRange(), playback)
            self.assertEqual(slider.getAnimationRange(), animation)
            cmds.redo()
            self.assertEqual(slider.getPlaybackRange(), (-10, 100))
            self.assertEqual(slider.getAnimationRange(), (-20, 200))
        finally:
            slider.setAnimationRange(*animation)
            slider.setPlaybackRange(*playback)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
