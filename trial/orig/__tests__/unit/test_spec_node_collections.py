"""Nodes(と派生コレクション)の構築・添字の約束を固定する(担当C)。

対象: 入力の展開と重複除去・型の検証・名前と Node の混在の拒否、添字とスライス・copy、空のコレクション。
3.0.0 で単数への一括転送(callEach 等)は廃止したため、各要素の操作は単数のメソッドを呼ぶ。
"""

import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import Joint, Joints, Node, Nodes
from support.specCase import NamespaceCase


def _names(nodes):
    """保持順の現在のノード名。"""
    return [node.getName() for node in nodes]


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecNodeColl_"
    UNLOCK_NODES = True


class ConstructionTest(_SpecCase):
    """入力の展開・重複除去・型の検証。"""

    def test_single_and_nested_inputs(self):
        """単一の名前・Node も受け、入れ子の列は入力順に展開する。空は空のコレクション。"""
        a, b, dg = self.make(), self.make(), self.make("network")
        self.assertEqual(_names(Nodes(a)), [a])
        self.assertEqual(_names(Nodes(Node(a))), [a])
        self.assertEqual(_names(Nodes([a, [b, (dg,)]])), [a, b, dg])
        self.assertEqual(len(Nodes()), 0)
        self.assertEqual(repr(Joints()), "Joints([])")

    def test_duplicates_removed_but_instances_kept(self):
        """同じノード・同じパスの重複だけを除き、別インスタンスのパスは残す。"""
        a = self.make()
        self.assertEqual(len(Nodes([a, a, a])), 1)
        shape_parent, other_parent = self.make(), self.make()
        shape = self.make("mesh", "shape", parent=shape_parent)
        cmds.parent(shape, other_parent, addObject=True, shape=True)
        paths = cmds.ls(shape, allPaths=True, long=True)
        self.assertEqual(len(Nodes(paths + paths)), 2)

    def test_mixed_names_and_nodes_rejected(self):
        """同じ列に名前と Node を混在させると TypeError。"""
        a, b = self.make(), self.make()
        with self.assertRaisesRegex(TypeError, "cannot be mixed"):
            Nodes([a, Node(b)])

    def test_item_class_checked(self):
        """派生コレクションは item_class の派生だけを受け、Nodes は全ノードを受ける。"""
        a, j, dg = self.make(), self.make("joint"), self.make("network")
        # network は Node を親にした自動生成クラス Network で包まれる。
        with self.assertRaisesRegex(TypeError, "Joints requires Joint, got Network"):
            Joints([j, dg])
        with self.assertRaisesRegex(TypeError, "Joints requires Joint, got Transform"):
            Joints([a])
        self.assertEqual([type(item) for item in Joints([j])], [Joint])
        self.assertEqual(len(Nodes([a, j, dg])), 3)

    def test_invalid_inputs(self):
        """存在しない名前・削除済みの参照は RuntimeError、未対応型は TypeError。"""
        with self.assertRaises(RuntimeError):
            Nodes([self.ns + ":missing"])
        node = Node(self.make())
        cmds.delete(node.getFullName())
        with self.assertRaisesRegex(RuntimeError, "Cannot collect an invalid node"):
            Nodes([node])
        with self.assertRaises(TypeError):
            Nodes(5)


class ContainerProtocolTest(_SpecCase):
    """添字・スライス・copy。"""

    def setUp(self):
        super().setUp()
        self.names = [self.make("joint") for _ in range(3)]
        self.nodes = Joints(self.names)

    def test_index_and_slice(self):
        """添字は同じ参照、スライスは同型の新しいコレクション。範囲外は IndexError。"""
        self.assertIs(self.nodes[0], self.nodes._items[0])
        self.assertIs(self.nodes[-1], self.nodes._items[-1])
        self.assertIs(self.nodes[True], self.nodes._items[1])
        part = self.nodes[1:]
        self.assertIs(type(part), Joints)
        self.assertEqual(_names(part), self.names[1:])
        self.assertIs(part[0], self.nodes[1])
        with self.assertRaises(IndexError):
            self.nodes[5]

    def test_copy_is_independent_container(self):
        """copy は同じ参照を共有し、保持列は独立する。"""
        copied = self.nodes.copy()
        self.assertIs(type(copied), Joints)
        self.assertIs(copied[0], self.nodes[0])
        self.assertIsNot(copied._items, self.nodes._items)

    def test_names_follow_rename_and_delete(self):
        """保持する参照は改名に追従し、削除済みの参照は空文字列の名前のまま保持する。"""
        self.nodes[0].rename(self.ns + ":renamed")
        cmds.delete(self.names[2])
        self.assertEqual(_names(self.nodes), [self.ns + ":renamed", self.names[1], ""])
        self.assertEqual(len(self.nodes), 3)


class EmptyCollectionTest(unittest.TestCase):
    """空のコレクション。"""

    def test_empty(self):
        """長さ0で、反復・スライス・copyも空の同型コレクション。"""
        nodes = Nodes()
        self.assertEqual(len(nodes), 0)
        self.assertEqual(list(nodes), [])
        self.assertIs(type(nodes[:]), Nodes)
        self.assertEqual(len(nodes.copy()), 0)
        self.assertEqual(len(Joints().sortedByDepth()), 0)


if __name__ == "__main__":
    unittest.main()
