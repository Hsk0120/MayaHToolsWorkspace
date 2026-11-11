"""12.4.0 で足した Transform・DagNode・Joint・IkHandle のメソッドと createGroup を確かめる。

- Transform.translateBy/rotateBy/scaleBy: cmds.move/rotate/scale(relative)と同じ結果、Undo 1回、不正入力。
- Transform.getLimits: setLimits・cmds.transformLimits と突き合わせ、setLimits へ渡して写せる。
- Transform.zeroTransformPivots: xform(zeroTransformPivots)と同じ結果で姿勢を保つ。ロックは更新前に拒否。
- Transform.ungroup: 子を親・ワールドへ移し、自身を消す。Undo 1回。
- DagNode.getCommonAncestor/getBoundingBoxCorners/isInstanced/getInstanceIndex。
- Joint.assumePreferredAngles/getDegreesOfFreedom/setDegreesOfFreedom。
- IkHandle.getSolver/setSolver/snapToEffector。
- cmds.createGroup: 子・親・ワールド・空のグループ、短縮名、選択を変えない、Undo 1回。
"""

import math
import sys
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from support.specCase import NamespaceCase


class _Case(NamespaceCase):
    """ノードを作る補助。"""

    PREFIX = "mlibV124dag_"

    def transform(self, text="node#", parent=None):
        """transform を作り、ラッパーを返す。"""
        return mlib.getNode(cmds.ls(self.make("transform", text, parent), long=True)[0])

    def chain(self):
        """3つの joint の連鎖を作り、名前のリストを返す。"""
        cmds.select(clear=True)
        names = [cmds.joint(name=self.name(f"j{i}"), position=position)
                 for i, position in enumerate(((0, 0, 0), (0, 2, 1), (0, 4, 0)))]
        cmds.select(clear=True)
        return [cmds.ls(name, long=True)[0] for name in names]

    def assertRaisesNoChange(self, error, read, call):
        """call が error を送出し、read の値を変えないことを確かめる。"""
        before = read()
        with self.assertRaises(error):
            call()
        self.assertEqual(read(), before)


