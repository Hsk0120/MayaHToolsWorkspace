"""hlib.decorators (undo_chunk/preserved_selection) を検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.decorators import preserved_selection, undo_chunk


class UndoDecoratorsTest(unittest.TestCase):
    """undo_chunk のwith構文とデコレータ が単一Undoチャンクとして機能することを検証する。"""

    def tearDown(self):
        for name in ("hlibUndoChunkNode", "hlibUndoableNode"):
            if cmds.objExists(name):
                cmds.delete(name)

    def test_decorator_repeated_calls_and_nested_chunks(self):
        @undo_chunk("outer")
        def create_and_move():
            """Nested chunk example."""
            with undo_chunk("inner"):
                node = cmds.createNode("transform", name="hlibUndoChunkNode")
                cmds.setAttr(node + ".translateX", 7)
            return node

        self.assertEqual(create_and_move.__doc__, "Nested chunk example.")
        for _ in range(2):
            node = create_and_move()
            self.assertEqual(cmds.undoInfo(query=True, undoName=True), "outer")
            cmds.undo()
            self.assertFalse(cmds.objExists(node))
            cmds.redo()
            self.assertEqual(cmds.getAttr(node + ".translateX"), 7)
            cmds.undo()

    def test_undo_chunk_groups_multiple_operations(self):
        with undo_chunk("hlibTestChunk"):
            cmds.createNode("transform", name="hlibUndoChunkNode")
            cmds.setAttr("hlibUndoChunkNode.translateX", 5.0)

        self.assertTrue(cmds.objExists("hlibUndoChunkNode"))
        cmds.undo()
        self.assertFalse(cmds.objExists("hlibUndoChunkNode"))

    def test_undo_chunk_wraps_function_in_single_chunk(self):
        @undo_chunk("hlibTestUndoable")
        def create_and_move():
            cmds.createNode("transform", name="hlibUndoableNode")
            cmds.setAttr("hlibUndoableNode.translateX", 3.0)

        create_and_move()
        self.assertTrue(cmds.objExists("hlibUndoableNode"))
        cmds.undo()
        self.assertFalse(cmds.objExists("hlibUndoableNode"))

    def test_undo_chunk_propagates_exception_and_still_closes_chunk(self):
        with self.assertRaises(RuntimeError):
            with undo_chunk("hlibTestChunkError"):
                cmds.createNode("transform", name="hlibUndoChunkNode")
                raise RuntimeError("boom")
        # 例外前の操作はロールバックされない(自動ロールバックしない設計)。
        self.assertTrue(cmds.objExists("hlibUndoChunkNode"))

        # チャンクが finally で正しく閉じられていれば、直後に別のチャンクを
        # 問題なく開始できる。
        with undo_chunk("hlibTestChunkAfterError"):
            cmds.setAttr("hlibUndoChunkNode.translateX", 9.0)
        self.assertEqual(cmds.getAttr("hlibUndoChunkNode.translateX"), 9.0)

    def test_undo_chunk_propagates_exception_without_rollback(self):
        @undo_chunk("hlibTestUndoableError")
        def create_then_fail():
            cmds.createNode("transform", name="hlibUndoableNode")
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            create_then_fail()
        # undo_chunk は完了済み操作を自動ロールバックしない。
        self.assertTrue(cmds.objExists("hlibUndoableNode"))

    def test_undo_chunk_preserves_function_metadata_and_return_value(self):
        @undo_chunk()
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
