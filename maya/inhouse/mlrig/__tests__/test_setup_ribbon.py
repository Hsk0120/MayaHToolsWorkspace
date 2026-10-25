"""Ribbonの帯の形と出力の行列を、OpenMayaで求めたサーフェスの点・接線・法線と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import Ribbon

#: コントロールの位置(cm)。根元から先端へ、上下に波打つ並び。
POINTS = [(0, 0, 0), (4, 1.5, 0.5), (8, -1, -0.5), (12, 0.5, 0), (16, 0, 0)]


def _matrix(plug):
    """matrixのplugの値。"""
    return om.MMatrix(cmds.getAttr(plug))


def _row(matrix, index):
    """行列の行(ローカル軸のワールドの向き)。"""
    return om.MVector(matrix[index * 4], matrix[index * 4 + 1], matrix[index * 4 + 2])


def _translate(matrix):
    """行列の位置。"""
    return om.MVector(matrix[12], matrix[13], matrix[14])


def _position(node):
    """ワールド位置。"""
    return om.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))


class RibbonTest(unittest.TestCase):
    """帯の形・出力の向き・ねじれ・幅・位置の変更・単位・引数検査・Undoを確認する。"""

    def setUp(self):
        """回転・移動した親の下に、5つのコントロールを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.parent = cmds.createNode("transform", name="ribbonParent")
        cmds.setAttr(self.parent + ".translate", 2, 30, -4)
        cmds.setAttr(self.parent + ".rotate", 15, -20, 10)
        self.controls = []
        for index, point in enumerate(POINTS):
            control = cmds.createNode("transform", name="ctrl{}".format(index), parent=self.parent)
            cmds.setAttr(control + ".translate", *point)
            self.controls.append(control)

    def surface(self, graph):
        """帯のサーフェスの関数セット。"""
        shape = str(graph.container) + "_surfaceShape"
        return om.MFnNurbsSurface(om.MSelectionList().add(shape).getDagPath(0))

    def check_frames(self, graph, count):
        """各出力が帯の中心線上にあり、X=Vの接線・Y=法線・Z=Uの接線の正規直交な右手系であることを確認する。"""
        fn = self.surface(graph)
        u0, u1, v0, v1 = fn.knotDomainInU + fn.knotDomainInV
        owner = str(graph.container)
        for index in range(count):
            u = cmds.getAttr("{}.position{}".format(owner, index))
            u, v = u0 + u * (u1 - u0), v0 + 0.5 * (v1 - v0)
            point = om.MVector(fn.getPointAtParam(u, v, om.MSpace.kWorld))
            tangent_u, tangent_v = fn.tangents(u, v, om.MSpace.kWorld)
            normal = fn.normal(u, v, om.MSpace.kWorld).normal()
            matrix = _matrix("{}.matrix{}".format(owner, index))
            x, y, z = (_row(matrix, axis) for axis in range(3))
            self.assertTrue(_translate(matrix).isEquivalent(point, 1e-3), index)
            for axis in (x, y, z):
                self.assertAlmostEqual(axis.length(), 1.0, places=4)
            self.assertAlmostEqual(x * y, 0.0, places=4)
            self.assertAlmostEqual(y * z, 0.0, places=4)
            self.assertTrue((x ^ y).isEquivalent(z, 1e-4), index)
            self.assertGreater(x * tangent_u.normal(), 0.9999, index)
            self.assertAlmostEqual(abs(y * normal), 1.0, places=4)
            # Zは幅の+側。断面は+側から-側へ向かうので、Vの接線とは逆向き。
            side = -tangent_v.normal()
            self.assertGreater(z * (side - x * (side * x)).normal(), 0.9999, index)

    def test_frames_follow_surface(self):
        """作成直後と、コントロールを動かした後の出力が帯の形と一致する。"""
        graph = Ribbon.create(self.controls, count=7, name="rib", width=2.0)
        self.check_frames(graph, 7)
        cmds.setAttr(self.controls[2] + ".translate", 8, 4, 2)
        cmds.setAttr(self.controls[4] + ".rotate", 0, 25, 0)
        cmds.setAttr(self.parent + ".rotateY", 70)
        self.check_frames(graph, 7)

    def test_ends_pass_through_controls(self):
        """両端の出力は両端のコントロールの位置にあり、端の幅の向きはコントロールのsideAxisに揃う。"""
        graph = Ribbon.create(self.controls, count=4, name="rib", sideAxis="z")
        owner = str(graph.container)
        cmds.setAttr(self.controls[-1] + ".rotateX", 60)
        for index, control in ((0, self.controls[0]), (3, self.controls[-1])):
            matrix = _matrix("{}.matrix{}".format(owner, index))
            self.assertTrue(_translate(matrix).isEquivalent(_position(control), 1e-4), index)
            world = _matrix(control + ".worldMatrix[0]")
            side = _row(world, 2).normal()
            along = _row(matrix, 0)
            expected = (side - along * (side * along)).normal()
            self.assertGreater(_row(matrix, 2) * expected, 0.9999, index)

    def test_twist_from_control(self):
        """先端のコントロールを沿う向きの軸でねじると、先端の出力も同じ角度だけねじれる。"""
        straight = [cmds.createNode("transform", name="s{}".format(i)) for i in range(3)]
        for index, node in enumerate(straight):
            cmds.setAttr(node + ".translateX", index * 5.0)
        graph = Ribbon.create(straight, count=5, name="ribTwist")
        owner = str(graph.container)
        for angle in (30.0, 90.0, 120.0, 150.0, -60.0):
            cmds.setAttr(straight[-1] + ".rotateX", angle)
            z = _row(_matrix(owner + ".matrix4"), 2)
            self.assertAlmostEqual(math.degrees(math.atan2(-z.y, z.z)), angle, places=3)
            # 根元と中間のコントロールの位置(U=0・0.5)ではねじれない。その間は3次の補間で少しずれる。
            for index in (0, 2):
                z = _row(_matrix("{}.matrix{}".format(owner, index)), 2)
                self.assertAlmostEqual(math.degrees(math.atan2(-z.y, z.z)), 0.0, places=3)
            # 中間と先端のコントロールの間の出力は、0度と先端の角度の間のねじれになる。
            z = _row(_matrix(owner + ".matrix3"), 2)
            twist = math.degrees(math.atan2(-z.y, z.z))
            self.assertGreater(abs(twist), 0.0)
            self.assertLess(abs(twist), abs(angle))
            self.assertGreater(twist * angle, 0.0)
        self.check_frames(graph, 5)

    def test_width_and_position(self):
        """widthを変えると帯の幅が変わり、positionを変えると出力が帯の上を滑る。"""
        graph = Ribbon.create(self.controls, count=5, name="rib", width=1.0)
        owner = str(graph.container)
        fn = self.surface(graph)
        for width in (1.0, 3.5):
            cmds.setAttr(owner + ".width", width)
            u0, _, v0, v1 = fn.knotDomainInU + fn.knotDomainInV
            edge = om.MPoint(fn.getPointAtParam(u0, v0, om.MSpace.kWorld))
            other = om.MPoint(fn.getPointAtParam(u0, v1, om.MSpace.kWorld))
            self.assertAlmostEqual(edge.distanceTo(other), width, places=4)
        cmds.setAttr(owner + ".position3", 0.0)
        self.assertTrue(_matrix(owner + ".matrix3").isEquivalent(_matrix(owner + ".matrix0"), 1e-4))
        cmds.setAttr(owner + ".position3", 0.4)
        self.check_frames(graph, 5)

    def test_linear_unit_is_centimeters(self):
        """UIの長さ単位がmmでも、widthはcmとして帯の幅になる。"""
        cmds.currentUnit(linear="mm")
        try:
            graph = Ribbon.create(self.controls, count=3, name="rib", width=2.0)
            fn = self.surface(graph)
            u0, _, v0, v1 = fn.knotDomainInU + fn.knotDomainInV
            edge = om.MPoint(fn.getPointAtParam(u0, v0, om.MSpace.kWorld))
            other = om.MPoint(fn.getPointAtParam(u0, v1, om.MSpace.kWorld))
            # OpenMayaの距離は内部単位(cm)。
            self.assertAlmostEqual(edge.distanceTo(other), 2.0, places=4)
        finally:
            cmds.currentUnit(linear="cm")
        self.check_frames(graph, 3)

    def test_passes_through_every_control(self):
        """帯は全てのコントロールの位置を通り、2つのコントロールでは1次の帯になる。"""
        graph = Ribbon.create(self.controls, count=len(self.controls), name="rib")
        for index, control in enumerate(self.controls):
            matrix = _matrix("{}.matrix{}".format(graph.container, index))
            self.assertTrue(_translate(matrix).isEquivalent(_position(control), 1e-4), index)
        self.assertEqual(self.surface(graph).degreeInU, 3)
        graph = Ribbon.create(self.controls[:2], count=3, name="ribTwo")
        self.assertEqual(self.surface(graph).degreeInU, 1)
        self.check_frames(graph, 3)

    def test_members(self):
        """生成した計算ノードとカーブ・サーフェスはcontainerが所有する。"""
        graph = Ribbon.create(self.controls, count=3, name="rib")
        members = set(cmds.container(str(graph.container), query=True, nodeList=True) or [])
        self.assertIn("rib_grp", members)
        self.assertIn("rib_surfaceShape", members)
        self.assertIn("rib_pin", members)
        self.assertTrue(graph.group.endswith("rib_grp"))
        self.assertFalse(cmds.getAttr("rib_section0.visibility"))

    def test_bad_arguments(self):
        """不正な引数は何も作らずにValueErrorになる。"""
        before = set(cmds.ls())
        for kwargs in ({"count": 1}, {"count": 2.5}, {"count": True}, {"width": 0.0},
                       {"width": float("nan")}, {"sideAxis": "w"}):
            with self.assertRaises(ValueError, msg=kwargs):
                Ribbon.create(self.controls, **kwargs)
        with self.assertRaises(ValueError):
            Ribbon.create(self.controls[:1])
        with self.assertRaises(ValueError):
            Ribbon.create([self.controls[0], self.controls[0]])
        self.assertEqual(set(cmds.ls()), before)
        Ribbon.create(self.controls, name="rib")
        with self.assertRaises(ValueError):
            Ribbon.create(self.controls, name="rib")

    def test_undo(self):
        """1回のUndoで生成物が消え、Redoで戻る。"""
        cmds.undoInfo(state=True, infinity=True)
        before = set(cmds.ls())
        Ribbon.create(self.controls, name="rib")
        after = set(cmds.ls())
        self.assertNotEqual(after, before)
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertEqual(set(cmds.ls()), after)


if __name__ == "__main__":
    unittest.main(argv=["ribbon"], exit=False, verbosity=2)
