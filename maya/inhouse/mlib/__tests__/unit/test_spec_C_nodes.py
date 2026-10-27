"""Nodes(と派生コレクション)の構築・添字・一括呼出しの約束を固定する(担当C)。

対象: 入力の展開と重複除去・型の検証・名前と Node の混在の拒否、添字とスライス・copy・getNames、
callEach の件数・メソッド名・呼出形式の検査、一括メソッドの戻り値(照会はリスト、更新は自身)、
失敗時の ``failed at item <番号>`` と先行変更の扱い、通常の一括更新が1回の Undo で戻ること、
全件 fast が Undo に記録されないこと、空のコレクション。
削除の一括化そのものは test_contract_changes_A.py が確かめているため、ここでは番号の報告だけを見る。
"""

import unittest
import uuid

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import DagNodes, Joint, Joints, Node, Nodes, Transform, Transforms


class _NamespaceCase(unittest.TestCase):
    """専用の一時名前空間でノードを作り、Undo の設定を元に戻す。"""

    def setUp(self):
        self.ns = "mlibSpecCNodes_" + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.ns)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)

    def tearDown(self):
        for name in cmds.ls(self.ns + ":*", long=True) or []:
            if cmds.objExists(name):
                cmds.lockNode(name, lock=False)
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_state)

    def make(self, kind="transform", text="node#", parent=None):
        flags = {"name": self.ns + ":" + text, "skipSelect": True}
        if parent is not None:
            flags["parent"] = parent
        return cmds.createNode(kind, **flags)


class ConstructionTest(_NamespaceCase):
    """入力の展開・重複除去・型の検証。"""

    def test_single_and_nested_inputs(self):
        """単一の名前・Node も受け、入れ子の列は入力順に展開する。空は空のコレクション。"""
        a, b, dg = self.make(), self.make(), self.make("network")
        self.assertEqual(Nodes(a).getNames(), [a])
        self.assertEqual(Nodes(Node(a)).getNames(), [a])
        self.assertEqual(Nodes([a, [b, (dg,)]]).getNames(), [a, b, dg])
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
        self.assertEqual(len(DagNodes(paths + paths)), 2)

    def test_mixed_names_and_nodes_rejected(self):
        """同じ列に名前と Node を混在させると TypeError。"""
        a, b = self.make(), self.make()
        with self.assertRaisesRegex(TypeError, "cannot be mixed"):
            Nodes([a, Node(b)])

    def test_item_class_checked(self):
        """派生コレクションは item_class の派生だけを受け、Joint は Transforms に入る。"""
        a, j, dg = self.make(), self.make("joint"), self.make("network")
        # network は Node を親にした自動生成クラス Network で包まれる。
        with self.assertRaisesRegex(TypeError, "Transforms requires Transform, got Network"):
            Transforms([a, dg])
        with self.assertRaisesRegex(TypeError, "Joints requires Joint, got Transform"):
            Joints([a])
        self.assertEqual([type(item) for item in Transforms([a, j])], [Transform, Joint])

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


class ContainerProtocolTest(_NamespaceCase):
    """添字・スライス・copy・getNames。"""

    def setUp(self):
        super().setUp()
        self.names = [self.make() for _ in range(3)]
        self.nodes = Transforms(self.names)

    def test_index_and_slice(self):
        """添字は同じ参照、スライスは同型の新しいコレクション。範囲外は IndexError。"""
        self.assertIs(self.nodes[0], self.nodes._items[0])
        self.assertIs(self.nodes[-1], self.nodes._items[-1])
        self.assertIs(self.nodes[True], self.nodes._items[1])
        part = self.nodes[1:]
        self.assertIs(type(part), Transforms)
        self.assertEqual(part.getNames(), self.names[1:])
        self.assertIs(part[0], self.nodes[1])
        with self.assertRaises(IndexError):
            self.nodes[5]

    def test_copy_is_independent_container(self):
        """copy は同じ参照を共有し、保持列は独立する。"""
        copied = self.nodes.copy()
        self.assertIs(type(copied), Transforms)
        self.assertIs(copied[0], self.nodes[0])
        self.assertIsNot(copied._items, self.nodes._items)

    def test_names_follow_rename_and_delete(self):
        """getNames は呼ぶたびに現在の名前を返し、削除済みの参照は空文字列のまま保持する。"""
        self.nodes[0].rename(self.ns + ":renamed")
        cmds.delete(self.names[2])
        self.assertEqual(self.nodes.getNames(), [self.ns + ":renamed", self.names[1], ""])
        self.assertEqual(len(self.nodes), 3)


