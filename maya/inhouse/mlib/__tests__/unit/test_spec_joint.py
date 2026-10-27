"""Joint の共通化(mlib 2.0、担当 2B)の約束を固定する。

対象: ``isJoint()`` の廃止と代替(``isinstance``・``isType("joint")``)、Joint の
``getRotate(order=)``(ゼロ回転に最も近い等価解)、``setParent(r=)`` と inverseScale の保守、
``resetAttrs`` が jointOrient を戻さないこと、``mfn()``、無効 joint への操作の例外、
Joints の一括転送(``_bulk_entries``・転送 def・``__signature__``)。
"""

import inspect
import math
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.maths import EulerRotate
from mlib.nodes import Joint, Joints, Node, Transform, Transforms
from support.specCase import NamespaceCase


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecJoint_"

    def make(self, kind="joint", text="joint#", parent=None):
        """既定で joint を作る(引数は NamespaceCase.make と同じ)。"""
        return super().make(kind, text, parent)


class RemovedApiTest(unittest.TestCase):
    """isJoint は単数・複数形・一括宣言のどこにも残さない。"""

    def test_isjoint_is_absent(self):
        for owner in (Joint, Joints, Transform, Transforms):
            with self.subTest(owner=owner.__name__):
                self.assertFalse(hasattr(owner, "isJoint"))
        self.assertNotIn("isJoint", Joints._bulk_entries)
        self.assertNotIn("isJoint", Joints._bulk_methods)
        self.assertNotIn("isJoint", Joints._bulk_returns)

    def test_bulk_entries_match_singular_and_forwarders(self):
        """チェックリスト(DESIGN §6.8): 宣言・単数 def・転送 def・__signature__ が揃う。"""
        for name, (function, policy) in Joints._bulk_entries.items():
            with self.subTest(name=name):
                self.assertIs(getattr(Joint, name), function)
                self.assertIn(policy, ("list", "self"))
                forwarder = getattr(Joints, name)
                self.assertTrue(callable(forwarder))
                if hasattr(forwarder, "__signature__"):
                    # 定型の転送 def。手書きの一括(jointOrientToRotate 等)と継承(delete)は署名を持たない。
                    self.assertEqual(forwarder.__signature__, inspect.signature(function))
        # Transforms から継承した転送は Joint 側で override していなければ Transform の宣言を使う。
        for name in ("mfn", "resetAttrs", "getShear", "setShear", "getRotate", "setParent"):
            with self.subTest(inherited=name):
                self.assertIn(name, Joints._bulk_methods)
                self.assertTrue(callable(getattr(Joints, name)))
        for name in ("transformFn", "reset", "resetPivot", "freeze", "getEuler", "getJointOrientQuaternion",
                     "getShearing", "setShearing", "getOffsetParentMatrix", "setOffsetParentMatrix"):
            with self.subTest(removed=name):
                self.assertFalse(hasattr(Joints, name))
                self.assertNotIn(name, Joints._bulk_methods)


class TypeQueryTest(_SpecCase):
    """isJoint の代替。"""

    def test_isinstance_and_istype(self):
        joint = Node(self.make())
        transform = Node(self.make("transform", "transform#"))
        self.assertIsInstance(joint, Joint)
        self.assertNotIsInstance(transform, Joint)
        self.assertTrue(joint.isType("joint"))
        self.assertFalse(transform.isType("joint"))
        self.assertEqual(joint.getType(), "joint")
        self.assertTrue(joint.hasFn(om2.MFn.kJoint))
        self.assertFalse(transform.hasFn(om2.MFn.kJoint))

    def test_joints_rejects_non_joints(self):
        transform = self.make("transform", "transform#")
        with self.assertRaises(TypeError):
            Joints([self.make(), transform])


class MfnTest(_SpecCase):
    """Joint の mfn() は MFnTransform(joint 専用の function set は om2 に無い)。"""

    def test_mfn(self):
        joint = Node(self.make())
        fn = joint.mfn()
        self.assertIs(type(fn), om2.MFnTransform)
        self.assertEqual(fn.fullPathName(), cmds.ls(str(joint), long=True)[0])
        self.assertIsNot(fn, joint.mfn())
        fns = Joints([str(joint)]).mfn()
        self.assertEqual([type(fn) for fn in fns], [om2.MFnTransform])


