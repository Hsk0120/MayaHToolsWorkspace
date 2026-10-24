"""AutoClavicleの分配を、Quaternionで求めた期待値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import AutoClavicle


def _rotation(matrix):
    """行列の回転をQuaternionで返す。"""
    return om.MTransformationMatrix(om.MMatrix(matrix)).rotation(asQuaternion=True)


def _local(node):
    """matrix * offsetParentMatrix。"""
    return om.MMatrix(cmds.getAttr(node + ".matrix")) * om.MMatrix(cmds.getAttr(node + ".offsetParentMatrix"))


class AutoClavicleTest(unittest.TestCase):
    """標準ノードの数値評価・上腕の向きの保持・境界・引数検査を確認する。"""

    def setUp(self):
        """胸→鎖骨→上腕と、出力を受ける結果jointを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.chest = cmds.createNode("transform", name="chest")
        self.clavicle = cmds.createNode("joint", name="clavicle", parent=self.chest)
        cmds.setAttr(self.clavicle + ".translate", 2, 15, 1)
        cmds.setAttr(self.clavicle + ".jointOrient", 0, -10, 5)
        self.upperarm = cmds.createNode("joint", name="upperarm", parent=self.clavicle)
        cmds.setAttr(self.upperarm + ".translate", 12, 0, 0)
        cmds.setAttr(self.upperarm + ".jointOrient", 0, 0, -20)

    def build(self, **kwargs):
        """セットアップと、出力をoffsetParentMatrixで受ける結果jointを作る。"""
        owner = AutoClavicle.create(self.clavicle, self.upperarm, **kwargs).container
        result_clavicle = cmds.createNode("joint", name="resultClavicle", parent=self.chest)
        result_upperarm = cmds.createNode("joint", name="resultUpperarm", parent=result_clavicle)
        cmds.connectAttr(str(owner) + ".clavicleMatrix", result_clavicle + ".offsetParentMatrix")
        cmds.connectAttr(str(owner) + ".matrix", result_upperarm + ".offsetParentMatrix")
        return owner, result_clavicle, result_upperarm

    def swingAngle(self, rest, axis="x"):
        """基準の長手軸と現在の長手軸のなす角(度)。"""
        unit = om.MVector(*[float(i == "xyz".index(axis)) for i in range(3)])
        before = unit.rotateBy(_rotation(rest))
        after = unit.rotateBy(_rotation(_local(self.upperarm)))
        return math.degrees(before.angle(after))

    def assertQuaternion(self, actual, expected, places=4):
        """符号の違いを同一視してQuaternionを比較する。"""
        dot = actual.x * expected.x + actual.y * expected.y + actual.z * expected.z + actual.w * expected.w
        self.assertAlmostEqual(abs(dot), 1.0, places=places)

    def check(self, owner, result_clavicle, result_upperarm, rest, start, weight, maximum):
        """スカラー出力・鎖骨の回転角・上腕のワールド回転を確認する。"""
        angle = self.swingAngle(rest)
        expected = AutoClavicle.clavicleAngle(angle, start, weight, maximum)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".swingAngle"), angle, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".clavicleAngle"), expected, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".upperarmAngle"), angle - expected, places=3)
        # 鎖骨の追加回転の角度がclavicleAngleになる。
        extra = _rotation(cmds.getAttr(str(owner) + ".clavicleRotation"))
        self.assertAlmostEqual(math.degrees(2 * math.acos(min(1.0, abs(extra.w)))), expected, places=3)
        # 上腕のワールド回転は入力と一致し、鎖骨は入力の鎖骨に追加回転を足したもの。
        source = _rotation(cmds.getAttr(self.upperarm + ".worldMatrix[0]"))
        actual = _rotation(cmds.getAttr(result_upperarm + ".worldMatrix[0]"))
        self.assertQuaternion(actual, source)
        clavicle = _rotation(cmds.getAttr(self.clavicle + ".worldMatrix[0]"))
        self.assertQuaternion(_rotation(cmds.getAttr(result_clavicle + ".worldMatrix[0]")), extra * clavicle)
        return expected

    def test_below_start_keeps_clavicle(self):
        """開始角以下では鎖骨は動かず、結果は入力と一致する。"""
        owner, result_clavicle, result_upperarm = self.build(start=30, weight=0.5, maximum=35)
        rest = _local(self.upperarm)
        for rotate in ((0, 0, 0), (0, 0, 25), (0, -20, 15), (40, 0, 0)):
            cmds.setAttr(self.upperarm + ".rotate", *rotate)
            self.assertAlmostEqual(self.check(owner, result_clavicle, result_upperarm, rest, 30, 0.5, 35), 0.0)
            source = om.MMatrix(cmds.getAttr(self.upperarm + ".worldMatrix[0]"))
            actual = om.MMatrix(cmds.getAttr(result_upperarm + ".worldMatrix[0]"))
            self.assertTrue(actual.isEquivalent(source, 1e-4))

    def test_share_and_preserve_direction(self):
        """開始角を超えると鎖骨が回り、上腕の向きと肩の移動が式どおりになる。"""
        owner, result_clavicle, result_upperarm = self.build(start=30, weight=1.0 / 3.0, maximum=35)
        rest = _local(self.upperarm)
        for rotate in ((0, 0, 60), (0, 0, 90), (0, -70, 0), (0, 45, 50), (30, 20, 80), (0, 0, -60)):
            cmds.setAttr(self.upperarm + ".rotate", *rotate)
            expected = self.check(owner, result_clavicle, result_upperarm, rest, 30, 1.0 / 3.0, 35)
            self.assertGreater(expected, 0.0)
            # 肩(上腕の根元)は鎖骨の追加回転で回した位置へ動く。
            extra = om.MMatrix(cmds.getAttr(str(owner) + ".clavicleRotation"))
            world = om.MMatrix(cmds.getAttr(self.clavicle + ".worldMatrix[0]"))
            expected_position = om.MPoint(12, 0, 0) * extra * world
            actual = om.MPoint(cmds.xform(result_upperarm, q=True, worldSpace=True, translation=True))
            self.assertTrue(actual.isEquivalent(expected_position, 1e-3))
            source = om.MPoint(cmds.xform(self.upperarm, q=True, worldSpace=True, translation=True))
            self.assertGreater((actual - source).length(), 1e-3)

    def test_maximum_and_return(self):
        """大きな曲げでもmaximum未満に収まり、戻すと0へ戻る。"""
        owner, result_clavicle, result_upperarm = self.build(start=20, weight=1.0, maximum=15)
        rest = _local(self.upperarm)
        for value in (30, 80, 150, 170, 40, 0):
            cmds.setAttr(self.upperarm + ".rotate", 0, 0, value)
            expected = self.check(owner, result_clavicle, result_upperarm, rest, 20, 1.0, 15)
            self.assertLess(expected, 15.0)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".clavicleAngle"), 0.0, places=6)

    def test_twist_kept_on_upperarm(self):
        """Twistは鎖骨へ移さず、上腕に残る。"""
        owner, result_clavicle, result_upperarm = self.build(start=0, weight=0.5, maximum=30)
        rest = _local(self.upperarm)
        cmds.setAttr(self.upperarm + ".rotate", 70, 0, 0)
        self.assertAlmostEqual(self.check(owner, result_clavicle, result_upperarm, rest, 0, 0.5, 30), 0.0, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".twist"), 70, places=2)

    def test_attributes_drive_graph(self):
        """containerのstart・weight・maximumを変えると出力が追従する。"""
        owner, result_clavicle, result_upperarm = self.build(start=30, weight=0.3, maximum=35)
        rest = _local(self.upperarm)
        cmds.setAttr(self.upperarm + ".rotate", 0, 0, 100)
        cmds.setAttr(str(owner) + ".start", 10)
        cmds.setAttr(str(owner) + ".weight", 0.8)
        cmds.setAttr(str(owner) + ".maximum", 50)
        self.check(owner, result_clavicle, result_upperarm, rest, 10, 0.8, 50)

    def test_invalid_arguments(self):
        """範囲外の値と親子関係の誤りを拒否する。"""
        for kwargs in ({"axis": "w"}, {"start": -1}, {"start": 180}, {"weight": 1.5}, {"maximum": 0},
                       {"maximum": 120}, {"weight": float("nan")}):
            with self.assertRaises(ValueError):
                AutoClavicle.create(self.clavicle, self.upperarm, **kwargs)
        other = cmds.createNode("joint", parent=self.chest)
        with self.assertRaises(ValueError):
            AutoClavicle.create(other, self.upperarm)

    def test_undo_removes_graph(self):
        """生成を1回のUndoで取り消せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        AutoClavicle.create(self.clavicle, self.upperarm, name="undoClavicle")
        self.assertTrue(cmds.objExists("undoClavicle"))
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main()