class CallEachTest(_NamespaceCase):
    """callEach の事前検査と、要素別の引数による実行。"""

    def setUp(self):
        super().setUp()
        self.names = [self.make() for _ in range(3)]
        self.nodes = Transforms(self.names)

    def test_argument_checks_before_execution(self):
        """件数・メソッド名・呼出形式の不正は何も実行せずに拒否する。"""
        with self.assertRaisesRegex(ValueError, "Argument count must match collection length"):
            self.nodes.callEach("rename", [("x",), ("y",)])
        with self.assertRaisesRegex(ValueError, "Argument count"):
            self.nodes.callEach("rename", [("x",)] * 3, [{}])
        for method in ("mlibNoSuch", "__init__", "create"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(ValueError, "Unsupported instance method"):
                    self.nodes.callEach(method, [()] * 3)
        with self.assertRaises(TypeError):
            self.nodes.callEach("rename", [("a",), ("b",), ("c", False, "extra")])
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            self.nodes.callEach("rename", [("a",), ("b",), ("c",)], [{"fast": 1}, {}, {}])
        self.assertEqual(self.nodes.getNames(), self.names)

    def test_query_returns_list_and_update_returns_self(self):
        """照会は保持順のリスト、更新は自身を返す。"""
        self.assertEqual(self.nodes.callEach("getNodeName", [(), (True,), ()]),
                         [self.names[0], self.names[1].split(":")[-1], self.names[2]])
        result = self.nodes.callEach("setAttrFlags", [("tx",), ("ty",), ("tz",)],
                                     [{"locked": True}] * 3)
        self.assertIs(result, self.nodes)
        self.assertEqual([cmds.getAttr(name + "." + attr, lock=True)
                          for name, attr in zip(self.names, ("tx", "ty", "tz"))], [True] * 3)

    def test_calculating_setter_with_get_returns_values(self):
        """get=True の計算付き setter は書き込まずに値のリストを返す。"""
        values = self.nodes.callEach("setTranslate", [((1, 0, 0),), ((2, 0, 0),), ((3, 0, 0),)],
                                     [{"get": True}] * 3)
        self.assertEqual([list(value) for value in values], [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0]])
        self.assertEqual([cmds.getAttr(name + ".tx") for name in self.names], [0.0, 0.0, 0.0])

    def test_one_undo_for_bulk_update(self):
        """通常の一括更新は1つのチャンク(mlibBulk_<メソッド>)で、1回の Undo で全件戻る。"""
        cmds.flushUndo()
        self.nodes.callEach("setTranslate", [((1, 0, 0),), ((2, 0, 0),), ((3, 0, 0),)])
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibBulk_setTranslate")
        cmds.undo()
        self.assertEqual([cmds.getAttr(name + ".tx") for name in self.names], [0.0, 0.0, 0.0])

    def test_all_fast_is_not_recorded(self):
        """全件 fast の一括更新は Undo に記録しない。"""
        cmds.flushUndo()
        self.nodes.setTranslate((5, 0, 0), fast=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertEqual([cmds.getAttr(name + ".tx") for name in self.names], [5.0] * 3)


class BulkFailureTest(_NamespaceCase):
    """一括メソッドの失敗時の番号・例外の種類・先行変更。"""

    def setUp(self):
        super().setUp()
        self.names = [self.make() for _ in range(3)]
        self.nodes = Transforms(self.names)

    def test_failed_at_item_keeps_earlier_changes(self):
        """失敗した番号を報告し、後続は実行しない。先行変更は残るが1回の Undo で戻る。"""
        cmds.setAttr(self.names[1] + ".tx", lock=True)
        cmds.flushUndo()
        with self.assertRaisesRegex(RuntimeError, r"Transforms\.setTranslate failed at item 1"):
            self.nodes.setTranslate((7, 0, 0))
        self.assertEqual([cmds.getAttr(name + ".tx") for name in self.names], [7.0, 0.0, 0.0])
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.names[0] + ".tx"), 0.0)

    def test_value_error_is_wrapped_in_runtime_error(self):
        """単数では ValueError になる失敗も、一括では番号付きの RuntimeError になる。"""
        with self.assertRaises(ValueError):
            self.nodes[0].getTranslate(ws=1)
        with self.assertRaisesRegex(RuntimeError, r"Transforms\.getTranslate failed at item 0"):
            self.nodes.getTranslate(ws=1)

    def test_argument_error_stays_type_error(self):
        """長短名の競合は番号付きの TypeError のまま。"""
        with self.assertRaisesRegex(TypeError, r"failed at item 0: Specify only one of 'worldSpace' and 'ws'"):
            self.nodes.getTranslate(worldSpace=True, ws=True)

    def test_mixed_types_fail_at_missing_attribute(self):
        """DG ノードを含む Nodes では、アトリビュートが無い要素の番号で止まる。"""
        dg = self.make("network")
        nodes = Nodes(self.names[:1] + [dg] + self.names[1:2])
        with self.assertRaisesRegex(RuntimeError, r"Nodes\.setAttrFlags failed at item 1"):
            nodes.setAttrFlags("tx", locked=True)
        self.assertTrue(cmds.getAttr(self.names[0] + ".tx", lock=True))
        self.assertFalse(cmds.getAttr(self.names[1] + ".tx", lock=True))

    def test_delete_reports_invalid_item(self):
        """実行前に削除済みの参照があれば番号を報告し、何も削除しない。"""
        cmds.delete(self.names[1])
        with self.assertRaisesRegex(RuntimeError, r"Transforms\.delete invalid item 1"):
            self.nodes.delete()
        self.assertTrue(cmds.objExists(self.names[0]))
        self.assertTrue(cmds.objExists(self.names[2]))
        with self.assertRaisesRegex(TypeError, "safe must be bool"):
            Transforms(self.names[:1]).delete(safe=1)


class EmptyCollectionTest(unittest.TestCase):
    """空のコレクションの一括メソッド。"""

    def test_empty(self):
        """照会は空リスト、更新は自身、delete は None。"""
        nodes = Nodes()
        self.assertEqual(nodes.getNames(), [])
        self.assertEqual(nodes.getName(), [])
        self.assertEqual(nodes.rename("mlibSpecUnused"), [])
        self.assertIs(nodes.setAttrFlags("tx", locked=True), nodes)
        self.assertIsNone(nodes.delete())
        self.assertEqual(nodes.callEach("getName", []), [])


if __name__ == "__main__":
    unittest.main()