class RelativeTransformTest(_Case):
    """translateBy・rotateBy・scaleBy。"""

    def setUp(self):
        super().setUp()
        self.parent = self.transform("parent#")
        cmds.setAttr(self.parent.getFullName() + ".r", 10, 40, -20)
        # 親の非一様なスケールはワールドのマトリクスにシアーを生み、ワールド軸の回転が定まらないため一様にする。
        cmds.setAttr(self.parent.getFullName() + ".s", 2, 2, 2)
        self.node = self.transform("node#", self.parent.getFullName())
        self.reference = self.transform("reference#", self.parent.getFullName())
        for node in (self.node, self.reference):
            cmds.setAttr(node.getFullName() + ".t", 1, 2, 3)
            cmds.setAttr(node.getFullName() + ".r", 10, 20, 30)
            cmds.setAttr(node.getFullName() + ".ro", 2)
            cmds.setAttr(node.getFullName() + ".s", 1, 2, 3)

    def values(self, node, attribute):
        return cmds.getAttr(node.getFullName() + "." + attribute)[0]

    def test_translate_by_matches_cmds_move(self):
        """translateBy は親の空間・ワールドの軸で cmds.move(relative) と同じ translate になる。"""
        ref = self.reference.getFullName()
        self.assertIs(self.node.translateBy((1, -2, 0.5)), self.node)
        cmds.move(1, -2, 0.5, ref, relative=True, localSpace=True)
        self.assertSequenceAlmostEqual(self.values(self.node, "t"), self.values(self.reference, "t"))
        self.node.translateBy((3, 0, 1), ws=True)
        cmds.move(3, 0, 1, ref, relative=True, worldSpace=True)
        self.assertSequenceAlmostEqual(self.values(self.node, "t"), self.values(self.reference, "t"))

    def test_rotate_by_matches_cmds_rotate(self):
        """rotateBy はローカル軸・ワールドの軸で cmds.rotate(relative) と同じ向きになる(rotateOrder=zxy)。"""
        ref = self.reference.getFullName()
        self.node.rotateBy((5, 15, 25))
        cmds.rotate(5, 15, 25, ref, relative=True, objectSpace=True)
        self.assertSequenceAlmostEqual(self.values(self.node, "r"), self.values(self.reference, "r"), places=6)
        self.node.rotateBy((math.radians(20), 0, math.radians(-10)), worldSpace=True, unit="rad")
        cmds.rotate(20, 0, -10, ref, relative=True, worldSpace=True)
        self.assertSequenceAlmostEqual(cmds.xform(self.node.getFullName(), query=True, matrix=True, worldSpace=True),
                                       cmds.xform(ref, query=True, matrix=True, worldSpace=True), places=6)

    def test_rotate_by_accumulates(self):
        """90度ずつ4回回すと rotate は360度へ進む(等価解を今の値の近くに選ぶ)。"""
        node = self.transform("free#")
        for _ in range(4):
            node.rotateBy((0, 0, 90))
        self.assertAlmostEqual(cmds.getAttr(node.getFullName() + ".rz"), 360.0, places=6)
        quarter = om2.MEulerRotation(0.0, math.radians(90), 0.0)
        node.rotateBy(quarter)
        self.assertAlmostEqual(cmds.getAttr(node.getFullName() + ".ry"), 90.0, places=6)

    def test_scale_by(self):
        """scaleBy は scale へ倍率を掛ける。数値1つは XYZ 共通。"""
        self.node.scaleBy((2, 0.5, 1))
        self.assertSequenceAlmostEqual(self.values(self.node, "s"), (2, 1, 3))
        self.node.scaleBy(3)
        self.assertSequenceAlmostEqual(self.values(self.node, "s"), (6, 3, 9))

    def test_undo_one_step(self):
        """各メソッドは Undo 1 回で戻る。"""
        name = self.node.getFullName()
        before = cmds.xform(name, query=True, matrix=True)
        for label, call in (("translateBy", lambda: self.node.translateBy((1, 2, 3), ws=True)),
                            ("rotateBy", lambda: self.node.rotateBy((10, 0, 5), ws=True)),
                            ("scaleBy", lambda: self.node.scaleBy((2, 2, 2)))):
            with self.subTest(label):
                self.flushUndo()
                call()
                self.assertUndoesInOneStep(
                    lambda: self.assertSequenceAlmostEqual(cmds.xform(name, query=True, matrix=True), before),
                    lambda: self.assertNotEqual(cmds.xform(name, query=True, matrix=True), before))

    def test_invalid_input(self):
        """不正な入力・ロック・削除済みノードは例外で、値を変えない。"""
        name = self.node.getFullName()

        def read():
            return cmds.xform(name, query=True, matrix=True)
        for label, error, call in (
                ("translate 2", ValueError, lambda: self.node.translateBy((1, 2))),
                ("translate str", TypeError, lambda: self.node.translateBy("abc")),
                ("translate nan", ValueError, lambda: self.node.translateBy((1, float("nan"), 0))),
                ("translate ws twice", TypeError, lambda: self.node.translateBy((1, 0, 0), True, ws=True)),
                ("translate ws int", TypeError, lambda: self.node.translateBy((1, 0, 0), worldSpace=1)),
                ("rotate unit", ValueError, lambda: self.node.rotateBy((1, 0, 0), unit="turn")),
                ("rotate 4", ValueError, lambda: self.node.rotateBy((1, 0, 0, 0))),
                ("scale bool", TypeError, lambda: self.node.scaleBy(True)),
                ("scale inf", ValueError, lambda: self.node.scaleBy(float("inf")))):
            with self.subTest(label):
                self.assertRaisesNoChange(error, read, call)
        cmds.setAttr(name + ".tx", lock=True)
        cmds.setAttr(name + ".rz", lock=True)
        cmds.setAttr(name + ".sy", lock=True)
        for label, call in (("translate", lambda: self.node.translateBy((1, 0, 0))),
                            ("rotate", lambda: self.node.rotateBy((0, 0, 5))),
                            ("scale", lambda: self.node.scaleBy(2))):
            with self.subTest(locked=label):
                self.assertRaisesNoChange(RuntimeError, read, call)
        free = self.transform("gone#")
        cmds.delete(free.getFullName())
        for call in (lambda: free.translateBy((1, 0, 0)), lambda: free.rotateBy((1, 0, 0)), lambda: free.scaleBy(2)):
            with self.assertRaises(RuntimeError):
                call()


