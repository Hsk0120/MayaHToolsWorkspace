"""DagPose のメンバー照会・姿勢判定・メンバー編集・統合と SkinCluster.resetBindPose を確かめる。

照会は素の ``cmds.dagPose``・``cmds.getAttr`` と突き合わせ、編集は Undo 1 回で戻ること、
不正な入力が TypeError/ValueError になりシーンを変更しないことを確かめる。
"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.maths import Matrix
from mlib.nodes import Node
from support.specCase import NamespaceCase


def _rounded(values):
    """マトリクスの値を丸めた tuple にする。未設定(None)は None のまま返す。"""
    return None if values is None else tuple(round(value, 6) for value in values)


class _PoseCase(NamespaceCase):
    """joint 連鎖 root→mid→tip と独立した joint・transform を用意する。"""

    PREFIX = "mlibDagPoseOps_"
    CLEAR_SELECTION = True

    def setUp(self):
        super().setUp()
        self.root, self.mid, self.tip = self.chain("root", "mid", "tip")
        cmds.select(clear=True)
        self.free = cmds.ls(cmds.joint(name=self.ns + ":free", position=(3, 0, 0)), long=True)[0]
        cmds.select(clear=True)
        self.xform = cmds.ls(cmds.createNode("transform", name=self.ns + ":xform"), long=True)[0]

    def chain(self, *names, x=0.0):
        """名前の順に親子にした joint を作り、完全パスを返す。"""
        cmds.select(clear=True)
        result = [cmds.ls(cmds.joint(name=self.ns + ":" + name, position=(x, i, 0)), long=True)[0]
                  for i, name in enumerate(names)]
        cmds.select(clear=True)
        return result

    def save(self, *members, name="pose", bindPose=False):
        """素の cmds.dagPose で指定メンバーだけを保存し、DagPose を返す。"""
        pose = cmds.dagPose(list(members), save=True, selection=True, bindPose=bindPose)
        return mlib.getNode(cmds.rename(pose, self.ns + ":" + name))

    @staticmethod
    def raw_members(pose):
        """cmds.dagPose の members 照会を完全パスの集合で返す。"""
        names = cmds.dagPose(pose.getFullName(), query=True, members=True) or []
        return set(cmds.ls(names, long=True))

    @staticmethod
    def raw_not_at_pose(pose):
        """cmds.dagPose の atPose 照会を完全パスの集合で返す。"""
        names = cmds.dagPose(pose.getFullName(), query=True, atPose=True) or []
        return set(cmds.ls(names, long=True))

    @staticmethod
    def pose_state(pose):
        """メンバー・親の接続・保存マトリクスを比較用にまとめる。"""
        name = pose.getFullName()
        if not cmds.objExists(name):
            return None
        state = []
        for index in cmds.getAttr(name + ".members", multiIndices=True) or []:
            source = cmds.listConnections(f"{name}.members[{index}]", source=True, destination=False,
                                          plugs=True, fullNodeName=True)
            if not source:
                # Undo 後に残る未接続の空要素はメンバーではないので比べない。
                continue
            parent = cmds.listConnections(f"{name}.parents[{index}]", source=True, destination=False,
                                          plugs=True, fullNodeName=True)
            world = _rounded(cmds.getAttr(f"{name}.worldMatrix[{index}]"))
            local = _rounded(cmds.getAttr(f"{name}.xformMatrix[{index}]"))
            state.append((index, tuple(source), tuple(parent or ()), world, local))
        return state

    def assert_matrix(self, actual, expected):
        """16 要素のマトリクスが一致することを確かめる。"""
        for a, b in zip(list(actual), list(expected)):
            self.assertAlmostEqual(a, b, places=6)


class QueryTest(_PoseCase):
    """メンバーと保存マトリクスの照会。"""

    def test_members_match_cmds(self):
        pose = self.save(self.root, self.mid, self.tip)
        members = pose.getMembers()
        self.assertIsInstance(members, list)
        self.assertTrue(all(isinstance(item, Node) for item in members))
        self.assertEqual({item.getFullName() for item in members}, self.raw_members(pose))
        indices = pose.getMemberIndices()
        self.assertEqual(indices, sorted(cmds.getAttr(pose.getFullName() + ".members", multiIndices=True)))
        self.assertTrue(all(type(index) is int for index in indices))
        for index, member in zip(indices, members):
            self.assertEqual(pose.getMemberIndex(member), index)
            self.assertEqual(pose.getMemberIndex(member.getFullName()), index)

    def test_indices_skip_disconnected_elements(self):
        pose = self.save(self.root, self.mid, self.tip)
        index = pose.getMemberIndex(self.mid)
        source = cmds.listConnections(f"{pose.getFullName()}.members[{index}]", source=True,
                                      destination=False, plugs=True)[0]
        cmds.disconnectAttr(source, f"{pose.getFullName()}.members[{index}]")
        self.assertNotIn(index, pose.getMemberIndices())
        self.assertEqual([m.getFullName() for m in pose.getMembers()],
                         [m for m in (self.root, self.tip)])

    def test_get_matrix_matches_stored_values(self):
        cmds.setAttr(self.mid + ".rz", 25)
        pose = self.save(self.root, self.mid)
        cmds.setAttr(self.mid + ".rz", 70)
        index = pose.getMemberIndex(self.mid)
        for worldSpace, attr in ((False, "xformMatrix"), (True, "worldMatrix")):
            with self.subTest(worldSpace=worldSpace):
                matrix = pose.getMatrix(self.mid, worldSpace=worldSpace)
                self.assertIs(type(matrix), Matrix)
                self.assert_matrix(matrix, cmds.getAttr(f"{pose.getFullName()}.{attr}[{index}]"))
        default = pose.getMatrix(self.mid)
        self.assert_matrix(default, cmds.getAttr(f"{pose.getFullName()}.xformMatrix[{index}]"))
        # 戻り値は独立したコピーで、変更してもポーズは変わらない。
        before = self.pose_state(pose)
        default[12] = 100.0
        self.assertEqual(self.pose_state(pose), before)

    def test_bind_pose_and_skin_clusters(self):
        pose = self.save(self.root, self.mid)
        self.assertIs(pose.isBindPose(), False)
        self.assertEqual(pose.getSkinClusters(), [])
        mesh = cmds.polyCube(name=self.ns + ":mesh")[0]
        skin = cmds.skinCluster(self.root, self.mid, mesh, toSelectedBones=True, name=self.ns + ":skin")[0]
        bind = mlib.getNode(skin).getBindPose()
        self.assertIs(bind.isBindPose(), True)
        self.assertEqual(bool(cmds.getAttr(bind.getFullName() + ".bindPose")), True)
        skins = bind.getSkinClusters()
        self.assertEqual([item.getFullName() for item in skins], [mlib.getNode(skin).getFullName()])
        self.assertIsInstance(skins[0], mlib.SkinCluster)

    def test_query_errors(self):
        pose = self.save(self.root, self.mid)
        with self.assertRaises(ValueError):
            pose.getMemberIndex(self.free)
        with self.assertRaises(ValueError):
            pose.getMatrix(self.free)
        for value in ("yes", 1, None):
            with self.subTest(worldSpace=value), self.assertRaises(TypeError):
                pose.getMatrix(self.mid, worldSpace=value)
        with self.assertRaises(TypeError):
            pose.getMemberIndex(1.5)
        cmds.delete(pose.getFullName())
        for call in (pose.getMembers, pose.getMemberIndices, pose.isBindPose, pose.isAtPose,
                     pose.getNotAtPose, pose.getSkinClusters):
            with self.subTest(call=call.__name__), self.assertRaisesRegex(RuntimeError, "invalid DagPose"):
                call()


class AtPoseTest(_PoseCase):
    """Maya の atPose 照会と同じ判定。"""

    def test_at_pose_follows_maya(self):
        pose = self.save(self.root, self.mid, self.tip)
        self.assertIs(pose.isAtPose(), True)
        self.assertEqual(pose.getNotAtPose(), [])
        cmds.setAttr(self.mid + ".rz", 30)
        self.assertIs(pose.isAtPose(), False)
        not_at = pose.getNotAtPose()
        self.assertTrue(all(isinstance(item, Node) for item in not_at))
        self.assertEqual({item.getFullName() for item in not_at}, self.raw_not_at_pose(pose))
        self.assertIn(self.mid, {item.getFullName() for item in not_at})
        pose.restore()
        self.assertIs(pose.isAtPose(), True)
        self.assertEqual(pose.getNotAtPose(), [])
        self.assertEqual(self.raw_not_at_pose(pose), set())


class EditTest(_PoseCase):
    """addMembers・removeMembers・reset の結果・Undo・入力検証。"""

    def assert_one_undo(self, pose, action):
        """action の前後の保存情報を比べ、Undo 1 回で戻り Redo で再現することを確かめる。"""
        before = self.pose_state(pose)
        result = action()
        after = self.pose_state(pose)
        self.assertNotEqual(after, before)
        cmds.undo()
        self.assertEqual(self.pose_state(pose), before)
        cmds.redo()
        self.assertEqual(self.pose_state(pose), after)
        return result

    def assert_rejected(self, pose, error, action):
        """action が error で拒否され、保存情報と Undo キューの先頭が変わらないことを確かめる。"""
        before = self.pose_state(pose)
        with self.assertRaises(error):
            action()
        self.assertEqual(self.pose_state(pose), before)

    def test_add_members(self):
        pose = self.save(self.root, self.mid)
        result = self.assert_one_undo(pose, lambda: pose.addMembers(mlib.getNode(self.free), [mlib.getNode(self.xform)]))
        self.assertIs(result, pose)
        self.assertTrue({self.free, self.xform} <= self.raw_members(pose))
        index = pose.getMemberIndex(self.free)
        self.assert_matrix(pose.getMatrix(self.free, worldSpace=True),
                           cmds.getAttr(self.free + ".worldMatrix[0]"))
        self.assertIsInstance(index, int)
        # 既存メンバーは無視し、保存姿勢も更新しない。
        cmds.setAttr(self.root + ".tx", 4)
        before = self.pose_state(pose)
        pose.addMembers(self.root)
        self.assertEqual(self.pose_state(pose), before)

    def test_add_members_rejects(self):
        pose = self.save(self.root, self.mid)
        shape = cmds.polyCube(name=self.ns + ":cube")[0]
        shape = cmds.listRelatives(shape, shapes=True, fullPath=True)[0]
        self.assert_rejected(pose, ValueError, lambda: pose.addMembers())
        self.assert_rejected(pose, ValueError, lambda: pose.addMembers([]))
        self.assert_rejected(pose, ValueError, lambda: pose.addMembers(self.free, shape))
        self.assert_rejected(pose, TypeError, lambda: pose.addMembers(self.free, 3))
        self.assert_rejected(pose, TypeError, lambda: pose.addMembers(mlib.getNode(self.free).getPlug("tx")))

    def test_remove_members(self):
        pose = self.save(self.root, self.mid, self.tip, self.free)
        result = self.assert_one_undo(pose, lambda: pose.removeMembers([self.free]))
        self.assertIs(result, pose)
        self.assertNotIn(self.free, self.raw_members(pose))
        self.assertTrue(cmds.objExists(self.free))

    def test_remove_members_rejects(self):
        pose = self.save(self.root, self.mid)
        self.assert_rejected(pose, ValueError, lambda: pose.removeMembers())
        # 未所属が 1 件でも含まれれば、所属している mid も外さない。
        self.assert_rejected(pose, ValueError, lambda: pose.removeMembers(self.mid, self.free))
        self.assert_rejected(pose, TypeError, lambda: pose.removeMembers(self.mid, object()))

    def test_reset_subset(self):
        pose = self.save(self.root, self.mid, self.tip)
        tip_before = pose.getMatrix(self.tip, worldSpace=True)
        cmds.setAttr(self.mid + ".rz", 30)
        self.assertIs(pose.isAtPose(), False)
        result = self.assert_one_undo(pose, lambda: pose.reset([self.mid]))
        self.assertIs(result, pose)
        self.assert_matrix(pose.getMatrix(self.mid, worldSpace=True), cmds.getAttr(self.mid + ".worldMatrix[0]"))
        self.assert_matrix(pose.getMatrix(self.mid), cmds.getAttr(self.mid + ".matrix"))
        # tip は対象外なので保存姿勢は以前のまま(現在は回転した mid の下で動いている)。
        self.assert_matrix(pose.getMatrix(self.tip, worldSpace=True), tip_before)
        self.assertNotIn(self.mid, self.raw_not_at_pose(pose))

    def test_reset_all(self):
        pose = self.save(self.root, self.mid, self.tip)
        cmds.setAttr(self.mid + ".rz", 30)
        cmds.setAttr(self.root + ".tx", 2)
        self.assert_one_undo(pose, lambda: pose.reset())
        self.assertIs(pose.isAtPose(), True)
        for member in (self.root, self.mid, self.tip):
            self.assert_matrix(pose.getMatrix(member, worldSpace=True), cmds.getAttr(member + ".worldMatrix[0]"))

    def test_reset_rejects(self):
        pose = self.save(self.root, self.mid)
        cmds.setAttr(self.mid + ".rz", 30)
        self.assert_rejected(pose, ValueError, lambda: pose.reset([]))
        self.assert_rejected(pose, ValueError, lambda: pose.reset([self.mid, self.free]))
        self.assert_rejected(pose, TypeError, lambda: pose.reset([self.mid, 7]))
        self.assertIs(pose.isAtPose(), False)


class MergeTest(_PoseCase):
    """merge の統合・削除・競合・Undo。"""

    def test_merge_two_poses(self):
        other_root, other_child = self.chain("oRoot", "oChild", x=5.0)
        for deleteSources in (True, False):
            with self.subTest(deleteSources=deleteSources):
                target = self.save(self.root, self.mid, name="target%d" % deleteSources)
                source = self.save(other_root, other_child, name="source%d" % deleteSources)
                source_name = source.getFullName()
                before = self.pose_state(target)
                result = target.merge(source, deleteSources=deleteSources)
                self.assertIs(result, target)
                after = self.pose_state(target)
                self.assertEqual(self.raw_members(target), {self.root, self.mid, other_root, other_child})
                self.assertEqual(cmds.objExists(source_name), not deleteSources)
                # 統合元の保存マトリクスと親子関係を引き継ぐ。
                self.assert_matrix(target.getMatrix(other_child, worldSpace=True),
                                   cmds.getAttr(other_child + ".worldMatrix[0]"))
                parent = cmds.listConnections(f"{target.getFullName()}.parents[{target.getMemberIndex(other_child)}]",
                                              plugs=True)[0]
                self.assertEqual(parent.split(".")[-1], f"members[{target.getMemberIndex(other_root)}]")
                self.assertIs(target.isAtPose(), True)
                cmds.undo()
                self.assertEqual(self.pose_state(target), before)
                self.assertTrue(cmds.objExists(source_name))
                cmds.redo()
                self.assertEqual(self.pose_state(target), after)
                self.assertEqual(cmds.objExists(source_name), not deleteSources)

    def test_merge_conflict_and_current_pose(self):
        target = self.save(self.root, self.mid, name="target")
        cmds.setAttr(self.mid + ".rz", 40)
        source = self.save(self.mid, self.tip, name="source")
        before = self.pose_state(target)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            target.merge(source)
        self.assertEqual(self.pose_state(target), before)
        self.assertTrue(cmds.objExists(source.getFullName()))
        target.merge([source], currentPose=True, deleteSources=False)
        self.assertEqual(self.raw_members(target), {self.root, self.mid, self.tip})
        self.assert_matrix(target.getMatrix(self.mid, worldSpace=True), cmds.getAttr(self.mid + ".worldMatrix[0]"))
        self.assertIs(target.isAtPose(), True)

    def test_merge_skin_bind_poses(self):
        other_root, other_child = self.chain("oRoot", "oChild", x=5.0)
        mesh_a = cmds.polyCube(name=self.ns + ":meshA")[0]
        mesh_b = cmds.polyCube(name=self.ns + ":meshB")[0]
        skin_a = mlib.getNode(cmds.skinCluster(self.root, self.mid, mesh_a, toSelectedBones=True,
                                               name=self.ns + ":skinA")[0])
        skin_b = mlib.getNode(cmds.skinCluster(other_root, other_child, mesh_b, toSelectedBones=True,
                                               name=self.ns + ":skinB")[0])
        pose_a, pose_b = skin_a.getBindPose(), skin_b.getBindPose()
        self.assertNotEqual(pose_a, pose_b)
        name_b = pose_b.getFullName()
        pose_a.merge(pose_b)
        self.assertFalse(cmds.objExists(name_b))
        self.assertEqual(skin_b.getBindPose(), pose_a)
        self.assertEqual({skin.getFullName() for skin in pose_a.getSkinClusters()},
                         {skin_a.getFullName(), skin_b.getFullName()})
        self.assertIs(pose_a.isAtPose(), True)
        cmds.undo()
        self.assertTrue(cmds.objExists(name_b))
        self.assertEqual(skin_b.getBindPose().getFullName(), name_b)

    def test_merge_rejects(self):
        target = self.save(self.root, self.mid, name="target")
        source = self.save(self.free, name="source")
        bind = self.save(self.xform, name="bind", bindPose=True)
        before = self.pose_state(target)
        cases = (
            (TypeError, lambda: target.merge(source, currentPose=1)),
            (TypeError, lambda: target.merge(source, deleteSources="yes")),
            (ValueError, lambda: target.merge([])),
            (ValueError, lambda: target.merge(self.free)),
            (ValueError, lambda: target.merge(bind)),
            (TypeError, lambda: target.merge([source, 3])),
        )
        for error, action in cases:
            with self.subTest(error=error.__name__), self.assertRaises(error):
                action()
            self.assertEqual(self.pose_state(target), before)
            self.assertTrue(cmds.objExists(source.getFullName()))
        # 自身だけの指定は何もしない。
        self.assertIs(target.merge(target), target)
        self.assertEqual(self.pose_state(target), before)


class SkinResetBindPoseTest(_PoseCase):
    """SkinCluster.resetBindPose は保存姿勢だけを更新する。"""

    def make_skin(self):
        mesh = cmds.polyCube(name=self.ns + ":mesh", subdivisionsY=2)[0]
        cmds.setAttr(self.root + ".ty", -0.5)
        name = cmds.skinCluster(self.root, self.mid, mesh, toSelectedBones=True, name=self.ns + ":skin")[0]
        return mlib.getNode(name)

    def test_reset_bind_pose(self):
        skin = self.make_skin()
        pose = skin.getBindPose()
        name = skin.getFullName()
        bind_pre = [cmds.getAttr(f"{name}.bindPreMatrix[{i}]") for i in range(2)]
        weights = cmds.getAttr(name + ".weightList[*].weights[*]")
        cmds.setAttr(self.mid + ".rz", 35)
        cmds.setAttr(self.root + ".tx", 1.5)
        self.assertIs(pose.isAtPose(), False)
        before = self.pose_state(pose)
        self.assertIs(skin.resetBindPose(), skin)
        after = self.pose_state(pose)
        for member in (self.root, self.mid):
            self.assert_matrix(pose.getMatrix(member, worldSpace=True), cmds.getAttr(member + ".worldMatrix[0]"))
            self.assert_matrix(pose.getMatrix(member), cmds.getAttr(member + ".matrix"))
        self.assertIs(pose.isAtPose(), True)
        for index, values in enumerate(bind_pre):
            self.assert_matrix(cmds.getAttr(f"{name}.bindPreMatrix[{index}]"), values)
        self.assertEqual(cmds.getAttr(name + ".weightList[*].weights[*]"), weights)
        cmds.undo()
        self.assertEqual(self.pose_state(pose), before)
        cmds.redo()
        self.assertEqual(self.pose_state(pose), after)

    def test_reset_bind_pose_errors(self):
        skin = self.make_skin()
        pose = skin.getBindPose()
        cmds.dagPose(self.mid, remove=True, name=pose.getFullName())
        cmds.setAttr(self.root + ".tx", 2)
        before = self.pose_state(pose)
        with self.assertRaises(ValueError):
            skin.resetBindPose()
        self.assertEqual(self.pose_state(pose), before)
        cmds.disconnectAttr(pose.getFullName() + ".message", skin.getFullName() + ".bindPose")
        with self.assertRaisesRegex(RuntimeError, "No bind pose"):
            skin.resetBindPose()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
