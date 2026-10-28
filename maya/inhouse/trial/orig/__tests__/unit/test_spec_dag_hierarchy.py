"""DagNode・DagNodes の共通化後の約束を固定する(Phase 2 2A)。

対象: mfn()(MFnDagNode)、DagNode へ移した getRoot・getSiblings・getBoundingBox(worldSpace/ws)・
isIntermediateObject(Transform・Shape 双方で使える)、show/hide の fast(Undo 1 回・fast は Undo なし)、
getShape の契約(Shape は自身)、廃止した名前(dagFn・getParentPath・getFullPath・getPartialPath・
collectSkinClusters)が DagNode・DagNodes から消えていること、DagNodes の宣言。
"""

import inspect
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import DagNode, DagNodes, Node, Shape, Transform
from support.specCase import NamespaceCase


REMOVED_DAG_METHODS = ("dagFn", "getParentPath", "getFullPath", "getPartialPath", "collectSkinClusters")


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecDagHier_"

    def cube(self, text, parent=None):
        """polyCube を作り (transform, shape) の完全パスを返す。"""
        transform = cmds.polyCube(name=self.name(text), constructionHistory=False)[0]
        if parent is not None:
            transform = cmds.parent(transform, parent)[0]
        transform = cmds.ls(transform, long=True)[0]
        shape = cmds.listRelatives(transform, shapes=True, fullPath=True)[0]
        return transform, shape


class HierarchyFixture(_SpecCase):
    """root > mid > (leaf, leaf2, leafShape...) の階層。"""

    def setUp(self):
        super().setUp()
        self.root = self.make("transform", "root")
        self.mid = self.make("transform", "mid", parent=self.root)
        self.leaf, self.leaf_shape = self.cube("leaf", parent=self.mid)
        self.leaf2 = cmds.ls(self.make("transform", "leaf2", parent=self.mid), long=True)[0]
        self.other_root = self.make("transform", "otherRoot")


class MfnTest(HierarchyFixture):
    def test_dag_fn_matches_held_path(self):
        """Shape の mfn は MFnDagNode で保持パスに対応し、毎回新しい。"""
        shape = Node(self.leaf_shape)
        fn = shape.mfn()
        self.assertIsInstance(fn, om2.MFnDagNode)
        self.assertEqual(fn.getPath().fullPathName(), self.leaf_shape)
        self.assertIsNot(shape.mfn(), fn)

    def test_invalid_path_raises(self):
        """削除したノードは RuntimeError。"""
        node = Node(self.leaf2)
        cmds.delete(self.leaf2)
        with self.assertRaises(RuntimeError):
            node.mfn()


class GetRootTest(HierarchyFixture):
    def test_transform_and_shape_share_root(self):
        """Transform・Shape のどちらからも最上位の Transform を返す。"""
        root = Node(self.root)
        for name in (self.mid, self.leaf, self.leaf_shape):
            with self.subTest(name=name):
                result = Node(name).getRoot()
                self.assertIsInstance(result, Transform)
                self.assertEqual(result, root)
                self.assertEqual(result.getFullName(), "|" + self.root)

    def test_world_level_returns_self(self):
        node = Node(self.root)
        self.assertIs(node.getRoot(), node)

    def test_matches_cmds_long_name(self):
        """cmds.ls(long=True) の先頭要素と一致する。"""
        expected = "|" + cmds.ls(self.leaf_shape, long=True)[0].split("|")[1]
        self.assertEqual(Node(self.leaf_shape).getRoot().getFullName(), expected)