class LimitsTest(_Case):
    """getLimits。"""

    def test_get_limits_round_trip(self):
        """setLimits で書いた値を同じ形で返し、別ノードへ写せる。無効な側は None。"""
        node = self.transform()
        node.setLimits(translateX=(-1, 2), rotateZ=(-45, None), scaleY=(None, 3))
        limits = node.getLimits()
        self.assertEqual(sorted(limits), sorted(prefix + axis for prefix in ("translate", "rotate", "scale")
                                                for axis in "XYZ"))
        self.assertEqual(limits["translateX"], (-1.0, 2.0))
        self.assertEqual(limits["rotateZ"][1], None)
        self.assertAlmostEqual(limits["rotateZ"][0], -45.0)
        self.assertEqual(limits["scaleY"], (None, 3.0))
        self.assertEqual(limits["translateY"], (None, None))
        self.assertAlmostEqual(node.getLimits(unit="rad")["rotateZ"][0], math.radians(-45))
        other = self.transform("other#")
        other.setLimits(**limits)
        self.assertEqual(other.getLimits(), limits)

    def test_matches_transform_limits_in_other_units(self):
        """UI の単位(mm・ラジアン)に依らず cm・度で返す。"""
        node = self.transform()
        cmds.transformLimits(node.getFullName(), translationY=(-2, 5), enableTranslationY=(True, True),
                             rotationX=(-30, 60), enableRotationX=(True, True))
        cmds.currentUnit(linear="mm", angle="rad")
        limits = node.getLimits()
        self.assertSequenceAlmostEqual(limits["translateY"], (-2.0, 5.0))
        self.assertSequenceAlmostEqual(limits["rotateX"], (-30.0, 60.0))

    def test_invalid(self):
        node = self.transform()
        with self.assertRaises(ValueError):
            node.getLimits(unit="turn")
        cmds.delete(node.getFullName())
        with self.assertRaises(RuntimeError):
            node.getLimits()


