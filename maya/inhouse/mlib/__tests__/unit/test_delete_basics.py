"""削除入口の入力検査・参照寿命・Undoとfastの境界を検証する。"""

import unittest
import uuid

import maya.cmds as cmds

import mlib


class DeleteBasicsTest(unittest.TestCase):
    """専用名前空間のノードを使い、拒否時に何も消えないことも確認する。"""

    def setUp(self):
        self.namespace = ":deleteBasics_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)

    def tearDown(self):
        for name in cmds.ls(self.namespace + ":*", long=True) or []:
            if cmds.objExists(name):
                cmds.lockNode(name, lock=False)
        if cmds.namespace(exists=self.namespace):
            cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_state)

    def make(self, kind="transform", parent=None):
        """専用名前空間にノードを作り、ラッパーを取得する。"""
        options = {"name": self.namespace + ":node#", "skipSelect": True}
        if parent is not None:
            options["parent"] = parent.getFullName()
        return mlib.getNode(cmds.createNode(kind, **options))

    def test_command_accepts_name_node_and_api_references(self):
        """文字列・Node・MObject・MDagPathの各入力を通常/fastで削除できる。"""
        for fast in (False, True):
            for mode in ("name", "node", "mobject", "dagpath"):
                with self.subTest(fast=fast, mode=mode):
                    node = self.make()
                    name = node.getFullName()
                    value = {"name": name, "node": node, "mobject": node.mnode(),
                             "dagpath": node.mpath()}[mode]
                    self.assertIsNone(mlib.delete(value, fast=fast))
                    self.assertFalse(cmds.objExists(name))
                    self.assertFalse(node.isValid())

    def test_nested_generator_input_is_deleted_in_one_undo(self):
        """入れ子とgeneratorの重複入力を削除し、1回のUndo/redoで全て戻せる。"""
        first, second, third = (self.make() for _ in range(3))
        names = [node.getFullName() for node in (first, second, third)]
        items = (item for item in (first, (second, [third, first])))
        cmds.flushUndo()
        mlib.delete(items)
        self.assertFalse(any(cmds.objExists(name) for name in names))
        cmds.undo()
        self.assertTrue(all(cmds.objExists(name) for name in names))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        cmds.redo()
        self.assertFalse(any(cmds.objExists(name) for name in names))

    def test_invalid_nested_value_does_not_delete_valid_prefix(self):
        """後半の未対応型を検出しても、先に渡したノードは削除しない。"""
        for fast in (False, True):
            for invalid in (1, object()):
                with self.subTest(fast=fast, invalid=type(invalid).__name__):
                    first, second = self.make(), self.make()
                    names = [first.getFullName(), second.getFullName()]
                    with self.assertRaises(TypeError):
                        mlib.delete([first, [second, invalid]], fast=fast)
                    self.assertTrue(all(cmds.objExists(name) for name in names))

    def test_plug_input_is_rejected_without_deleting_its_owner(self):
        """PlugとMPlugを含む削除要求は所有ノードごと消す操作に変換しない。"""
        for fast in (False, True):
            for raw in (False, True):
                with self.subTest(fast=fast, raw=raw):
                    first, owner = self.make(), self.make()
                    plug = owner.getPlug("tx")
                    with self.assertRaises(TypeError):
                        mlib.delete([first, plug.mplug() if raw else plug], fast=fast)
                    self.assertTrue(first.isValid() and owner.isValid() and plug.isValid())

    def test_empty_collections_are_rejected(self):
        """空list・tuple・generatorでは削除対象を暗黙の選択へ置き換えない。"""
        selected = self.make()
        cmds.select(selected.getFullName())
        for fast in (False, True):
            for kind in (list, tuple, iter):
                with self.subTest(fast=fast, kind=kind.__name__):
                    with self.assertRaises(ValueError):
                        mlib.delete(kind([]), fast=fast)
                    self.assertTrue(selected.isValid())

    def test_invalid_flags_are_rejected_before_deletion(self):
        """fast/safeの不正な型によってノードを削除しない。"""
        node = self.make()
        for value in (None, 0, 1, "true"):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    mlib.delete(node, fast=value)
                with self.assertRaises(TypeError):
                    node.delete(safe=value)
                self.assertTrue(node.isValid())

    def test_fast_component_rejection_preserves_all_targets(self):
        """fast非対応のコンポーネントが混ざると、先行ノードも形状も変更しない。"""
        plain = self.make()
        mesh = cmds.polyCube(name=self.namespace + ":mesh", constructionHistory=False)[0]
        before = cmds.polyEvaluate(mesh, vertex=True)
        with self.assertRaises(NotImplementedError):
            mlib.delete([plain.getFullName(), mesh + ".vtx[0]"], fast=True)
        self.assertTrue(plain.isValid())
        self.assertEqual(cmds.polyEvaluate(mesh, vertex=True), before)

    def test_fast_delete_does_not_consume_or_append_undo(self):
        """既存Undoの前後でfast削除が設定やキューを変更しない。"""
        marker, deleted = self.make(), self.make()
        deleted_name = deleted.getFullName()
        cmds.flushUndo()
        marker.getPlug("tx").set(5)
        undo_name = cmds.undoInfo(query=True, undoName=True)
        self.assertIsNone(deleted.delete(fast=True))
        self.assertTrue(cmds.undoInfo(query=True, state=True))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        cmds.undo()
        self.assertEqual(cmds.getAttr(marker.getFullName() + ".tx"), 0)
        self.assertFalse(cmds.objExists(deleted_name))

    def test_normal_delete_restores_held_references_across_redo_cycles(self):
        """同じNodeとPlugを保持したまま、削除/Undo/redoを繰り返せる。"""
        node = self.make()
        name = node.getFullName()
        plug = node.getPlug("tx")
        plug.set(7)
        cmds.flushUndo()
        node.delete()
        for _ in range(3):
            self.assertFalse(node.isValid())
            self.assertFalse(plug.isValid())
            with self.assertRaises(RuntimeError):
                plug.get()
            cmds.undo()
            self.assertTrue(node.isValid() and plug.isValid())
            self.assertEqual(plug.get(), 7)
            self.assertEqual(cmds.getAttr(name + ".tx"), 7)
            cmds.redo()

    def test_safe_parent_delete_becomes_possible_after_message_disconnect(self):
        """子のmessage接続で保護された親を、切断後には削除できる。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                parent = self.make()
                child = self.make(parent=parent)
                receiver = self.make("network")
                cmds.addAttr(receiver.getFullName(), longName="owner", attributeType="message")
                source = child.getPlug("message")
                destination = receiver.getPlug("owner")
                destination.connect(source)
                self.assertIsNone(parent.delete(safe=True, fast=fast))
                self.assertTrue(parent.isValid() and child.isValid())
                destination.disconnect(source, fast=fast)
                parent.delete(safe=True, fast=fast)
                self.assertFalse(parent.isValid() or child.isValid())
                self.assertTrue(receiver.isValid())

    def test_locked_descendant_rejection_preserves_siblings_and_values(self):
        """ロックされた孫を含む削除要求で、別枝や既存値を変更しない。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                root = self.make()
                child = self.make(parent=root)
                grandchild = self.make(parent=child)
                sibling = self.make()
                sibling.getPlug("tx").set(11)
                names = [node.getFullName() for node in (root, child, grandchild, sibling)]
                cmds.lockNode(grandchild.getFullName(), lock=True)
                with self.assertRaises(RuntimeError):
                    mlib.delete([sibling, root], fast=fast)
                self.assertTrue(all(cmds.objExists(name) for name in names))
                self.assertEqual(cmds.getAttr(sibling.getFullName() + ".tx"), 11)
                cmds.lockNode(grandchild.getFullName(), lock=False)


if __name__ == "__main__":
    unittest.main()
