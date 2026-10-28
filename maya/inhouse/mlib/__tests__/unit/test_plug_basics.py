"""Plugの値・接続・疎配列・ロックを基本操作の境界から検証する。"""

import math
import unittest
import uuid

import maya.cmds as cmds

import mlib


class PlugBasicsTest(unittest.TestCase):
    """コマンドで用意した値や接続を独立した比較対象に使う。"""

    def setUp(self):
        self.namespace = ":plugBasics_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg")
        self.node = self.make()
        name = self.node.getFullName()
        cmds.addAttr(name, longName="amount", attributeType="double", defaultValue=3)
        cmds.addAttr(name, longName="count", attributeType="long", defaultValue=2)
        cmds.addAttr(name, longName="enabled", attributeType="bool", defaultValue=True)
        cmds.addAttr(name, longName="label", dataType="string")
        cmds.addAttr(name, longName="mode", attributeType="enum", enumName="off:on:preview")
        cmds.addAttr(name, longName="values", attributeType="double", multi=True)
        cmds.setAttr(name + ".label", "initial", type="string")

    def tearDown(self):
        for name in cmds.ls(self.namespace + ":*", long=True) or []:
            if cmds.objExists(name):
                cmds.lockNode(name, lock=False)
        if cmds.namespace(exists=self.namespace):
            cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.currentUnit(linear=self.units[0], angle=self.units[1])
        cmds.undoInfo(state=self.undo_state)

    def make(self, kind="network"):
        """Mayaコマンドで作成したノードを取得する。"""
        return mlib.getNode(cmds.createNode(kind, name=self.namespace + ":node#", skipSelect=True))

    def number(self, node=None):
        """接続用の独立したdoubleアトリビュートを用意する。"""
        node = self.make() if node is None else node
        cmds.addAttr(node.getFullName(), longName="number", attributeType="double")
        return node.getPlug("number")

    def test_false_zero_and_empty_string_are_real_values(self):
        """False・0・空文字列を省略値と混同せず、型と自身返却を維持する。"""
        for fast in (False, True):
            for attr, value in (("amount", 0.0), ("count", 0), ("enabled", False), ("label", ""), ("mode", 0)):
                with self.subTest(fast=fast, attr=attr):
                    plug = self.node.getPlug(attr)
                    self.assertIs(plug.set(value, fast=fast), plug)
                    self.assertEqual(cmds.getAttr(plug.getFullName()), value)
                    self.assertEqual(plug.get(), value)

    def test_scalar_types_each_have_one_step_undo_redo(self):
        """基本型ごとに1回のsetをUndo/redoで往復する。"""
        for attr, value in (("amount", -4.5), ("count", 12), ("enabled", False), ("label", "日本語"), ("mode", 2)):
            with self.subTest(attr=attr):
                plug = self.node.getPlug(attr)
                previous = cmds.getAttr(plug.getFullName())
                cmds.flushUndo()
                plug.set(value)
                cmds.undo()
                self.assertEqual(cmds.getAttr(plug.getFullName()), previous)
                self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
                cmds.redo()
                self.assertEqual(cmds.getAttr(plug.getFullName()), value)

    def test_fast_scalar_edits_leave_the_undo_queue_empty(self):
        """fastの型別設定はUndo設定を変えず、記録を追加しない。"""
        cmds.flushUndo()
        for attr, value in (("amount", 5.5), ("count", 6), ("enabled", False), ("label", "direct"), ("mode", 1)):
            self.node.getPlug(attr).set(value, fast=True)
            self.assertEqual(cmds.getAttr(self.node.getFullName() + "." + attr), value)
        self.assertTrue(cmds.undoInfo(query=True, state=True))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_locked_scalar_failure_preserves_value_lock_and_safe_result(self):
        """ロック時は値を保ち、safeだけが失敗数を返す。"""
        plug = self.node.getPlug("amount")
        plug.setLocked(True)
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaises(RuntimeError):
                    plug.set(8, fast=fast)
                self.assertEqual(plug.set(8, safe=True, fast=fast), 1)
                self.assertEqual(cmds.getAttr(plug.getFullName()), 3)
                self.assertTrue(cmds.getAttr(plug.getFullName(), lock=True))

    def test_equal_set_if_changed_does_not_unlock_or_record(self):
        """ロック済みでも同じ値の要求はFalseで、ロック変更もUndoも発生しない。"""
        plug = self.node.getPlug("amount")
        plug.setLocked(True)
        for fast in (False, True):
            cmds.flushUndo()
            self.assertFalse(plug.setIfChanged(3, unlock=True, fast=fast))
            self.assertTrue(cmds.getAttr(plug.getFullName(), lock=True))
            self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_set_if_changed_updates_and_relocks_with_one_undo(self):
        """一時解除したロックと値を1回のUndoで戻し、redo後も再ロックする。"""
        plug = self.node.getPlug("amount")
        plug.setLocked(True)
        cmds.flushUndo()
        self.assertTrue(plug.setIfChanged(9, unlock=True))
        self.assertEqual(cmds.getAttr(plug.getFullName()), 9)
        self.assertTrue(cmds.getAttr(plug.getFullName(), lock=True))
        cmds.undo()
        self.assertEqual(cmds.getAttr(plug.getFullName()), 3)
        self.assertTrue(cmds.getAttr(plug.getFullName(), lock=True))
        cmds.redo()
        self.assertEqual(cmds.getAttr(plug.getFullName()), 9)
        self.assertTrue(cmds.getAttr(plug.getFullName(), lock=True))

    def test_failed_set_if_changed_relocks_and_keeps_input(self):
        """入力接続による書込み失敗の後も、接続と一時解除前のロックを保つ。"""
        source = self.number()
        destination = self.node.getPlug("amount")
        source.set(4)
        destination.connect(source)
        destination.setLocked(True)
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaises(RuntimeError):
                    destination.setIfChanged(8, unlock=True, fast=fast)
                self.assertTrue(cmds.isConnected(source.getFullName(), destination.getFullName()))
                self.assertTrue(cmds.getAttr(destination.getFullName(), lock=True))
                self.assertEqual(cmds.getAttr(destination.getFullName()), 4)

    def test_wrong_disconnect_source_preserves_the_real_connection(self):
        """別の入力元や長短名の競合を指定しても、既存の入力を切断しない。"""
        source, wrong = self.number(), self.number()
        destination = self.node.getPlug("amount")
        destination.connect(source)
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaises(RuntimeError):
                    destination.disconnect(wrong, fast=fast)
                self.assertTrue(cmds.isConnected(source.getFullName(), destination.getFullName()))

    def test_force_reconnect_restores_lock_and_undo_restores_old_source(self):
        """force置換のUndo/redoで入力元を往復し、接続先ロックを維持する。"""
        source, replacement = self.number(), self.number()
        destination = self.node.getPlug("amount")
        destination.connect(source)
        destination.setLocked(True)
        cmds.flushUndo()
        self.assertEqual(destination.connect(replacement, force=True), destination)
        self.assertTrue(cmds.isConnected(replacement.getFullName(), destination.getFullName()))
        self.assertTrue(cmds.getAttr(destination.getFullName(), lock=True))
        cmds.undo()
        self.assertTrue(cmds.isConnected(source.getFullName(), destination.getFullName()))
        self.assertTrue(cmds.getAttr(destination.getFullName(), lock=True))
        cmds.redo()
        self.assertTrue(cmds.isConnected(replacement.getFullName(), destination.getFullName()))
        self.assertTrue(cmds.getAttr(destination.getFullName(), lock=True))

    def test_disconnect_input_is_idempotent_and_keeps_output_connections(self):
        """入力解除を繰り返しても出力接続を消さず、自身を返す。"""
        source, downstream = self.number(), self.number()
        center = self.node.getPlug("amount")
        center.connect(source)
        downstream.connect(center)
        for fast in (False, True):
            with self.subTest(fast=fast):
                self.assertIs(center.disconnectInput(fast=fast), center)
                self.assertIs(center.disconnectInput(fast=fast), center)
                self.assertFalse(cmds.isConnected(source.getFullName(), center.getFullName()))
                self.assertTrue(cmds.isConnected(center.getFullName(), downstream.getFullName()))
                center.connect(source)

    def test_safe_compound_set_keeps_connected_child_and_updates_others(self):
        """safeの部分更新で入力付きのYだけを保ち、書けた成分をUndoで戻す。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                transform = self.make("transform")
                source = self.make("transform").getPlug("ty")
                source.set(12)
                transform.getPlug("ty").connect(source)
                plug = transform.getPlug("translate")
                cmds.flushUndo()
                self.assertEqual(plug.set((4, 5, 6), safe=True, fast=fast), 1)
                self.assertEqual(cmds.getAttr(transform.getFullName() + ".t")[0], (4, 12, 6))
                self.assertTrue(cmds.isConnected(source.getFullName(), transform.getFullName() + ".ty"))
                if not fast:
                    cmds.undo()
                    self.assertEqual(cmds.getAttr(transform.getFullName() + ".t")[0], (0, 12, 0))

    def test_sparse_array_reference_errors_do_not_create_elements(self):
        """欠番・不正番号・別名競合の照会は配列の論理番号を増やさない。"""
        array = self.node.getPlug("values")
        array[3].set(2)
        array[1000].set(5)
        for index in (0, 2, 999):
            with self.assertRaises(IndexError):
                array.getElement(index)
        for index in (-1, 2147483648):
            with self.assertRaises(IndexError):
                array[index]
        self.assertEqual(array.getIndices(), [3, 1000])
        self.assertEqual(cmds.getAttr(array.getFullName(), multiIndices=True), [3, 1000])

    def test_array_remove_restores_element_value_and_connection_on_undo(self):
        """接続された疎配列要素の削除をUndo/redoし、欠番と他要素を保つ。"""
        array = self.node.getPlug("values")
        source = self.number()
        source.set(9)
        array[2].set(3)
        array[7].connect(source)
        cmds.flushUndo()
        self.assertIs(array.removeElement(7), array)
        self.assertEqual(array.getIndices(), [2])
        cmds.undo()
        self.assertEqual(array.getIndices(), [2, 7])
        self.assertTrue(cmds.isConnected(source.getFullName(), array[7].getFullName()))
        self.assertEqual(cmds.getAttr(array[7].getFullName()), 9)
        cmds.redo()
        self.assertEqual(array.getIndices(), [2])
        self.assertEqual(cmds.getAttr(array[2].getFullName()), 3)

    def test_array_whole_set_rejection_preserves_sparse_values(self):
        """配列全体のsetはsafe指定でも拒否し、既存値を変更しない。"""
        array = self.node.getPlug("values")
        array[4].set(11)
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaises(TypeError):
                    array.set([1, 2], safe=True, fast=fast)
                self.assertEqual(array.get(), {4: 11})

    def test_internal_distance_and_angle_values_survive_ui_unit_changes(self):
        """UIのm/mm・rad/degへ切り替えても内部cm/radとUI値を区別する。"""
        transform = self.make("transform")
        distance, angle = transform.getPlug("tx"), transform.getPlug("rx")
        for fast in (False, True):
            for linear, angular, ui_distance, ui_angle in (("m", "deg", 1, 90), ("mm", "rad", 1000, math.pi / 2)):
                with self.subTest(fast=fast, linear=linear, angle=angular):
                    cmds.currentUnit(linear=linear, angle=angular)
                    distance.set(100, fast=fast)
                    angle.set(math.pi / 2, fast=fast)
                    self.assertAlmostEqual(cmds.getAttr(distance.getFullName()), ui_distance)
                    self.assertAlmostEqual(cmds.getAttr(angle.getFullName()), ui_angle)
                    self.assertAlmostEqual(distance.get(), 100)
                    self.assertAlmostEqual(angle.get(), math.pi / 2)
                    self.assertAlmostEqual(distance.get(uiUnits=True), ui_distance)
                    self.assertAlmostEqual(angle.get(uiUnits=True), ui_angle)

    def test_held_plug_follows_node_and_attribute_rename(self):
        """取得済みPlugはノード名とアトリビュート名の変更後も同じ対象を更新する。"""
        plug = self.node.getPlug("amount")
        renamed = cmds.rename(self.node.getFullName(), self.namespace + ":renamed")
        cmds.renameAttr(renamed + ".amount", "renamedAmount")
        self.assertTrue(plug.isValid())
        self.assertEqual(plug.getFullName(), renamed + ".renamedAmount")
        plug.set(17)
        self.assertEqual(cmds.getAttr(renamed + ".renamedAmount"), 17)

    def test_recreated_attribute_does_not_revive_the_old_plug(self):
        """同名アトリビュートの再作成と、Undoによる元の復元を混同しない。"""
        old = self.node.getPlug("amount")
        cmds.deleteAttr(old.getFullName())
        cmds.addAttr(self.node.getFullName(), longName="amount", attributeType="double", defaultValue=20)
        self.assertFalse(old.isValid())
        with self.assertRaises(RuntimeError):
            old.set(99)
        self.assertEqual(cmds.getAttr(self.node.getFullName() + ".amount"), 20)

    def test_reset_uses_attribute_defaults_and_has_undo(self):
        """resetは型ごとの既定値へ戻し、Undoで設定済みの値を復元する。"""
        for attr, value, expected in (("amount", 9, 3), ("count", 8, 2), ("enabled", False, True), ("mode", 2, 0)):
            with self.subTest(attr=attr):
                plug = self.node.getPlug(attr)
                plug.set(value)
                cmds.flushUndo()
                self.assertIs(plug.reset(), plug)
                self.assertEqual(cmds.getAttr(plug.getFullName()), expected)
                cmds.undo()
                self.assertEqual(cmds.getAttr(plug.getFullName()), value)


if __name__ == "__main__":
    unittest.main()
