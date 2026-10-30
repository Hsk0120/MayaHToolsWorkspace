"""DagNode の階層とパス・表示の約束を固定する(担当C)。

対象: getName・getFullName(インスタンスごと)、getParents(indirect)、getParent(step)、
getInstances(noSelf)、mfn、show・hide・setVisibility(Undo・fast・ロック)、getVisibility と isVisible の違い、
getChildren の引数検査、保持インスタンスだけが消えた参照と削除済みノードの扱い。
"""

import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import Node
from support.specCase import NamespaceCase


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecDagPaths_"


class InstancedPathTest(_SpecCase):
    """インスタンス化した Transform のパス・親の照会。"""

    def setUp(self):
        super().setUp()
        self.g1, self.g2 = self.make("transform", "g1"), self.make("transform", "g2")
        child = self.make("transform", "child", parent=self.g1)
        cmds.parent(child, self.g2, addObject=True, relative=True)
        self.paths = cmds.ls(self.name("child"), allPaths=True, long=True)
        self.first, self.second = Node(self.paths[0]), Node(self.paths[1])

    def test_partial_and_full_path_per_instance(self):
        """getName は保持インスタンスの最短一意パス、getFullName は完全パス。"""
        self.assertEqual(self.first.getFullName(), self.paths[0])
        self.assertEqual(self.second.getFullName(), self.paths[1])
        self.assertEqual([self.first.getName(), self.second.getName()], cmds.ls(self.paths))
        self.assertEqual(self.first.getName(), self.first.mpath().partialPathName())
        self.assertEqual(self.first.getName(), self.first.getName())

    def test_partial_path_of_unique_node_is_its_name(self):
        """一意な名前のノードでは getName はノード名だけになる。"""
        node = Node(self.make("transform", "unique", parent=self.g1))
        self.assertEqual(node.getName(), self.name("unique"))

    def test_get_parents(self):
        """直接の親を API の順で返し、保持パスの親はそのパスを使う。ワールド直下は空。"""
        self.assertEqual([parent.getFullName() for parent in self.first.getParents()],
                         ["|" + self.g1, "|" + self.g2])
        self.assertEqual([parent.getFullName() for parent in self.second.getParents()],
                         ["|" + self.g1, "|" + self.g2])
        self.assertEqual(Node(self.g1).getParents(), [])

    def test_get_parents_indirect(self):
        """親自体がインスタンス化されると、indirect=True だけが親の別パスも返す。"""
        holder = self.make("transform", "holder", parent=self.g1)
        self.make("transform", "leaf", parent=holder)
        cmds.parent(cmds.ls(holder, long=True)[0], self.g2, addObject=True, relative=True)
        leaf_paths = cmds.ls(self.name("leaf"), allPaths=True, long=True)
        self.assertEqual(len(leaf_paths), 2)
        node = Node(leaf_paths[0])
        self.assertEqual([parent.getFullName() for parent in node.getParents()],
                         [leaf_paths[0].rsplit("|", 1)[0]])
        self.assertEqual([parent.getFullName() for parent in node.getParents(indirect=True)],
                         [path.rsplit("|", 1)[0] for path in leaf_paths])

    def test_get_parent_step(self):
        """step は保持パスを遡り、0以下・ワールド到達は None。"""
        self.make("transform", "deep", parent=self.paths[1])
        # 親がインスタンスなので deep にもパスが2つある。g2 側のパスを明示して保持する。
        deep = Node([path for path in cmds.ls(self.name("deep"), allPaths=True, long=True)
                     if path.startswith("|" + self.g2)][0])
        self.assertEqual(deep.getParent().getFullName(), self.paths[1])
        self.assertEqual(deep.getParent(2).getFullName(), "|" + self.g2)
        for step in (0, -1, 3, 10):
            with self.subTest(step=step):
                self.assertIsNone(deep.getParent(step))

    def test_get_instances(self):
        """getInstances は全パスで、保持パスは自身。noSelf=True は保持パスを除く。"""
        instances = self.first.getInstances()
        self.assertEqual([item.getFullName() for item in instances], self.paths)
        self.assertIs(instances[0], self.first)
        self.assertEqual([item.getFullName() for item in self.first.getInstances(noSelf=True)], [self.paths[1]])
        self.assertEqual([item.getFullName() for item in self.second.getInstances(noSelf=True)], [self.paths[0]])

    def test_dag_fn(self):
        """mfn は保持インスタンスの MFnDagNode(Transform は MFnTransform)。"""
        fn = self.second.mfn()
        self.assertIsInstance(fn, om2.MFnDagNode)
        self.assertEqual(fn.fullPathName(), self.paths[1])

    def test_removed_instance(self):
        """保持インスタンスだけが外れると、ノードは有効でもパスを使う照会は RuntimeError。"""
        cmds.parent(self.paths[1], removeObject=True)
        self.assertTrue(self.second.isValid())
        for method in ("getName", "getFullName", "getName", "getParents", "getChildren",
                       "mpath", "mfn"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(RuntimeError, "no longer exists"):
                    getattr(self.second, method)()
        self.assertEqual(self.first.getFullName(), self.paths[0])


class DeletedDagNodeTest(_SpecCase):
    """ノードごと削除した DAG 参照の照会。"""

    #: 削除直後(Undo の記録に残る間)も、破棄後も RuntimeError になるパスの照会。
    PATH_METHODS = ("isVisible", "getParent", "getParents", "mpath",
                    "mfn", "getInstances", "getSkinClusters", "getBindPoses", "isRoot")

    def setUp(self):
        super().setUp()
        self.parent = self.make("transform", "parent")
        self.node = Node(self.make("transform", "gone", parent=self.parent))
        cmds.delete(self.node.getFullName())

    def test_deleted_but_alive(self):
        """Undo の記録に残る間も、パスの照会は古い値・空文字列を返さず RuntimeError。

        名前の照会(getName・getFullName)は従来どおり空文字列、getChildren は空リスト、
            """
        self.assertTrue(self.node.isAlive())
        for method in self.PATH_METHODS:
            with self.subTest(method=method):
                with self.assertRaisesRegex(RuntimeError, "no longer exists"):
                    getattr(self.node, method)()
        # 5.0.0から名前の取得は無効なノードでRuntimeError(str()は空文字列、getFullNameは従来どおり)。
        with self.assertRaisesRegex(RuntimeError, "was deleted or undone"):
            self.node.getName()
        self.assertEqual(str(self.node), "")
        self.assertEqual(self.node.getFullName(), "")
        self.assertEqual(self.node.getChildren(), [])
        with self.assertRaises(RuntimeError):
            self.node.getVisibility()
        with self.assertRaises(RuntimeError):
            self.node.show()

    def test_undo_restores_queries(self):
        """削除を Undo すると、同じ参照のパスの照会が再び使える。"""
        cmds.undo()
        self.assertTrue(self.node.isValid())
        self.assertEqual(self.node.getFullName(), cmds.ls(self.name("gone"), long=True)[0])
        self.assertEqual(self.node.getParent().getFullName(), cmds.ls(self.parent, long=True)[0])
        self.assertTrue(self.node.isVisible())

    def test_destroyed(self):
        """Undo の記録を消すと、パスの照会は RuntimeError になる。getChildren だけは空リスト。"""
        cmds.flushUndo()
        for method in self.PATH_METHODS:
            with self.subTest(method=method):
                with self.assertRaisesRegex(RuntimeError, "no longer exists"):
                    getattr(self.node, method)()
        self.assertEqual(self.node.getChildren(), [])


class VisibilityTest(_SpecCase):
    """show・hide・setVisibility と、getVisibility・isVisible の違い。"""

    def setUp(self):
        super().setUp()
        self.parent = self.make("transform", "visParent")
        self.child_name = self.make("transform", "visChild", parent=self.parent)
        self.node = Node(self.child_name)

    def test_show_hide_return_self_and_undo(self):
        """hide・show は visibility だけを変えて自身を返し、それぞれ1回の Undo で戻る。"""
        cmds.flushUndo()
        self.assertIs(self.node.hide(), self.node)
        self.assertFalse(cmds.getAttr(self.child_name + ".visibility"))
        self.assertRegex(cmds.undoInfo(query=True, undoName=True), r"^mlib setVisibility( |$)")
        cmds.undo()
        self.assertTrue(cmds.getAttr(self.child_name + ".visibility"))
        self.node.setVisibility(False)
        self.assertIs(self.node.show(), self.node)
        self.assertTrue(cmds.getAttr(self.child_name + ".visibility"))

    def test_show_hide_accept_fast(self):
        """show・hide の fast=True は setVisibility(fast=True) と同じで、Undo に記録しない。bool 以外は TypeError。"""
        with self.assertRaises(TypeError):
            self.node.hide(fast=1)
        cmds.flushUndo()
        self.assertIs(self.node.hide(fast=True), self.node)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertFalse(cmds.getAttr(self.child_name + ".visibility"))
        self.assertIs(self.node.show(fast=True), self.node)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertTrue(cmds.getAttr(self.child_name + ".visibility"))
        self.node.setVisibility(False, fast=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertFalse(cmds.getAttr(self.child_name + ".visibility"))

    def test_set_visibility_type_checks(self):
        """state・fast は bool だけ。"""
        with self.assertRaisesRegex(TypeError, "state must be a bool"):
            self.node.setVisibility(1)
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            self.node.setVisibility(True, fast=1)

    def test_locked_or_connected(self):
        """ロック・入力接続された visibility は RuntimeError で、値を変えない。"""
        cmds.setAttr(self.child_name + ".visibility", lock=True)
        with self.assertRaises(RuntimeError):
            self.node.hide()
        cmds.setAttr(self.child_name + ".visibility", lock=False)
        source = self.make("transform", "visSource")
        cmds.connectAttr(source + ".visibility", self.child_name + ".visibility")
        with self.assertRaises(RuntimeError):
            self.node.hide()
        self.assertTrue(cmds.getAttr(self.child_name + ".visibility"))

    def test_visibility_vs_is_visible(self):
        """getVisibility は自身の値、isVisible は親を含めた表示状態。"""
        cmds.setAttr(self.parent + ".visibility", False)
        self.assertTrue(self.node.getVisibility())
        self.assertFalse(self.node.isVisible())

    def test_get_children_argument_checks(self):
        """探索フラグは bool、order は2種類、leaves と shapes は併用できない。"""
        with self.assertRaisesRegex(TypeError, "must be a bool"):
            self.node.getChildren(allDescendents=1)
        with self.assertRaisesRegex(ValueError, "order"):
            self.node.getChildren(order="random")
        with self.assertRaisesRegex(ValueError, "leaves"):
            self.node.getChildren(leaves=True, shapes=True)


if __name__ == "__main__":
    unittest.main()
