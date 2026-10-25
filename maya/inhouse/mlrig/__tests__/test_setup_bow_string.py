"""BowStringの弦の向き・長さ・引き量を、OpenMayaで求めた期待値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import BowString

#: nockを動かす量(弓の親空間)。引く・押す・横へずらす・上下へずらすを含む。
MOVES = [(0, 0, -4), (0, 0, -9), (0, 0, -15), (0, 0, 1), (1.5, 0, -6), (0, 3, -6), (-2, -2, -12)]


def _world(node):
    """ワールド行列。"""
    return om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _position(node):
    """ワールド位置。"""
    return om.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))


def _axis(matrix, index):
    """行列の行(ローカル軸のワールドの向き)を正規化して返す。"""
    return om.MVector(matrix[index * 4], matrix[index * 4 + 1], matrix[index * 4 + 2]).normal()


class BowStringTest(unittest.TestCase):
    """作成時の姿勢・弦の向き・弓の面・長さ・引き量・引数検査・Undoを確認する。"""

    def setUp(self):
        """回転した親の下に、別々の親を持つ上下の先端と、ノックのコントロールを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.bow = cmds.createNode("transform", name="bow")
        cmds.setAttr(self.bow + ".translate", 3, 100, -2)
        cmds.setAttr(self.bow + ".rotate", 10, 35, -5)
        upper = cmds.createNode("transform", name="upperLimb", parent=self.bow)
        lower = cmds.createNode("transform", name="lowerLimb", parent=self.bow)
        cmds.setAttr(upper + ".rotate", 0, 0, 8)
        self.top = cmds.createNode("joint", name="topTip", parent=upper)
        cmds.setAttr(self.top + ".translate", 0, 50, -3)
        self.bottom = cmds.createNode("joint", name="bottomTip", parent=lower)
        cmds.setAttr(self.bottom + ".translate", 0, -50, -3)
        cmds.setAttr(self.bottom + ".rotate", 20, 0, 0)
        self.nock = cmds.createNode("transform", name="nock", parent=self.bow)
        cmds.setAttr(self.nock + ".translate", 0, 2, -15)
        self.parents = {"top": upper, "bottom": lower}

    def build(self, **kwargs):
        """セットアップと、出力をoffsetParentMatrixで受ける結果transformを各先端の親の下に作る。"""
        graph = BowString.create(self.top, self.bottom, self.nock, name="bowStr", **kwargs)
        owner = str(graph.container)
        results = {}
        for role in ("top", "bottom"):
            result = cmds.createNode("transform", name="result_" + role, parent=self.parents[role])
            cmds.connectAttr(owner + "." + role + "Matrix", result + ".offsetParentMatrix")
            results[role] = result
        return owner, results

    def restNormal(self):
        """生成時の弓の面の法線(ワールド)。"""
        top, bottom, nock = _position(self.top), _position(self.bottom), _position(self.nock)
        return ((top - nock) ^ (bottom - nock)).normal()

    def test_no_pop_on_create(self):
        """作成直後の出力は各先端のワールド行列と一致する。"""
        before = {role: _world(node) for role, node in (("top", self.top), ("bottom", self.bottom))}
        _, results = self.build()
        for role, matrix in before.items():
            self.assertTrue(_world(results[role]).isEquivalent(matrix, 1e-4), role)

    def test_aim_plane_length_and_draw(self):
        """nockを動かすと、生成時にnockを向いていたローカルの向きが常にnockを向き、長さと引き量が合う。"""
        rest_draw = (_position(self.nock) - (_position(self.top) + _position(self.bottom)) * 0.5).length()
        rest = {}
        for role, node in (("top", self.top), ("bottom", self.bottom)):
            world = _world(node)
            direction = (_position(self.nock) - _position(node)).normal()
            rotation = om.MTransformationMatrix(world).rotation(asQuaternion=True).asMatrix()
            rest[role] = direction * rotation.inverse()
        owner, results = self.build(maxDraw=10.0)
        self.assertAlmostEqual(cmds.getAttr(owner + ".restDraw"), rest_draw, places=4)
        start = cmds.getAttr(self.nock + ".translate")[0]
        for move in MOVES:
            cmds.setAttr(self.nock + ".translate", *[s + m for s, m in zip(start, move)])
            nock = _position(self.nock)
            draw = (nock - (_position(self.top) + _position(self.bottom)) * 0.5).length() - rest_draw
            self.assertAlmostEqual(cmds.getAttr(owner + ".draw"), draw, places=4, msg=move)
            self.assertAlmostEqual(cmds.getAttr(owner + ".drawWeight"), BowString.drawWeight(draw, 10.0),
                                   places=5, msg=move)
            for role, node in (("top", self.top), ("bottom", self.bottom)):
                actual = _world(results[role])
                target = nock - _position(node)
                self.assertAlmostEqual(cmds.getAttr(owner + "." + role + "Length"), target.length(), places=4)
                # 位置は先端の現在位置のまま。
                self.assertTrue(om.MVector(actual[12], actual[13], actual[14]).isEquivalent(_position(node), 1e-4))
                rotation = om.MTransformationMatrix(actual).rotation(asQuaternion=True).asMatrix()
                self.assertTrue((rest[role] * rotation).isEquivalent(target.normal(), 1e-4), (role, move))
        cmds.setAttr(self.nock + ".translate", *start)
        self.assertAlmostEqual(cmds.getAttr(owner + ".draw"), 0.0, places=5)
        self.assertAlmostEqual(cmds.getAttr(owner + ".drawWeight"), 0.0, places=6)

    def test_up_axis_is_plane_normal(self):
        """upAxis=yのとき、aimMatrixの出力のYは弓の面の法線(生成時、親の回転に追従)を向く。"""
        graph = BowString.create(self.top, self.bottom, self.nock, name="bowStr")
        normal = self.restNormal()
        for role in ("top", "bottom"):
            frame = om.MMatrix(cmds.getAttr("{}_{}Aim.outputMatrix".format(graph.container, role)))
            self.assertAlmostEqual(abs(_axis(frame, 1) * normal), 1.0, places=4)
        cmds.setAttr(self.bow + ".rotateY", 80)
        normal = self.restNormal()
        for role in ("top", "bottom"):
            frame = om.MMatrix(cmds.getAttr("{}_{}Aim.outputMatrix".format(graph.container, role)))
            self.assertAlmostEqual(abs(_axis(frame, 1) * normal), 1.0, places=4)

    def test_draw_weight_formula(self):
        """drawWeightは0〜1に収まる。"""
        self.assertEqual(BowString.drawWeight(-3.0, 10.0), 0.0)
        self.assertAlmostEqual(BowString.drawWeight(4.0, 10.0), 0.4)
        self.assertEqual(BowString.drawWeight(25.0, 10.0), 1.0)

    def test_default_max_draw(self):
        """maxDrawを省略すると上下の先端の距離の0.5倍。"""
        span = (_position(self.top) - _position(self.bottom)).length()
        owner, _ = self.build()
        self.assertAlmostEqual(cmds.getAttr(owner + ".maxDraw"), span * 0.5, places=4)

    def test_bad_arguments(self):
        """不正な引数は何も作らずにValueErrorになる。"""
        before = set(cmds.ls())
        with self.assertRaises(ValueError):
            BowString.create(self.top, self.bottom, self.nock, aimAxis="y", upAxis="y")
        with self.assertRaises(ValueError):
            BowString.create(self.top, self.top, self.nock)
        with self.assertRaises(ValueError):
            BowString.create(self.top, self.bottom, self.nock, maxDraw=0.0)
        middle = [(a + b) / 2 for a, b in zip(_position(self.top), _position(self.bottom))]
        cmds.xform(self.nock, worldSpace=True, translation=middle)
        with self.assertRaises(ValueError):
            BowString.create(self.top, self.bottom, self.nock)
        self.assertEqual(set(cmds.ls()), before)
        cmds.setAttr(self.nock + ".translate", 0, 2, -15)
        BowString.create(self.top, self.bottom, self.nock, name="bowStr")
        with self.assertRaises(ValueError):
            BowString.create(self.top, self.bottom, self.nock, name="bowStr")

    def test_undo(self):
        """1回のUndoで生成物が消える。"""
        cmds.undoInfo(state=True, infinity=True)
        before = set(cmds.ls())
        BowString.create(self.top, self.bottom, self.nock, name="bowStr")
        self.assertNotEqual(set(cmds.ls()), before)
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main(argv=["bowString"], exit=False, verbosity=2)
