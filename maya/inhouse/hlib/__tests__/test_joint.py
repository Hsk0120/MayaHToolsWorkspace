"""hlib.nodes.joint の Joint ラッパーを検証するMaya内テスト。"""

import math
import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.maths import EulerRotation, Scale
from hlib.nodes import Node
from hlib.nodes.joint import Joint


class JointTest(unittest.TestCase):
    """joint_orient/inverse_scale の単位変換、階層クエリ、skinCluster/IK連携を検証する。"""

    namespace = ":hlibJointTest"

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
            cmds.parent(joint_name, parent.full_name())
        self.created.append(joint_name)
        return Joint(joint_name)

    def test_segment_scale_compensate_bulk_and_undo(self):
        from hlib.nodes.joint import Joints
        parent = self.create_joint("sscParent")
        child = self.create_joint("sscChild", parent)
        joints = Joints([parent, child])
        self.assertEqual(joints.get_segment_scale_compensate(), [True, True])
        joints.set_segment_scale_compensate(False)
        self.assertEqual(joints.get_segment_scale_compensate(), [False, False])
        cmds.undo()
        self.assertEqual(joints.get_segment_scale_compensate(), [True, True])
        cmds.redo()
        self.assertEqual(joints.get_segment_scale_compensate(), [False, False])
        self.assertIs(child.set_segment_scale_compensate(True, fast=True), child)
        self.assertTrue(child.get_segment_scale_compensate())
        with self.assertRaises(TypeError):
            child.set_segment_scale_compensate(1)

    def test_inverse_scale_connect_disconnect_bulk(self):
        from hlib.nodes.joint import Joints
        parent = self.create_joint("connectParent")
        child = self.create_joint("connectChild", parent)
        joints = Joints([parent, child])
        joints.disconnect_inverse_scale()
        self.assertIsNone(child.plug("inverseScale").source())
        joints.connect_inverse_scale()
        self.assertEqual(child.plug("inverseScale").source(), parent.plug("scale"))
        cmds.undo()
        self.assertIsNone(child.plug("inverseScale").source())
        child.connect_inverse_scale(parent.full_name())
        child.connect_inverse_scale()  # 同じ接続はそのまま
        child.disconnect_inverse_scale()
        parent.plug("sx").connect(child.plug("inverseScaleX"))
        parent.plug("sy").connect(child.plug("inverseScaleY"))
        child.plug("inverseScaleZ").connect(parent.plug("radius"))
        child.disconnect_inverse_scale()
        self.assertIsNone(child.plug("inverseScaleX").source())
        self.assertIsNone(child.plug("inverseScaleY").source())
        self.assertEqual(parent.plug("radius").source(), child.plug("inverseScaleZ"))
        with self.assertRaises(ValueError):
            child.connect_inverse_scale(child)

    def test_joint_radius_and_bulk_undo(self):
        from hlib.nodes.joint import Joints
        joints = Joints([self.create_joint("radiusA"), self.create_joint("radiusB")])
        before = joints.get_radius()
        joints.set_radius(2.5)
        self.assertEqual(joints.get_radius(), [2.5, 2.5])
        cmds.undo()
        self.assertEqual(joints.get_radius(), before)
        cmds.redo()
        self.assertEqual(joints.get_radius(), [2.5, 2.5])
        joints[0].set_radius(0, fast=True)
        self.assertEqual(joints[0].get_radius(), 0)
        for value in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                joints[0].set_radius(value)

    def test_node_create_resolves_to_joint_wrapper(self):
        joint = self.create_joint("hlibJointBasic")
        self.assertIsInstance(joint, Joint)
        self.assertIsInstance(Node(joint.full_name()), Joint)

    def test_joint_orient_returns_degrees_converted_to_radians(self):
        joint = self.create_joint("hlibJointOrient")
        cmds.setAttr(joint.full_name() + ".jointOrientX", 90.0)
        cmds.setAttr(joint.full_name() + ".jointOrientY", -45.0)

        orient = joint.get_joint_orient()
        self.assertIsInstance(orient, EulerRotation)
        self.assertAlmostEqual(orient.x, math.radians(90.0), places=9)
        self.assertAlmostEqual(orient.y, math.radians(-45.0), places=9)
        self.assertAlmostEqual(orient.z, 0.0, places=9)

    def test_joint_orient_z_returns_radians(self):
        joint = self.create_joint("hlibJointOrientation")
        cmds.setAttr(joint.full_name() + ".jointOrientZ", 30.0)
        self.assertAlmostEqual(joint.get_joint_orient().z, math.radians(30.0))

    def test_inverse_scale_is_not_angle_converted(self):
        joint = self.create_joint("hlibJointInverseScale")
        cmds.setAttr(joint.full_name() + ".inverseScale", 2.0, 3.0, 4.0)

        inverse_scale = joint.get_inverse_scale()
        self.assertIsInstance(inverse_scale, Scale)
        self.assertEqual(tuple(inverse_scale), (2.0, 3.0, 4.0))

    def test_set_rotate_preserves_joint_orient_and_rotate_axis(self):
        # jointOrient/rotateAxis は度数法のアトリビュートなので、内部で角度単位を取り違えると
        # ここで大きくズレる（asDouble() はラジアンを返すため）。set_rotate は
        # rotateAxis/jointOrient を補正した上で .rotate チャンネルへ書き込むため、
        # .rotate の生値ではなく get_rotate() による round-trip で検証する。
        joint = self.create_joint("hlibJointOrientPreserve")
        cmds.setAttr(joint.full_name() + ".jointOrientX", 90.0)
        cmds.setAttr(joint.full_name() + ".rotateAxisY", 30.0)

        joint.set_rotate((0.0, math.radians(45.0), 0.0))

        self.assertAlmostEqual(cmds.getAttr(joint.full_name() + ".jointOrientX"), 90.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(joint.full_name() + ".rotateAxisY"), 30.0, places=6)

        rotate = joint.get_rotate()
        self.assertAlmostEqual(rotate.x, 0.0, places=6)
        self.assertAlmostEqual(rotate.y, math.radians(45.0), places=6)
        self.assertAlmostEqual(rotate.z, 0.0, places=6)

    def test_negative_scale_joint_set_matrix_round_trip_keeps_world_matrix(self):
        # 回転・スケール・シアーを同じ MTransformationMatrix の分解から取るため、
        # 行列式が負(負スケール)の joint でも set_matrix(get_matrix()) で姿勢が変わらない。
        root = self.create_joint("hlibJointNegativeRoot")
        joint = self.create_joint("hlibJointNegative", parent=root)
        name = joint.full_name()
        cmds.setAttr(root.full_name() + ".rotate", 15.0, -25.0, 35.0)
        cmds.setAttr(name + ".translate", 1.0, 2.0, 3.0)
        cmds.setAttr(name + ".jointOrient", 10.0, 20.0, 30.0)
        cmds.setAttr(name + ".rotate", 40.0, -50.0, 60.0)
        cmds.setAttr(name + ".scale", -1.0, 2.0, 3.0)
        world = joint.get_matrix(ws=True)

        joint.set_matrix(joint.get_matrix())
        self.assertTrue(joint.get_matrix(ws=True).is_equivalent(world, 1e-9))
        joint.set_matrix(world, ws=True)
        self.assertTrue(joint.get_matrix(ws=True).is_equivalent(world, 1e-9))
        self.assertAlmostEqual(cmds.getAttr(name + ".jointOrientZ"), 30.0, places=6)

    def test_segment_scale_compensate_round_trip_under_scaled_parent(self):
        # ssc が有効な joint の行列は S·RA·R·JO·IS·T(IS は inverseScale の逆数)。
        # IS を正しく打ち消すため、非一様スケールの親の下でも姿勢とチャンネル値が変わらない。
        root = self.create_joint("hlibJointSscRoot")
        joint = self.create_joint("hlibJointSsc", parent=root)
        name = joint.full_name()
        cmds.setAttr(root.full_name() + ".scale", 2.0, 3.0, 0.5)
        cmds.connectAttr(root.full_name() + ".scale", name + ".inverseScale", force=True)
        cmds.setAttr(name + ".segmentScaleCompensate", True)
        cmds.setAttr(name + ".translate", 1.0, 2.0, 3.0)
        cmds.setAttr(name + ".jointOrient", 10.0, 20.0, 30.0)
        cmds.setAttr(name + ".rotate", 40.0, -50.0, 60.0)
        cmds.setAttr(name + ".scale", -1.0, 2.0, 3.0)
        world = joint.get_matrix(ws=True)
        for operation in (
            lambda: joint.set_matrix(joint.get_matrix()),
            lambda: joint.set_matrix(world, ws=True),
            lambda: joint.set_translate(joint.get_translate()),
            lambda: joint.set_scale(joint.get_scale()),
        ):
            operation()
            self.assertTrue(joint.get_matrix(ws=True).is_equivalent(world, 1e-9))
            for actual, expected in zip(cmds.getAttr(name + ".translate")[0], (1.0, 2.0, 3.0)):
                self.assertAlmostEqual(actual, expected, places=9)
            for actual, expected in zip(cmds.getAttr(name + ".rotate")[0], (40.0, -50.0, 60.0)):
                self.assertAlmostEqual(actual, expected, places=9)
            for actual, expected in zip(cmds.getAttr(name + ".scale")[0], (-1.0, 2.0, 3.0)):
                self.assertAlmostEqual(actual, expected, places=9)

    def test_set_matrix_round_trip_for_every_rotate_order_with_orient_and_axis(self):
        for order in range(6):
            joint = self.create_joint("hlibJointOrder%d" % order)
            name = joint.full_name()
            cmds.setAttr(name + ".rotateOrder", order)
            cmds.setAttr(name + ".jointOrient", 10.0, 20.0, 30.0)
            cmds.setAttr(name + ".rotateAxis", 5.0, -15.0, 25.0)
            cmds.setAttr(name + ".rotate", 40.0, -50.0, 60.0)
            local = joint.get_matrix()
            joint.set_matrix(local)
            self.assertTrue(joint.get_matrix().is_equivalent(local, 1e-9), order)
            self.assertAlmostEqual(cmds.getAttr(name + ".rotateAxisY"), -15.0, places=6)

    def test_parent_children_depth_and_is_joint(self):
        root = self.create_joint("hlibJointHierarchyRoot")
        mid = self.create_joint("hlibJointHierarchyMid", parent=root)
        leaf = self.create_joint("hlibJointHierarchyLeaf", parent=mid)

        self.assertIsNone(root.parent_joint_name())
        self.assertEqual(mid.parent_joint_name(), root.name())
        self.assertEqual(leaf.parent_joint_name(), mid.name())

        self.assertEqual(root.child_joint_names(), [mid.name()])
        self.assertEqual(mid.child_joint_names(), [leaf.name()])
        self.assertEqual(leaf.child_joint_names(), [])

        self.assertEqual(root.depth(), 0)
        self.assertEqual(mid.depth(), 1)
        self.assertEqual(leaf.depth(), 2)

        self.assertTrue(root.is_joint())

        non_joint = Node.create(type="transform", name="hlibJointNonJoint")
        self.created.append(non_joint.name())
        self.assertNotIsInstance(non_joint, Joint)

    def test_parent_returns_none_when_parent_is_not_a_joint(self):
        transform_parent = Node.create(type="transform", name="hlibJointTransformParent")
        self.created.append(transform_parent.name())
        joint = self.create_joint("hlibJointUnderTransform")
        cmds.parent(joint.name(), transform_parent.name())

        self.assertIsNone(joint.parent_joint_name())

    def test_reparent_children(self):
        root = self.create_joint("hlibJointReparentRoot")
        mid = self.create_joint("hlibJointReparentMid", parent=root)
        leaf1 = self.create_joint("hlibJointReparentLeaf1", parent=mid)
        leaf2 = self.create_joint("hlibJointReparentLeaf2", parent=mid)

        mid.reparent_children(root.name())

        # mid 自身は root の子のまま残り、mid が持っていた子(leaf1/leaf2)だけが
        # root の直接の子へ移る。
        self.assertEqual(
            sorted(root.child_joint_names()),
            sorted([mid.name(), leaf1.name(), leaf2.name()]),
        )
        self.assertEqual(mid.child_joint_names(), [])

    def test_chain_from_here_and_ik_handles_dedupe_multiple_plugs(self):
        root = self.create_joint("hlibJointIkRoot")
        mid = self.create_joint("hlibJointIkMid", parent=root)
        tip = self.create_joint("hlibJointIkTip", parent=mid)

        chain = root.chain_from_here()
        self.assertEqual([joint.full_name() for joint in chain], [root.full_name(), mid.full_name(), tip.full_name()])

        self.assertEqual(root.ik_handles(), [])
        handle_name = cmds.ikHandle(startJoint=root.full_name(), endEffector=tip.full_name(), solver="ikRPsolver")[0]
        self.created.append(handle_name)

        # startJoint 接続に加え、poleVector 拘束などで同じ joint から同じ
        # ikHandle へ複数の接続が生じても、ノード単位で重複を除いて1件になる。
        found = root.ik_handles()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].name(), handle_name)

    def test_skin_clusters_dedupes_multiple_plugs_to_same_node(self):
        # skinCluster は joint の matrix と bindPreMatrix の両方に接続するため、
        # ノード単位の重複排除(uuidベース)を検証できる。
        joint = self.create_joint("hlibJointSkinCluster")
        mesh_transform = cmds.polyCube(name="hlibJointSkinClusterMesh", constructionHistory=False)[0]
        self.created.append(mesh_transform)
        skin_name = cmds.skinCluster(joint.full_name(), mesh_transform)[0]
        self.created.append(skin_name)

        found = joint.skin_clusters()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].name(), skin_name)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
