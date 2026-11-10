"""Joint.delete・Joints.delete・Joints.removeInfluence の契約を固定する。

- 削除の前に自身と子孫の influence を外し、ウェイトは残る最も近い祖先へ集まる。
- ウェイトのロックは一時的に外して元へ戻し、レイヤーでは拒否しない。fast も同じ結果になる。
- 削除できない場合は何も変えない。mlib.delete は Maya 標準の削除のまま。
"""

import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import Joints, SkinCluster
from support.specCase import NamespaceCase


class JointDeleteTest(NamespaceCase):
    """root→mid→tip と other にバインドした平面のウェイトで確かめる。"""

    PREFIX = "mlibSpecJointDelete_"
    ENABLE_UNDO = True

    def setUp(self):
        super().setUp()
        cmds.select(clear=True)
        self.root = mlib.getNode(cmds.joint(name=self.name("root"), position=(0, 0, 0)))
        self.mid = mlib.getNode(cmds.joint(name=self.name("mid"), position=(1, 0, 0)))
        self.tip = mlib.getNode(cmds.joint(name=self.name("tip"), position=(2, 0, 0)))
        cmds.select(clear=True)
        self.other = mlib.getNode(cmds.joint(name=self.name("other"), position=(0, 2, 0)))
        cmds.select(clear=True)
        self.skin = self._bind([self.root, self.mid, self.tip, self.other], "mesh")
        self.values = (.1, .2, .3, .4)
        self.names = [joint.getFullName() for joint in (self.root, self.mid, self.tip, self.other)]
        self.skin.setWeights(self.names, list(self.values), broadcast=True)

    def _bind(self, joints, name):
        """平面を joints へバインドした SkinCluster を返す。"""
        mesh = cmds.polyPlane(name=self.name(name), constructionHistory=False,
                              subdivisionsX=2, subdivisionsY=2)[0]
        skin = cmds.skinCluster([joint.getFullName() for joint in joints], mesh, toSelectedBones=True)[0]
        cmds.select(clear=True)
        return SkinCluster(skin)

    def _column(self, joint, skin=None):
        """joint の列の値を返す。"""
        return list((skin or self.skin).getWeights([joint.getFullName()]))

    def _influences(self, skin=None):
        """登録された influence の UUID を返す。"""
        return {node.getUuid() for node in (skin or self.skin).getInfluences()}

    def assertColumn(self, joint, value):
        """joint の列の全頂点が value であることを確かめる。"""
        for actual in self._column(joint):
            self.assertAlmostEqual(actual, value, places=6)

    def assertUntouched(self):
        """influence とウェイトが setUp のままであることを確かめる。"""
        self.assertEqual(self._influences(), {j.getUuid() for j in (self.root, self.mid, self.tip, self.other)})
        for joint, value in zip((self.root, self.mid, self.tip, self.other), self.values):
            self.assertTrue(joint.isValid())
            self.assertColumn(joint, value)

    def test_delete_moves_descendant_weights_to_remaining_ancestor(self):
        """子孫も一緒に解除し、Undo 1 回で登録・ウェイト・ノードが戻る。"""
        cmds.flushUndo()
        self.mid.delete()
        self.assertFalse(self.mid.isValid())
        self.assertFalse(self.tip.isValid())
        self.assertEqual(self._influences(), {self.root.getUuid(), self.other.getUuid()})
        self.assertColumn(self.root, .6)
        self.assertColumn(self.other, .4)
        self.assertRegex(cmds.undoInfo(query=True, undoName=True), r"^mlib delete( |$)")
        cmds.undo()
        self.assertUntouched()

    def test_delete_without_remaining_ancestor_redistributes(self):
        """残る祖先が無ければ標準の再配分に任せる。"""
        self.root.delete()
        self.assertFalse(self.root.isValid())
        self.assertEqual(self._influences(), {self.other.getUuid()})
        self.assertColumn(self.other, 1.0)

    def test_transfer_to_parent_false_redistributes(self):
        """transferToParent=False は祖先へ加算しない。"""
        self.tip.delete(transferToParent=False)
        self.assertFalse(self.tip.isValid())
        self.assertEqual(self._influences(), {j.getUuid() for j in (self.root, self.mid, self.other)})
        self.assertNotAlmostEqual(self._column(self.mid)[0], .5, places=3)

    def test_deleting_every_influence_is_left_to_maya(self):
        """全 influence が消える skinCluster では解除せず、削除は成功する。"""
        cmds.select(clear=True)
        solo = mlib.getNode(cmds.joint(name=self.name("solo")))
        cmds.select(clear=True)
        self._bind([solo], "soloMesh")
        solo.delete()
        self.assertFalse(solo.isValid())

    def test_remove_influence_false_keeps_standard_delete(self):
        """removeInfluence=False と mlib.delete は祖先へ移さない。"""
        self.tip.delete(removeInfluence=False)
        self.assertFalse(self.tip.isValid())
        self.assertColumn(self.mid, .2)
        mlib.delete(self.mid)
        self.assertFalse(self.mid.isValid())
        self.assertColumn(self.root, .1)

    def _lock(self, joint, state=True):
        """joint のウェイトのロックを切り替える。"""
        cmds.setAttr(joint.getFullName() + ".liw", state)

    def _is_locked(self, joint):
        """joint のウェイトのロックを返す。"""
        return cmds.getAttr(joint.getFullName() + ".liw")

    def _link_layer(self):
        """レイヤーと推定される接続を skinCluster へ作る。"""
        layer = cmds.createNode("network", name=self.name("ngSkinToolsData_test"))
        cmds.addAttr(self.skin.getFullName(), longName="layerLink", attributeType="message")
        cmds.connectAttr(layer + ".message", self.skin.getFullName() + ".layerLink")

    def test_locked_influence_is_restored(self):
        """ロックを保ったまま移送し、Undo 1 回で全て戻る。"""
        self._lock(self.other)
        cmds.flushUndo()
        Joints([self.tip, self.mid]).delete()
        self.assertFalse(self.mid.isValid())
        self.assertColumn(self.root, .6)
        self.assertColumn(self.other, .4)
        self.assertTrue(self._is_locked(self.other))
        cmds.undo()
        self.assertTrue(self._is_locked(self.other))
        self.assertUntouched()

    def test_locked_influence_joins_redistribution(self):
        """処理中はロックを外すため、ロックしたインフルエンスにも再配分する。"""
        self._lock(self.other)
        self.tip.delete(transferToParent=False)
        self.assertColumn(self.other, .4 / .7)
        self.assertTrue(self._is_locked(self.other))
        cmds.undo()
        self._lock(self.other)
        Joints([self.tip]).removeInfluence(transferToParent=False)
        self.assertColumn(self.other, .4 / .7)
        self.assertTrue(self._is_locked(self.other))

    def test_locked_source_joint_stays_locked_when_kept(self):
        """残るジョイントのロックも元へ戻す。"""
        self._lock(self.tip)
        Joints([self.tip]).removeInfluence()
        self.assertTrue(self._is_locked(self.tip))
        self.assertColumn(self.mid, .5)

    def test_unwritable_lock_changes_nothing(self):
        """ロックを切り替えられない場合は何も変えない。"""
        self._lock(self.other)
        cmds.setAttr(self.other.getFullName() + ".liw", lock=True)
        try:
            with self.assertRaises(RuntimeError):
                self.tip.delete()
            self.assertUntouched()
            self.assertTrue(self._is_locked(self.other))
        finally:
            cmds.setAttr(self.other.getFullName() + ".liw", lock=False)

    def test_layers_are_not_rejected(self):
        """レイヤーがあっても各入口で解除できる。"""
        self._link_layer()
        self.tip.delete()
        self.assertColumn(self.mid, .5)
        Joints([self.mid]).removeInfluence(force=True)
        self.assertColumn(self.root, .6)
        self.assertTrue(self.mid.isValid())

    def test_layers_are_not_rejected_with_fast(self):
        """fast でもレイヤーでは拒否しない。"""
        self._link_layer()
        self.tip.delete(fast=True, force=True)
        self.assertFalse(self.tip.isValid())
        self.assertColumn(self.mid, .5)

    def test_invalid_weight_cleanup_still_rejects_layers(self):
        """単独の removeInvalidWeights はレイヤーの拒否を維持する。"""
        self._link_layer()
        with self.assertRaises(RuntimeError):
            self.skin.removeInvalidWeights()

    def test_locked_node_changes_nothing(self):
        """削除できないノードでは influence も外さない。"""
        cmds.lockNode(self.tip.getFullName(), lock=True)
        try:
            with self.assertRaises(RuntimeError):
                self.mid.delete()
            self.assertUntouched()
        finally:
            cmds.lockNode(self.tip.getFullName(), lock=False)

    def test_safe_skips_connected_joints(self):
        """safe は skinCluster の接続があれば何もしない。"""
        self.mid.delete(safe=True)
        self.assertUntouched()
        cmds.select(clear=True)
        free = mlib.getNode(cmds.joint(name=self.name("free")))
        cmds.select(clear=True)
        Joints([self.mid, free]).delete(safe=True)
        self.assertFalse(free.isValid())
        self.assertUntouched()

    def _weights(self, joints):
        """joints の列を返す。"""
        return list(self.skin.getWeights([joint.getFullName() for joint in joints]))

    def _fast_case(self, label):
        """現在の fixture での処理と、残るジョイントを返す。"""
        return {
            "transfer": (lambda fast: self.tip.delete(fast=fast), (self.root, self.mid, self.other)),
            "descendants": (lambda fast: self.mid.delete(fast=fast), (self.root, self.other)),
            "plural": (lambda fast: Joints([self.tip, self.mid]).delete(fast=fast), (self.root, self.other)),
            "no ancestor": (lambda fast: self.root.delete(fast=fast), (self.other,)),
            "redistribute": (lambda fast: self.tip.delete(fast=fast, transferToParent=False),
                             (self.root, self.mid, self.other)),
        }[label]

    def test_fast_matches_normal(self):
        """fast は通常と同じ結果で、Undo に何も積まない。"""
        for locked in (False, True):
            for label in ("transfer", "descendants", "plural", "no ancestor", "redistribute"):
                with self.subTest(case=label, locked=locked):
                    action, remaining = self._fast_case(label)
                    self._lock(self.other, locked)
                    action(False)
                    expected = self._weights(remaining)
                    cmds.undo()
                    self.assertUntouched()
                    cmds.flushUndo()
                    action(True)
                    self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
                    self.assertTrue(cmds.undoInfo(query=True, state=True))
                    for actual, value in zip(self._weights(remaining), expected):
                        self.assertAlmostEqual(actual, value, places=6)
                    self.assertEqual(self._is_locked(self.other), locked)
                    self.assertEqual(self._influences(), {joint.getUuid() for joint in remaining})
                # fast は Undo で戻せないため、ケースごとに fixture を作り直す。
                self.tearDown()
                self.setUp()

    def test_fast_standard_delete_and_unskinned(self):
        """removeInfluence=False と未スキニングの fast も削除する。"""
        self.tip.delete(fast=True, removeInfluence=False)
        self.assertFalse(self.tip.isValid())
        cmds.select(clear=True)
        free = mlib.getNode(cmds.joint(name=self.name("free")))
        cmds.select(clear=True)
        free.delete(fast=True)
        self.assertFalse(free.isValid())

    def test_invalid_flags_are_rejected(self):
        """bool 以外のフラグは変更前に拒否する。"""
        for flags in ({"safe": 1}, {"fast": 1}, {"removeInfluence": 1}, {"transferToParent": 1}, {"force": 1}):
            with self.subTest(flags=flags), self.assertRaises(TypeError):
                self.tip.delete(**flags)
            with self.subTest(plural=flags), self.assertRaises(TypeError):
                Joints([self.tip]).delete(**flags)
        self.assertUntouched()

    def test_joints_delete_undoes_in_one_step(self):
        """親子の同時指定でも残る祖先へ集まり、Undo 1 回で戻る。"""
        cmds.flushUndo()
        Joints([self.tip, self.mid]).delete()
        self.assertFalse(self.mid.isValid())
        self.assertFalse(self.tip.isValid())
        self.assertColumn(self.root, .6)
        self.assertRegex(cmds.undoInfo(query=True, undoName=True), r"^mlib delete( |$)")
        cmds.undo()
        self.assertUntouched()

    def test_empty_joints_delete_does_nothing(self):
        Joints([]).delete()
        self.assertUntouched()

    def test_joints_delete_handles_every_skin(self):
        """複数の skinCluster の両方で解除する。"""
        second = self._bind([self.root, self.mid, self.tip, self.other], "second")
        Joints([self.tip]).delete()
        self.assertEqual(self._influences(), self._influences(second))
        self.assertEqual(len(self._influences(second)), 3)

    def test_joints_remove_influence_keeps_joints(self):
        """ノードを残して祖先へ移し、Undo 1 回で戻る。"""
        cmds.flushUndo()
        joints = Joints([self.mid, self.tip])
        self.assertIs(joints.removeInfluence(), joints)
        self.assertTrue(self.mid.isValid())
        self.assertTrue(self.tip.isValid())
        self.assertEqual(self._influences(), {self.root.getUuid(), self.other.getUuid()})
        self.assertColumn(self.root, .6)
        cmds.undo()
        self.assertUntouched()

    def test_joints_remove_influence_with_skin_cluster(self):
        """指定した skinCluster だけを変更し、未登録は拒否する。"""
        second = self._bind([self.root, self.mid, self.tip, self.other], "second")
        Joints([self.tip]).removeInfluence(self.skin)
        self.assertEqual(len(self._influences()), 3)
        self.assertEqual(len(self._influences(second)), 4)
        with self.assertRaises(ValueError):
            Joints([self.tip]).removeInfluence(self.skin.getFullName())

    def test_joints_remove_influence_ignores_unbound_joints(self):
        """対象省略の未スキニングは変更しない。"""
        cmds.select(clear=True)
        free = mlib.getNode(cmds.joint(name=self.name("free")))
        cmds.select(clear=True)
        joints = Joints([free])
        self.assertIs(joints.removeInfluence(), joints)
        self.assertTrue(free.isValid())

    def test_joints_remove_every_influence_is_rejected(self):
        """全 influence は外せず、何も変えない。"""
        with self.assertRaises(ValueError):
            Joints([self.root, self.mid, self.tip, self.other]).removeInfluence()
        self.assertUntouched()


if __name__ == "__main__":
    unittest.main()