class GetRotateTest(_SpecCase):
    """Joint の getRotate は jointOrient と rotateAxis を含み、ゼロ回転に最も近い解を選ぶ。"""

    def test_default_includes_orient_and_matches_matrix(self):
        for rotate_order in range(6):
            with self.subTest(rotateOrder=rotate_order):
                joint = self._joint(rotate_order)
                rotate = joint.getRotate()
                self.assertIsInstance(rotate, EulerRotate)
                self.assertEqual(rotate.order, rotate_order)
                expected = self._local_quaternion(str(joint))
                actual = om2.MEulerRotation(rotate.x, rotate.y, rotate.z, rotate_order).asQuaternion()
                self.assertTrue(actual.isEquivalent(expected, 1e-9) or actual.isEquivalent(-expected, 1e-9))
                # rotate チャンネルそのものではない(jointOrient・rotateAxis を含む)。
                channel = [math.radians(v) for v in cmds.getAttr(str(joint) + ".rotate")[0]]
                self.assertFalse(all(abs(a - b) < 1e-6 for a, b in zip(rotate, channel)))

    def test_default_is_closest_to_zero(self):
        """等価解のうちゼロ回転に最も近いもの(素の分解値とその代替解のどちらより遠くない)。"""
        joint = self._joint(0)
        rotate = joint.getRotate()
        plain = self._local_quaternion(str(joint)).asEulerRotation().reorder(0)
        alternate = om2.MEulerRotation(plain).setToAlternateSolution()
        distance = sum(value ** 2 for value in rotate)
        for candidate in (plain, alternate):
            with self.subTest(candidate=(candidate.x, candidate.y, candidate.z)):
                self.assertLessEqual(distance, candidate.x ** 2 + candidate.y ** 2 + candidate.z ** 2 + 1e-9)

    def test_order_rules(self):
        joint = self._joint(2)
        for ws in (False, True):
            default = joint.getRotate(ws=ws)
            self.assertSequenceAlmostEqual(joint.getRotate(ws=ws, order=2), default)
            self.assertSequenceAlmostEqual(joint.getRotate(ws=ws, order="zxy"), default)
            if ws:
                matrix = om2.MMatrix(cmds.getAttr(str(joint) + ".worldMatrix[0]"))
            else:
                matrix = om2.MMatrix(cmds.getAttr(str(joint) + ".matrix"))
            quaternion = om2.MTransformationMatrix(matrix).rotation(asQuaternion=True)
            for order in (0, 1, 3, 4, 5):
                with self.subTest(ws=ws, order=order):
                    expected = quaternion.asEulerRotation().reorder(order)
                    actual = joint.getRotate(ws=ws, order=order)
                    self.assertEqual(actual.order, order)
                    self.assertSequenceAlmostEqual(actual, (expected.x, expected.y, expected.z))
        with self.assertRaises(ValueError):
            joint.getRotate(order=7)
        with self.assertRaises(TypeError):
            joint.getRotate(False, ws=False)

    def _joint(self, rotate_order):
        parent = self.make(text="parent#")
        cmds.setAttr(parent + ".jointOrient", 15.0, -20.0, 25.0)
        name = self.make(text="child#", parent=parent)
        cmds.setAttr(name + ".rotateOrder", rotate_order)
        cmds.setAttr(name + ".jointOrient", 10.0, 20.0, 30.0)
        cmds.setAttr(name + ".rotateAxis", 5.0, -5.0, 2.5)
        cmds.setAttr(name + ".rotate", 40.0, 50.0, -60.0)
        return Node(name)

    def _local_quaternion(self, name):
        return om2.MTransformationMatrix(om2.MMatrix(cmds.getAttr(name + ".matrix"))).rotation(asQuaternion=True)


