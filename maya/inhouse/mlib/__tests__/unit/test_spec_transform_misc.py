"""Transform の参照の少ない公開APIの約束を固定する(担当C)。

対象: getQuaternion(r=False)・getRotate(order=0)・getShear(ローカル/ワールド)、setPivot((0, 0, 0))、makeIdentity、
mirrorGeometry、getRoot・getSiblings、getBoundingBox(ws)、resetAttrs と Transforms の同名メソッド。
setRotate・setMatrix の書き込むチャンネルは test_contract_changes_B.py が確かめているため重ねない。
"""

import math
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.maths import EulerRotate, Quaternion, Shear
from mlib.nodes import Node, Transforms
from support.specCase import NamespaceCase

TOLERANCE = 1e-9


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecXformMisc_"


class JointOrientQuaternionTest(_SpecCase):
    """getQuaternion(r=False) は jointOrient(とワールドなら親)だけの回転。"""

    def setUp(self):
        super().setUp()
        self.parent = self.make("transform", "parent")
        cmds.setAttr(self.parent + ".rotate", 30, 0, 0)
        self.joint_name = self.make("joint", "joint", parent=self.parent)
        cmds.setAttr(self.joint_name + ".jointOrient", 0, 45, 0)
        cmds.setAttr(self.joint_name + ".rotate", 0, 0, 20)
        self.joint = Node(self.joint_name)
        self.transform = Node(self.parent)

    def test_local_joint_is_joint_orient(self):
        """ローカルの Joint は jointOrient だけを Quaternion で返し、rotate を含めない。"""
        value = self.joint.getQuaternion(r=False)
        self.assertIsInstance(value, Quaternion)
        expected = om2.MEulerRotation(0, math.radians(45), 0).asQuaternion()
        self.assertSameRotation(value, expected)
        self.assertSameRotation(value, self.joint.getQuaternion(r=False))

    def test_world_joint_includes_parent(self):
        """ワールドは保持パスから求め、親の回転を含めて rotate だけを除く。"""
        expected = (om2.MEulerRotation(0, math.radians(45), 0).asQuaternion()
                    * om2.MEulerRotation(math.radians(30), 0, 0).asQuaternion())
        self.assertSameRotation(self.joint.getQuaternion(ws=True, r=False), expected)
        self.assertSameRotation(self.joint.getQuaternion(worldSpace=True, r=False), expected)

    def test_transform(self):
        """非 Joint のローカルは単位回転、ワールドは親側の回転(ワールド直下なら単位)。"""
        self.assertSameRotation(self.transform.getQuaternion(r=False), [0, 0, 0, 1])
        self.assertSameRotation(self.transform.getQuaternion(ws=True, r=False), [0, 0, 0, 1])
        child = Node(self.make("transform", "child", parent=self.parent))
        cmds.setAttr(child.getFullName() + ".rotate", 0, 90, 0)
        self.assertSameRotation(child.getQuaternion(ws=True, r=False),
                                om2.MEulerRotation(math.radians(30), 0, 0).asQuaternion())

    def test_argument_errors(self):
        """ws と worldSpace の同時指定は TypeError、bool 以外は ValueError。"""
        with self.assertRaisesRegex(TypeError, "Specify only one of"):
            self.joint.getQuaternion(ws=True, worldSpace=True, r=False)
        with self.assertRaises(ValueError):
            self.joint.getQuaternion(ws=1, r=False)

    def test_independent_value(self):
        """戻り値を変えてもシーンは変わらない。"""
        value = self.joint.getQuaternion(r=False)
        value.x = 0.9
        self.assertEqual(cmds.getAttr(self.joint_name + ".jointOrient")[0], (0.0, 45.0, 0.0))


