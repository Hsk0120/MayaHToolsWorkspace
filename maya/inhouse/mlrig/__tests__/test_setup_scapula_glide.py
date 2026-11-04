"""ScapulaGlideの投影と向きを、OpenMayaで独立に求めた楕円体の放射方向の表面の点・陰関数の勾配の法線と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import ScapulaGlide

RADII = (4.0, 6.0, 3.0)
OFFSET = 0.5


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _position(matrix):
    """行列の平行移動をMPointで返す。"""
    return om.MPoint(matrix[12], matrix[13], matrix[14])


def _row(matrix, index):
    """行列の行ベクトル(長さ1)を返す。"""
    return om.MVector(matrix[index * 4], matrix[index * 4 + 1], matrix[index * 4 + 2]).normal()


def _rotation(node):
    """ノードのワールド回転(scaleを除く)をMQuaternionで返す。"""
    return om.MTransformationMatrix(_matrix(node + ".worldMatrix[0]")).rotation(asQuaternion=True)


def _expected(target, ribcage, radii, offset):
    """OpenMayaで、期待する位置・外向きの法線・距離・向きの半径を求める。"""
    c = _position(_matrix(ribcage + ".worldMatrix[0]"))
    p = _position(_matrix(target + ".worldMatrix[0]"))
    rotation = _rotation(ribcage)
    world = p - c
    if world.length() <= 1e-6:
        local = om.MVector(1, 0, 0)
    else:
        local = world.normal().rotateBy(rotation.inverse())
    radius = 1.0 / math.sqrt(sum((value / r) ** 2 for value, r in zip(local, radii)))
    surface = local * radius
    normal = om.MVector(*[value / (r * r) for value, r in zip(surface, radii)]).normal().rotateBy(rotation)
    position = c + surface.rotateBy(rotation) + normal * offset
    return position, normal, world.length() - radius, radius


class ScapulaGlideTest(unittest.TestCase):
    """表面への投影・法線・向き・offset・胸郭の移動と回転・Python版・所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転・拡大した胸郭と、背中側に離れた肩甲骨のコントロールを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.ribcage = cmds.createNode("transform", name="ribcage")
        cmds.setAttr(self.ribcage + ".translate", 1, 10, -2)
        cmds.setAttr(self.ribcage + ".rotate", 10, 25, -15)
        cmds.setAttr(self.ribcage + ".scale", 2, 2, 2)
        self.target = cmds.createNode("transform", name="scapulaCtrl")
        cmds.setAttr(self.target + ".translate", 3, 12, -7)
        cmds.setAttr(self.target + ".rotate", 5, -10, 20)
        self.setup = ScapulaGlide.create(self.target, self.ribcage, name="glide", radiusX=RADII[0],
                                         radiusY=RADII[1], radiusZ=RADII[2], offset=OFFSET)
        self.owner = str(self.setup.container)

    def _assertExpected(self, radii=RADII, offset=OFFSET, owner=None, normalIndex=2, upIndex=1,
                        tolerance=1e-4):
        owner = owner or self.owner
        position, normal, distance, radius = _expected(self.target, self.ribcage, radii, offset)
        matrix = _matrix(owner + ".matrix")
        self.assertLess((_position(matrix) - position).length(), tolerance)
        self.assertLess((_row(matrix, normalIndex) - normal).length(), tolerance)
        self.assertLess((om.MVector(cmds.getAttr(owner + ".normal")[0]) - normal).length(), tolerance)
        self.assertAlmostEqual(cmds.getAttr(owner + ".distance"), distance, delta=tolerance)
        self.assertAlmostEqual(cmds.getAttr(owner + ".directionRadius"), radius, delta=tolerance)
        # upAxisは target の同じ軸を法線に垂直な面へ射影した向き。
        reference = _row(_matrix(self.target + ".worldMatrix[0]"), upIndex)
        up = (reference - normal * (reference * normal)).normal()
        self.assertLess((_row(matrix, upIndex) - up).length(), tolerance)
        # scaleは1(正規直交)。
        for index in range(3):
            row = om.MVector(matrix[index * 4], matrix[index * 4 + 1], matrix[index * 4 + 2])
            self.assertAlmostEqual(row.length(), 1.0, delta=tolerance)
        return position, normal

    def _surfaceValue(self, point, offset=OFFSET):
        """出力の位置から法線の向きへ offset だけ戻した点の陰関数の値(表面なら1)。"""
        world = _matrix(self.ribcage + ".worldMatrix[0]")
        c = _position(world)
        normal = om.MVector(cmds.getAttr(self.owner + ".normal")[0])
        local = (om.MPoint(point) - normal * offset - c).rotateBy(_rotation(self.ribcage).inverse())
        return sum((value / r) ** 2 for value, r in zip(local, RADII))

    def test_rest_on_surface(self):
        """生成時の出力が式と一致し、offsetを除いた点が楕円体の表面にある。"""
        position, _normal = self._assertExpected()
        self.assertAlmostEqual(self._surfaceValue(position), 1.0, delta=1e-4)
        self.assertGreater(cmds.getAttr(self.owner + ".distance"), 0.0)

    def test_glide_inside_and_outside(self):
        """内側・外側・軸の向き・斜めのどこへ動かしても表面に吸い付いて滑る。"""
        c = _position(_matrix(self.ribcage + ".worldMatrix[0]"))
        for offset in ((20, 0, 0), (0, -30, 0), (0, 0, 2), (1, 1, 1), (-3, 2, -5), (0.5, -0.2, 0.1), (8, 8, -8)):
            point = c + om.MVector(*offset)
            cmds.setAttr(self.target + ".translate", point.x, point.y, point.z)
            with self.subTest(offset=offset):
                position, _normal = self._assertExpected()
                self.assertAlmostEqual(self._surfaceValue(position), 1.0, delta=1e-4)

    def test_normal_is_gradient(self):
        """法線は楕円体の陰関数の勾配の向きで、表面の接線に垂直になる。"""
        position, normal = self._assertExpected()
        # 表面上で近くの点を2つ作り、その差(接線)が法線に垂直であることを確かめる。
        rotation = _rotation(self.ribcage)
        c = _position(_matrix(self.ribcage + ".worldMatrix[0]"))
        base = (om.MPoint(position) - normal * OFFSET - c).rotateBy(rotation.inverse())
        for delta in ((1e-3, 0, 0), (0, 1e-3, 0), (0, 0, 1e-3)):
            moved = base + om.MVector(*delta)
            scale = 1.0 / math.sqrt(sum((value / r) ** 2 for value, r in zip(moved, RADII)))
            tangent = (moved * scale - base).rotateBy(rotation)
            if tangent.length() > 1e-9:
                self.assertLess(abs(tangent.normal() * normal), 1e-2)

    def test_center_fallback(self):
        """中心と一致すると局所+Xの向きの表面を使う。"""
        c = _position(_matrix(self.ribcage + ".worldMatrix[0]"))
        cmds.setAttr(self.target + ".translate", c.x, c.y, c.z)
        position, _normal = self._assertExpected()
        axis = om.MVector(1, 0, 0).rotateBy(_rotation(self.ribcage))
        expected = c + axis * (RADII[0] + OFFSET)
        self.assertLess((position - expected).length(), 1e-4)

    def test_attributes_and_ribcage(self):
        """半径・offsetの変更と、胸郭の移動・回転に追従する。"""
        cmds.setAttr(self.owner + ".radiusX", 2.5)
        cmds.setAttr(self.owner + ".radiusY", 7.0)
        cmds.setAttr(self.owner + ".radiusZ", 5.0)
        cmds.setAttr(self.owner + ".offset", -0.25)
        self._assertExpected(radii=(2.5, 7.0, 5.0), offset=-0.25)
        cmds.setAttr(self.owner + ".radiusX", RADII[0])
        cmds.setAttr(self.owner + ".radiusY", RADII[1])
        cmds.setAttr(self.owner + ".radiusZ", RADII[2])
        cmds.setAttr(self.owner + ".offset", OFFSET)
        cmds.setAttr(self.ribcage + ".translate", -4, 3, 6)
        cmds.setAttr(self.ribcage + ".rotate", 70, -40, 110)
        self._assertExpected()
        cmds.setAttr(self.target + ".rotate", 90, 30, -60)
        self._assertExpected()

    def test_sphere_is_radial(self):
        """3つの半径が同じなら法線は中心からの向きと一致する。"""
        for item in "XYZ":
            cmds.setAttr(self.owner + ".radius" + item, 5.0)
        position, normal = self._assertExpected(radii=(5.0, 5.0, 5.0))
        c = _position(_matrix(self.ribcage + ".worldMatrix[0]"))
        p = _position(_matrix(self.target + ".worldMatrix[0]"))
        self.assertLess((normal - (p - c).normal()).length(), 1e-4)
        self.assertAlmostEqual((position - c).length(), 5.0 + OFFSET, delta=1e-4)

    def test_python_matches(self):
        """glidePositionの値がDGの出力と一致する。"""
        rotation = _rotation(self.ribcage)
        axes = [tuple(om.MVector(*axis).rotateBy(rotation)) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
        center = tuple(_position(_matrix(self.ribcage + ".worldMatrix[0]")))[:3]
        for offset in ((3, 12, -7), (-6, 9, 4), (1, 10, -2)):
            cmds.setAttr(self.target + ".translate", *offset)
            point = tuple(_position(_matrix(self.target + ".worldMatrix[0]")))[:3]
            position, normal = ScapulaGlide.glidePosition(point, center, RADII, OFFSET, axes)
            matrix = _matrix(self.owner + ".matrix")
            with self.subTest(offset=offset):
                self.assertLess((_position(matrix) - om.MPoint(*position)).length(), 1e-4)
                self.assertLess((_row(matrix, 2) - om.MVector(*normal)).length(), 1e-4)

    def test_other_axes(self):
        """normalAxis=x・upAxis=zでも、指定した軸が法線・上方向になる。"""
        setup = ScapulaGlide.create(self.target, self.ribcage, name="glideX", radiusX=RADII[0], radiusY=RADII[1],
                                    radiusZ=RADII[2], offset=OFFSET, normalAxis="x", upAxis="z")
        self._assertExpected(owner=str(setup.container), normalIndex=0, upIndex=2)

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.owner + ".matrix", pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        ribcage = cmds.createNode("transform", name="undoRibcage")
        target = cmds.createNode("transform", name="undoTarget")
        cmds.setAttr(target + ".translateZ", -5)
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        ScapulaGlide.create(target, ribcage, name="undoGlide")
        self.assertTrue(cmds.objExists("undoGlide"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoGlide"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoGlide.normal"))

    def test_arguments(self):
        """値・軸の不正、transform以外・同じノード・名前の重複を拒否する。"""
        for kwargs in ({"radiusX": 0.0}, {"radiusY": -1.0}, {"radiusZ": float("nan")}, {"offset": float("inf")},
                       {"normalAxis": "w"}, {"upAxis": "z", "normalAxis": "z"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ScapulaGlide.create(self.target, self.ribcage, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            ScapulaGlide.create(node, self.ribcage, name="bad")
        with self.assertRaises(ValueError):
            ScapulaGlide.create(self.target, self.target, name="bad")
        with self.assertRaises(ValueError):
            ScapulaGlide.create(self.target, self.ribcage, name="glide")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
