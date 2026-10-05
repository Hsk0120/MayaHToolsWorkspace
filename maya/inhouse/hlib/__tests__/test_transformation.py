"""補助成分を含むTransformationの値・取得・復元を検証する。"""
import copy
import math
from pathlib import Path
import sys
import unittest
import maya.cmds as cmds
import maya.api.OpenMaya as om2
from hlib.maths import Transformation, Matrix, EulerRotation, Quaternion
from hlib.nodes import Node, Transforms
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "external" / "cymel" / "python"))
from cymel import core as cy


class TransformationTest(unittest.TestCase):
    """独立したシーンでチャンネルと行列を比較する。"""

    def setUp(self):
        """専用Mayaのシーンを初期化する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg")

    def node(self, joint=False):
        """親・負スケール・補助回転・ピボットを持つノードを作る。"""
        parent = cmds.createNode("transform")
        cmds.setAttr(parent + ".translate", 7, -3, 5)
        cmds.setAttr(parent + ".rotate", 12, 31, -9)
        cmds.setAttr(parent + ".scale", 1.2, 2, .8)
        name = cmds.createNode("joint" if joint else "transform", parent=parent)
        cmds.setAttr(name + ".rotateOrder", 3)
        for attr, values in (("translate", (2, -4, 3)), ("rotate", (375, -21, 33)),
                             ("scale", (-1.1, 1.3, .9)), ("shear", (.1, .2, -.15)),
                             ("rotateAxis", (5, 13, -8))):
            cmds.setAttr(name + "." + attr, *values)
        if joint:
            cmds.setAttr(name + ".jointOrient", 21, -7, 32)
            cmds.connectAttr(parent + ".scale", name + ".inverseScale")
        else:
            for attr, values in (("rotatePivot", (1, 2, -1)), ("scalePivot", (-2, 1, 3)),
                                 ("rotatePivotTranslate", (.2, -.3, .1)), ("scalePivotTranslate", (.4, .2, -.1))):
                cmds.setAttr(name + "." + attr, *values)
        return Node(name)

    def assertMatrix(self, actual, expected):
        """行列の全成分を比較する。"""
        self.assertTrue(Matrix(actual).isEquivalent(Matrix(expected), tolerance=1e-7), (list(actual), list(expected)))

    def test_value_and_copy(self):
        """値の所有・短縮名・コピー・Euler周期を保持する。"""
        x = Transformation(t=(1, 2, 3), r=(math.tau + .2, .3, .4), ro=3,
                           ra=EulerRotation(.1, .2, .3), jo=EulerRotation(.3, .1, .2),
                           rp=(2, 3, 4), sp=(1, -2, 3), is_=(2, 3, 4), s=(-1, 2, 3))
        y = copy.deepcopy(x)
        self.assertTrue(x.isEquivalent(y))
        y.t.x = 10
        self.assertEqual(x.t.x, 1)
        self.assertEqual(x.ro, 3)
        self.assertAlmostEqual(x.r.x, math.tau + .2)
        x.m = x.m
        self.assertAlmostEqual(x.r.x, math.tau + .2)
        for actual, expected in zip(x.s, (-1, 2, 3)):
            self.assertAlmostEqual(actual, expected)
        with self.assertRaises(TypeError):
            Transformation(t=(0, 0, 0), translate=(0, 0, 0))
        with self.assertRaises(TypeError):
            hash(x)

    def test_local_matrix_and_cymel(self):
        """全回転順序・SSCの有無で合成行列をMayaと比較する。"""
        for joint in (False, True):
            node = self.node(joint)
            for order in range(6):
                node.plug("rotateOrder").set(order)
                for ssc in (False, True):
                    if joint:
                        node.plug("segmentScaleCompensate").set(ssc)
                    x = node.getX()
                    self.assertMatrix(x.m, node.getMatrix())
                    cx = cy.Transform(node.name()).getX()
                    self.assertMatrix(x.m, list(cx.m))
                    self.assertEqual(x.ro, cx.ro)
                    self.assertAlmostEqual(x.r.x, node.plug("rotate").get().x)

    def test_restore_and_undo(self):
        """補助成分とEuler周期を復元し、一回のUndoで変更前へ戻す。"""
        for joint in (False, True):
            node = self.node(joint)
            saved = node.getX()
            node.plug("rotate").set((0, 0, 0))
            node.plug("rotateAxis").set((0, 0, 0))
            if joint:
                node.plug("jointOrient").set((0, 0, 0))
            before = node.getX()
            self.assertIs(node.setX(saved), node)
            self.assertMatrix(node.getMatrix(), saved.m)
            self.assertEqual(tuple(node.getX().r), tuple(saved.r))
            cmds.undo()
            self.assertMatrix(node.getMatrix(), before.m)
            cmds.redo()
            self.assertMatrix(node.getMatrix(), saved.m)

    def test_world_and_parent_conversion(self):
        """非一様スケールの親とOPMを含むワールド姿勢を別階層へ適用する。"""
        for joint in (False, True):
            source = self.node(joint)
            source.plug("offsetParentMatrix").set(Matrix(translate=(2, 1, -3), rotate=EulerRotation(.1, .2, .3)))
            x = source.getX(ws=True)
            self.assertMatrix(x.m, source.getMatrix(ws=True))
            cx = cy.Transform(source.name()).getX(ws=True)
            self.assertMatrix(x.m, list(cx.m))
            # 負スケールとピボットを含む場合も元のtranslate位置をワールドへ変換する。
            expected_translation = Matrix(source.mpath().exclusiveMatrix()).transformPoint(source.getX().t)
            for actual, expected in zip(x.t, expected_translation):
                self.assertAlmostEqual(actual, expected, places=7)
            destination = self.node(joint)
            destination.parent().plug("translate").set((8, 2, 4))
            calculated = destination.setX(x, ws=True, get=True)
            self.assertIsInstance(calculated, Transformation)
            before = destination.getX()
            self.assertMatrix(before.m, destination.getMatrix())
            destination.setX(x, ws=True)
            self.assertMatrix(destination.getMatrix(ws=True), x.m)
            self.assertTrue(source.getX(ws=True).isEquivalent(x))

    def test_cross_type(self):
        """jointとtransformの間で姿勢を保ち、接続inverseScaleを維持する。"""
        for source_joint in (False, True):
            source = self.node(source_joint)
            target = self.node(not source_joint)
            x = source.getX()
            connection = cmds.listConnections(target.name() + ".inverseScale", s=True, d=False, p=True) if not source_joint else None
            target.setX(x)
            self.assertMatrix(target.getMatrix(), x.m)
            if not source_joint:
                self.assertEqual(cmds.listConnections(target.name() + ".inverseScale", s=True, d=False, p=True), connection)

    def test_safe_and_collection(self):
        """getで更新せず、safeはロック成分を維持する。"""
        node = self.node()
        before = node.getX()
        x = Transformation(t=(8, 9, 10))
        self.assertIsInstance(node.setX(x, get=True), Transformation)
        self.assertTrue(node.getX().isEquivalent(before))
        node.plug("rotateAxis").setLocked(True)
        node.plug("rotateOrder").setLocked(True)
        x.r = (.2, -.3, .4)
        node.setX(x, safe=True)
        self.assertMatrix(node.getMatrix(), x.m)
        self.assertTrue(node.plug("rotateAxis").isLocked())
        values = Transforms([node]).setX(x, get=True)
        self.assertIsInstance(values[0], Transformation)

    def test_invalid_matrix_is_atomic(self):
        """分解できない行列を拒否し、値を途中変更しない。"""
        x = Transformation(t=(2, 3, 4))
        before = x.copy()
        with self.assertRaises(ValueError):
            x.m = Matrix(scale=(0, 1, 1))
        self.assertTrue(x.isEquivalent(before))

    def test_units_and_negative_parent(self):
        """UI単位によらず内部単位で保存し、負スケール親へも適用する。"""
        node = self.node(True)
        node.parent().plug("scale").set((-2, 3, .8))
        before = node.getX()
        cmds.currentUnit(linear="m", angle="rad")
        self.assertTrue(node.getX().isEquivalent(before))
        world = node.getX(ws=True)
        target = self.node(True)
        target.setX(world, ws=True)
        self.assertMatrix(target.getMatrix(ws=True), world.m)

    def test_rotation_order_and_singular_parent(self):
        """順序変更は姿勢を保持し、特異な親へのワールド適用は更新前に拒否する。"""
        x = Transformation(r=(.2, .5, -.3))
        matrix = x.m
        x.ro = 5
        self.assertMatrix(x.m, matrix)
        x.q = Quaternion(EulerRotation(.1, .2, .3).asQuaternion())
        self.assertEqual(x.ro, 5)
        node = self.node()
        node.parent().plug("scale").set((0, 1, 1))
        before = node.getX()
        with self.assertRaises(ValueError):
            node.setX(x, ws=True)
        self.assertTrue(node.getX().isEquivalent(before))

    def test_openmaya_value_and_pivots(self):
        """MTransformationMatrixから取得可能なピボットと回転軸を保持する。"""
        node = self.node()
        tm = node.transformFn().transformation()
        value = Transformation(tm)
        self.assertMatrix(value.m, tm.asMatrix())
        self.assertEqual(tuple(value.rp), tuple(tm.rotatePivot(om2.MSpace.kTransform))[:3])
        euler = EulerRotation(.2, .4, .1, order=2)
        x = Transformation(r=euler, ro=5)
        self.assertEqual(x.ro, 5)
        self.assertMatrix(x.q.asMatrix(), euler.asMatrix())

    def test_no_inheritance_and_instance(self):
        """継承無効とインスタンスのパスごとの親行列を扱う。"""
        node = self.node()
        node.plug("inheritsTransform").set(False)
        self.assertMatrix(node.getX(ws=True).m, node.getMatrix(ws=True))
        node.setX(Transformation(t=(3, 4, 5)), ws=True)
        self.assertMatrix(node.getMatrix(ws=True), Matrix(translate=(3, 4, 5)))
        first = cmds.createNode("transform")
        second = cmds.createNode("transform")
        cmds.setAttr(first + ".tx", 2)
        cmds.setAttr(second + ".tx", 7)
        name = cmds.createNode("transform", parent=first)
        cmds.parent(name, second, add=True)
        a = Node("|" + first + "|" + name.split("|")[-1])
        b = Node("|" + second + "|" + name.split("|")[-1])
        self.assertAlmostEqual(a.getX(ws=True).t.x, 2)
        self.assertAlmostEqual(b.getX(ws=True).t.x, 7)
