"""形状とTransformからのスキニング関係照会を実Mayaで検証する。"""

import sys
import unittest
import uuid

import hlib
import maya.cmds as cmds

hlib.reload()


class GeometrySkinQueriesTest(unittest.TestCase):
    def setUp(self):
        self.ns = "geometrySkin_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.joint = cmds.createNode("joint", name=self.ns + ":joint")

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def bind(self, geometry):
        skin = hlib.getNode(cmds.skinCluster(self.joint, geometry, toSelectedBones=True,
                                           name=self.ns + ":skin")[0])
        pose = skin.getBindPose()
        if not pose.getFullName().startswith(self.ns + ":"):
            cmds.rename(pose.getFullName(), self.ns + ":pose")
        return skin

    def cube(self):
        return hlib.getNode(cmds.polyCube(name=self.ns + ":mesh")[0])

    def test_mesh_curve_surface_and_no_undo_entry(self):
        geometries = [self.cube(),
                      hlib.getNode(cmds.curve(name=self.ns + ":curve", degree=1,
                                             point=[(0, 0, 0), (0, 1, 0), (1, 2, 0)])),
                      hlib.getNode(cmds.nurbsPlane(name=self.ns + ":surface")[0])]
        for geometry in geometries:
            with self.subTest(geometry=geometry.getFullName()):
                self.assertEqual(geometry.getSkinClusters(), [])
                self.assertEqual(geometry.getBindPoses(), [])
                skin = self.bind(geometry.getFullName())
                shape = geometry.getShape()
                undo_name = cmds.undoInfo(query=True, undoName=True)
                selected = cmds.ls(selection=True, long=True)
                self.assertEqual(geometry.getSkinClusters(), [skin])
                self.assertEqual(shape.getSkinClusters(), [skin])
                self.assertEqual(shape.getBindPoses(), [skin.getBindPose()])
                self.assertEqual(geometry.getBindPoses(), [skin.getBindPose()])
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
                self.assertEqual(cmds.ls(selection=True, long=True), selected)

    def test_multiple_shapes_shared_pose_and_missing_pose(self):
        first, second = self.cube(), self.cube()
        skin_a, skin_b = self.bind(first.getFullName()), self.bind(second.getFullName())
        shape_b = second.getShape()
        cmds.parent(shape_b.getFullName(), first.getFullName(), shape=True, relative=True)
        pose = skin_a.getBindPose()
        if skin_b.getBindPose() != pose:
            cmds.connectAttr(pose.getFullName() + ".message", skin_b.getFullName() + ".bindPose", force=True)
        self.assertEqual(first.getSkinClusters(), [skin_a, skin_b])
        self.assertEqual(first.getBindPoses(), [pose])
        for skin in (skin_a, skin_b):
            cmds.disconnectAttr(pose.getFullName() + ".message", skin.getFullName() + ".bindPose")
        self.assertEqual(first.getBindPoses(), [])
        self.assertEqual(second.getSkinClusters(), [])

    def test_excludes_blendshape_target_history(self):
        base, target = self.cube(), self.cube()
        base_skin, target_skin = self.bind(base.getFullName()), self.bind(target.getFullName())
        cmds.blendShape(target.getFullName(), base.getFullName(), name=self.ns + ":blend", after=True)
        self.assertIn(target_skin, base.getHistory(type="skinCluster"))
        self.assertEqual(base.getSkinClusters(), [base_skin])
        self.assertEqual(base.getBindPoses(), [base_skin.getBindPose()])

    def test_non_geometry_and_direct_children_only(self):
        group = hlib.getNode(cmds.createNode("transform", name=self.ns + ":group"))
        geometry = self.cube()
        self.bind(geometry.getFullName())
        cmds.parent(geometry.getFullName(), group.getFullName())
        self.assertEqual(group.getSkinClusters(), [])
        self.assertEqual(group.getBindPoses(), [])
        camera = hlib.getNode(cmds.camera(name=self.ns + ":camera")[0])
        self.assertEqual(camera.getSkinClusters(), [])
        self.assertEqual(camera.getShape().getBindPoses(), [])

    def test_multiple_skin_deformers_in_chain(self):
        geometry = self.cube()
        first = self.bind(geometry.getFullName())
        # バージョン固有の複数バインドフラグに依存せず、標準deformerで直列接続。
        second = hlib.getNode(cmds.deformer(geometry.getFullName(), type="skinCluster",
                                           name=self.ns + ":secondSkin")[0])
        self.assertEqual(geometry.getSkinClusters(), [second, first])
        self.assertEqual(geometry.getBindPoses(), [first.getBindPose()])

    def test_intermediates_instances_and_joint_compatibility(self):
        geometry = self.cube()
        skin = self.bind(geometry.getFullName())
        original = [s for s in geometry.getShapes(intermediates=True)
                    if cmds.getAttr(s.getFullName() + ".intermediateObject")][0]
        self.assertEqual(original.getSkinClusters(), [])
        instance = hlib.getNode(cmds.instance(geometry.getFullName(), name=self.ns + ":instance")[0])
        self.assertEqual(instance.getSkinClusters(), [skin])
        self.assertEqual(instance.getShape().getSkinClusters(), [skin])
        self.assertEqual(hlib.getNode(self.joint).getSkinClusters(), [skin])
        self.assertEqual(hlib.getNode(self.joint).getBindPoses(), [skin.getBindPose()])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
