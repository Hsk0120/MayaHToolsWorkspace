"""高速化で保持すべき評価・Undo・更新時検証の契約を確認する。"""
from maya.api.OpenMaya import MSpace
import sys
import unittest
from unittest.mock import patch

import maya.cmds as cmds
import hlib

hlib.reload()
from hlib.decorators._fast import fast_edit, is_fast
from hlib.decorators.undo import undo_chunk, undo_transaction


class PerformanceContractsTest(unittest.TestCase):
    """速度ではなく、最適化で失いやすいシーン操作の意味を検証する。"""

    def setUp(self):
        """専用テストシーンを初期化する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg")

    def test_fast_validation_and_nested_state(self):
        """省略・明示False・異常引数・例外のどれでも状態を漏らさない。"""
        @fast_edit
        def inner(value, *, fast=False):
            if value == "fail":
                raise ValueError("test")
            return is_fast()

        @fast_edit
        def outer(*, fast=False):
            return inner(1, fast=False)

        self.assertFalse(inner(1))
        self.assertTrue(outer(fast=True))
        self.assertFalse(is_fast())
        for kwargs in ({"fast": 1}, {"fast": True, "unknown": 1}):
            with self.assertRaises(TypeError):
                inner(1, **kwargs)
            self.assertFalse(is_fast())
        with self.assertRaises(TypeError):
            inner(fast=True)
        with self.assertRaises(ValueError):
            inner("fail", fast=True)
        self.assertFalse(is_fast())

        @fast_edit
        def positional(value, fast=False):
            return is_fast()

        self.assertTrue(positional(1, True))
        with self.assertRaises(TypeError):
            positional(1, 1)

    def test_nested_chunks_one_pair_and_redo(self):
        """通常の入れ子は1チャンクでまとめ、外側の名前とRedoを維持する。"""
        node = hlib.getNode(cmds.createNode("transform"))
        original = cmds.undoInfo
        with patch.object(cmds, "undoInfo", wraps=original) as calls:
            with undo_chunk("outer"):
                node.plug("tx").set(3)
                with undo_chunk("inner"):
                    node.plug("ty").set(7)
        self.assertEqual(sum(bool(c[1].get("openChunk")) for c in calls.call_args_list), 1)
        self.assertEqual(sum(bool(c[1].get("closeChunk")) for c in calls.call_args_list), 1)
        self.assertEqual(cmds.undoInfo(q=True, undoName=True), "outer")
        cmds.undo()
        self.assertEqual(tuple(node.plug("translate").get()), (0, 0, 0))
        cmds.redo()
        self.assertEqual(tuple(node.plug("translate").get()), (3, 7, 0))

    def test_chunk_state_after_open_failure_and_body_exception(self):
        """開閉の失敗や本体の例外で後続操作のチャンクを省略しない。"""
        with patch.object(cmds, "undoInfo", side_effect=RuntimeError("open failed")):
            with self.assertRaises(RuntimeError):
                with undo_chunk("failed"):
                    pass
        with self.assertRaises(ValueError):
            with undo_chunk("body failed"):
                raise ValueError("body")
        node = hlib.getNode(cmds.createNode("transform"))
        node.plug("tx").set(8)
        cmds.undo()
        self.assertEqual(node.plug("tx").get(), 0)

    def test_transaction_is_not_suppressed(self):
        """トランザクション自体の独立チャンクは通常チャンク内でも維持する。"""
        with patch.object(cmds, "undoInfo") as calls:
            with undo_chunk("outer"):
                with undo_transaction("transaction"):
                    with undo_chunk("inner"):
                        pass
        names = [c[1].get("chunkName") for c in calls.call_args_list if c[1].get("openChunk")]
        self.assertEqual(names, ["outer", "transaction"])
        node = hlib.getNode(cmds.createNode("transform"))
        with self.assertRaises(ValueError):
            with undo_transaction("rollback"):
                node.plug("tx").set(9)
                raise ValueError("rollback")
        self.assertEqual(node.plug("tx").get(), 0)

    def assert_matrix(self, node):
        """対象インスタンスのworldMatrixとローカルmatrixの一致を確認する。"""
        path = node.dagPath()
        for ws, attr in ((True, "worldMatrix[%d]" % path.instanceNumber()), (False, "matrix")):
            expected = cmds.getAttr(path.fullPathName() + "." + attr)
            for a, b in zip(node.getMatrix(space=MSpace.kWorld if ws else MSpace.kObject), expected):
                self.assertAlmostEqual(a, b, places=8)

    def test_matrix_joint_and_transform_evaluation(self):
        """SSC・負スケール・シアー・OPM・継承無効・時間変更に追従する。"""
        parent = cmds.createNode("joint")
        cmds.setAttr(parent + ".scale", -2, 3, 1.5)
        cmds.setAttr(parent + ".rotate", 12, 23, 34)
        for kind in ("transform", "joint"):
            name = cmds.createNode(kind, parent=parent)
            node = hlib.getNode(name)
            cmds.setAttr(name + ".shear", .2, .1, -.15)
            cmds.setAttr(name + ".rotate", 17, -23, 6)
            if kind == "joint":
                cmds.connectAttr(parent + ".scale", name + ".inverseScale")
                cmds.setAttr(name + ".jointOrient", 11, 9, 7)
            source = cmds.createNode("composeMatrix")
            cmds.setAttr(source + ".inputTranslate", 4, 8, 2)
            cmds.connectAttr(source + ".outputMatrix", name + ".offsetParentMatrix")
            cmds.setKeyframe(name, at="tx", t=1, v=0)
            cmds.setKeyframe(name, at="tx", t=10, v=7)
            for frame in (1, 10, 4):
                cmds.currentTime(frame)
                for inherit in (True, False):
                    cmds.setAttr(name + ".inheritsTransform", inherit)
                    if kind == "joint":
                        for ssc in (True, False):
                            cmds.setAttr(name + ".segmentScaleCompensate", ssc)
                            self.assert_matrix(node)
                    else:
                        self.assert_matrix(node)

    def test_matrix_instance_rename_reparent_delete_undo(self):
        """DAGパスごとの参照と削除Undo後の復帰を確認する。"""
        a = cmds.createNode("transform", name="a")
        b = cmds.createNode("transform", name="b")
        cmds.setAttr(a + ".tx", 3)
        cmds.setAttr(b + ".ty", 7)
        n = cmds.createNode("transform", name="child", parent=a)
        cmds.parent(n, b, add=True)
        first, second = hlib.getNode("|a|child"), hlib.getNode("|b|child")
        self.assert_matrix(first)
        self.assert_matrix(second)
        self.assertNotEqual(list(first.getMatrix(space=MSpace.kWorld)), list(second.getMatrix(space=MSpace.kWorld)))
        n = cmds.createNode("transform", name="single")
        node = hlib.getNode(n)
        n = cmds.rename(n, "renamed")
        cmds.parent(n, a)
        self.assert_matrix(node)
        cmds.delete(node.fullName())
        with self.assertRaises(RuntimeError):
            node.getMatrix(space=MSpace.kWorld)
        cmds.undo()
        self.assert_matrix(node)

    def test_fast_checks_follow_edits(self):
        """範囲・ロック・接続・単位・動的アトリビュート削除を再照会する。"""
        name = cmds.createNode("transform")
        node = hlib.getNode(name)
        cmds.addAttr(name, ln="bounded", at="double", min=0, max=10)
        plug = node.plug("bounded")
        plug.set(8, fast=True)
        cmds.addAttr(name + ".bounded", e=True, max=5)
        with self.assertRaises(RuntimeError):
            plug.set(8, fast=True)
        cmds.setAttr(name + ".bounded", lock=True)
        with self.assertRaises(RuntimeError):
            plug.set(2, fast=True)
        cmds.setAttr(name + ".bounded", lock=False)
        cmds.connectAttr(name + ".tx", name + ".bounded")
        with self.assertRaises(RuntimeError):
            plug.set(2, fast=True)
        cmds.disconnectAttr(name + ".tx", name + ".bounded")
        cmds.deleteAttr(name + ".bounded")
        with self.assertRaises(RuntimeError):
            plug.set(2, fast=True)
        cmds.undo()
        plug.set(2, fast=True)
        for unit in ("cm", "m"):
            cmds.currentUnit(linear=unit)
            node.plug("tx").set(3, fast=True)
            self.assertAlmostEqual(node.plug("tx").mplug().asMDistance().asCentimeters(), 3)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