class EulerShearTest(_SpecCase):
    """getRotate(order=0) と getShear。"""

    def setUp(self):
        super().setUp()
        self.parent = self.make("transform", "parent")
        cmds.setAttr(self.parent + ".rotate", 30, 0, 0)
        self.child_name = self.make("transform", "child", parent=self.parent)
        self.child = Node(self.child_name)

    def test_get_euler_is_xyz_regardless_of_rotate_order(self):
        """getRotate(order=0) は rotateOrder によらず XYZ 順の radian。"""
        cmds.setAttr(self.child_name + ".rotateOrder", 2)
        cmds.setAttr(self.child_name + ".rotate", 0, 0, 40)
        value = self.child.getRotate(order=0)
        self.assertIsInstance(value, EulerRotate)
        self.assertEqual(value.order, om2.MEulerRotation.kXYZ)
        self.assertSequenceAlmostEqual(list(value), [0.0, 0.0, math.radians(40)])

    def test_get_euler_world(self):
        """ws=True はワールドマトリクスの回転を XYZ 順で返す。"""
        cmds.setAttr(self.child_name + ".rotate", 0, 0, 40)
        expected = om2.MTransformationMatrix(om2.MMatrix(cmds.getAttr(self.child_name + ".worldMatrix[0]")))
        expected = expected.rotation(asQuaternion=True).asEulerRotation()
        self.assertSequenceAlmostEqual(list(self.child.getRotate(ws=True, order=0)), list(expected))
        with self.assertRaises(ValueError):
            self.child.getRotate(ws="yes", order=0)

    def test_get_euler_with_zero_scale_raises(self):
        """自身・親のスケールが0(Maya は 1e-12 として評価)なら ValueError。"""
        cmds.setAttr(self.parent + ".scale", 0, 1, 1)
        with self.assertRaisesRegex(ValueError, "zero scale axis"):
            self.child.getRotate(ws=True, order=0)
        self.assertIsInstance(self.child.getRotate(order=0), EulerRotate)
        cmds.setAttr(self.parent + ".scale", 1, 1, 1)
        cmds.setAttr(self.child_name + ".scale", 1, 0, 1)
        with self.assertRaisesRegex(ValueError, "zero scale axis"):
            self.child.getRotate(order=0)
        with self.assertRaisesRegex(ValueError, "zero scale axis"):
            self.child.getRotate(ws=True, order=0)

    def test_get_euler_with_small_scale(self):
        """小さくても0でないスケールは分解する。"""
        cmds.setAttr(self.child_name + ".rotate", 0, 0, 40)
        cmds.setAttr(self.child_name + ".scale", 1e-4, 1e-4, 1e-4)
        self.assertSequenceAlmostEqual(list(self.child.getRotate(order=0)), [0.0, 0.0, math.radians(40)])

    def test_get_shearing(self):
        """ローカルは shear チャンネル、ワールドは API の分解値。戻り値は Shear。"""
        cmds.setAttr(self.child_name + ".shear", 0.5, 0, 0)
        local = self.child.getShear()
        self.assertIsInstance(local, Shear)
        self.assertSequenceAlmostEqual(list(local), [0.5, 0.0, 0.0])
        cmds.setAttr(self.parent + ".rotate", 0, 0, 0)
        cmds.setAttr(self.parent + ".shear", 0.2, 0, 0)
        expected = om2.MTransformationMatrix(om2.MMatrix(cmds.getAttr(self.child_name + ".worldMatrix[0]")))
        self.assertSequenceAlmostEqual(list(self.child.getShear(ws=True)), list(expected.shear(om2.MSpace.kTransform)))
        self.assertSequenceAlmostEqual(list(self.child.getShear(ws=True)), [0.7, 0.0, 0.0])
        with self.assertRaises(TypeError):
            self.child.getShear(worldSpace=True, ws=True)


