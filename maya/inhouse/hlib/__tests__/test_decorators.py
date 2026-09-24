"""hlib.decorators (undo_chunk/preserved_selection/preserved_skin_shape) を検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.decorators import preserved_selection, preserved_skin_shape, undo_chunk, undo_transaction
from hlib.nodes.joint import Joint


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

    def test_public_operations_have_separate_undo_steps(self):
        node = hlib.createNode("transform", name="hlibUndoChunkNode")
        node.attr("visibility").set(False)
        cmds.undo()
        self.assertTrue(cmds.objExists("hlibUndoChunkNode"))
        self.assertTrue(cmds.getAttr("hlibUndoChunkNode.visibility"))
        cmds.undo()
        self.assertFalse(cmds.objExists("hlibUndoChunkNode"))
        cmds.redo()
        cmds.redo()
        self.assertFalse(cmds.getAttr("hlibUndoChunkNode.visibility"))

    def test_tool_groups_public_operations_and_queries_add_no_step(self):
        @undo_chunk("createControlTool")
        def create_control():
            node = hlib.createNode("transform", name="hlibUndoChunkNode")
            node.attr("visibility").set(False)
            return node

        node = create_control()
        hlib.ls(type="transform")
        hlib.node(node.name())
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "createControlTool")
        cmds.undo()
        self.assertFalse(cmds.objExists("hlibUndoChunkNode"))
        cmds.redo()
        self.assertFalse(cmds.getAttr("hlibUndoChunkNode.visibility"))

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


class UndoTransactionTest(unittest.TestCase):
    """undo_transaction が例外時のみ自動ロールバックすることを検証する。"""

    def tearDown(self):
        for name in ("hlibUndoTxnBefore", "hlibUndoTxnNode", "hlibUndoTxnA", "hlibUndoTxnB"):
            if cmds.objExists(name):
                cmds.delete(name)

    def test_commits_normally_when_no_exception(self):
        with undo_transaction("hlibUndoTxnCommit"):
            cmds.createNode("transform", name="hlibUndoTxnNode")
            cmds.setAttr("hlibUndoTxnNode.translateX", 5.0)

        self.assertTrue(cmds.objExists("hlibUndoTxnNode"))
        # 正常終了時はロールバックせず、undo_chunk と同様に1回のUndoにまとまる。
        cmds.undo()
        self.assertFalse(cmds.objExists("hlibUndoTxnNode"))

    def test_rolls_back_all_operations_on_exception(self):
        with self.assertRaises(RuntimeError):
            with undo_transaction("hlibUndoTxnRollback"):
                cmds.createNode("transform", name="hlibUndoTxnA")
                cmds.createNode("transform", name="hlibUndoTxnB")
                raise RuntimeError("boom")

        self.assertFalse(cmds.objExists("hlibUndoTxnA"))
        self.assertFalse(cmds.objExists("hlibUndoTxnB"))

    def test_exception_type_and_message_are_preserved(self):
        with self.assertRaises(ValueError) as context:
            with undo_transaction("hlibUndoTxnMessage"):
                cmds.createNode("transform", name="hlibUndoTxnNode")
                raise ValueError("specific message")
        self.assertEqual(str(context.exception), "specific message")
        self.assertFalse(cmds.objExists("hlibUndoTxnNode"))

    def test_empty_body_exception_does_not_undo_unrelated_prior_operation(self):
        # チャンク内で実際の変更が無いまま例外になっても、直前の無関係な
        # 操作を巻き込んでUndoしてはならない(空チャンクの既定挙動への対策)。
        cmds.createNode("transform", name="hlibUndoTxnBefore")
        self.assertTrue(cmds.objExists("hlibUndoTxnBefore"))

        with self.assertRaises(RuntimeError):
            with undo_transaction("hlibUndoTxnEmptyBody"):
                raise RuntimeError("boom before any Maya operation")

        self.assertTrue(cmds.objExists("hlibUndoTxnBefore"))

    def test_decorator_usage_rolls_back_on_exception(self):
        @undo_transaction("hlibUndoTxnDecorator")
        def create_then_fail():
            cmds.createNode("transform", name="hlibUndoTxnNode")
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            create_then_fail()
        self.assertFalse(cmds.objExists("hlibUndoTxnNode"))

    def test_decorator_usage_commits_on_success(self):
        @undo_transaction("hlibUndoTxnDecoratorOk")
        def create():
            cmds.createNode("transform", name="hlibUndoTxnNode")
            return 42

        self.assertEqual(create(), 42)
        self.assertTrue(cmds.objExists("hlibUndoTxnNode"))


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


class PreservedSkinShapeTest(unittest.TestCase):
    """preserved_skin_shape がjoint姿勢の変更中もスキン変形を保つことを検証する。"""

    def setUp(self):
        self.joint = cmds.createNode("joint", name="hlibPreservedSkinShapeJoint")
        cmds.setAttr(self.joint + ".translateY", 1.0)
        self.mesh_transform, _ = cmds.polyCube(name="hlibPreservedSkinShapeMesh")
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

        with preserved_skin_shape([Joint(self.joint)]) as skins:
            self.assertEqual([skin.full_name for skin in skins], [self.skin_name])
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
        with preserved_skin_shape([Joint(self.joint)]):
            cmds.setAttr(self.joint + ".jointOrientZ", 45.0)

        before = self._vertex_positions()
        cmds.setAttr(self.joint + ".rotateZ", 30.0)
        after = self._vertex_positions()
        self.assertNotEqual(after, before)

    def test_normal_deformation_resumes_even_when_block_raises(self):
        with self.assertRaises(RuntimeError):
            with preserved_skin_shape([Joint(self.joint)]):
                raise RuntimeError("boom")

        before = self._vertex_positions()
        cmds.setAttr(self.joint + ".rotateZ", 30.0)
        after = self._vertex_positions()
        self.assertNotEqual(after, before)

    def test_is_undoable_as_a_single_step(self):
        before = self._vertex_positions()
        original_orient = cmds.getAttr(self.joint + ".jointOrientZ")

        with preserved_skin_shape([Joint(self.joint)]):
            cmds.setAttr(self.joint + ".jointOrientZ", 45.0)

        cmds.undo()

        self.assertAlmostEqual(cmds.getAttr(self.joint + ".jointOrientZ"), original_orient, places=6)
        after = self._vertex_positions()
        for a, b in zip(after, before):
            self.assertAlmostEqual(a, b, places=6)

    def test_ignores_joints_without_a_skin_cluster(self):
        lone_joint = cmds.createNode("joint", name="hlibPreservedSkinShapeLoneJoint")
        try:
            with preserved_skin_shape([Joint(lone_joint)]) as skins:
                self.assertEqual(list(skins), [])
                cmds.setAttr(lone_joint + ".jointOrientZ", 45.0)
            self.assertAlmostEqual(cmds.getAttr(lone_joint + ".jointOrientZ"), 45.0, places=6)
        finally:
            if cmds.objExists(lone_joint):
                cmds.delete(lone_joint)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