class GetSiblingsTest(HierarchyFixture):
    def test_transform_siblings_match_cmds(self):
        """Transform の兄弟は親直下の他 Transform(DAG の子順)。"""
        expected = [path for path in cmds.listRelatives(self.mid, children=True, type="transform", fullPath=True)
                    if path != self.leaf]
        self.assertEqual([node.getFullName() for node in Node(self.leaf).getSiblings()], expected)
        self.assertEqual(expected, [self.leaf2])

    def test_shape_siblings_exclude_intermediate(self):
        """Shape の兄弟は親直下の他の非中間 Shape。"""
        second = cmds.createNode("mesh", name=self.name("leafShape2"), parent=self.leaf, skipSelect=True)
        hidden = cmds.createNode("mesh", name=self.name("leafShapeOrig"), parent=self.leaf, skipSelect=True)
        cmds.setAttr(hidden + ".intermediateObject", True)
        siblings = Node(self.leaf_shape).getSiblings()
        self.assertEqual([node.getFullName() for node in siblings], cmds.ls(second, long=True))
        self.assertTrue(all(isinstance(node, Shape) for node in siblings))

    def test_world_level_transform_uses_assemblies(self):
        """ワールド直下は cmds.ls(assemblies=True) から自身を除いたもの。"""
        expected = [path for path in cmds.ls(assemblies=True, long=True) if path != "|" + self.root]
        self.assertEqual(sorted(node.getFullName() for node in Node(self.root).getSiblings()), sorted(expected))

    def test_instances_of_self_are_not_siblings(self):
        """自身の別インスタンスは兄弟に含めない。"""
        cmds.parent(self.leaf, self.leaf2, addObject=True, relative=True)
        instance = cmds.ls(self.name("leaf"), allPaths=True, long=True)[1]
        self.assertEqual([node.getFullName() for node in Node(instance).getSiblings()], [])

    def test_invalid_node_returns_empty(self):
        node = Node(self.leaf2)
        cmds.delete(self.leaf2)
        self.assertEqual(node.getSiblings(), [])


class GetBoundingBoxTest(HierarchyFixture):
    def setUp(self):
        super().setUp()
        cmds.setAttr(self.root + ".translate", 10, 0, 0)
        cmds.setAttr(self.mid + ".scale", 2, 2, 2)
        cmds.setAttr(self.leaf + ".translate", 1, 2, 3)

    def bounds(self, box):
        return [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z]

    def assertBox(self, box, expected):
        for value, want in zip(self.bounds(box), expected):
            self.assertAlmostEqual(value, want, places=5)

    def test_local_matches_xform(self):
        """worldSpace=False は Transform では cmds.xform(boundingBox=True)(自身の変換を含み親を含まない)、
        Shape では形状そのもの(単位立方体 ±0.5)。"""
        self.assertBox(Node(self.leaf).getBoundingBox(), cmds.xform(self.leaf, query=True, boundingBox=True))
        self.assertBox(Node(self.leaf_shape).getBoundingBox(), [-0.5, -0.5, -0.5, 0.5, 0.5, 0.5])

    def test_world_matches_exact_world_bounding_box(self):
        """worldSpace=True(別名 ws)は cmds.exactWorldBoundingBox と同じ。Transform・Shape で同じ値。"""
        expected = cmds.exactWorldBoundingBox(self.leaf_shape)
        for name in (self.leaf, self.leaf_shape):
            for flags in ({"worldSpace": True}, {"ws": True}):
                with self.subTest(name=name, flags=flags):
                    self.assertBox(Node(name).getBoundingBox(**flags), expected)

    def test_flag_validation(self):
        node = Node(self.leaf)
        with self.assertRaises(TypeError):
            node.getBoundingBox(True, ws=True)
        with self.assertRaises(TypeError):
            node.getBoundingBox(1)
        with self.assertRaises(TypeError):
            node.getBoundingBox(ws="yes")

    def test_invalid_node_raises(self):
        node = Node(self.leaf2)
        cmds.delete(self.leaf2)
        with self.assertRaises(RuntimeError):
            node.getBoundingBox()


class IsIntermediateObjectTest(HierarchyFixture):
    def test_shape_and_transform(self):
        """Shape は intermediateObject の値、Transform は常に False。"""
        shape = Node(self.leaf_shape)
        self.assertFalse(shape.isIntermediateObject())
        cmds.setAttr(self.leaf_shape + ".intermediateObject", True)
        self.assertTrue(shape.isIntermediateObject())
        self.assertEqual(shape.isIntermediateObject(), cmds.getAttr(self.leaf_shape + ".intermediateObject"))
        self.assertFalse(Node(self.leaf).isIntermediateObject())