class PivotAndUngroupTest(_Case):
    """zeroTransformPivots・ungroup。"""

    def pivoted(self, text):
        node = self.transform(text)
        name = node.getFullName()
        cmds.setAttr(name + ".t", 1, 2, 3)
        cmds.setAttr(name + ".r", 10, 20, 30)
        cmds.xform(name, rotatePivot=(1, 1, 1), scalePivot=(2, 0, 0), preserve=True)
        cmds.setAttr(name + ".s", 1, 2, 1)
        return node

    def test_zero_transform_pivots_matches_xform(self):
        """xform(zeroTransformPivots) と同じアトリビュートになり、ワールドのマトリクスを保つ。Undo 1回。"""
        node, reference = self.pivoted("node#"), self.pivoted("reference#")
        name = node.getFullName()
        matrix = cmds.xform(name, query=True, matrix=True, worldSpace=True)
        cmds.xform(reference.getFullName(), zeroTransformPivots=True)
        self.flushUndo()
        self.assertIs(node.zeroTransformPivots(), node)
        for attribute in ("t", "rp", "sp", "rpt", "spt"):
            with self.subTest(attribute):
                self.assertSequenceAlmostEqual(cmds.getAttr(name + "." + attribute)[0],
                                               cmds.getAttr(reference.getFullName() + "." + attribute)[0])
        self.assertSequenceAlmostEqual(cmds.xform(name, query=True, matrix=True, worldSpace=True), matrix)
        self.assertSequenceAlmostEqual(cmds.getAttr(name + ".rp")[0], (0, 0, 0))
        self.assertUndoesInOneStep(
            lambda: self.assertSequenceAlmostEqual(cmds.getAttr(name + ".rp")[0], (1, 1, 1)),
            lambda: self.assertSequenceAlmostEqual(cmds.getAttr(name + ".rp")[0], (0, 0, 0)))

    def test_zero_transform_pivots_locked(self):
        """translate のロックは更新前に拒否し、何も変えない。削除済みは RuntimeError。"""
        node = self.pivoted("node#")
        name = node.getFullName()
        cmds.setAttr(name + ".tx", lock=True)
        self.assertRaisesNoChange(RuntimeError, lambda: cmds.getAttr(name + ".rp")[0], node.zeroTransformPivots)
        cmds.setAttr(name + ".tx", lock=False)
        cmds.delete(name)
        with self.assertRaises(RuntimeError):
            node.zeroTransformPivots()

    def test_ungroup(self):
        """子を親の下へ移して自身を消し、ワールドの位置を保つ。world=True はワールド直下。Undo 1回。"""
        top = self.transform("top#")
        group = self.transform("group#", top.getFullName())
        cmds.setAttr(group.getFullName() + ".t", 1, 0, 0)
        a = self.transform("a#", group.getFullName())
        b = self.transform("b#", group.getFullName())
        cmds.setAttr(a.getFullName() + ".t", 0, 2, 0)
        world_a = cmds.xform(a.getFullName(), query=True, translation=True, worldSpace=True)
        group_name = group.getFullName()
        self.flushUndo()
        children = group.ungroup()
        self.assertEqual([child.getUuid() for child in children], [a.getUuid(), b.getUuid()])
        self.assertFalse(cmds.objExists(group_name))
        self.assertEqual(children[0].getParent().getUuid(), top.getUuid())
        self.assertSequenceAlmostEqual(cmds.xform(children[0].getFullName(), query=True, translation=True,
                                                  worldSpace=True), world_a)
        self.assertUndoesInOneStep(lambda: self.assertTrue(cmds.objExists(group_name)),
                                   lambda: self.assertFalse(cmds.objExists(group_name)))
        group = mlib.getNode(group_name)
        children = group.ungroup(world=True)
        self.assertTrue(all(child.getParent() is None for child in children))
        with self.assertRaises(TypeError):
            top.ungroup(world=1)
        with self.assertRaises(RuntimeError):
            group.ungroup()


class DagQueryTest(_Case):
    """getCommonAncestor・getBoundingBoxCorners・isInstanced・getInstanceIndex。"""

    def test_common_ancestor(self):
        root = self.transform("root#")
        hip = self.transform("hip#", root.getFullName())
        hand = self.transform("hand#", self.transform("arm#", hip.getFullName()).getFullName())
        foot = self.transform("foot#", self.transform("leg#", hip.getFullName()).getFullName())
        alone = self.transform("alone#")
        self.assertEqual(hand.getCommonAncestor(foot).getUuid(), hip.getUuid())
        self.assertEqual(hand.getCommonAncestor(foot.getFullName()).getUuid(), hip.getUuid())
        self.assertIs(hip.getCommonAncestor(hand), hip)
        self.assertEqual(hand.getCommonAncestor(root).getUuid(), root.getUuid())
        self.assertIs(hand.getCommonAncestor(hand), hand)
        self.assertIsNone(hand.getCommonAncestor(alone))
        network = cmds.createNode("network", name=self.name("net#"))
        with self.assertRaises(TypeError):
            hand.getCommonAncestor(network)
        cmds.delete(alone.getFullName())
        with self.assertRaises(RuntimeError):
            hand.getCommonAncestor(alone)

    def test_bounding_box_corners(self):
        """8隅は getBoundingBox の最小・最大の組み合わせ(ローカル・ワールドとも cmds.exactWorldBoundingBox と一致)。"""
        cube = cmds.polyCube(name=self.name("cube#"), width=2, height=4, depth=6, constructionHistory=False)[0]
        cmds.setAttr(cube + ".t", 1, 2, 3)
        cmds.setAttr(cube + ".r", 0, 45, 0)
        node = mlib.getNode(cube)
        corners = node.getBoundingBoxCorners(ws=True)
        self.assertEqual(len(corners), 8)
        self.assertIsInstance(corners[0], mlib.Vector)
        xmin, ymin, zmin, xmax, ymax, zmax = cmds.exactWorldBoundingBox(cube)
        self.assertSequenceAlmostEqual(corners[0], (xmin, ymin, zmin), places=5)
        self.assertSequenceAlmostEqual(corners[1], (xmin, ymin, zmax), places=5)
        self.assertSequenceAlmostEqual(corners[7], (xmax, ymax, zmax), places=5)
        local = node.getShape().getBoundingBoxCorners()
        self.assertSequenceAlmostEqual(local[0], (-1, -2, -3))
        self.assertSequenceAlmostEqual(local[7], (1, 2, 3))
        with self.assertRaises(TypeError):
            node.getBoundingBoxCorners(True, ws=True)
        cmds.delete(cube)
        with self.assertRaises(RuntimeError):
            node.getBoundingBoxCorners()

    def test_instances(self):
        cube = cmds.polyCube(name=self.name("cube#"), constructionHistory=False)[0]
        group = cmds.group(cube, name=self.name("grp#"))
        single = self.transform("single#")
        self.assertIs(single.isInstanced(), False)
        self.assertEqual(single.getInstanceIndex(), 0)
        cmds.instance(group, name=self.name("inst#"))
        shape = mlib.getNode(cmds.listRelatives(cube, shapes=True, fullPath=True)[0])
        instances = shape.getInstances()
        self.assertIs(shape.isInstanced(), True)
        self.assertEqual(sorted(node.getInstanceIndex() for node in instances), [0, 1])
        cmds.delete(single.getFullName())
        with self.assertRaises(RuntimeError):
            single.isInstanced()
        with self.assertRaises(RuntimeError):
            single.getInstanceIndex()


