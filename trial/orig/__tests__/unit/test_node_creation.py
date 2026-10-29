"""mlib のノード作成APIを検証するMaya内テスト。"""

import sys
import unittest
import importlib

import maya.cmds as cmds

import mlib

mlib.reload()
mlib_cmds = importlib.import_module("mlib.cmds")
from mlib.nodes import Node, Transform
from mlib.nodes.joint import Joint, Joints
from mlib.nodes.skinCluster import SkinClusters


class NodeCreationTest(unittest.TestCase):
    """mlib.createNode と mlib.cmds.createNode の基本動作を検証する。"""

    def setUp(self):
        self.previous_namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        cmds.namespace(set=":")

    def tearDown(self):
        for name in ("mlibCreateJoint", "mlibCreateTransform"):
            if cmds.objExists(name):
                cmds.delete(name)
        cmds.namespace(set=self.previous_namespace)

    def test_create_node_returns_registered_wrapper(self):
        joint = mlib_cmds.createNode(type="joint", name="mlibCreateJoint")

        self.assertIsInstance(joint, Joint)
        self.assertEqual(joint.getName(), "mlibCreateJoint")
        self.assertEqual(joint.getType(), "joint")

    def test_cmds_package_reexports_node_commands(self):
        self.assertTrue(callable(mlib_cmds.createNode))
        self.assertTrue(callable(mlib_cmds.ls))
        self.assertIs(mlib.createNode, mlib_cmds.createNode)
        self.assertIs(mlib.ls, mlib_cmds.ls)
        transform = mlib_cmds.createNode(type="transform", name="mlibCreateTransform")

        self.assertIsInstance(transform, Node)
        self.assertEqual(transform.getName(), "mlibCreateTransform")

    def test_root_create_node_forwards_create_node_flags(self):
        transform = mlib.createNode(type="transform", name="mlibCreateTransform")

        self.assertIsInstance(transform, Node)
        self.assertEqual(transform.getName(), "mlibCreateTransform")
        self.assertEqual(transform.getType(), "transform")

    def test_create_node_rejects_invalid_node_type(self):
        with self.assertRaises(ValueError):
            mlib_cmds.createNode(type="")

    def test_node_resolves_unregistered_derived_type_via_inheritance(self):
        # airField はmlibが個別登録していない組み込みノードタイプだが、Mayaの
        # 継承チェーン上は transform の派生であるため、Transform で解決される。
        name = cmds.createNode("airField", name="mlibCreateAirField")
        try:
            wrapped = mlib.getNode(name)
            self.assertIsInstance(wrapped, Transform)
        finally:
            cmds.delete(name)

    def test_node_wraps_existing_nodes_without_scene_changes(self):
        name = cmds.createNode("joint", name="mlibCreateJoint")
        before = cmds.ls(long=True)
        selection = cmds.ls(sl=True, long=True)
        self.assertIs(mlib.getNode, mlib_cmds.getNode)
        wrapped = mlib.getNode(name)
        self.assertIsInstance(wrapped, Joint)
        for value in (wrapped.mnode(), wrapped.mpath()):
            self.assertIsInstance(mlib.getNode(value), Joint)
        self.assertEqual(cmds.ls(long=True), before)
        self.assertEqual(cmds.ls(sl=True, long=True), selection)
        with self.assertRaises(RuntimeError):
            mlib.getNode("__mlib_missing_node_for_test__")
        with self.assertRaises(TypeError):
            mlib.getNode(None)


