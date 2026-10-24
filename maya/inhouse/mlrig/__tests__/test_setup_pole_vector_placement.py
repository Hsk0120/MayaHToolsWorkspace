"""PoleVectorPlacementのポールの位置を、Pythonの式とOpenMayaで求めた期待値と比較する。"""

import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import PoleVectorPlacement


def _position(node):
    """ワールド位置をMVectorで返す。"""
    return om.MVector(cmds.xform(node, q=True, worldSpace=True, translation=True))


class PoleVectorPlacementTest(unittest.TestCase):
    """標準ノードの数値評価・平面と垂直の性質・一直線・単位・引数検査を確認する。"""

    def setUp(self):
        """回転した親の下に、肩・肘・手首の3関節を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.root = cmds.createNode("transform", name="chest")
        cmds.setAttr(self.root + ".rotate", 10, 20, 30)
        cmds.setAttr(self.root + ".translate", 1, 2, 3)
        self.start = cmds.createNode("joint", name="shoulder", parent=self.root)
        self.mid = cmds.createNode("joint", name="elbow", parent=self.start)
        cmds.setAttr(self.mid + ".translate", 10, 0, 0)
        self.end = cmds.createNode("joint", name="wrist", parent=self.mid)
        cmds.setAttr(self.end + ".translate", 9, 0, 0)
        cmds.setAttr(self.mid + ".rotate", 0, 40, 0)

    def build(self, **kwargs):
        """セットアップと、出力行列をoffsetParentMatrixで受けるワールド直下のtransformを作る。"""
        owner = PoleVectorPlacement.create(self.start, self.mid, self.end, **kwargs).container
        marker = cmds.createNode("transform", name="poleMarker")
        cmds.connectAttr(str(owner) + ".matrix", marker + ".offsetParentMatrix")
        return owner, marker

    def check(self, owner, marker, distance):
        """position・matrix・bendDistanceと、ポールが曲がる平面上で付け根-先端の線に垂直なことを確認する。"""
        s, m, e = (_position(node) for node in (self.start, self.mid, self.end))
        expected = om.MVector(*PoleVectorPlacement.polePosition(s, m, e, distance))
        actual = om.MVector(cmds.getAttr(str(owner) + ".position")[0])
        self.assertTrue(actual.isEquivalent(expected, 1e-4), (actual, expected))
        self.assertTrue(_position(marker).isEquivalent(expected, 1e-4))
        line = e - s
        offset = actual - m
        if offset.length() > 1e-6:
            # 付け根-先端の線に垂直、かつ3関節の平面上にある。
            self.assertAlmostEqual(offset.normal() * line.normal(), 0.0, places=4)
            normal = ((m - s) ^ line).normal()
            self.assertAlmostEqual(offset.normal() * normal, 0.0, places=4)
            self.assertAlmostEqual(offset.length(), distance, places=4)
        projection = s + line * (((m - s) * line) / (line * line))
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".bendDistance"), (m - projection).length(), places=4)
        return actual

    def test_default_distance(self):
        """既定の距離は、生成時の上腕と前腕の長さの合計の0.5倍。"""
        owner, marker = self.build()
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".distance"), 9.5, places=5)
        self.check(owner, marker, 9.5)

    def test_follows_fk_pose(self):
        """FKの姿勢を変えると、ポールが曲がる向きの延長上へ移る。"""
        owner, marker = self.build(distance=20)
        for shoulder, elbow in (((0, 0, 0), (0, 40, 0)), ((30, -20, 45), (0, 90, 0)),
                                ((-60, 10, 0), (0, 15, 0)), ((0, 0, 90), (20, 120, 5))):
            cmds.setAttr(self.start + ".rotate", *shoulder)
            cmds.setAttr(self.mid + ".rotate", *elbow)
            self.check(owner, marker, 20)

    def test_straight_chain(self):
        """一直線では向きが決まらず、ポールは中間関節の位置になる。"""
        owner, marker = self.build(distance=10)
        cmds.setAttr(self.mid + ".rotate", 0, 0, 0)
        actual = self.check(owner, marker, 10)
        self.assertTrue(actual.isEquivalent(_position(self.mid), 1e-4))
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".bendDistance"), 0.0, places=5)

    def test_distance_attribute_and_units(self):
        """distanceの変更に追従し、UIの長さ単位がmでも位置はcmのまま。"""
        owner, marker = self.build(distance=5)
        cmds.setAttr(str(owner) + ".distance", 12)
        expected = self.check(owner, marker, 12)
        cmds.currentUnit(linear="m")
        try:
            raw = om.MVector(cmds.getAttr(str(owner) + ".position")[0])
            self.assertTrue(raw.isEquivalent(expected, 1e-4))
            matrix = om.MMatrix(cmds.getAttr(str(owner) + ".matrix"))
            self.assertTrue(om.MVector(matrix[12], matrix[13], matrix[14]).isEquivalent(expected, 1e-4))
        finally:
            cmds.currentUnit(linear="cm")

    def test_invalid_arguments(self):
        """同じノード・負の距離・既存の名前を拒否する。"""
        with self.assertRaises(ValueError):
            PoleVectorPlacement.create(self.start, self.start, self.end)
        for distance in (-1, float("nan")):
            with self.assertRaises(ValueError):
                PoleVectorPlacement.create(self.start, self.mid, self.end, distance=distance)
        PoleVectorPlacement.create(self.start, self.mid, self.end, name="taken")
        with self.assertRaises(ValueError):
            PoleVectorPlacement.create(self.start, self.mid, self.end, name="taken")

    def test_undo_removes_graph(self):
        """生成を1回のUndoで取り消せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        PoleVectorPlacement.create(self.start, self.mid, self.end, name="undoPole")
        self.assertTrue(cmds.objExists("undoPole"))
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main()