class ResetPivotTest(_SpecCase):
    """setPivot((0, 0, 0), ws=True, kind="both") は姿勢を保ってピボットを原点へ移す。"""

    def setUp(self):
        super().setUp()
        self.parent = self.make("transform", "parent")
        cmds.setAttr(self.parent + ".translate", 1, 0, 0)
        self.name_ = self.make("transform", "pivot", parent=self.parent)
        cmds.setAttr(self.name_ + ".rotate", 0, 30, 0)
        cmds.xform(self.name_, worldSpace=True, rotatePivot=(1, 2, 3), scalePivot=(4, 5, 6))
        self.node = Node(self.name_)
        self.matrix = cmds.getAttr(self.name_ + ".worldMatrix[0]")

    def world_pivots(self):
        return (cmds.xform(self.name_, query=True, worldSpace=True, rotatePivot=True),
                cmds.xform(self.name_, query=True, worldSpace=True, scalePivot=True))

    def test_both_world_and_undo(self):
        """既定は両方のピボットをワールド原点へ移し、姿勢を変えない。1回の Undo で戻る。"""
        cmds.flushUndo()
        self.assertIs(self.node.setPivot((0, 0, 0), ws=True, kind="both"), self.node)
        rotate_pivot, scale_pivot = self.world_pivots()
        self.assertSequenceAlmostEqual(rotate_pivot, [0, 0, 0])
        self.assertSequenceAlmostEqual(scale_pivot, [0, 0, 0])
        self.assertSequenceAlmostEqual(cmds.getAttr(self.name_ + ".worldMatrix[0]"), self.matrix)
        self.assertSequenceAlmostEqual(cmds.getAttr(self.name_ + ".translate")[0], [0, 0, 0])
        cmds.undo()
        rotate_pivot, _ = self.world_pivots()
        self.assertSequenceAlmostEqual(rotate_pivot, [1, 2, 3])

    def test_kind_and_object_space(self):
        """kind=rotate は回転ピボットだけ、ws=False は object 空間の原点へ移す。"""
        self.node.setPivot((0, 0, 0), ws=True, kind="rotate")
        rotate_pivot, scale_pivot = self.world_pivots()
        self.assertSequenceAlmostEqual(rotate_pivot, [0, 0, 0])
        self.assertSequenceAlmostEqual(scale_pivot, [4, 5, 6])
        self.node.setPivot((0, 0, 0), ws=False, kind="scale")
        self.assertSequenceAlmostEqual(
            cmds.xform(self.name_, query=True, objectSpace=True, scalePivot=True), [0, 0, 0])
        self.assertSequenceAlmostEqual(cmds.getAttr(self.name_ + ".worldMatrix[0]"), self.matrix)

    def test_fast_matches_and_is_not_recorded(self):
        """fast=True も同じ結果で、Undo に記録しない。"""
        cmds.flushUndo()
        self.node.setPivot((0, 0, 0), ws=True, fast=True, kind="both")
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        rotate_pivot, scale_pivot = self.world_pivots()
        self.assertSequenceAlmostEqual(rotate_pivot, [0, 0, 0])
        self.assertSequenceAlmostEqual(scale_pivot, [0, 0, 0])
        self.assertSequenceAlmostEqual(cmds.getAttr(self.name_ + ".worldMatrix[0]"), self.matrix)

    def test_errors(self):
        """kind・ws の不正は ValueError、Joint・fast の型は TypeError。"""
        with self.assertRaisesRegex(ValueError, "kind"):
            self.node.setPivot((0, 0, 0), ws=True, kind="both2")
        with self.assertRaises(ValueError):
            self.node.setPivot((0, 0, 0), ws=1, kind="both")
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            self.node.setPivot((0, 0, 0), ws=True, fast=1, kind="both")
        with self.assertRaisesRegex(TypeError, "Joint does not support"):
            Node(self.make("joint", "jointPivot")).setPivot((0, 0, 0), ws=True, kind="both")
        with self.assertRaisesRegex(TypeError, "Specify only one"):
            self.node.setPivot((0, 0, 0), worldSpace=True, ws=True, kind="both")

    def test_locked_pivot(self):
        """ロックされたピボットの成分は通常・fast とも RuntimeError で、何も変えない。"""
        cmds.setAttr(self.name_ + ".rotatePivotX", lock=True)
        before = [cmds.getAttr(self.name_ + "." + name)[0]
                  for name in ("rotatePivot", "rotatePivotTranslate", "scalePivot", "scalePivotTranslate")]
        cmds.flushUndo()
        for fast in (True, False):
            for kind in ("rotate", "both"):
                with self.assertRaisesRegex(RuntimeError, "locked or connected"):
                    self.node.setPivot((0, 0, 0), ws=True, kind=kind, fast=fast)
                with self.assertRaisesRegex(RuntimeError, "locked or connected"):
                    self.node.setPivot((0, 0, 0), kind=kind, fast=fast)
            with self.assertRaisesRegex(RuntimeError, "locked or connected"):
                self.node.centerPivot(fast=fast)
        after = [cmds.getAttr(self.name_ + "." + name)[0]
                 for name in ("rotatePivot", "rotatePivotTranslate", "scalePivot", "scalePivotTranslate")]
        self.assertEqual(after, before)
        self.assertSequenceAlmostEqual(cmds.getAttr(self.name_ + ".worldMatrix[0]"), self.matrix)
        # ロックされていない種類は変更できる。
        self.node.setPivot((0, 0, 0), ws=True, kind="scale")
        _, scale_pivot = self.world_pivots()
        self.assertSequenceAlmostEqual(scale_pivot, [0, 0, 0])

    def test_locked_pivot_translate(self):
        """preserve=True で書き換える補償値のロックも通常・fast とも拒否し、preserve=False は通る。"""
        cmds.setAttr(self.name_ + ".rotatePivotTranslateY", lock=True)
        for fast in (True, False):
            with self.assertRaisesRegex(RuntimeError, "locked or connected"):
                self.node.setPivot((0, 0, 0), ws=True, fast=fast)
        translate_before = cmds.getAttr(self.name_ + ".rotatePivotTranslate")[0]
        self.assertSequenceAlmostEqual(cmds.getAttr(self.name_ + ".worldMatrix[0]"), self.matrix)
        # 補償値を書かない preserve=False はロックに当たらない。
        self.node.setPivot((0, 0, 0), ws=False, preserve=False)
        self.assertSequenceAlmostEqual(cmds.getAttr(self.name_ + ".rotatePivot")[0], [0, 0, 0])
        self.assertEqual(cmds.getAttr(self.name_ + ".rotatePivotTranslate")[0], translate_before)


