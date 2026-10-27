"""Joint・Joints・IkHandle の参照の少ない公開APIの約束を固定する(担当C)。

対象: reparentChildren(通常・fast・Undo・Joint 以外の子)、Joints.sortedByDepth、getInverseScale、
isType("joint")、getDepth・getChainFromHere の境界、IkHandle.getEndJoint・getJoints。
"""

import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.maths import Scale
from mlib.nodes import IkHandle, Joint, Joints, Node
from support.specCase import NamespaceCase


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecJointChain_"
    CLEAR_SELECTION = True

    def chain(self, *items):
        """(名前, 位置) の並びで、選択を使わずに親子の joint を作る。"""
        cmds.select(clear=True)
        names = [cmds.joint(name=self.name(text), position=position) for text, position in items]
        cmds.select(clear=True)
        return names


class ReparentChildrenTest(_SpecCase):
    """reparentChildren は直接の子 joint だけを付け替える。"""

    def setUp(self):
        super().setUp()
        self.a, self.b, self.c = self.chain(("a", (0, 0, 0)), ("b", (1, 0, 0)), ("c", (2, 0, 0)))
        self.d, = self.chain(("d", (0, 5, 0)))
        self.extra = cmds.createNode("transform", name=self.name("extra"), parent=self.b, skipSelect=True)
        self.node = Node(self.b)

    def children(self, name):
        return [item.split(":")[-1] for item in cmds.listRelatives(name, children=True) or []]

    def test_normal_and_undo(self):
        """子 joint だけを移して位置を保ち、inverseScale を新しい親へつなぐ。1回の Undo で戻る。"""
        cmds.flushUndo()
        self.assertEqual(self.node.reparentChildren(self.d), self.node)
        self.assertEqual(self.children(self.b), ["extra"])
        self.assertEqual(self.children(self.d), ["c"])
        self.assertEqual(cmds.xform(self.c, query=True, worldSpace=True, translation=True), [2.0, 0.0, 0.0])
        self.assertEqual(cmds.listConnections(self.c + ".inverseScale", source=True, plugs=True),
                         [self.d + ".scale"])
        cmds.undo()
        self.assertEqual(self.children(self.b), ["c", "extra"])

    def test_fast_matches_normal(self):
        """fast=True も同じ結果で、Undo に記録しない。"""
        cmds.flushUndo()
        self.node.reparentChildren(self.d, fast=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertEqual(self.children(self.d), ["c"])
        self.assertEqual(cmds.xform(self.c, query=True, worldSpace=True, translation=True), [2.0, 0.0, 0.0])
        self.assertEqual(cmds.listConnections(self.c + ".inverseScale", source=True, plugs=True),
                         [self.d + ".scale"])

    def test_errors_and_no_children(self):
        """存在しない親はどちらも例外で何も移さない。子 joint が無ければ何もしない。fast は bool。"""
        with self.assertRaises((RuntimeError, ValueError)):
            self.node.reparentChildren(self.name("missing"))
        with self.assertRaises(RuntimeError):
            self.node.reparentChildren(self.name("missing"), fast=True)
        self.assertEqual(self.children(self.b), ["c", "extra"])
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            self.node.reparentChildren(self.d, fast=1)
        joint = Node(self.d)
        self.assertEqual(joint.reparentChildren(self.a), joint)
        self.assertEqual(self.children(self.a), ["b"])


class JointsOrderTest(_SpecCase):
    """Joints.sortedByDepth。"""

    def test_sorted_by_depth(self):
        """深い順の新しいコレクション。同じ深さは元の順を保つ。"""
        root, middle, leaf = self.chain(("root", (0, 0, 0)), ("mid", (1, 0, 0)), ("leaf", (2, 0, 0)))
        single = cmds.createNode("joint", name=self.name("single"), skipSelect=True)
        joints = Joints([root, leaf, single, middle])
        ordered = joints.sortedByDepth()
        self.assertIs(type(ordered), Joints)
        self.assertIsNot(ordered, joints)
        self.assertEqual(ordered.getNames(), [leaf, middle, root, single])
        self.assertEqual(joints.getNames(), [root, leaf, single, middle])
        self.assertEqual(len(Joints().sortedByDepth()), 0)

    def test_depth_counts_joint_parents_only(self):
        """getDepth は joint の親だけを数え、間の transform で止まる。"""
        root, = self.chain(("depthRoot", (0, 0, 0)))
        group = cmds.createNode("transform", name=self.name("group"), parent=root, skipSelect=True)
        child = cmds.createNode("joint", name=self.name("child"), parent=group, skipSelect=True)
        self.assertEqual(Node(child).getDepth(), 0)
        self.assertIsNone(Node(child).getParentJointName())


class InverseScaleTest(_SpecCase):
    """getInverseScale と isType("joint")。"""

    def test_inverse_scale_value(self):
        """接続された親の scale、切断後は保持値をそのまま返す。逆数にはしない。"""
        root, child = self.chain(("isRoot", (0, 0, 0)), ("isChild", (1, 0, 0)))
        node = Node(child)
        self.assertEqual(list(node.getInverseScale()), [1.0, 1.0, 1.0])
        cmds.setAttr(root + ".scale", 2, 3, 4)
        value = node.getInverseScale()
        self.assertIsInstance(value, Scale)
        self.assertEqual(list(value), [2.0, 3.0, 4.0])
        cmds.disconnectAttr(root + ".scale", child + ".inverseScale")
        cmds.setAttr(child + ".inverseScale", 5, 6, 7)
        self.assertEqual(list(node.getInverseScale()), [5.0, 6.0, 7.0])
        cmds.setAttr(child + ".segmentScaleCompensate", False)
        self.assertEqual(list(node.getInverseScale()), [5.0, 6.0, 7.0])

    def test_deleted_joint(self):
        """削除済みでは getInverseScale は (0, 0, 0)、isType("joint") は False。"""
        joint, = self.chain(("deleted", (0, 0, 0)))
        node = Node(joint)
        self.assertTrue(node.isType("joint"))
        cmds.delete(joint)
        self.assertEqual(list(node.getInverseScale()), [0.0, 0.0, 0.0])
        self.assertFalse(node.isType("joint"))

    def test_bulk(self):
        """Joints の同名メソッドは保持順のリスト。"""
        root, child = self.chain(("bulkRoot", (0, 0, 0)), ("bulkChild", (1, 0, 0)))
        cmds.setAttr(root + ".scale", 2, 2, 2)
        joints = Joints([root, child])
        self.assertEqual(joints.isType("joint"), [True, True])
        self.assertEqual([list(value) for value in joints.getInverseScale()], [[1.0] * 3, [2.0] * 3])


class ChainTest(_SpecCase):
    """getChainFromHere の境界。"""

    def test_chain_until_branch_and_to(self):
        """to を省くと分岐で止まり、to が子孫でなければ ValueError。"""
        root, middle, leaf = self.chain(("cRoot", (0, 0, 0)), ("cMid", (1, 0, 0)), ("cLeaf", (2, 0, 0)))
        cmds.select(clear=True)
        branch = cmds.joint(name=self.name("cBranch"), position=(1, 1, 0))
        cmds.parent(branch, middle)
        cmds.select(clear=True)
        self.assertEqual([item.getName() for item in Node(root).getChainFromHere()], [root, middle])
        self.assertEqual([item.getName() for item in Node(root).getChainFromHere(to=leaf)], [root, middle, leaf])
        self.assertEqual(Node(leaf).getChainFromHere(), [Node(leaf)])
        with self.assertRaisesRegex(ValueError, "descendant"):
            Node(leaf).getChainFromHere(to=root)
        with self.assertRaisesRegex(ValueError, "descendant"):
            Node(root).getChainFromHere(to=root)


class IkHandleTest(_SpecCase):
    """IkHandle.getEndJoint・getJoints。"""

    def setUp(self):
        super().setUp()
        self.j1, self.j2, self.j3 = self.chain(("j1", (0, 0, 0)), ("j2", (1, 0, 1)), ("j3", (2, 0, 0)))
        self.handle = cmds.ikHandle(startJoint=self.j1, endEffector=self.j3, name=self.name("ik"))[0]
        self.node = Node(self.handle)

    def test_end_joint_and_joints(self):
        """getJoints は jointList(末端を含まない)、includeTip=True で末端を足す。"""
        self.assertIs(type(self.node), IkHandle)
        self.assertEqual(self.node.getEndJoint(), Joint(self.j3))
        self.assertEqual(self.node.getJoints(), [Joint(self.j1), Joint(self.j2)])
        self.assertEqual(self.node.getJoints(includeTip=True), [Joint(self.j1), Joint(self.j2), Joint(self.j3)])
        self.assertTrue(all(type(item) is Joint for item in self.node.getJoints(True)))

    def test_disconnected_effector(self):
        """effector の translate の入力が無ければ getEndJoint は None、getJoints は末端を足さない。"""
        effector = cmds.listConnections(self.handle + ".endEffector")[0]
        cmds.disconnectAttr(self.j3 + ".translateX", effector + ".translateX")
        self.assertIsNone(self.node.getEndJoint())
        self.assertEqual(self.node.getJoints(includeTip=True), [Joint(self.j1), Joint(self.j2)])

    def test_deleted_handle(self):
        """削除済みのハンドルの getJoints は RuntimeError。"""
        cmds.delete(self.handle)
        with self.assertRaisesRegex(RuntimeError, r"invalid IkHandle"):
            self.node.getJoints()


if __name__ == "__main__":
    unittest.main()
