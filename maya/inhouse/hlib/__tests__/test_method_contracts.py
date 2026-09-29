"""メソッド整理後の責務・Undo・旧入口の除去をMayaで検証する。"""
import sys
import unittest
import uuid

import maya.cmds as cmds
import hlib

hlib.reload()


class MethodContractTest(unittest.TestCase):
    """属性書込みとノード変換を取り違えないことを検証する。"""

    def setUp(self):
        """独立した名前空間に検証対象を作成する。"""
        self.ns = 'hlibMethod_' + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.node = hlib.createNode('transform', name=self.ns + ':node')

    def tearDown(self):
        """検証用ノードだけを削除する。"""
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_matrix_attribute_never_redirects_to_transform(self):
        """Transform上の行列属性でもTRSを変えず、Undoで属性値を戻す。"""
        self.node.set_translate((2, 3, 4))
        plug = self.node.add_attribute(long_name='storedMatrix', data_type='matrix')
        identity = hlib.maths.Matrix()
        plug.set(identity)
        value = hlib.maths.Matrix(translate=(8, 9, 10))
        before = self.node.get_matrix()
        plug.set(value)
        self.assertTrue(plug.get().is_equivalent(value))
        self.assertTrue(self.node.get_matrix().is_equivalent(before))
        cmds.undo()
        self.assertTrue(plug.get().is_equivalent(identity))
        cmds.redo()
        self.assertTrue(plug.get().is_equivalent(value))
        plug.set(identity, fast=True)
        self.assertTrue(plug.get().is_equivalent(identity))
        self.assertTrue(self.node.get_matrix().is_equivalent(before))
        with self.assertRaises(TypeError):
            plug.set(value, ws=True)
        with self.assertRaises(TypeError):
            plug.get(ws=True)

    def test_visibility_state_and_undo(self):
        """表示状態変更と入力検証を確認する。"""
        self.node.set_visibility(False)
        self.assertFalse(self.node.plug('visibility').get())
        cmds.undo()
        self.assertTrue(self.node.plug('visibility').get())
        self.node.set_visibility(False, fast=True)
        self.assertFalse(self.node.plug('visibility').get())
        with self.assertRaises(TypeError):
            self.node.set_visibility('false')

    def test_selection_empty_modes_and_invalid_mode(self):
        """追加・除外の空入力で現在選択を消さない。"""
        from hlib.general.selection import Selection
        cmds.select(str(self.node))
        for mode in ('add', 'remove'):
            Selection().select(mode=mode)
            self.assertEqual(cmds.ls(selection=True), [str(self.node)])
        with self.assertRaises(ValueError):
            Selection().select(mode='invalid')
        self.assertEqual(cmds.ls(selection=True), [str(self.node)])
        Selection().select()
        self.assertEqual(cmds.ls(selection=True), [])
        cmds.undo()
        self.assertEqual(cmds.ls(selection=True), [str(self.node)])

    def test_removed_names_and_bulk_api(self):
        """リロード後も互換入口を公開せず、複数形も新しい入口を使う。"""
        from hlib.nodes.node import Node
        from hlib.nodes.transform import Transform
        from hlib.nodes.skinCluster import SkinCluster, SkinClusters
        from hlib.nodes.joint import Joints
        from hlib.plugs.matrixPlug import MatrixPlug
        for cls, names in ((Node, ('attr', 'partial_path', 'full_path')),
                           (Transform, ('decompose', 'show', 'hide')),
                           (SkinCluster, ('transfer_weight', 'transfer_weights_batch')),
                           (SkinClusters, ('remove_joints',)),
                           (MatrixPlug, ('set_value',))):
            for name in names:
                self.assertFalse(hasattr(cls, name), (cls, name))
        self.assertIn('set_visibility', Joints._bulk_methods)
        self.assertNotIn('hide', Joints._bulk_methods)


    def test_joint_channels_round_trip_in_both_backends_and_units(self):
        """jointOrient・親スケールを持つJointも属性値の往復で姿勢を変えない。"""
        parent = cmds.createNode('joint', name=self.ns + ':parent')
        joint = hlib.getNode(cmds.createNode('joint', name=self.ns + ':child', parent=parent))
        cmds.setAttr(parent + '.scale', 2, 3, 4)
        cmds.setAttr(str(joint) + '.jointOrient', 13, 21, 34)
        cmds.setAttr(str(joint) + '.rotateAxis', 5, 8, 11)
        old_unit = cmds.currentUnit(query=True, angle=True)
        try:
            for angle_unit in ('deg', 'rad'):
                cmds.currentUnit(angle=angle_unit)
                for order in range(6):
                    cmds.setAttr(str(joint) + '.rotateOrder', order)
                    joint.plug('rotate').set((17, 23, 31), unit='deg')
                    joint.plug('scale').set((1.2, 1.3, 1.4))
                    for fast in (False, True):
                        before = joint.get_matrix(ws=True)
                        rotation = joint.plug('rotate').get()
                        scale = joint.plug('scale').get()
                        joint.plug('rotate').set(rotation, fast=fast)
                        joint.plug('scale').set(scale, fast=fast)
                        self.assertTrue(joint.get_matrix(ws=True).is_equivalent(before, 1e-9))
                        self.assertTrue(joint.plug('rotate').get().is_equivalent(rotation, 1e-9))
        finally:
            cmds.currentUnit(angle=old_unit)

    def test_rotation_order_conversion_and_undo(self):
        """型付き回転の順序を変換し、通常更新を一回のUndoで戻す。"""
        from hlib.maths import EulerRotation
        cmds.setAttr(str(self.node) + '.rotateOrder', 4)
        plug = self.node.plug('rotate')
        original = plug.get()
        value = EulerRotation(.2, .4, .6, 'zyx')
        plug.set(value)
        self.assertTrue(plug.get().asMatrix().isEquivalent(value.asMatrix(), 1e-9))
        cmds.undo()
        self.assertTrue(plug.get().is_equivalent(original, 1e-9))
        cmds.redo()
        self.assertTrue(plug.get().asMatrix().isEquivalent(value.asMatrix(), 1e-9))
        for fast in (False, True):
            plug.set(value.asQuaternion(), fast=fast)
            self.assertTrue(plug.get().asMatrix().isEquivalent(value.asMatrix(), 1e-9))
        cmds.setAttr(str(self.node) + '.rotateY', lock=True)
        before = tuple(plug.get())
        try:
            with self.assertRaises(RuntimeError):
                plug.set((1, 2, 3))
            self.assertEqual(tuple(plug.get()), before)
        finally:
            cmds.setAttr(str(self.node) + '.rotateY', lock=False)

    def test_flags_validate_before_write_and_preserve_omitted_state(self):
        """省略・不正値・Undo・fastの状態設定契約を確認する。"""
        plug = self.node.plug('tx')
        plug.set_flags(keyable=False, channel_box=True)
        self.assertFalse(plug.is_keyable())
        self.assertTrue(cmds.getAttr(plug.full_name(), channelBox=True))
        plug.set_flags(locked=True)
        self.assertTrue(plug.is_locked())
        self.assertFalse(plug.is_keyable())
        cmds.undo()
        self.assertFalse(plug.is_locked())
        with self.assertRaises(TypeError):
            plug.set_flags(locked=True, keyable='false')
        self.assertFalse(plug.is_locked())
        self.node.set_attribute_flags(['tx'], locked=True, fast=True)
        self.assertTrue(plug.is_locked())
        plug.set_flags(locked=False, keyable=True, fast=True)
        self.assertTrue(plug.is_keyable())
        self.assertFalse(plug.is_locked())
        self.assertFalse(hasattr(type(plug), 'set_locked'))

    def test_constraint_invalid_target_never_partially_updates(self):
        """有効なターゲットと無関係なノードの混在を更新前に拒否する。"""
        a = hlib.createNode('transform', name=self.ns + ':a')
        b = hlib.createNode('transform', name=self.ns + ':b')
        outsider = hlib.createNode('transform', name=self.ns + ':outsider')
        constraint = hlib.addConstraint([a, b], self.node, type='point')
        before = constraint.get_weights()
        for fast in (False, True):
            with self.assertRaises(ValueError):
                constraint.set_weight(.25, a, outsider, fast=fast)
            self.assertEqual(constraint.get_weights(), before)
        constraint.set_weight(.25, a)
        self.assertAlmostEqual(constraint.get_weights()[0], .25)
        cmds.undo()
        self.assertEqual(constraint.get_weights(), before)

    def test_plug_space_argument_and_redundant_methods_are_removed(self):
        """属性の型にかかわらず空間指定と古い別名を公開しない。"""
        from hlib.general import Plugin, Module
        from hlib.nodes import Joint
        for name in ('tx', 'translate', 'worldMatrix'):
            with self.assertRaises(TypeError):
                self.node.plug(name).get(ws=True)
        self.assertFalse(hasattr(Joint, 'orientation'))
        self.assertFalse(hasattr(Plugin, 'version_tuple'))
        self.assertFalse(hasattr(Module, 'version_tuple'))


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MethodContractTest))
    if not result.wasSuccessful():
        raise AssertionError('method contract tests failed')