class ShowHideTest(HierarchyFixture):
    def visible(self):
        return cmds.getAttr(self.leaf + ".visibility")

    def test_normal_path_is_one_undo(self):
        """hide/show は 1 回の Undo で戻り、自身を返す。"""
        node = Node(self.leaf)
        cmds.flushUndo()
        self.assertIs(node.hide(), node)
        self.assertFalse(self.visible())
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibNodeSetVisible")
        cmds.undo()
        self.assertTrue(self.visible())
        node.hide()
        self.assertIs(node.show(), node)
        self.assertTrue(self.visible())

    def test_fast_leaves_no_undo(self):
        """fast=True は Undo に残らず値だけ変わる。"""
        node = Node(self.leaf)
        for method, expected in (("hide", False), ("show", True)):
            with self.subTest(method=method):
                cmds.flushUndo()
                self.assertIs(getattr(node, method)(fast=True), node)
                self.assertEqual(self.visible(), expected)
                self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_fast_validation(self):
        node = Node(self.leaf)
        for method in ("show", "hide"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(TypeError, "fast must be a bool"):
                    getattr(node, method)(fast=1)
                with self.assertRaises(TypeError):
                    getattr(node, method)(True)
        self.assertTrue(self.visible())

    def test_dag_nodes_forward_fast(self):
        """DagNodes.hide(fast=True) は全要素を更新してコレクション自身を返す。"""
        nodes = DagNodes([self.leaf, self.leaf2])
        cmds.flushUndo()
        self.assertIs(nodes.hide(fast=True), nodes)
        self.assertEqual([cmds.getAttr(name + ".visibility") for name in (self.leaf, self.leaf2)], [False, False])
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertIs(nodes.show(), nodes)
        self.assertEqual([cmds.getAttr(name + ".visibility") for name in (self.leaf, self.leaf2)], [True, True])


class GetShapeContractTest(HierarchyFixture):
    def test_shape_returns_self_regardless_of_arguments(self):
        shape = Node(self.leaf_shape)
        for flags in ({}, {"idx": 5}, {"index": 3, "intermediates": True}):
            with self.subTest(flags=flags):
                self.assertIs(shape.getShape(**flags), shape)

    def test_index_aliases_conflict(self):
        with self.assertRaises(TypeError):
            Node(self.leaf_shape).getShape(0, index=0)

    def test_transform_out_of_range_is_none(self):
        self.assertIsNone(Node(self.leaf).getShape(5))
        self.assertEqual(Node(self.leaf).getShape(0).getFullName(), self.leaf_shape)


class RemovedNamesTest(HierarchyFixture):
    def test_removed_from_classes(self):
        for name in REMOVED_DAG_METHODS:
            with self.subTest(name=name):
                self.assertFalse(hasattr(DagNode, name))
                self.assertFalse(hasattr(DagNodes, name))
                self.assertNotIn(name, DagNodes._bulk_entries)

    def test_removed_from_instances(self):
        node = Node(self.leaf)
        for name in REMOVED_DAG_METHODS:
            with self.subTest(name=name):
                with self.assertRaises(AttributeError):
                    getattr(node, name)

    def test_replacements(self):
        """代替: getFullName / getName / getParent().mpath() / SkinClusters(getSkinClusters())。"""
        node = Node(self.leaf_shape)
        self.assertEqual(node.getFullName(), node.mpath().fullPathName())
        self.assertEqual(node.getName(), node.mpath().partialPathName())
        self.assertEqual(node.getParent().mpath().fullPathName(), self.leaf)


class DagNodesDeclarationTest(unittest.TestCase):
    def test_moved_entries_present(self):
        for name in ("mfn", "getRoot", "getSiblings", "getBoundingBox", "isIntermediateObject"):
            with self.subTest(name=name):
                self.assertIs(DagNodes._bulk_entries[name][0], getattr(DagNode, name))
                self.assertEqual(DagNodes._bulk_entries[name][1], "list")
                self.assertEqual(inspect.signature(getattr(DagNodes, name)),
                                 inspect.signature(getattr(DagNode, name)))

    def test_show_hide_entries_return_self(self):
        self.assertEqual(DagNodes._bulk_entries["show"][1], "self")
        self.assertEqual(DagNodes._bulk_entries["hide"][1], "self")
        self.assertEqual(inspect.signature(DagNodes.show), inspect.signature(DagNode.show))

    def test_every_entry_has_forwarder(self):
        for name in DagNodes._bulk_entries:
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(DagNodes, name)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
