"""mlib.decorator (undoChunk/preservedSelection/preservedSkinShape) を検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.decorator import preservedSelection, preservedSkinShape, undoChunk, undoTransaction
from mlib.nodes.joint import Joint


class UndoDecoratorsTest(unittest.TestCase):
    """undoChunk のwith構文とデコレータ が単一Undoチャンクとして機能することを検証する。"""

    def tearDown(self):
        for name in ("mlibUndoChunkNode", "mlibUndoableNode"):
            if cmds.objExists(name):
                cmds.delete(name)

    def test_decorator_repeated_calls_and_nested_chunks(self):
        @undoChunk("outer")
        def create_and_move():
            """Nested chunk example."""
            with undoChunk("inner"):
                node = cmds.createNode("transform", name="mlibUndoChunkNode")
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
        with undoChunk("mlibTestChunk"):
            cmds.createNode("transform", name="mlibUndoChunkNode")
            cmds.setAttr("mlibUndoChunkNode.translateX", 5.0)

        self.assertTrue(cmds.objExists("mlibUndoChunkNode"))
        cmds.undo()
        self.assertFalse(cmds.objExists("mlibUndoChunkNode"))

    def test_public_operations_have_separate_undo_steps(self):
        node = mlib.createNode("transform", name="mlibUndoChunkNode")
        node.getPlug("visibility").set(False)
        cmds.undo()
        self.assertTrue(cmds.objExists("mlibUndoChunkNode"))
        self.assertTrue(cmds.getAttr("mlibUndoChunkNode.visibility"))
        cmds.undo()
        self.assertFalse(cmds.objExists("mlibUndoChunkNode"))
        cmds.redo()
        cmds.redo()
        self.assertFalse(cmds.getAttr("mlibUndoChunkNode.visibility"))

    def test_tool_groups_public_operations_and_queries_add_no_step(self):
        @undoChunk("createControlTool")
        def create_control():
            node = mlib.createNode("transform", name="mlibUndoChunkNode")
            node.getPlug("visibility").set(False)
            return node

        node = create_control()
        mlib.ls(type="transform")
        mlib.getNode(node.getName())
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "createControlTool")
        cmds.undo()
        self.assertFalse(cmds.objExists("mlibUndoChunkNode"))
        cmds.redo()
        self.assertFalse(cmds.getAttr("mlibUndoChunkNode.visibility"))

    def test_undo_chunk_wraps_function_in_single_chunk(self):
        @undoChunk("mlibTestUndoable")
        def create_and_move():
            cmds.createNode("transform", name="mlibUndoableNode")
            cmds.setAttr("mlibUndoableNode.translateX", 3.0)

        create_and_move()
        self.assertTrue(cmds.objExists("mlibUndoableNode"))
        cmds.undo()
        self.assertFalse(cmds.objExists("mlibUndoableNode"))

    def test_undo_chunk_propagates_exception_and_still_closes_chunk(self):
        with self.assertRaises(RuntimeError):
            with undoChunk("mlibTestChunkError"):
                cmds.createNode("transform", name="mlibUndoChunkNode")
                raise RuntimeError("boom")
        # 例外前の操作はロールバックされない(自動ロールバックしない設計)。
        self.assertTrue(cmds.objExists("mlibUndoChunkNode"))

        # チャンクが finally で正しく閉じられていれば、直後に別のチャンクを
        # 問題なく開始できる。
        with undoChunk("mlibTestChunkAfterError"):
            cmds.setAttr("mlibUndoChunkNode.translateX", 9.0)
        self.assertEqual(cmds.getAttr("mlibUndoChunkNode.translateX"), 9.0)

    def test_undo_chunk_propagates_exception_without_rollback(self):
        @undoChunk("mlibTestUndoableError")
        def create_then_fail():
            cmds.createNode("transform", name="mlibUndoableNode")
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            create_then_fail()
        # undoChunk は完了済み操作を自動ロールバックしない。
        self.assertTrue(cmds.objExists("mlibUndoableNode"))

    def test_undo_chunk_preserves_function_metadata_and_return_value(self):
        @undoChunk()
        def sample_function():
            """docstring for sample_function."""
            return 42

        self.assertEqual(sample_function.__name__, "sample_function")
        self.assertEqual(sample_function(), 42)


class UndoTransactionTest(unittest.TestCase):
    """undoTransaction が例外時のみ自動ロールバックすることを検証する。"""

    def tearDown(self):
        for name in ("mlibUndoTxnBefore", "mlibUndoTxnNode", "mlibUndoTxnA", "mlibUndoTxnB"):
            if cmds.objExists(name):
                cmds.delete(name)

    def test_commits_normally_when_no_exception(self):
        with undoTransaction("mlibUndoTxnCommit"):
            cmds.createNode("transform", name="mlibUndoTxnNode")
            cmds.setAttr("mlibUndoTxnNode.translateX", 5.0)

        self.assertTrue(cmds.objExists("mlibUndoTxnNode"))
        # 正常終了時はロールバックせず、undoChunk と同様に1回のUndoにまとまる。
        cmds.undo()
        self.assertFalse(cmds.objExists("mlibUndoTxnNode"))

    def test_rolls_back_all_operations_on_exception(self):
        with self.assertRaises(RuntimeError):
            with undoTransaction("mlibUndoTxnRollback"):
                cmds.createNode("transform", name="mlibUndoTxnA")
                cmds.createNode("transform", name="mlibUndoTxnB")
                raise RuntimeError("boom")

        self.assertFalse(cmds.objExists("mlibUndoTxnA"))
        self.assertFalse(cmds.objExists("mlibUndoTxnB"))

    def test_exception_type_and_message_are_preserved(self):
        with self.assertRaises(ValueError) as context:
            with undoTransaction("mlibUndoTxnMessage"):
                cmds.createNode("transform", name="mlibUndoTxnNode")
                raise ValueError("specific message")
        self.assertEqual(str(context.exception), "specific message")
        self.assertFalse(cmds.objExists("mlibUndoTxnNode"))

    def test_empty_body_exception_does_not_undo_unrelated_prior_operation(self):
        # チャンク内で実際の変更が無いまま例外になっても、直前の無関係な
        # 操作を巻き込んでUndoしてはならない(空チャンクの既定挙動への対策)。
        cmds.createNode("transform", name="mlibUndoTxnBefore")
        self.assertTrue(cmds.objExists("mlibUndoTxnBefore"))

        with self.assertRaises(RuntimeError):
            with undoTransaction("mlibUndoTxnEmptyBody"):
                raise RuntimeError("boom before any Maya operation")

        self.assertTrue(cmds.objExists("mlibUndoTxnBefore"))

    def test_decorator_usage_rolls_back_on_exception(self):
        @undoTransaction("mlibUndoTxnDecorator")
        def create_then_fail():
            cmds.createNode("transform", name="mlibUndoTxnNode")
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            create_then_fail()
        self.assertFalse(cmds.objExists("mlibUndoTxnNode"))

    def test_decorator_usage_commits_on_success(self):
        @undoTransaction("mlibUndoTxnDecoratorOk")
        def create():
            cmds.createNode("transform", name="mlibUndoTxnNode")
            return 42

        self.assertEqual(create(), 42)
        self.assertTrue(cmds.objExists("mlibUndoTxnNode"))


class PreservedSelectionTest(unittest.TestCase):
    """preservedSelection が選択状態を保存・復元することを検証する。"""

    def setUp(self):
        self.nodes = [
            cmds.createNode("transform", name="mlibPreservedSelectionA"),
            cmds.createNode("transform", name="mlibPreservedSelectionB"),
            cmds.createNode("transform", name="mlibPreservedSelectionC"),
        ]

    def tearDown(self):
        for name in self.nodes:
            if cmds.objExists(name):
                cmds.delete(name)
        cmds.select(clear=True)

    def test_restores_original_selection_after_block(self):
        cmds.select(self.nodes[0], replace=True)

        with preservedSelection():
            cmds.select(self.nodes[1], replace=True)
            self.assertEqual(cmds.ls(sl=True, long=True), cmds.ls(self.nodes[1], long=True))

        self.assertEqual(cmds.ls(sl=True, long=True), cmds.ls(self.nodes[0], long=True))

    def test_restores_empty_selection_when_nothing_was_selected(self):
        cmds.select(clear=True)

        with preservedSelection():
            cmds.select(self.nodes[2], replace=True)

        self.assertEqual(cmds.ls(sl=True), [])

    def test_restores_selection_even_when_block_raises(self):
        cmds.select(self.nodes[0], replace=True)

        with self.assertRaises(RuntimeError):
            with preservedSelection():
                cmds.select(self.nodes[1], replace=True)
                raise RuntimeError("boom")

        self.assertEqual(cmds.ls(sl=True, long=True), cmds.ls(self.nodes[0], long=True))


class PreservedSkinShapeTest(unittest.TestCase):
    """preservedSkinShape がjoint姿勢の変更中もスキン変形を保つことを検証する。"""

    def setUp(self):
        self.joint = cmds.createNode("joint", name="mlibPreservedSkinShapeJoint")
        cmds.setAttr(self.joint + ".translateY", 1.0)
        self.mesh_transform, _ = cmds.polyCube(name="mlibPreservedSkinShapeMesh")
        cmds.move(0, 1, 0, self.mesh_transform, relative=True)
        self.skin_name = cmds.skinCluster(self.joint, self.mesh_transform)[0]

    def tearDown(self):
        if cmds.objExists(self.mesh_transform):
            cmds.delete(self.mesh_transform)
        if cmds.objExists(self.joint):
            cmds.delete(self.joint)
        cmds.select(clear=True)

    def _vertex_positions(self):
        return cmds.xform(self.mesh_transform + ".vtx[*]", query=True, worldSpace=True, translation=True)

    def test_reorienting_joint_does_not_move_the_mesh(self):
        before = self._vertex_positions()
        before_world_matrix = cmds.xform(self.joint, query=True, worldSpace=True, matrix=True)

        with preservedSkinShape([Joint(self.joint)]) as skins:
            self.assertEqual([skin.getFullName() for skin in skins], [self.skin_name])
            cmds.setAttr(self.joint + ".jointOrientZ", 45.0)

        after_world_matrix = cmds.xform(self.joint, query=True, worldSpace=True, matrix=True)
        self.assertNotEqual(after_world_matrix, before_world_matrix)
        after = self._vertex_positions()
        for a, b in zip(after, before):
            self.assertAlmostEqual(a, b, places=6)

    def test_normal_deformation_resumes_after_the_block(self):
        # cmds.skinCluster(query=True, moveJointsMode=True) は常にNoneを返す既知のMaya挙動
        # のため、フラグ値ではなく「ブロックを抜けた後は通常通りjointの回転がメッシュへ
        # 反映される(=moveJointsModeが元に戻っている)」という観測可能な挙動で検証する。
        with preservedSkinShape([Joint(self.joint)]):
            cmds.setAttr(self.joint + ".jointOrientZ", 45.0)

        before = self._vertex_positions()
        cmds.setAttr(self.joint + ".rotateZ", 30.0)
        after = self._vertex_positions()
        self.assertNotEqual(after, before)

    def test_normal_deformation_resumes_even_when_block_raises(self):
        with self.assertRaises(RuntimeError):
            with preservedSkinShape([Joint(self.joint)]):
                raise RuntimeError("boom")

        before = self._vertex_positions()
        cmds.setAttr(self.joint + ".rotateZ", 30.0)
        after = self._vertex_positions()
        self.assertNotEqual(after, before)

    def test_is_undoable_as_a_single_step(self):
        before = self._vertex_positions()
        original_orient = cmds.getAttr(self.joint + ".jointOrientZ")

        with preservedSkinShape([Joint(self.joint)]):
            cmds.setAttr(self.joint + ".jointOrientZ", 45.0)

        cmds.undo()

        self.assertAlmostEqual(cmds.getAttr(self.joint + ".jointOrientZ"), original_orient, places=6)
        after = self._vertex_positions()
        for a, b in zip(after, before):
            self.assertAlmostEqual(a, b, places=6)

    def test_ignores_joints_without_a_skin_cluster(self):
        lone_joint = cmds.createNode("joint", name="mlibPreservedSkinShapeLoneJoint")
        try:
            with preservedSkinShape([Joint(lone_joint)]) as skins:
                self.assertEqual(list(skins), [])
                cmds.setAttr(lone_joint + ".jointOrientZ", 45.0)
            self.assertAlmostEqual(cmds.getAttr(lone_joint + ".jointOrientZ"), 45.0, places=6)
        finally:
            if cmds.objExists(lone_joint):
                cmds.delete(lone_joint)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
