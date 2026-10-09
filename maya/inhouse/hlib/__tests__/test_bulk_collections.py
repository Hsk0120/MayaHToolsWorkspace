"""同種コレクションの一括API、要素別引数、失敗とUndoを検証する。"""
import inspect
import sys
import unittest
import uuid
from unittest.mock import patch
import maya.cmds as cmds
import hlib

hlib.reload()


class BulkCollectionsTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibBulk_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.names = [cmds.createNode("joint", name=self.ns + ":j" + str(i)) for i in range(2)]
        self.joints = hlib.nodes.Joints(self.names)

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_common_and_per_item_transform_undo(self):
        self.joints.setTranslate((1, 2, 3), at=4)
        self.assertEqual([tuple(p) for p in self.joints.getTranslate(at=4)], [(1, 2, 3)] * 2)
        cmds.undo()
        self.assertEqual([tuple(p) for p in self.joints.getTranslate(at=4)], [(0, 0, 0)] * 2)
        cmds.redo()
        self.assertEqual([tuple(p) for p in self.joints.getTranslate(at=4)], [(1, 2, 3)] * 2)
        self.joints.callEach("setTranslate", [((4, 5, 6),), ((7, 8, 9),)])
        self.assertEqual([tuple(p) for p in self.joints.getTranslate(at=4)], [(4, 5, 6), (7, 8, 9)])
        self.assertEqual(self.joints.isJoint(), [True, True])
        self.assertEqual(self.joints.getFullName(), [item.getFullName() for item in self.joints])
        self.assertEqual(self.joints[:1].getNames(), self.names[:1])
        self.assertEqual(len(self.joints), 2)
        self.assertFalse(hasattr(self.joints, "create"))
        self.assertEqual(hlib.nodes.Joints().getTranslate(at=4), [])

    def test_argument_validation_and_failure_context(self):
        with self.assertRaises(ValueError):
            self.joints.callEach("setTranslate", [((1, 2, 3),)])
        with self.assertRaises(TypeError):
            self.joints.callEach("setTranslate", [((1, 2, 3),), ()])
        self.assertEqual([tuple(p) for p in self.joints.getTranslate(at=4)], [(0, 0, 0)] * 2)
        cmds.setAttr(self.names[1] + ".translateX", lock=True)
        try:
            with self.assertRaisesRegex(RuntimeError, "setTranslate failed at item 1"):
                self.joints.setTranslate((5, 0, 0), at=4)
            self.assertEqual(cmds.getAttr(self.names[0] + ".translateX"), 5)
            cmds.undo()
            self.assertEqual(cmds.getAttr(self.names[0] + ".translateX"), 0)
        finally:
            cmds.setAttr(self.names[1] + ".translateX", lock=False)

    def test_explicit_entries_preserve_raw_arguments_and_empty_calls(self):
        """明示した入口でも引数の省略・別名・利用側overrideを維持する。"""
        captured = []

        class CustomJoints(hlib.nodes.Joints):
            """要素別入口を拡張する利用側コレクション。"""

            def callEach(self, method, arguments, keyword_arguments=None):
                """既定値を補わず元の指定を受け取る。"""
                captured.append((method, arguments, keyword_arguments))
                return self

        joints = CustomJoints(self.names)
        self.assertIs(joints.setTranslate((1, 2, 3), ws=True), joints)
        self.assertEqual(captured, [("setTranslate", [((1, 2, 3),)] * 2,
                                     [{"ws": True}] * 2)])
        self.assertIs(joints.translate(ws=True), joints)
        self.assertEqual(captured[-1], ("getTranslate", [()] * 2, [{"ws": True}] * 2))
        self.assertEqual(inspect.signature(hlib.nodes.Transforms.setTranslate),
                         inspect.signature(hlib.nodes.Transform.setTranslate))
        empty = hlib.nodes.Transforms()
        self.assertIs(empty.setTranslate(), empty)
        self.assertEqual(empty.getTranslate(unknown=True), [])
        self.assertEqual(empty.translate(unknown=True), [])

    def test_skin_methods_and_file_operations_are_explicit(self):
        meshes = [cmds.polyCube(name=self.ns + ":mesh")[0] for _ in range(2)]
        skins = hlib.nodes.SkinClusters([cmds.skinCluster(self.names, mesh, toSelectedBones=True)[0] for mesh in meshes])
        self.assertEqual(len(skins.getInfluences()), 2)
        self.assertEqual(skins.hasInfluence(self.names[0]), [True, True])
        for skin, mesh in zip(skins, meshes):
            cmds.skinPercent(skin.getFullName(), mesh, transformValue=[(self.names[0], 0.75), (self.names[1], 0.25)])
        skins.transferWeights([(self.names[0], self.names[1])])
        for skin, mesh in zip(skins, meshes):
            self.assertAlmostEqual(cmds.skinPercent(skin.getFullName(), mesh + ".vtx[0]", query=True, transform=self.names[1]), 1)
        cmds.undo()
        for skin, mesh in zip(skins, meshes):
            self.assertAlmostEqual(cmds.skinPercent(skin.getFullName(), mesh + ".vtx[0]", query=True, transform=self.names[0]), 0.75)
        self.assertFalse(hasattr(skins, "dumpWeights"))
        self.assertIn("dumpWeights", skins._bulk_methods)
        self.assertEqual(len(skins[:1]), 1)
        self.assertTrue(callable(skins.removeInfluences))

    def test_registration_coverage(self):
        for collection, single in ((hlib.nodes.Nodes(), hlib.nodes.Node),
                                   (hlib.nodes.DagNodes(), hlib.nodes.DagNode),
                                   (hlib.nodes.Transforms(), hlib.nodes.Transform),
                                   (self.joints, hlib.nodes.Joint),
                                   (hlib.nodes.SkinClusters(), hlib.nodes.SkinCluster)):
            for name in dir(single):
                if not name.startswith("_") and inspect.isfunction(inspect.getattr_static(single, name)):
                    with self.subTest(collection=type(collection).__name__, method=name):
                        self.assertIn(name, collection._bulk_methods)

    def test_management_tables_and_explicit_entries_are_consistent(self):
        """分類・許可表だけの登録や、直接入口の追加忘れを検出する。"""
        for collection in (hlib.nodes.Nodes(), hlib.nodes.DagNodes(),
                           hlib.nodes.Transforms(), self.joints, hlib.nodes.SkinClusters()):
            collection_class = type(collection)
            registered = set(collection._bulk_methods)
            restricted = collection._bulk_per_item_only
            with self.subTest(collection=collection_class.__name__):
                self.assertEqual(registered, set(collection._bulk_returns))
                self.assertLessEqual(restricted, registered)
            for name, function in collection._bulk_methods.items():
                with self.subTest(collection=collection_class.__name__, method=name):
                    self.assertFalse(name.startswith("_"))
                    self.assertTrue(inspect.isfunction(function))
                    self.assertEqual(function.__name__, name)
                    self.assertTrue(inspect.isfunction(inspect.getattr_static(collection.item_class, name)))
                    if name in restricted:
                        self.assertFalse(hasattr(collection_class, name))
                        self.assertFalse(hasattr(collection, name))
                    else:
                        self.assertTrue(callable(getattr(collection_class, name, None)))
                        self.assertTrue(callable(getattr(collection, name, None)))
                    if name.startswith("get") and len(name) > 3 and name[3].isupper():
                        alias = name[3].lower() + name[4:]
                        self.assertIn(alias, registered)
                        self.assertEqual(collection._bulk_returns[alias], collection._bulk_returns[name])
                        self.assertEqual(collection._bulk_methods[alias].__hlib_getter_name__, name)
                        if name in restricted:
                            self.assertIn(alias, restricted)
                        else:
                            self.assertEqual(inspect.signature(getattr(collection_class, alias)),
                                             inspect.signature(getattr(collection_class, name)))

    def test_file_methods_stay_hidden_when_base_defines_an_entry(self):
        """基底への入口追加でも禁止を継承し、callEachのみ許可する。"""
        class DerivedSkinClusters(hlib.nodes.SkinClusters):
            """要素別指定の禁止設定を継承する利用側コレクション。"""

        class Item:
            """ファイル操作を行わず転送した引数を確認する単数型。"""

            def dumpWeights(self, path):
                """受け取った保存先を返す。"""
                return path

            def loadWeights(self, path):
                """受け取った読み込み先を返す。"""
                return path

        with patch.object(hlib.nodes.Nodes, "dumpWeights", lambda *_: "base", create=True), \
                patch.object(hlib.nodes.Nodes, "loadWeights", lambda *_: "base", create=True):
            for collection_class in (hlib.nodes.SkinClusters, DerivedSkinClusters):
                collection = collection_class()
                collection._items = [Item()]
                for name in ("dumpWeights", "loadWeights"):
                    self.assertFalse(hasattr(collection_class, name))
                    self.assertFalse(hasattr(collection, name))
                self.assertEqual(collection.callEach("dumpWeights", [("saved.json",)]), ["saved.json"])
                self.assertIs(collection.callEach("loadWeights", [("saved.json",)]), collection)

    def test_geometry_and_joint_bind_pose_queries_preserve_order(self):
        """継承した関係照会は対象順の結果を返し、既存の集約照会も維持する。"""
        meshes = [cmds.polyCube(name=self.ns + ":mesh" + str(i))[0] for i in range(2)]
        skins = [hlib.getNode(cmds.skinCluster(self.names, mesh, toSelectedBones=True,
                                             name=self.ns + ":skin" + str(index))[0])
                 for index, mesh in enumerate(meshes)]
        for skin in skins:
            pose = skin.getBindPose()
            if not pose.getFullName().startswith(self.ns + ":"):
                cmds.rename(pose.getFullName(), self.ns + ":pose")
        empty = cmds.createNode("transform", name=self.ns + ":empty")
        transforms = hlib.nodes.Transforms([meshes[0], empty, meshes[1]])
        shapes = hlib.nodes.DagNodes([hlib.getNode(mesh).getShape() for mesh in meshes])
        undo_name = cmds.undoInfo(query=True, undoName=True)
        self.assertEqual(transforms.getSkinClusters(), [[skins[0]], [], [skins[1]]])
        self.assertEqual(transforms.getBindPoses(), [[skins[0].getBindPose()], [], [skins[1].getBindPose()]])
        self.assertEqual(shapes.getSkinClusters(), [[skin] for skin in skins])
        self.assertEqual(shapes.getBindPoses(), [[skin.getBindPose()] for skin in skins])
        self.assertEqual(self.joints.getBindPoses(), [joint.getBindPoses() for joint in self.joints])
        aggregated = self.joints.getSkinClusters()
        self.assertIsInstance(aggregated, hlib.nodes.SkinClusters)
        self.assertCountEqual(aggregated, skins)
        self.assertIsInstance(self.joints.skinClusters(), hlib.nodes.SkinClusters)
        self.assertCountEqual(self.joints.skinClusters(), skins)
        self.assertEqual(transforms.skinClusters(), transforms.getSkinClusters())
        self.assertEqual(self.joints.callEach("skinClusters", [()] * len(self.joints)),
                         [joint.getSkinClusters() for joint in self.joints])
        self.assertEqual(self.joints.names(), self.joints.getNames())
        with self.assertRaises(ValueError):
            self.joints.callEach("names", [()] * len(self.joints))
        self.assertIs(transforms.transform(), transforms)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        self.assertEqual(hlib.nodes.DagNodes().getBindPoses(), [])

    def test_inherited_intermediate_shape_cleanup_is_one_undo(self):
        """Jointへ継承した削除は全対象を一回でUndo/Redoし、親と通常Shapeを残す。"""
        unused, visible = [], []
        for index, name in enumerate(self.names):
            intermediate = cmds.createNode("mesh", parent=name,
                                           name=self.ns + ":unused" + str(index))
            cmds.setAttr(intermediate + ".intermediateObject", True)
            unused.append(hlib.getNode(intermediate))
            visible.append(cmds.createNode("mesh", parent=name,
                                           name=self.ns + ":visible" + str(index)))
        names = [shape.getFullName() for shape in unused]
        self.assertEqual(self.joints.getUnusedIntermediateShapes(), [[shape] for shape in unused])
        self.assertIs(self.joints.deleteUnusedIntermediateShapes(), self.joints)
        self.assertTrue(all(not cmds.objExists(name) for name in names))
        self.assertTrue(all(cmds.objExists(name) for name in self.names + visible))
        cmds.undo()
        self.assertTrue(all(cmds.objExists(name) for name in names))
        cmds.redo()
        self.assertTrue(all(not cmds.objExists(name) for name in names))
        empty = hlib.nodes.Transforms()
        self.assertEqual(empty.getUnusedIntermediateShapes(), [])
        self.assertIs(empty.deleteUnusedIntermediateShapes(), empty)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