class SceneEditingCommandsTest(unittest.TestCase):
    """mlibの削除・複製・グループ化とmaya.cmdsの存在照会を検証する。"""

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
        node = mlib_cmds.createNode("transform", name=name)
        self.created.append(node.getName())
        return node

    def test_ls_returns_wrapped_nodes_and_type_specific_collections(self):
        a = self.create_transform("mlibLsTransformA")
        b = self.create_transform("mlibLsTransformB")

        result = mlib_cmds.ls(type="transform")
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(item, Node) for item in result))
        self.assertIn(a.getName(), [item.getName() for item in result])
        self.assertIn(b.getName(), [item.getName() for item in result])

        cmds.select([a.getName(), b.getName()], replace=True)
        selected = mlib_cmds.ls(selection=True)
        self.assertEqual({item.getName() for item in selected}, {a.getName(), b.getName()})
        cmds.select(clear=True)

        joint_name = cmds.createNode("joint", name="mlibLsJoint")
        self.created.append(joint_name)
        joints_result = mlib_cmds.ls(type="joint")
        self.assertIsInstance(joints_result, Joints)
        self.assertIn(joint_name, [item.getName() for item in joints_result])

        mesh_transform = cmds.polyCube(name="mlibLsSkinMesh", constructionHistory=False)[0]
        self.created.append(mesh_transform)
        skin_name = cmds.skinCluster(joint_name, mesh_transform)[0]
        self.created.append(skin_name)
        skin_result = mlib_cmds.ls(type="skinCluster")
        self.assertIsInstance(skin_result, SkinClusters)
        self.assertIn(skin_name, [item.getName() for item in skin_result])

    def test_obj_exists_reflects_scene_state(self):
        self.assertTrue(cmds.objExists("persp"))
        self.assertFalse(cmds.objExists("mlibObjExistsMissing"))
        node = self.create_transform("mlibObjExistsPresent")
        self.assertTrue(cmds.objExists(node))
        self.assertTrue(cmds.objExists(node.getName()))

    def test_delete_removes_single_and_multiple_nodes(self):
        a = self.create_transform("mlibDeleteA")
        b = self.create_transform("mlibDeleteB")
        mlib_cmds.delete(a)
        self.assertFalse(cmds.objExists("mlibDeleteA"))
        mlib_cmds.delete([b.getName()])
        self.assertFalse(cmds.objExists("mlibDeleteB"))
        with self.assertRaises(ValueError):
            mlib_cmds.delete([])

    def test_duplicate_returns_wrapped_copy(self):
        original = self.create_transform("mlibDuplicateSource")
        copy = mlib_cmds.duplicate(original, name="mlibDuplicateCopy")
        self.created.append(copy.getName())

        self.assertIsInstance(copy, Node)
        self.assertNotEqual(copy.getFullName(), original.getFullName())
        self.assertTrue(cmds.objExists("mlibDuplicateCopy"))



class SelectionAndAnimationCommandsTest(unittest.TestCase):
    """mlibの選択とmaya.cmdsの時刻・キー・ベイク操作を検証する。"""

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
        node = mlib_cmds.createNode("transform", name=name)
        self.created.append(node.getName())
        return node

    def test_select_sets_and_clears_selection(self):
        a = self.create_transform("mlibSelectA")
        b = self.create_transform("mlibSelectB")

        mlib_cmds.select([a, b])
        self.assertEqual(set(cmds.ls(sl=True)), {"mlibSelectA", "mlibSelectB"})

        mlib_cmds.select(a.getName())
        self.assertEqual(cmds.ls(sl=True), ["mlibSelectA"])

        mlib_cmds.select(clear=True)
        self.assertEqual(cmds.ls(sl=True), [])

    def test_current_time_query_and_set_round_trip(self):
        result = cmds.currentTime(10)
        self.assertEqual(result, 10.0)
        self.assertEqual(cmds.currentTime(query=True), 10.0)

    def test_set_keyframe_on_plug_and_query_via_cmds(self):
        node = self.create_transform("mlibSetKeyframe")

        cmds.currentTime(1)
        cmds.setKeyframe(node.getPlug("translateX"), value=0.0)
        cmds.currentTime(24)
        cmds.setKeyframe(node.getPlug("translateX"), value=10.0)

        times = cmds.keyframe(node.getFullName(), attribute="translateX", query=True, timeChange=True)
        self.assertEqual(sorted(times), [1.0, 24.0])

    def test_bake_results_creates_keys_across_range(self):
        node = self.create_transform("mlibBakeResults")
        cmds.currentTime(1)
        cmds.setKeyframe(node.getPlug("translateX"), value=0.0)
        cmds.currentTime(10)
        cmds.setKeyframe(node.getPlug("translateX"), value=9.0)

        cmds.bakeResults(node.getFullName(), time=(1, 10), attribute=["translateX"], simulation=True)

        times = cmds.keyframe(node.getFullName(), attribute="translateX", query=True, timeChange=True)
        self.assertEqual(len(times), 10)
        self.assertEqual(sorted(times), [float(t) for t in range(1, 11)])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