class MakeIdentityTest(_SpecCase):
    """makeIdentity は cmds.makeIdentity へ委譲する。"""

    def setUp(self):
        super().setUp()
        self.name_ = self.make("transform", "freeze")
        cmds.setAttr(self.name_ + ".translate", 1, 2, 3)
        cmds.setAttr(self.name_ + ".rotate", 10, 0, 0)
        self.node = Node(self.name_)

    def test_apply_translate_only(self):
        """apply・t の指定はそのまま渡り、指定しないチャンネルは残る。1回の Undo で戻る。"""
        cmds.flushUndo()
        self.assertIs(self.node.makeIdentity(apply=True, t=True), self.node)
        self.assertEqual(cmds.getAttr(self.name_ + ".translate")[0], (0.0, 0.0, 0.0))
        self.assertEqual(cmds.getAttr(self.name_ + ".rotate")[0], (10.0, 0.0, 0.0))
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.name_ + ".translate")[0], (1.0, 2.0, 3.0))

    def test_without_apply_resets(self):
        """apply を省くと Maya の既定どおり姿勢を単位へ戻す(フリーズではない)。"""
        self.node.makeIdentity()
        self.assertEqual(cmds.getAttr(self.name_ + ".translate")[0], (0.0, 0.0, 0.0))
        self.assertEqual(cmds.getAttr(self.name_ + ".rotate")[0], (0.0, 0.0, 0.0))
        self.assertSequenceAlmostEqual(cmds.getAttr(self.name_ + ".worldMatrix[0]"), list(om2.MMatrix()))

    def test_errors(self):
        """長短名の同時指定は TypeError、削除済みは RuntimeError。"""
        with self.assertRaisesRegex(TypeError, "Specify only one of 'translate' and 't'"):
            self.node.makeIdentity(apply=True, t=True, translate=True)
        cmds.delete(self.name_)
        with self.assertRaisesRegex(RuntimeError, "invalid transform"):
            self.node.makeIdentity(apply=True)


