"""Node・Nodes の共通化後の約束を固定する(Phase 2 2A)。

対象: mfn()(最も具体的な function set を毎回新規に返す)、setLocked(state, fast)(cmds.lockNode との
突き合わせ・Undo 1 回・fast は Undo なし・不正入力)、getPlugs(userDefined, includeChildren, **listAttrFlags)、
getConnections の pcls 廃止、廃止した名前(isChildOf・getAttrCount・getPath・sameInstance・
getAssignedObjects・getMaterials・getExtraAttrs)が Node・Nodes から消えていること。
"""

import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import DagNode, Node, Nodes, Transform
from mlib.plugs import MultiPlug, Plug
from support.specCase import NamespaceCase


REMOVED_NODE_METHODS = ("isChildOf", "getAttrCount", "getPath", "sameInstance", "getAssignedObjects",
                        "getMaterials", "getExtraAttrs")


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecNodeId_"
    UNLOCK_NODES = True


class MfnTest(_SpecCase):
    """mfn() はクラスごとに最も具体的な om2 function set を毎回新しく返す。"""

    def test_node_returns_dependency_fn(self):
        """DG ノードは MFnDependencyNode。同じ MObject を指し、毎回別のオブジェクト。"""
        node = Node(self.make("network", "net"))
        fn = node.mfn()
        self.assertIs(type(fn), om2.MFnDependencyNode)
        self.assertEqual(fn.object(), node.mnode())
        self.assertIsNot(node.mfn(), fn)
        self.assertEqual(node.mfn().name(), cmds.ls(self.name("net"))[0])

    def test_dag_node_returns_dag_fn_on_held_path(self):
        """Shape(DagNode)は MFnDagNode で、保持する DAG パスに対応する。"""
        transform = cmds.polyCube(name=self.name("root"), constructionHistory=False)[0]
        shape = cmds.listRelatives(transform, shapes=True, fullPath=True)[0]
        node = Node(shape)
        self.assertIsInstance(node, DagNode)
        fn = node.mfn()
        self.assertIsInstance(fn, om2.MFnDagNode)
        self.assertIs(type(fn), om2.MFnMesh)
        self.assertEqual(fn.getPath().fullPathName(), node.mpath().fullPathName())

    def test_transform_returns_transform_fn(self):
        """Transform は MFnTransform(2B の override)。"""
        node = Node(self.make("transform", "t"))
        self.assertIsInstance(node, Transform)
        self.assertIs(type(node.mfn()), om2.MFnTransform)

    def test_mfn_is_not_the_internal_cache(self):
        """内部キャッシュ(_dependency_fn)とは別のオブジェクト。"""
        node = Node(self.make("transform", "t2"))
        self.assertIsNot(node.mfn(), node._dependency_fn())

    def test_destroyed_node_raises(self):
        """削除して Undo の記録からも消えたノードは RuntimeError。"""
        node = Node(self.make("network", "gone"))
        cmds.delete(str(node))
        cmds.flushUndo()
        with self.assertRaises(RuntimeError):
            node.mfn()

