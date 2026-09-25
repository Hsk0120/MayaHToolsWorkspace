"""hlib のノード作成APIを検証するMaya内テスト。"""

import sys
import unittest
import importlib

import maya.cmds as cmds

import hlib
hlib.reload()
hlib_cmds = importlib.import_module("hlib.cmds")
from hlib.nodes import Node, Transform
from hlib.nodes.joint import Joint, Joints
from hlib.nodes.skinCluster import SkinClusters


class NodeCreationTest(unittest.TestCase):
    """Node.create と hlib.cmds.createNode の基本動作を検証する。"""

    def setUp(self):
        self.previous_namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        cmds.namespace(set=":")

    def tearDown(self):
        for name in ("hlibCreateJoint", "hlibCreateTransform"):
            if cmds.objExists(name):
                cmds.delete(name)
        cmds.namespace(set=self.previous_namespace)

    def test_create_node_returns_registered_wrapper(self):
        joint = hlib_cmds.createNode(type="joint", name="hlibCreateJoint")

        self.assertIsInstance(joint, Joint)
        self.assertEqual(joint.name(), "hlibCreateJoint")
        self.assertEqual(joint.type(), "joint")

    def test_cmds_package_reexports_node_commands(self):
        self.assertTrue(callable(hlib_cmds.createNode))
        self.assertTrue(callable(hlib_cmds.ls))
        self.assertIs(hlib.createNode, hlib_cmds.createNode)
        self.assertIs(hlib.ls, hlib_cmds.ls)
        transform = hlib_cmds.createNode(type="transform", name="hlibCreateTransform")

        self.assertIsInstance(transform, Node)
        self.assertEqual(transform.name(), "hlibCreateTransform")

    def test_node_create_forwards_create_node_flags(self):
        transform = Node.create(type="transform", name="hlibCreateTransform")

        self.assertIsInstance(transform, Node)
        self.assertEqual(transform.name(), "hlibCreateTransform")
        self.assertEqual(transform.type(), "transform")

    def test_create_node_rejects_invalid_node_type(self):
        with self.assertRaises(ValueError):
            hlib_cmds.createNode(type="")


    def test_node_resolves_unregistered_derived_type_via_inheritance(self):
        # airField はhlibが個別登録していない組み込みノードタイプだが、Mayaの
        # 継承チェーン上は transform の派生であるため、Transform で解決される。
        name = cmds.createNode("airField", name="hlibCreateAirField")
        try:
            wrapped = hlib.node(name)
            self.assertIsInstance(wrapped, Transform)
        finally:
            cmds.delete(name)

    def test_node_wraps_existing_nodes_without_scene_changes(self):
        name = cmds.createNode("joint", name="hlibCreateJoint")
        before = cmds.ls(long=True)
        selection = cmds.ls(sl=True, long=True)
        self.assertIs(hlib.node, hlib_cmds.node)
        wrapped = hlib.node(name)
        self.assertIsInstance(wrapped, Joint)
        for value in (wrapped.mobject(), wrapped.dag_path()):
            self.assertIsInstance(hlib.node(value), Joint)
        self.assertEqual(cmds.ls(long=True), before)
        self.assertEqual(cmds.ls(sl=True, long=True), selection)
        with self.assertRaises(RuntimeError):
            hlib.node("__hlib_missing_node_for_test__")
        with self.assertRaises(TypeError):
            hlib.node(None)