class JointTest(_Case):
    """assumePreferredAngles・DegreesOfFreedom。"""

    def test_assume_preferred_angles(self):
        j0, j1, _ = self.chain()
        cmds.setAttr(j0 + ".preferredAngle", 5, 0, 0)
        cmds.setAttr(j1 + ".preferredAngle", 10, 20, 30)
        cmds.setAttr(j0 + ".r", 1, 1, 1)
        cmds.setAttr(j1 + ".r", 2, 2, 2)
        node = mlib.getNode(j0)
        self.flushUndo()
        self.assertIs(node.assumePreferredAngles(children=False), node)
        self.assertSequenceAlmostEqual(cmds.getAttr(j0 + ".r")[0], (5, 0, 0))
        self.assertSequenceAlmostEqual(cmds.getAttr(j1 + ".r")[0], (2, 2, 2))
        self.assertUndoesInOneStep(lambda: self.assertSequenceAlmostEqual(cmds.getAttr(j0 + ".r")[0], (1, 1, 1)),
                                   lambda: None)
        self.flushUndo()
        node.assumePreferredAngles()
        self.assertSequenceAlmostEqual(cmds.getAttr(j1 + ".r")[0], (10, 20, 30))
        self.assertUndoesInOneStep(lambda: self.assertSequenceAlmostEqual(cmds.getAttr(j1 + ".r")[0], (2, 2, 2)),
                                   lambda: None)
        with self.assertRaises(TypeError):
            node.assumePreferredAngles(children=1)
        cmds.delete(j0)
        with self.assertRaises(RuntimeError):
            node.assumePreferredAngles()

    def test_degrees_of_freedom(self):
        j0, j1, _ = self.chain()
        node = mlib.getNode(j1)
        self.assertEqual(node.getDegreesOfFreedom(), "xyz")
        self.flushUndo()
        self.assertIs(node.setDegreesOfFreedom("ZX"), node)
        self.assertEqual(node.getDegreesOfFreedom(), "xz")
        self.assertEqual(cmds.joint(j1, query=True, degreeOfFreedom=True), "xz")
        self.assertUndoesInOneStep(lambda: self.assertEqual(node.getDegreesOfFreedom(), "xyz"), lambda: None)
        node.setDegreesOfFreedom("")
        self.assertEqual(node.getDegreesOfFreedom(), "")
        for value, error in ((("x",), TypeError), (None, TypeError), ("xw", ValueError), ("xx", ValueError)):
            with self.subTest(value=value):
                self.assertRaisesNoChange(error, node.getDegreesOfFreedom, lambda: node.setDegreesOfFreedom(value))
        cmds.setAttr(j1 + ".jointTypeY", lock=True)
        self.assertRaisesNoChange(RuntimeError, node.getDegreesOfFreedom, lambda: node.setDegreesOfFreedom("xyz"))
        cmds.setAttr(j1 + ".jointTypeY", lock=False)
        cmds.delete(j0)
        for call in (node.getDegreesOfFreedom, lambda: node.setDegreesOfFreedom("x")):
            with self.assertRaises(RuntimeError):
                call()