class SetLockedTest(_SpecCase):
    """setLocked は通常 cmds.lockNode(Undo 1 回)、fast は MFnDependencyNode.isLocked 直接。"""

    def setUp(self):
        super().setUp()
        self.node_name = self.make("transform", "locked")
        self.node = Node(self.node_name)

    def locked(self):
        return cmds.lockNode(self.node_name, query=True, lock=True)[0]

    def test_default_locks_and_returns_self(self):
        """引数なしはロック。cmds と一致し、自身を返す。"""
        self.assertFalse(self.locked())
        self.assertIs(self.node.setLocked(), self.node)
        self.assertTrue(self.locked())
        self.assertTrue(self.node.isLocked())

    def test_state_combinations_match_cmds(self):
        """state と fast の組合せで、結果は常に cmds.lockNode の照会と一致する。"""
        for state in (True, False):
            for fast in (False, True):
                with self.subTest(state=state, fast=fast):
                    self.node.setLocked(not state, fast=fast)
                    self.node.setLocked(state, fast=fast)
                    self.assertEqual(self.locked(), state)
                    self.assertEqual(self.node.isLocked(), state)
        self.node.setLocked(False)

    def test_normal_path_is_one_undo(self):
        """通常経路は 1 回の Undo で戻り、チャンク名は mlibNodeSetLocked。"""
        cmds.flushUndo()
        self.node.setLocked(True)
        self.assertRegex(cmds.undoInfo(query=True, undoName=True), r"^mlib setLocked( |$)")
        cmds.undo()
        self.assertFalse(self.locked())
        cmds.redo()
        self.assertTrue(self.locked())
        self.node.setLocked(False)

    def test_fast_path_leaves_no_undo(self):
        """fast=True は Undo に残らない。"""
        cmds.flushUndo()
        self.node.setLocked(True, fast=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertTrue(self.locked())
        self.node.setLocked(False, fast=True)
        self.assertFalse(self.locked())

    def test_invalid_inputs(self):
        """state・fast は bool だけ。fast の検査は変更前。"""
        for bad in (1, "True", None):
            with self.subTest(state=bad):
                with self.assertRaisesRegex(TypeError, "state must be a bool"):
                    self.node.setLocked(bad)
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            self.node.setLocked(True, fast=1)
        self.assertFalse(self.locked())

    def test_fast_is_keyword_only(self):
        """fast は位置引数で渡せない。"""
        with self.assertRaises(TypeError):
            self.node.setLocked(True, True)

    def test_destroyed_node_raises(self):
        """破棄済みノードは RuntimeError。"""
        node = Node(self.make("network", "gone"))
        cmds.delete(str(node))
        cmds.flushUndo()
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaises(RuntimeError):
                    node.setLocked(True, fast=fast)

class GetPlugsTest(_SpecCase):
    """getPlugs(userDefined, includeChildren, **listAttrFlags)。"""

    def setUp(self):
        super().setUp()
        self.node_name = self.make("transform", "attrs")
        cmds.addAttr(self.node_name, longName="scalar", attributeType="double")
        cmds.addAttr(self.node_name, longName="vec", attributeType="double3")
        for axis in "XYZ":
            cmds.addAttr(self.node_name, longName="vec" + axis, attributeType="double", parent="vec")
        cmds.addAttr(self.node_name, longName="arr", attributeType="double", multi=True)
        cmds.addAttr(self.node_name, longName="hiddenAttr", attributeType="long", hidden=True)
        self.node = Node(self.node_name)

    def test_user_defined_top_level_matches_definition_order(self):
        """userDefined=True, includeChildren=False はトップレベルの動的アトリビュートを追加順に返す。"""
        plugs = self.node.getPlugs(userDefined=True, includeChildren=False)
        self.assertEqual([plug.getLongName() for plug in plugs], ["scalar", "vec", "arr", "hiddenAttr"])
        self.assertTrue(all(isinstance(plug, Plug) for plug in plugs))
        self.assertIsInstance(plugs[2], MultiPlug)

    def test_user_defined_with_children_matches_list_attr(self):
        """userDefined=True(既定 includeChildren=True)は子も含み、cmds.listAttr(userDefined=True) と同じ集合。"""
        names = [plug.getLongName() for plug in self.node.getPlugs(userDefined=True)]
        self.assertEqual(sorted(names), sorted(cmds.listAttr(self.node_name, userDefined=True)))
        self.assertEqual(names[:5], ["scalar", "vec", "vecX", "vecY", "vecZ"])

    def test_list_attr_flags_pass_through(self):
        """userDefined=False は cmds.listAttr のフラグをそのまま使い、同じ順で返す。"""
        plugs = self.node.getPlugs(keyable=True)
        expected = cmds.listAttr(self.node_name, keyable=True)
        self.assertEqual([plug.getLongName() for plug in plugs], expected)

    def test_include_children_false_filters_list_attr(self):
        """includeChildren=False は listAttr 経路でもコンパウンドアトリビュートの子(translateX 等)を除く。"""
        plugs = self.node.getPlugs(includeChildren=False)
        names = [plug.getLongName() for plug in plugs]
        self.assertIn("translate", names)
        self.assertNotIn("translateX", names)
        self.assertTrue(all(not plug.mplug().isChild for plug in plugs))
        self.assertIn("translateX", [plug.getLongName() for plug in self.node.getPlugs()])

    def test_invalid_inputs(self):
        """bool 以外、または userDefined=True と listAttr フラグの併用は TypeError。"""
        with self.assertRaisesRegex(TypeError, "userDefined must be a bool"):
            self.node.getPlugs(userDefined=1)
        with self.assertRaisesRegex(TypeError, "includeChildren must be a bool"):
            self.node.getPlugs(includeChildren=None)
        with self.assertRaisesRegex(TypeError, "cannot be combined"):
            self.node.getPlugs(userDefined=True, keyable=True)

    def test_invalid_node_raises(self):
        """削除したノードは RuntimeError。"""
        node = Node(self.make("network", "gone"))
        cmds.delete(str(node))
        with self.assertRaises(RuntimeError):
            node.getPlugs(userDefined=True)

    def test_move_attr_order_still_works_without_get_extra_attrs(self):
        """moveAttrOrder は getExtraAttrs 無しで動く(内部で定義の名前を使う)。"""
        node = Node(self.make("transform", "order"))
        for attr in ("a1", "a2", "a3"):
            cmds.addAttr(str(node), longName=attr, attributeType="double")
        node.moveAttrOrder("a3", -10)
        names = [plug.getLongName() for plug in node.getPlugs(userDefined=True, includeChildren=False)]
        self.assertEqual(names, ["a3", "a1", "a2"])


class RemovedNamesTest(_SpecCase):
    """廃止した名前は Node・Nodes のどちらにも無い。"""

    def test_removed_from_node_class(self):
        for name in REMOVED_NODE_METHODS:
            with self.subTest(name=name):
                self.assertFalse(hasattr(Node, name))
                self.assertFalse(hasattr(Nodes, name))

    def test_removed_from_instances(self):
        """インスタンスの __getattr__ もアトリビュート検索へ落ちて AttributeError。"""
        node = Node(self.make("transform", "plain"))
        for name in REMOVED_NODE_METHODS:
            with self.subTest(name=name):
                with self.assertRaises(AttributeError):
                    getattr(node, name)

    def test_get_connections_has_no_pcls(self):
        """getConnections に pcls は無い。"""
        node = Node(self.make("transform", "conn"))
        with self.assertRaises(TypeError):
            node.getConnections(pcls=Plug, skipConversionNodes=True)
        self.assertNotIn("pcls", Node.getConnections.__code__.co_varnames)


if __name__ == "__main__":
    unittest.main(verbosity=2)
