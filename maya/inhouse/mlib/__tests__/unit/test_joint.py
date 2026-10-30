"""mlib.nodes.joint の Joint ラッパーを検証するMaya内テスト。"""
from maya.api.OpenMaya import MSpace

import math
import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.maths import EulerRotate, Scale
from mlib.nodes import Node
from mlib.nodes.joint import Joint


class JointTest(unittest.TestCase):
    """joint_orient/inverse_scale の単位変換、階層クエリ、skinCluster/IK連携を検証する。"""

    namespace = ":mlibJointTest"

    def setUp(self):
        self.created = []
        if cmds.namespace(exists=self.namespace):
            cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.namespace(add=self.namespace)

    def tearDown(self):
        for node in reversed(self.created):
            if cmds.objExists(node):
                cmds.delete(node)
        if cmds.namespace(exists=self.namespace):
            cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def create_joint(self, name, parent=None):
        cmds.select(clear=True)
        joint_name = cmds.joint(name=self.namespace + ":" + name)
        if parent is not None:
            cmds.parent(joint_name, parent.getFullName())
        self.created.append(joint_name)
        return Joint(joint_name)

    def test_segment_scale_compensate_and_undo(self):
        parent = self.create_joint("sscParent")
        child = self.create_joint("sscChild", parent)
        joints = [parent, child]

        def values():
            return [joint.getSegmentScaleCompensate() for joint in joints]

        self.assertEqual(values(), [True, True])
        for joint in joints:
            self.assertIs(joint.setSegmentScaleCompensate(False), joint)
        self.assertEqual(values(), [False, False])
        cmds.undo()
        self.assertEqual(values(), [False, True])
        cmds.undo()
        self.assertEqual(values(), [True, True])
        cmds.redo()
        cmds.redo()
        self.assertEqual(values(), [False, False])
        self.assertIs(child.setSegmentScaleCompensate(True, fast=True), child)
        self.assertTrue(child.getSegmentScaleCompensate())
        with self.assertRaises(TypeError):
            child.setSegmentScaleCompensate(1)

    def test_inverse_scale_connect_disconnect(self):
        parent = self.create_joint("connectParent")
        child = self.create_joint("connectChild", parent)
        for joint in (parent, child):
            joint.disconnectInverseScale()
        self.assertIsNone(child.getPlug('inverseScale').getSource(skipConversionNodes=False))
        for joint in (parent, child):
            joint.connectInverseScale()
        self.assertEqual(child.getPlug('inverseScale').getSource(skipConversionNodes=False), parent.getPlug('scale'))
        cmds.undo()
        self.assertIsNone(child.getPlug('inverseScale').getSource(skipConversionNodes=False))
        child.connectInverseScale(parent.getFullName())
        child.connectInverseScale()  # 同じ接続はそのまま
        child.disconnectInverseScale()
        parent.getPlug("sx").connectTo(child.getPlug("inverseScaleX"))
        parent.getPlug("sy").connectTo(child.getPlug("inverseScaleY"))
        child.getPlug("inverseScaleZ").connectTo(parent.getPlug("radius"))
        child.disconnectInverseScale()
        self.assertIsNone(child.getPlug('inverseScaleX').getSource(skipConversionNodes=False))
        self.assertIsNone(child.getPlug('inverseScaleY').getSource(skipConversionNodes=False))
        self.assertEqual(parent.getPlug('radius').getSource(skipConversionNodes=False), child.getPlug('inverseScaleZ'))
        with self.assertRaises(ValueError):
            child.connectInverseScale(child)

    def test_joint_radius_and_undo(self):
        joints = [self.create_joint("radiusA"), self.create_joint("radiusB")]

        def radii():
            return [joint.getRadius() for joint in joints]

        before = radii()
        for joint in joints:
            self.assertIs(joint.setRadius(2.5), joint)
        self.assertEqual(radii(), [2.5, 2.5])
        cmds.undo()
        cmds.undo()
        self.assertEqual(radii(), before)
        cmds.redo()
        cmds.redo()
        self.assertEqual(radii(), [2.5, 2.5])
        joints[0].setRadius(0, fast=True)
        self.assertEqual(joints[0].getRadius(), 0)
        for value in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                joints[0].setRadius(value)

    def test_node_create_resolves_to_joint_wrapper(self):
        joint = self.create_joint("mlibJointBasic")
        self.assertIsInstance(joint, Joint)
        self.assertIsInstance(Node(joint.getFullName()), Joint)

    def test_joint_orient_returns_degrees_converted_to_radians(self):
        joint = self.create_joint("mlibJointOrient")
        cmds.setAttr(joint.getFullName() + ".jointOrientX", 90.0)
        cmds.setAttr(joint.getFullName() + ".jointOrientY", -45.0)

        orient = joint.getJointOrient()
        self.assertIsInstance(orient, EulerRotate)
        self.assertAlmostEqual(orient.x, math.radians(90.0), places=9)
        self.assertAlmostEqual(orient.y, math.radians(-45.0), places=9)
        self.assertAlmostEqual(orient.z, 0.0, places=9)

    def test_joint_orient_z_returns_radians(self):
        joint = self.create_joint("mlibJointOrientation")
        cmds.setAttr(joint.getFullName() + ".jointOrientZ", 30.0)
        self.assertAlmostEqual(joint.getJointOrient().z, math.radians(30.0))

    def test_inverse_scale_is_not_angle_converted(self):
        joint = self.create_joint("mlibJointInverseScale")
        cmds.setAttr(joint.getFullName() + ".inverseScale", 2.0, 3.0, 4.0)

        inverse_scale = joint.getInverseScale()
        self.assertIsInstance(inverse_scale, Scale)
        self.assertEqual(tuple(inverse_scale), (2.0, 3.0, 4.0))

    def test_set_rotate_preserves_joint_orient_and_rotate_axis(self):
        # jointOrient/rotateAxis は度数法のアトリビュートなので、内部で角度単位を取り違えると
        # ここで大きくズレる（asDouble() はラジアンを返すため）。setRotate は
        # rotateAxis/jointOrient を補正した上で .rotate チャンネルへ書き込むため、
        # .rotate の生値ではなく getRotate() による round-trip で検証する。
        joint = self.create_joint("mlibJointOrientPreserve")
        cmds.setAttr(joint.getFullName() + ".jointOrientX", 90.0)
        cmds.setAttr(joint.getFullName() + ".rotateAxisY", 30.0)

        joint.setRotate((0.0, 45.0, 0.0))

        self.assertAlmostEqual(cmds.getAttr(joint.getFullName() + ".jointOrientX"), 90.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(joint.getFullName() + ".rotateAxisY"), 30.0, places=6)

        rotate = joint.getRotate()
        self.assertAlmostEqual(rotate.x, 0.0, places=6)
        self.assertAlmostEqual(rotate.y, math.radians(45.0), places=6)
        self.assertAlmostEqual(rotate.z, 0.0, places=6)

    def test_negative_scale_joint_set_matrix_round_trip_keeps_world_matrix(self):
        # 回転・スケール・シアーを同じ MTransformationMatrix の分解から取るため、
        # 行列式が負(負スケール)の joint でも setMatrix(getMatrix()) で姿勢が変わらない。
        root = self.create_joint("mlibJointNegativeRoot")
        joint = self.create_joint("mlibJointNegative", parent=root)
        name = joint.getFullName()
        cmds.setAttr(root.getFullName() + ".rotate", 15.0, -25.0, 35.0)
        cmds.setAttr(name + ".translate", 1.0, 2.0, 3.0)
        cmds.setAttr(name + ".jointOrient", 10.0, 20.0, 30.0)
        cmds.setAttr(name + ".rotate", 40.0, -50.0, 60.0)
        cmds.setAttr(name + ".scale", -1.0, 2.0, 3.0)
        world = joint.getMatrix(worldSpace=True)

        joint.setMatrix(joint.getMatrix())
        self.assertTrue(joint.getMatrix(worldSpace=True).isEquivalent(world, 1e-9))
        joint.setMatrix(world, worldSpace=True)
        self.assertTrue(joint.getMatrix(worldSpace=True).isEquivalent(world, 1e-9))
        self.assertAlmostEqual(cmds.getAttr(name + ".jointOrientZ"), 30.0, places=6)

    def test_segment_scale_compensate_round_trip_under_scaled_parent(self):
        # ssc が有効な joint の行列は S·RA·R·JO·IS·T(IS は inverseScale の逆数)。
        # IS を正しく打ち消すため、非一様スケールの親の下でも姿勢とチャンネル値が変わらない。
        root = self.create_joint("mlibJointSscRoot")
        joint = self.create_joint("mlibJointSsc", parent=root)
        name = joint.getFullName()
        cmds.setAttr(root.getFullName() + ".scale", 2.0, 3.0, 0.5)
        cmds.connectAttr(root.getFullName() + ".scale", name + ".inverseScale", force=True)
        cmds.setAttr(name + ".segmentScaleCompensate", True)
        cmds.setAttr(name + ".translate", 1.0, 2.0, 3.0)
        cmds.setAttr(name + ".jointOrient", 10.0, 20.0, 30.0)
        cmds.setAttr(name + ".rotate", 40.0, -50.0, 60.0)
        cmds.setAttr(name + ".scale", -1.0, 2.0, 3.0)
        world = joint.getMatrix(worldSpace=True)
        for operation in (
            lambda: joint.setMatrix(joint.getMatrix()),
            lambda: joint.setMatrix(world, worldSpace=True),
            lambda: joint.setTranslation(joint.getTranslation(at=4), at=4),
            lambda: joint.setScale(joint.getScale()),
        ):
            operation()
            self.assertTrue(joint.getMatrix(worldSpace=True).isEquivalent(world, 1e-9))
            for actual, expected in zip(cmds.getAttr(name + ".translate")[0], (1.0, 2.0, 3.0)):
                self.assertAlmostEqual(actual, expected, places=9)
            for actual, expected in zip(cmds.getAttr(name + ".rotate")[0], (40.0, -50.0, 60.0)):
                self.assertAlmostEqual(actual, expected, places=9)
            for actual, expected in zip(cmds.getAttr(name + ".scale")[0], (-1.0, 2.0, 3.0)):
                self.assertAlmostEqual(actual, expected, places=9)

    def test_set_matrix_round_trip_for_every_rotate_order_with_orient_and_axis(self):
        for order in range(6):
            joint = self.create_joint("mlibJointOrder%d" % order)
            name = joint.getFullName()
            cmds.setAttr(name + ".rotateOrder", order)
            cmds.setAttr(name + ".jointOrient", 10.0, 20.0, 30.0)
            cmds.setAttr(name + ".rotateAxis", 5.0, -15.0, 25.0)
            cmds.setAttr(name + ".rotate", 40.0, -50.0, 60.0)
            local = joint.getMatrix()
            joint.setMatrix(local)
            self.assertTrue(joint.getMatrix().isEquivalent(local, 1e-9), order)
            self.assertAlmostEqual(cmds.getAttr(name + ".rotateAxisY"), -15.0, places=6)

    def test_parent_children_depth_and_is_joint(self):
        root = self.create_joint("mlibJointHierarchyRoot")
        mid = self.create_joint("mlibJointHierarchyMid", parent=root)
        leaf = self.create_joint("mlibJointHierarchyLeaf", parent=mid)

        self.assertIsNone(root.getParent())
        self.assertEqual(mid.getParent(), root)
        self.assertEqual(leaf.getParent(), mid)
        for removed in ("getParentJointName", "getChildJointNames"):
            self.assertFalse(hasattr(Joint, removed), removed)

        self.assertEqual(root.getChildren(type="joint"), [mid])
        self.assertEqual(mid.getChildren(type="joint"), [leaf])
        self.assertEqual(leaf.getChildren(type="joint"), [])

        self.assertEqual(root.getDepth(), 0)
        self.assertEqual(mid.getDepth(), 1)
        self.assertEqual(leaf.getDepth(), 2)

        self.assertIsInstance(root, Joint)

        non_joint = mlib.createNode(type="transform", name="mlibJointNonJoint")
        self.created.append(non_joint.getName())
        self.assertNotIsInstance(non_joint, Joint)

    def test_parent_returns_none_when_parent_is_not_a_joint(self):
        transform_parent = mlib.createNode(type="transform", name="mlibJointTransformParent")
        self.created.append(transform_parent.getName())
        joint = self.create_joint("mlibJointUnderTransform")
        cmds.parent(joint.getName(), transform_parent.getName())

        self.assertNotIsInstance(joint.getParent(), Joint)
        self.assertEqual(joint.getDepth(), 0)

    def test_reparent_children(self):
        root = self.create_joint("mlibJointReparentRoot")
        mid = self.create_joint("mlibJointReparentMid", parent=root)
        leaf1 = self.create_joint("mlibJointReparentLeaf1", parent=mid)
        leaf2 = self.create_joint("mlibJointReparentLeaf2", parent=mid)

        mid.reparentChildren(root.getName())

        # mid 自身は root の子のまま残り、mid が持っていた子(leaf1/leaf2)だけが
        # root の直接の子へ移る。
        self.assertEqual(
            sorted(child.getName() for child in root.getChildren(type="joint")),
            sorted([mid.getName(), leaf1.getName(), leaf2.getName()]),
        )
        self.assertEqual(mid.getChildren(type="joint"), [])

    def test_chain_from_here_and_ik_handles_dedupe_multiple_plugs(self):
        root = self.create_joint("mlibJointIkRoot")
        mid = self.create_joint("mlibJointIkMid", parent=root)
        tip = self.create_joint("mlibJointIkTip", parent=mid)

        chain = root.getChainFromHere()
        self.assertEqual([joint.getFullName() for joint in chain], [root.getFullName(), mid.getFullName(), tip.getFullName()])

        self.assertEqual(root.getIkHandles(), [])
        handle_name = cmds.ikHandle(startJoint=root.getFullName(), endEffector=tip.getFullName(), solver="ikRPsolver")[0]
        self.created.append(handle_name)

        # startJoint 接続に加え、poleVector 拘束などで同じ joint から同じ
        # ikHandle へ複数の接続が生じても、ノード単位で重複を除いて1件になる。
        found = root.getIkHandles()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].getName(), handle_name)

    def test_skin_clusters_dedupes_multiple_plugs_to_same_node(self):
        # skinCluster は joint の matrix と bindPreMatrix の両方に接続するため、
        # ノード単位の重複排除(uuidベース)を検証できる。
        joint = self.create_joint("mlibJointSkinCluster")
        mesh_transform = cmds.polyCube(name="mlibJointSkinClusterMesh", constructionHistory=False)[0]
        self.created.append(mesh_transform)
        skin_name = cmds.skinCluster(joint.getFullName(), mesh_transform)[0]
        self.created.append(skin_name)

        found = joint.getSkinClusters()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].getName(), skin_name)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
