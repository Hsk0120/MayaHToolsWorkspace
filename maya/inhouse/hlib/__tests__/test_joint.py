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
            cmds.parent(joint_name, parent.full_name)
        self.created.append(joint_name)
        return Joint(joint_name)

    def test_node_create_resolves_to_joint_wrapper(self):
        joint = self.create_joint("hlibJointBasic")
        self.assertIsInstance(joint, Joint)
        self.assertIsInstance(Node(joint.full_name), Joint)

    def test_joint_orient_returns_degrees_converted_to_radians(self):
        joint = self.create_joint("hlibJointOrient")
        cmds.setAttr(joint.full_name + ".jointOrientX", 90.0)
        cmds.setAttr(joint.full_name + ".jointOrientY", -45.0)

        orient = joint.joint_orient
        self.assertIsInstance(orient, EulerRotation)
        self.assertAlmostEqual(orient.x, math.radians(90.0), places=9)
        self.assertAlmostEqual(orient.y, math.radians(-45.0), places=9)
        self.assertAlmostEqual(orient.z, 0.0, places=9)

    def test_orientation_alias_matches_joint_orient(self):
        joint = self.create_joint("hlibJointOrientation")
        cmds.setAttr(joint.full_name + ".jointOrientZ", 30.0)
        self.assertEqual(joint.orientation, joint.joint_orient)

    def test_inverse_scale_is_not_angle_converted(self):
        joint = self.create_joint("hlibJointInverseScale")
        cmds.setAttr(joint.full_name + ".inverseScale", 2.0, 3.0, 4.0)

        inverse_scale = joint.inverse_scale
        self.assertIsInstance(inverse_scale, Scale)
        self.assertEqual(tuple(inverse_scale), (2.0, 3.0, 4.0))

    def test_set_rotate_preserves_joint_orient_and_rotate_axis(self):
        # jointOrient/rotateAxis は度数法の属性なので、内部で角度単位を取り違えると
        # ここで大きくズレる（asDouble() はラジアンを返すため）。set_rotate は
        # rotateAxis/jointOrient を補正した上で .rotate チャンネルへ書き込むため、
        # .rotate の生値ではなく get_rotate() による round-trip で検証する。
        joint = self.create_joint("hlibJointOrientPreserve")
        cmds.setAttr(joint.full_name + ".jointOrientX", 90.0)
        cmds.setAttr(joint.full_name + ".rotateAxisY", 30.0)

        joint.set_rotate((0.0, math.radians(45.0), 0.0))

        self.assertAlmostEqual(cmds.getAttr(joint.full_name + ".jointOrientX"), 90.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(joint.full_name + ".rotateAxisY"), 30.0, places=6)

        rotate = joint.get_rotate()
        self.assertAlmostEqual(rotate.x, 0.0, places=6)
        self.assertAlmostEqual(rotate.y, math.radians(45.0), places=6)
        self.assertAlmostEqual(rotate.z, 0.0, places=6)

    def test_parent_children_depth_and_is_joint(self):
        root = self.create_joint("hlibJointHierarchyRoot")
        mid = self.create_joint("hlibJointHierarchyMid", parent=root)
        leaf = self.create_joint("hlibJointHierarchyLeaf", parent=mid)

        self.assertIsNone(root.parent())
        self.assertEqual(mid.parent(), root.name())
        self.assertEqual(leaf.parent(), mid.name())

        self.assertEqual(root.children(), [mid.name()])
        self.assertEqual(mid.children(), [leaf.name()])
        self.assertEqual(leaf.children(), [])

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

        self.assertIsNone(joint.parent())

    def test_reparent_children(self):
        root = self.create_joint("hlibJointReparentRoot")
        mid = self.create_joint("hlibJointReparentMid", parent=root)
        leaf1 = self.create_joint("hlibJointReparentLeaf1", parent=mid)
        leaf2 = self.create_joint("hlibJointReparentLeaf2", parent=mid)

        mid.reparent_children(root.name())

        # mid 自身は root の子のまま残り、mid が持っていた子(leaf1/leaf2)だけが
        # root の直接の子へ移る。
        self.assertEqual(
            sorted(root.children()),
            sorted([mid.name(), leaf1.name(), leaf2.name()]),
        )
        self.assertEqual(mid.children(), [])

    def test_chain_from_here_and_ik_handles_dedupe_multiple_plugs(self):
        root = self.create_joint("hlibJointIkRoot")
        mid = self.create_joint("hlibJointIkMid", parent=root)
        tip = self.create_joint("hlibJointIkTip", parent=mid)

        chain = root.chain_from_here()
        self.assertEqual([joint.full_name for joint in chain], [root.full_name, mid.full_name, tip.full_name])

        self.assertEqual(root.ik_handles(), [])
        handle_name = cmds.ikHandle(startJoint=root.full_name, endEffector=tip.full_name, solver="ikRPsolver")[0]
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
        skin_name = cmds.skinCluster(joint.full_name, mesh_transform)[0]
        self.created.append(skin_name)

        found = joint.skin_clusters()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].name(), skin_name)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