class MirrorGeometryTest(_SpecCase):
    """mirrorGeometry は直下の Shape の mirror へ委譲する。"""

    def setUp(self):
        super().setUp()
        self.cube = cmds.polyCube(name=self.name("cube"), constructionHistory=False)[0]
        cmds.move(1, 0, 0, self.cube + ".vtx[*]", relative=True)
        cmds.setAttr(self.cube + ".translate", 5, 0, 0)
        self.node = Node(self.cube)
        self.before = cmds.xform(self.cube + ".vtx[0]", query=True, objectSpace=True, translation=True)

    def vertex(self):
        return cmds.xform(self.cube + ".vtx[0]", query=True, objectSpace=True, translation=True)

    def test_object_space_and_undo(self):
        """既定は object 空間の X 反転で、Transform は変えない。1回の Undo で戻る。"""
        cmds.flushUndo()
        self.assertIs(self.node.mirrorGeometry(), self.node)
        self.assertSequenceAlmostEqual(self.vertex(), [-self.before[0], self.before[1], self.before[2]])
        self.assertEqual(cmds.getAttr(self.cube + ".translate")[0], (5.0, 0.0, 0.0))
        cmds.undo()
        self.assertSequenceAlmostEqual(self.vertex(), self.before)

    def test_world_space_pivot(self):
        """ws=True はワールド空間の pivot を中心に反転する。"""
        self.node.mirrorGeometry(axis="X", ws=True, pivot=(5, 0, 0))
        self.assertSequenceAlmostEqual(self.vertex(), [-self.before[0], self.before[1], self.before[2]])

    def test_fast(self):
        """fast=True は Undo に記録しない。"""
        cmds.flushUndo()
        self.node.mirrorGeometry(axis="y", fast=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertSequenceAlmostEqual(self.vertex(), [self.before[0], -self.before[1], self.before[2]])

    def test_errors(self):
        """軸・空間は ValueError、fast は TypeError、mirror の無い Shape は AttributeError。"""
        with self.assertRaises(ValueError):
            self.node.mirrorGeometry(axis="q")
        with self.assertRaises(ValueError):
            self.node.mirrorGeometry(ws=1)
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            self.node.mirrorGeometry(fast=1)
        locator = cmds.spaceLocator(name=self.name("loc"))[0]
        with self.assertRaises(AttributeError):
            Node(locator).mirrorGeometry()
        self.assertSequenceAlmostEqual(self.vertex(), self.before)

    def test_without_shapes(self):
        """Shape が無ければ何もせず自身を返す。"""
        empty = Node(self.make("transform", "empty"))
        self.assertIs(empty.mirrorGeometry(), empty)


class HierarchyQueryTest(_SpecCase):
    """getRoot・getSiblings・getBoundingBox。"""

    def test_root_and_siblings(self):
        """getRoot はワールド直下の祖先、getSiblings は同じ親の Transform(自身・Shape を除く)。"""
        root = self.make("transform", "root")
        middle = self.make("transform", "middle", parent=root)
        first = self.make("transform", "first", parent=middle)
        second = self.make("joint", "second", parent=middle)
        self.make("mesh", "shape", parent=middle)
        self.assertEqual(Node(first).getRoot(), Node(root))
        self.assertEqual(Node(root).getRoot(), Node(root))
        self.assertEqual(Node(first).getSiblings(), [Node(second)])
        self.assertNotIn(Node(root), Node(root).getSiblings())
        self.assertIn(Node(root), Node(self.make("transform", "otherRoot")).getSiblings())

    def test_bounding_box_world_applies_parent(self):
        """ws=False は親を含まず、ws=True は親のワールドマトリクスも適用する。"""
        parent = self.make("transform", "bboxParent")
        cmds.setAttr(parent + ".translate", 10, 0, 0)
        cube = cmds.polyCube(name=self.name("bboxCube"), constructionHistory=False)[0]
        cube = cmds.parent(cube, parent, relative=True)[0]
        cmds.setAttr(cube + ".translate", 1, 0, 0)
        node = Node(cube)
        local = node.getBoundingBox()
        world = node.getBoundingBox(ws=True)
        self.assertAlmostEqual(local.center.x, 1.0)
        self.assertAlmostEqual(world.center.x, 11.0)
        self.assertSequenceAlmostEqual(
            [world.min.x, world.min.y, world.min.z, world.max.x, world.max.y, world.max.z],
            cmds.exactWorldBoundingBox(cube))


class TransformsBulkTest(_SpecCase):
    """Transforms の同名メソッド。"""

    def test_bulk_queries_and_reset_pivot(self):
        """照会はリスト、setPivot は自身を返す。Joint を含むと番号付きで止まる。"""
        names = [self.make("transform", "bulk#") for _ in range(2)]
        for name in names:
            cmds.setAttr(name + ".shear", 0.25, 0, 0)
            cmds.xform(name, worldSpace=True, rotatePivot=(1, 1, 1))
        nodes = Transforms(names)
        self.assertEqual([list(value) for value in nodes.getShear()], [[0.25, 0.0, 0.0]] * 2)
        self.assertEqual(len(nodes.getQuaternion(r=False)), 2)
        self.assertEqual(len(nodes.getRotate(ws=True, order=0)), 2)
        self.assertIs(nodes.setPivot((0, 0, 0), ws=True, kind="rotate"), nodes)
        for name in names:
            self.assertSequenceAlmostEqual(cmds.xform(name, query=True, worldSpace=True, rotatePivot=True), [0, 0, 0])
        mixed = Transforms(names + [self.make("joint", "bulkJoint")])
        with self.assertRaisesRegex(RuntimeError, r"Transforms\.setPivot failed at item 2"):
            mixed.setPivot((0, 0, 0), ws=True, kind="both")


if __name__ == "__main__":
    unittest.main()
