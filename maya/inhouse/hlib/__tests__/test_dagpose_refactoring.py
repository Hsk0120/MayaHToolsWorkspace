"""DagPose.mergeの最後の削除境界と接続・削除順を実Mayaで検証する。"""

import sys
import unittest
from unittest import mock

import hlib
import maya.cmds as cmds


class DagPoseRefactoringTest(unittest.TestCase):
    """処理分解後も一時ポーズ・再接続・統合元削除のtransactionを維持する。"""

    def setUp(self):
        """各テストを独立した空シーンとUndoキューで実行する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def test_source_delete_failure_rolls_back_rows_reconnections_and_temporary_pose(self):
        """最後の統合元削除が失敗しても、保存行・再接続・一時ポーズを戻す。"""
        for current_pose in (False, True):
            with self.subTest(currentPose=current_pose):
                cmds.file(new=True, force=True)
                first_skin, target = self._skin_pose("target")
                other_skin, source = self._skin_pose("source")
                source_name = source.getFullName()
                before = self._public_state(target, [first_skin, other_skin])
                original_delete = cmds.delete
                attempted_connections = []
                error = RuntimeError("Injected source delete failure")

                def fail_source_delete(value, **kwargs):
                    """再接続後の統合元削除だけを失敗させる。"""
                    if isinstance(value, list) and source_name in value:
                        attempted_connections.append(other_skin.getBindPose().getFullName())
                        raise error
                    return original_delete(value, **kwargs)

                with mock.patch("maya.cmds.delete", side_effect=fail_source_delete):
                    with self.assertRaises(RuntimeError) as caught:
                        target.merge(source, currentPose=current_pose)
                self.assertIs(caught.exception, error)
                self.assertEqual(attempted_connections, [target.getFullName()])
                self.assertEqual(self._public_state(target, [first_skin, other_skin]), before)
                self.assertTrue(source.isValid())

    def test_temporary_pose_delete_failure_rolls_back_before_skin_reconnection(self):
        """一時ポーズ削除時の失敗を戻し、skin再接続と統合元削除へ進まない。"""
        first_skin, target = self._skin_pose("target")
        other_skin, source = self._skin_pose("source")
        before = self._public_state(target, [first_skin, other_skin])
        member_count = len({node.getFullName() for pose in (target, source) for node in pose.getMembers()})
        original_delete = cmds.delete
        at_failure = []
        error = RuntimeError("Injected temporary pose delete failure")

        def fail_temporary_delete(value, **kwargs):
            """行書込み後の一時dagPose削除だけを失敗させる。"""
            if isinstance(value, str) and cmds.nodeType(value) == "dagPose":
                at_failure.append((len(target.getMembers()), other_skin.getBindPose().getFullName()))
                raise error
            return original_delete(value, **kwargs)

        with mock.patch("maya.cmds.delete", side_effect=fail_temporary_delete):
            with self.assertRaises(RuntimeError) as caught:
                target.merge(source, currentPose=True)
        self.assertIs(caught.exception, error)
        self.assertEqual(at_failure, [(member_count, source.getFullName())])
        self.assertEqual(self._public_state(target, [first_skin, other_skin]), before)
        self.assertTrue(source.isValid())

    def test_source_order_deduplication_reconnects_before_delete_and_one_undo(self):
        """統合元の入力順と重複除去を保ち、再接続後に削除して一回でUndoする。"""
        target_skin, target = self._skin_pose("target")
        first_skin, first = self._skin_pose("first")
        second_skin, second = self._skin_pose("second")
        first_name, second_name = first.getFullName(), second.getFullName()
        events = []
        original_connect = cmds.connectAttr
        original_delete = cmds.delete
        destinations = {first_skin.getFullName() + ".bindPose", second_skin.getFullName() + ".bindPose"}

        def record_connect(source, destination, **kwargs):
            """skinClusterのbindPose接続の順序を記録する。"""
            if destination in destinations:
                events.append(("connect", destination))
            return original_connect(source, destination, **kwargs)

        def record_delete(value, **kwargs):
            """統合元の削除順序を記録する。"""
            if isinstance(value, list):
                events.append(("delete", value[:]))
            return original_delete(value, **kwargs)

        cmds.flushUndo()
        with mock.patch("maya.cmds.connectAttr", side_effect=record_connect):
            with mock.patch("maya.cmds.delete", side_effect=record_delete):
                result = target.merge([second, first, second])
        self.assertIs(result, target)
        self.assertEqual(events, [("connect", second_skin.getFullName() + ".bindPose"),
                                  ("connect", first_skin.getFullName() + ".bindPose"),
                                  ("delete", [second_name, first_name])])
        self.assertEqual([skin.getBindPose() for skin in (target_skin, first_skin, second_skin)],
                         [target, target, target])
        cmds.undo()
        self.assertTrue(cmds.objExists(first_name))
        self.assertTrue(cmds.objExists(second_name))
        self.assertEqual(first_skin.getBindPose().getFullName(), first_name)
        self.assertEqual(second_skin.getBindPose().getFullName(), second_name)
        cmds.redo()
        self.assertFalse(cmds.objExists(first_name))
        self.assertFalse(cmds.objExists(second_name))
        self.assertEqual(first_skin.getBindPose(), target)
        self.assertEqual(second_skin.getBindPose(), target)

    def _skin_pose(self, name):
        """独立したjointとmeshを持つskinClusterとbindPoseを作成する。

        Args:
            name (str): 作成するノード名の接頭辞。

        Returns:
            tuple: skinClusterとそのbindPose。
        """
        joint = cmds.createNode("joint", name=name + "Joint")
        mesh = cmds.polyCube(name=name + "Mesh", ch=False)[0]
        skin = hlib.nodes.Node(cmds.skinCluster(joint, mesh, name=name + "Skin", tsb=True)[0])
        return skin, skin.getBindPose()

    def _public_state(self, target, skins):
        """公開照会でシーンのノード・保存姿勢・bindPose接続を記録する。

        Args:
            target (DagPose): 統合先。
            skins (Iterable[SkinCluster]): 接続を記録するskinCluster。

        Returns:
            tuple: ノード名集合、保存行、各skinClusterのbindPose名。
        """
        rows = [(node.getFullName(), target.getMemberIndex(node),
                 list(target.getMatrix(node)), list(target.getMatrix(node, ws=True)))
                for node in target.getMembers()]
        return set(cmds.ls(long=True)), rows, [skin.getBindPose().getFullName() for skin in skins]


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