class SceneEditingCommandsTest(unittest.TestCase):
    """hlib.cmds.delete/duplicate/group/objExists の基本動作を検証する。"""

    def setUp(self):
        self.previous_namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        cmds.namespace(set=":")
        self.created = []

    def tearDown(self):
        for name in reversed(self.created):
            if cmds.objExists(name):
                cmds.delete(name)
        cmds.namespace(set=self.previous_namespace)

    def create_transform(self, name):
        node = hlib_cmds.createNode("transform", name=name)
        self.created.append(node.name())
        return node

    def test_ls_returns_wrapped_nodes_and_type_specific_collections(self):
        a = self.create_transform("hlibLsTransformA")
        b = self.create_transform("hlibLsTransformB")

        result = hlib_cmds.ls(type="transform")
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(item, Node) for item in result))
        self.assertIn(a.name(), [item.name() for item in result])
        self.assertIn(b.name(), [item.name() for item in result])

        cmds.select([a.name(), b.name()], replace=True)
        selected = hlib_cmds.ls(selection=True)
        self.assertEqual({item.name() for item in selected}, {a.name(), b.name()})
        cmds.select(clear=True)

        joint_name = cmds.createNode("joint", name="hlibLsJoint")
        self.created.append(joint_name)
        joints_result = hlib_cmds.ls(type="joint")
        self.assertIsInstance(joints_result, Joints)
        self.assertIn(joint_name, [item.name() for item in joints_result])

        mesh_transform = cmds.polyCube(name="hlibLsSkinMesh", constructionHistory=False)[0]
        self.created.append(mesh_transform)
        skin_name = cmds.skinCluster(joint_name, mesh_transform)[0]
        self.created.append(skin_name)
        skin_result = hlib_cmds.ls(type="skinCluster")
        self.assertIsInstance(skin_result, SkinClusters)
        self.assertIn(skin_name, [item.name() for item in skin_result])

    def test_obj_exists_reflects_scene_state(self):
        self.assertTrue(hlib_cmds.objExists("persp"))
        self.assertFalse(hlib_cmds.objExists("hlibObjExistsMissing"))
        node = self.create_transform("hlibObjExistsPresent")
        self.assertTrue(hlib_cmds.objExists(node))
        self.assertTrue(hlib_cmds.objExists(node.name()))

    def test_delete_removes_single_and_multiple_nodes(self):
        a = self.create_transform("hlibDeleteA")
        b = self.create_transform("hlibDeleteB")
        hlib_cmds.delete(a)
        self.assertFalse(cmds.objExists("hlibDeleteA"))
        hlib_cmds.delete([b.name()])
        self.assertFalse(cmds.objExists("hlibDeleteB"))
        with self.assertRaises(ValueError):
            hlib_cmds.delete([])

    def test_duplicate_returns_wrapped_copy(self):
        original = self.create_transform("hlibDuplicateSource")
        copy = hlib_cmds.duplicate(original, name="hlibDuplicateCopy")
        self.created.append(copy.name())

        self.assertIsInstance(copy, Node)
        self.assertNotEqual(copy.full_name(), original.full_name())
        self.assertTrue(cmds.objExists("hlibDuplicateCopy"))

    def test_group_wraps_given_nodes_and_supports_empty_group(self):
        a = self.create_transform("hlibGroupA")
        b = self.create_transform("hlibGroupB")
        grp = hlib_cmds.group([a, b], name="hlibGroupParent", world=True)
        self.created.append(grp.name())

        self.assertIsInstance(grp, Node)
        self.assertEqual(cmds.listRelatives(grp.name(), children=True), ["hlibGroupA", "hlibGroupB"])

        empty = hlib_cmds.group(name="hlibGroupEmpty", world=True, empty=True)
        self.created.append(empty.name())
        self.assertEqual(cmds.listRelatives(empty.name(), children=True), None)

        cmds.select(clear=True)
        with self.assertRaises(RuntimeError):
            hlib_cmds.group(name="hlibGroupShouldFail", world=True)


class SelectionAndAnimationCommandsTest(unittest.TestCase):
    """hlib.cmds.select/currentTime/setKeyframe/bakeResults の基本動作を検証する。"""

    def setUp(self):
        self.previous_namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        cmds.namespace(set=":")
        self.previous_time = cmds.currentTime(query=True)
        self.created = []

    def tearDown(self):
        cmds.currentTime(self.previous_time)
        cmds.select(clear=True)
        for name in reversed(self.created):
            if cmds.objExists(name):
                cmds.delete(name)
        cmds.namespace(set=self.previous_namespace)

    def create_transform(self, name):
        node = hlib_cmds.createNode("transform", name=name)
        self.created.append(node.name())
        return node

    def test_select_sets_and_clears_selection(self):
        a = self.create_transform("hlibSelectA")
        b = self.create_transform("hlibSelectB")

        hlib_cmds.select([a, b])
        self.assertEqual(set(cmds.ls(sl=True)), {"hlibSelectA", "hlibSelectB"})

        hlib_cmds.select(a.name())
        self.assertEqual(cmds.ls(sl=True), ["hlibSelectA"])

        hlib_cmds.select(clear=True)
        self.assertEqual(cmds.ls(sl=True), [])

    def test_current_time_query_and_set_round_trip(self):
        result = hlib_cmds.currentTime(10)
        self.assertEqual(result, 10.0)
        self.assertEqual(hlib_cmds.currentTime(), 10.0)

    def test_set_keyframe_on_plug_and_query_via_cmds(self):
        node = self.create_transform("hlibSetKeyframe")

        hlib_cmds.currentTime(1)
        hlib_cmds.setKeyframe(node.attr("translateX"), value=0.0)
        hlib_cmds.currentTime(24)
        hlib_cmds.setKeyframe(node.attr("translateX"), value=10.0)

        times = cmds.keyframe(node.full_name(), attribute="translateX", query=True, timeChange=True)
        self.assertEqual(sorted(times), [1.0, 24.0])

    def test_bake_results_creates_keys_across_range(self):
        node = self.create_transform("hlibBakeResults")
        hlib_cmds.currentTime(1)
        hlib_cmds.setKeyframe(node.attr("translateX"), value=0.0)
        hlib_cmds.currentTime(10)
        hlib_cmds.setKeyframe(node.attr("translateX"), value=9.0)

        hlib_cmds.bakeResults(node, time=(1, 10), attribute=["translateX"], simulation=True)

        times = cmds.keyframe(node.full_name(), attribute="translateX", query=True, timeChange=True)
        self.assertEqual(len(times), 10)
        self.assertEqual(sorted(times), [float(t) for t in range(1, 11)])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])