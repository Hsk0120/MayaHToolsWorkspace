"""ノードコレクションの継承・参照・色更新の契約を検証する。"""
import inspect
import sys
import unittest
import uuid
from unittest.mock import patch

import maya.cmds as cmds
import hlib

hlib.reload()


class NodeCollectionsTest(unittest.TestCase):
    """既存シーンと分離した名前空間で複数形APIを検証する。"""

    def setUp(self):
        """検証用ノードを作る。"""
        self.ns = 'hlibCollections_' + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.names = [cmds.createNode('joint', name=self.ns + ':j' + str(i)) for i in range(2)]
        self.joints = hlib.nodes.Joints(self.names)

    def tearDown(self):
        """検証用名前空間を片付ける。"""
        for name in cmds.ls(self.ns + ':*') or []:
            cmds.lockNode(name, lock=False)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_hierarchy_inputs_copy_and_strict_type(self):
        """型階層と単一入力・重複・コピーを検証する。"""
        from hlib.nodes import Nodes, Transforms, Joints, SkinClusters
        self.assertIsInstance(self.joints, Transforms)
        self.assertIsInstance(self.joints, Nodes)
        self.assertTrue(issubclass(SkinClusters, Nodes))
        self.assertEqual(len(Nodes(self.names[0])), 1)
        self.assertEqual(len(Joints(self.names + self.names)), 2)
        self.assertEqual(len(Transforms(self.joints)), 2)
        self.assertIs(self.joints.copy()[0], self.joints[0])
        self.assertIsInstance(self.joints[:1], Joints)
        plain = cmds.createNode('transform', name=self.ns + ':plain')
        with self.assertRaises(TypeError):
            Joints([self.names[0], plain])
        with self.assertRaises(TypeError):
            SkinClusters(self.names)
        cmds.rename(self.names[0], self.ns + ':renamed')
        self.assertTrue(self.joints.names()[0].endswith('renamed'))
        self.assertEqual(len(Nodes(self.joints)), 2)
        cmds.delete(self.joints[0])
        self.assertEqual(self.joints.is_valid(), [False, True])
        self.assertEqual(len(self.joints[:]), 2)
        with self.assertRaises(RuntimeError):
            Joints(self.joints)

    def test_colors_roundtrip_and_undo(self):
        """色の取得・個別反映・一回のUndoを検証する。"""
        from hlib.general import Color, Colors
        joints = self.joints
        self.assertIsInstance(joints.get_override_color(), Colors)
        self.assertEqual(joints.get_override_color().mode, ['disabled'] * 2)
        self.assertIs(joints.set_override_colors([13, 6]), joints)
        self.assertEqual(joints.get_override_color().index, [13, 6])
        cmds.undo()
        self.assertEqual(joints.get_override_color().mode, ['disabled'] * 2)
        cmds.redo()
        colors = joints.get_override_color()
        colors[0].index = 17
        self.assertEqual(joints.get_override_color().index, [13, 6])
        joints.set_override_colors(colors)
        self.assertEqual(joints.get_override_color().index, [17, 6])
        joints.set_outliner_colors([Color(), None])
        self.assertEqual(joints.get_outliner_color().mode, ['rgb', 'disabled'])
        joints.set_outliner_color(13)
        self.assertEqual(joints.get_outliner_color().rgb, [(1, 0, 0)] * 2)
        joints.set_override_color(None)
        self.assertEqual(joints.get_override_color().mode, ['disabled'] * 2)

    def test_prevalidation_fast_and_empty(self):
        """後続ロック・入力接続・不正色を検証してから変更する。"""
        from hlib.nodes import Joints
        for fast in (False, True):
            self.joints.set_override_color(6, fast=fast)
            cmds.setAttr(self.names[1] + '.overrideRGBColors', lock=True)
            try:
                with self.assertRaisesRegex(RuntimeError, 'item 1'):
                    self.joints.set_override_colors([13, (1, .5, 0)], fast=fast)
                self.assertEqual(self.joints.get_override_color().index, [6, 6])
            finally:
                cmds.setAttr(self.names[1] + '.overrideRGBColors', lock=False)
            with self.assertRaises(ValueError):
                self.joints.set_override_colors([13], fast=fast)
            with self.assertRaises(ValueError):
                self.joints.set_override_colors([13, 32], fast=fast)
            self.assertEqual(self.joints.get_override_color().index, [6, 6])
            self.joints.set_override_colors([17, 13], fast=fast)
            self.assertEqual(self.joints.get_override_color().index, [17, 13])
        cmds.connectAttr(self.names[0] + '.overrideColor', self.names[1] + '.overrideColor')
        try:
            with self.assertRaises(RuntimeError):
                self.joints.set_override_color(6)
            self.assertEqual(cmds.getAttr(self.names[0] + '.overrideColor'), 17)
        finally:
            cmds.disconnectAttr(self.names[0] + '.overrideColor', self.names[1] + '.overrideColor')
        cmds.lockNode(self.names[1], lock=True)
        try:
            with self.assertRaises(RuntimeError):
                self.joints.set_override_color(6)
        finally:
            cmds.lockNode(self.names[1], lock=False)
        self.assertEqual(len(Joints().get_override_color()), 0)
        self.assertIsInstance(Joints().set_override_colors([]), Joints)
        with self.assertRaises(ValueError):
            Joints().set_override_color(32)
        with self.assertRaises(TypeError):
            Joints().set_override_color(6, fast=1)

    def test_instance_paths_and_shared_color_conflicts(self):
        """パス別行列を保持し、共有属性へ矛盾した更新を拒否する。"""
        from hlib.nodes import Transforms
        group = cmds.createNode('transform', name=self.ns + ':group')
        leaf = cmds.createNode('transform', name=self.ns + ':leaf', parent=group)
        other = cmds.instance(group, name=self.ns + ':other')[0]
        cmds.setAttr(other + '.tx', 10)
        paths = cmds.ls(leaf, long=True, allPaths=True)
        nodes = Transforms(paths + paths)
        self.assertEqual(len(nodes), 2)
        self.assertNotEqual(list(nodes.get_matrix(ws=True)[0]), list(nodes.get_matrix(ws=True)[1]))
        nodes.set_override_colors([6, 6])
        with self.assertRaises(ValueError):
            nodes.set_override_colors([13, 17])
        self.assertEqual(nodes.get_override_color().index, [6, 6])

    def test_parent_deletion_and_extension_reference(self):
        """親子削除と、派生ラッパーを作り直さず保持することを確認する。"""
        from hlib.nodes import Nodes, Transforms, Joint
        class ExtendedJoint(Joint):
            """外部拡張相当の派生型。"""
        wrapped = object.__new__(ExtendedJoint)
        wrapped.__dict__.update(self.joints[0].__dict__)
        self.assertIs(Transforms([wrapped])[0], wrapped)
        parent = cmds.createNode('transform', name=self.ns + ':parent')
        child = cmds.createNode('transform', name=self.ns + ':child', parent=parent)
        nodes = Nodes([parent, child])
        nodes.delete()
        self.assertFalse(cmds.objExists(parent))
        cmds.undo()
        self.assertTrue(cmds.objExists(child))
        self.assertEqual(hlib.ls([]), [])  # 検索の戻り値契約は維持

    def test_instanced_joint_delete(self):
        """同じjointの異なるパスを渡しても専用削除が完了する。"""
        a = cmds.createNode('transform', name=self.ns + ':instanceA')
        b = cmds.createNode('transform', name=self.ns + ':instanceB')
        joint = cmds.createNode('joint', name=self.ns + ':instanceJoint', parent=a)
        cmds.parent(joint, b, addObject=True)
        paths = cmds.ls(joint, long=True, allPaths=True)
        self.assertEqual(len(paths), 2)
        hlib.nodes.Joints(paths).delete()
        self.assertFalse(cmds.objExists(joint))
        cmds.undo()
        self.assertTrue(cmds.objExists(joint))

    def test_bulk_inheritance_signature_and_restrictions(self):
        """自動生成は派生signatureへ更新し、明示実装と禁止設定を保つ。"""
        from hlib._core.collection import BulkCollection, bulk_api
        class Item:
            """基底の単体API。"""
            def edit(self, value):
                """入力を返す。"""
                return value
        class Child(Item):
            """引数が増えた単体API。"""
            def edit(self, value, *, extra=False):
                """値と追加フラグを返す。"""
                return value, extra
        @bulk_api(Item, undo=False)
        class Base(BulkCollection):
            """基底コレクション。"""
        @bulk_api(Child, undo=False)
        class Derived(Base):
            """派生コレクション。"""
        self.assertIn('extra', inspect.signature(Derived.edit).parameters)
        @bulk_api(Child, undo=False, per_item_only=('edit',))
        class Restricted(Derived):
            """直接一括実行を禁止する。"""
        restricted = Restricted()
        restricted._items = [Child()]
        self.assertFalse(hasattr(restricted, 'edit'))
        self.assertEqual(restricted.call_each('edit', [(3,)]), [(3, False)])
        @bulk_api(Child, undo=False)
        class Grandchild(Restricted):
            """禁止設定を継承する。"""
        self.assertFalse(hasattr(Grandchild(), 'edit'))
        self.assertEqual(hlib.nodes.Joints.freeze_rotation.__module__, 'hlib.nodes.joint')


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