class IkHandleTest(_Case):
    """getSolver・setSolver・snapToEffector。"""

    def setUp(self):
        super().setUp()
        if not cmds.ls(type="ikSCsolver"):
            # 最初のソルバーノードは Undo で消えないため、Undo の確認の前に作っておく。
            cmds.createNode("ikSCsolver", name="ikSCsolver")
        self.joints = self.chain()
        self.handle = mlib.createIkHandle(self.joints[0], self.joints[2], solver="ikRPsolver",
                                          name=self.name("ikh#"))

    def test_solver(self):
        handle = self.handle
        self.assertEqual(handle.getSolver(), "ikRPsolver")
        self.assertEqual(handle.getSolver(), cmds.ikHandle(handle.getFullName(), query=True, solver=True))
        self.flushUndo()
        self.assertIs(handle.setSolver("ikSCsolver"), handle)
        self.assertEqual(handle.getSolver(), "ikSCsolver")
        self.assertUndoesInOneStep(lambda: self.assertEqual(handle.getSolver(), "ikRPsolver"), lambda: None)
        handle.setSolver("ikSpringSolver")
        self.assertEqual(handle.getSolver(), "ikSpringSolver")
        for value, error in ((None, TypeError), ("ikSplineSolver", ValueError), ("bogus", ValueError)):
            with self.subTest(value=value):
                self.assertRaisesNoChange(error, handle.getSolver, lambda: handle.setSolver(value))
        source = cmds.listConnections(handle.getFullName() + ".ikSolver", plugs=True)[0]
        cmds.disconnectAttr(source, handle.getFullName() + ".ikSolver")
        self.assertIsNone(handle.getSolver())

    def test_spline_handle_is_rejected(self):
        cmds.select(clear=True)
        joints = [cmds.joint(name=self.name(f"s{i}"), position=(0, i, 0)) for i in range(3)]
        cmds.select(clear=True)
        spline = mlib.createIkHandle(joints[0], joints[2], solver="ikSplineSolver", name=self.name("spl#"))
        self.assertEqual(spline.getSolver(), "ikSplineSolver")
        self.assertRaisesNoChange(ValueError, spline.getSolver, lambda: spline.setSolver("ikRPsolver"))

    def test_snap_to_effector(self):
        """届かない位置のハンドルをエフェクターの位置へ移す。Undo 1回。"""
        handle = self.handle
        name = handle.getFullName()
        cmds.setAttr(name + ".snapEnable", False)
        cmds.setAttr(name + ".t", 10, 10, 10)
        effector = handle.getEffector().getFullName()
        self.flushUndo()
        self.assertIs(handle.snapToEffector(), handle)
        self.assertSequenceAlmostEqual(cmds.xform(name, query=True, rotatePivot=True, worldSpace=True),
                                       cmds.xform(effector, query=True, rotatePivot=True, worldSpace=True), places=5)
        self.assertUndoesInOneStep(lambda: self.assertSequenceAlmostEqual(cmds.getAttr(name + ".t")[0], (10, 10, 10)),
                                   lambda: None)
        cmds.delete(name)
        for call in (handle.getSolver, lambda: handle.setSolver("ikSCsolver"), handle.snapToEffector):
            with self.assertRaises(RuntimeError):
                call()


