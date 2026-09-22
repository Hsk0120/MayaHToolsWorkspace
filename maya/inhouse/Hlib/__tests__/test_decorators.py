"""Hlib.decorators (undo_chunk/undoable) を検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import Hlib
Hlib.reload_all()
from Hlib.decorators import undo_chunk, undoable


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


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