class SetParentTest(_SpecCase):
    """Joint の setParent は cmds.parent に従う(inverseScale の接続は relative=False のときだけ)。fast は未対応。"""

    def test_relative_keeps_channels_without_inverse_scale(self):
        for flags in ({"relative": True}, {"r": True}):
            with self.subTest(flags=flags):
                parent = self.make(text="parent#")
                cmds.setAttr(parent + ".translate", 3.0, 0.0, 0.0)
                child = self.make(text="child#")
                cmds.setAttr(child + ".translate", 1.0, 2.0, 3.0)
                joint = Node(child)
                self.assertIs(joint.setParent(parent, **flags), joint)
                self.assertSequenceAlmostEqual(cmds.getAttr(str(joint) + ".translate")[0], (1.0, 2.0, 3.0))
                # cmds.parent -relative と同じく inverseScale は接続しない(Maya の仕様)。
                self.assertIsNone(cmds.listConnections(str(joint) + ".inverseScale", plugs=True, source=True,
                                                       destination=False))

    def test_default_keeps_world_and_undo(self):
        parent = self.make(text="parent#")
        cmds.setAttr(parent + ".translate", 3.0, 0.0, 0.0)
        cmds.setAttr(parent + ".rotate", 0.0, 0.0, 90.0)
        child = self.make(text="child#")
        cmds.setAttr(child + ".translate", 1.0, 2.0, 3.0)
        world = cmds.getAttr(child + ".worldMatrix[0]")
        joint = Node(child)
        cmds.flushUndo()
        joint.setParent(parent)
        self.assertSequenceAlmostEqual(cmds.getAttr(str(joint) + ".worldMatrix[0]"), world, places=6)
        # cmds.parent(relative=False) と同じく親 joint の scale が inverseScale へ接続される。
        sources = cmds.listConnections(str(joint) + ".inverseScale", plugs=True, source=True, destination=False)
        self.assertEqual(len(sources), 1)
        source_node, source_attr = sources[0].rsplit(".", 1)
        self.assertEqual(source_attr, "scale")
        self.assertEqual(cmds.ls(source_node, long=True)[0], cmds.ls(parent, long=True)[0])
        self.assertFalse(cmds.undoInfo(query=True, undoQueueEmpty=True))
        cmds.undo()
        self.assertIsNone(cmds.listRelatives(str(joint), parent=True))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_fast_is_not_implemented_for_joints(self):
        parent = self.make(text="parent#")
        joint = Node(self.make(text="child#"))
        with self.assertRaises(NotImplementedError):
            joint.setParent(parent, fast=True)
        with self.assertRaises(NotImplementedError):
            joint.setParent(parent, r=True, fast=True)
        self.assertIsNone(cmds.listRelatives(str(joint), parent=True))
        with self.assertRaises(TypeError):
            joint.setParent(parent, True, r=True)


class ResetAttrsTest(_SpecCase):
    """Joint.resetAttrs の既定は TRS とシアーだけで、jointOrient は戻さない。"""

    def test_default_keeps_joint_orient(self):
        name = self.make()
        cmds.setAttr(name + ".translate", 1.0, 2.0, 3.0)
        cmds.setAttr(name + ".rotate", 10.0, 20.0, 30.0)
        cmds.setAttr(name + ".jointOrient", 5.0, 6.0, 7.0)
        joint = Node(name)
        plugs = joint.resetAttrs()
        self.assertEqual([plug.getLongName() for plug in plugs], ["translate", "rotate", "scale", "shear"])
        self.assertSequenceAlmostEqual(cmds.getAttr(name + ".rotate")[0], (0.0, 0.0, 0.0))
        self.assertSequenceAlmostEqual(cmds.getAttr(name + ".jointOrient")[0], (5.0, 6.0, 7.0))
        plugs = joint.resetAttrs("jointOrient")
        self.assertEqual([plug.getLongName() for plug in plugs], ["jointOrient"])
        self.assertSequenceAlmostEqual(cmds.getAttr(name + ".jointOrient")[0], (0.0, 0.0, 0.0))

    def test_joints_returns_list_of_lists(self):
        names = [self.make(), self.make()]
        for name in names:
            cmds.setAttr(name + ".translate", 1.0, 2.0, 3.0)
        result = Joints(names).resetAttrs("translate", fast=True)
        self.assertEqual([[plug.getLongName() for plug in plugs] for plugs in result], [["translate"], ["translate"]])
        for name in names:
            self.assertEqual(cmds.getAttr(name + ".translate")[0], (0.0, 0.0, 0.0))


class InvalidJointTest(_SpecCase):
    """削除済み joint への操作は isValid() の判定で RuntimeError。"""

    def test_operations_on_deleted_joint(self):
        joint = Node(self.make())
        cmds.delete(str(joint))
        self.assertFalse(joint.isValid())
        for method, flags in (("jointOrientToRotate", {}), ("freezeRotate", {}), ("jointOrientToRotate", {"fast": True})):
            with self.subTest(method=method, flags=flags):
                with self.assertRaises(RuntimeError):
                    getattr(joint, method)(**flags)


if __name__ == "__main__":
    unittest.main(verbosity=2)
