"""Hlib.decorators (undo_chunk/undoable/preserved_selection) を検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import Hlib
Hlib.reload()
from Hlib.decorators import preserved_selection, undo_chunk, undoable


class UndoDecoratorsTest(unittest.TestCase):
    """undo_chunk と undoable が単一Undoチャンクとして機能することを検証する。"""

    def tearDown(self):
        for name in ("hlibUndoChunkNode", "hlibUndoableNode"):
            if cmds.objExists(name):
                cmds.delete(name)

    def test_undo_chunk_groups_multiple_operations(self):
        with undo_chunk("HlibTestChunk"):
            cmds.createNode("transform", name="hlibUndoChunkNode")
            cmds.setAttr("hlibUndoChunkNode.translateX", 5.0)

        self.assertTrue(cmds.objExists("hlibUndoChunkNode"))
        cmds.undo()
        self.assertFalse(cmds.objExists("hlibUndoChunkNode"))

    def test_undoable_wraps_function_in_single_chunk(self):
        @undoable("HlibTestUndoable")
        def create_and_move():
            cmds.createNode("transform", name="hlibUndoableNode")
            cmds.setAttr("hlibUndoableNode.translateX", 3.0)

        create_and_move()
        self.assertTrue(cmds.objExists("hlibUndoableNode"))
        cmds.undo()
        self.assertFalse(cmds.objExists("hlibUndoableNode"))

    def test_undoable_preserves_function_metadata_and_return_value(self):
        @undoable()
        def sample_function():
            """docstring for sample_function."""
            return 42

        self.assertEqual(sample_function.__name__, "sample_function")
        self.assertEqual(sample_function(), 42)


class PreservedSelectionTest(unittest.TestCase):
    """preserved_selection が選択状態を保存・復元することを検証する。"""

    def setUp(self):
        self.nodes = [
            cmds.createNode("transform", name="hlibPreservedSelectionA"),
            cmds.createNode("transform", name="hlibPreservedSelectionB"),
            cmds.createNode("transform", name="hlibPreservedSelectionC"),
        ]

    def tearDown(self):
        for name in self.nodes:
            if cmds.objExists(name):
                cmds.delete(name)
        cmds.select(clear=True)

    def test_restores_original_selection_after_block(self):
        cmds.select(self.nodes[0], replace=True)

        with preserved_selection():
            cmds.select(self.nodes[1], replace=True)
            self.assertEqual(cmds.ls(sl=True, long=True), cmds.ls(self.nodes[1], long=True))

        self.assertEqual(cmds.ls(sl=True, long=True), cmds.ls(self.nodes[0], long=True))

    def test_restores_empty_selection_when_nothing_was_selected(self):
        cmds.select(clear=True)

        with preserved_selection():
            cmds.select(self.nodes[2], replace=True)

        self.assertEqual(cmds.ls(sl=True), [])

    def test_restores_selection_even_when_block_raises(self):
        cmds.select(self.nodes[0], replace=True)

        with self.assertRaises(RuntimeError):
            with preserved_selection():
                cmds.select(self.nodes[1], replace=True)
                raise RuntimeError("boom")

        self.assertEqual(cmds.ls(sl=True, long=True), cmds.ls(self.nodes[0], long=True))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