class CreateGroupTest(_Case):
    """cmds.createGroup。"""

    CLEAR_SELECTION = True

    def test_group_children(self):
        """子を入れたグループを子の共通の親の下に作り、ピボットは子の中心。ワールドの位置を保つ。"""
        parent = self.transform("parent#")
        cmds.setAttr(parent.getFullName() + ".t", 5, 0, 0)
        a = self.transform("a#", parent.getFullName())
        b = self.transform("b#", parent.getFullName())
        cmds.setAttr(a.getFullName() + ".t", 2, 0, 0)
        cmds.setAttr(b.getFullName() + ".t", 0, 4, 0)
        world_a = cmds.xform(a.getFullName(), query=True, translation=True, worldSpace=True)
        cmds.select(parent.getFullName())
        group = mlib.createGroup([a, b.getFullName()], name=self.name("grp"))
        self.assertIsInstance(group, mlib.Transform)
        self.assertEqual(group.getName(), self.name("grp"))
        self.assertEqual(group.getParent().getUuid(), parent.getUuid())
        self.assertEqual([child.getUuid() for child in group.getChildren()], [a.getUuid(), b.getUuid()])
        self.assertSequenceAlmostEqual(cmds.xform(a.getFullName(), query=True, translation=True, worldSpace=True),
                                       world_a)
        self.assertSequenceAlmostEqual(cmds.xform(group.getFullName(), query=True, rotatePivot=True, worldSpace=True),
                                       (6, 2, 0))
        self.assertEqual(cmds.ls(selection=True, long=True), [parent.getFullName()])

    def test_parent_world_and_empty(self):
        """parent・world=True・空のグループ・短縮名。"""
        parent = self.transform("parent#")
        child = self.transform("child#", parent.getFullName())
        other = self.transform("other#")
        in_other = mlib.createGroup(child, parent=other)
        self.assertEqual(in_other.getParent().getUuid(), other.getUuid())
        at_world = mlib.createGroup(child, n=self.name("w#"), w=True)
        self.assertIsNone(at_world.getParent())
        empty = mlib.createGroup(name=self.name("empty#"), parent=parent)
        self.assertEqual(empty.getParent().getUuid(), parent.getUuid())
        self.assertEqual(empty.getChildren(shapes=True), [])
        self.assertIsNone(mlib.createGroup(n=self.name("top#")).getParent())
        self.assertEqual(cmds.ls(selection=True), [])

    def test_undo_one_step(self):
        child = self.transform("child#")
        child_name = child.getFullName()
        self.flushUndo()
        group = mlib.createGroup([child], name=self.name("grp"))
        self.assertUndoesInOneStep(
            lambda: (self.assertFalse(cmds.objExists(self.name("grp"))),
                     self.assertEqual(cmds.ls(child_name, long=True), [child_name])),
            lambda: self.assertEqual(child.getParent().getUuid(), group.getUuid()))

    def test_invalid(self):
        """不正な入力は何も作らない。"""
        child = self.transform("child#")
        network = cmds.createNode("network", name=self.name("net#"))
        gone = self.transform("gone#")
        cmds.delete(gone.getFullName())

        def read():
            return sorted(cmds.ls(self.ns + ":*", long=True))
        for label, error, call in (
                ("name twice", TypeError, lambda: mlib.createGroup(child, name="a", n="b")),
                ("world twice", TypeError, lambda: mlib.createGroup(child, world=True, w=True)),
                ("world int", TypeError, lambda: mlib.createGroup(child, world=1)),
                ("name int", TypeError, lambda: mlib.createGroup(child, name=3)),
                ("name empty", ValueError, lambda: mlib.createGroup(child, name="")),
                ("parent and world", ValueError, lambda: mlib.createGroup(child, parent=child, world=True)),
                ("same child", ValueError, lambda: mlib.createGroup([child, child.getFullName()])),
                ("not transform", TypeError, lambda: mlib.createGroup([network])),
                ("parent not transform", TypeError, lambda: mlib.createGroup([child], parent=network)),
                ("deleted child", RuntimeError, lambda: mlib.createGroup([gone])),
                ("missing", RuntimeError, lambda: mlib.createGroup(["noSuchNode_mlibV124"]))):
            with self.subTest(label):
                self.assertRaisesNoChange(error, read, call)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
