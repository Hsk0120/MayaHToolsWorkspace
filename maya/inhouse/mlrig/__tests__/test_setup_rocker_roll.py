"""RockerRollの転がりを、OpenMayaで独立に組んだ回転と、底の円弧が床の上を滑らないこと(接地点・転がった弧の長さ)で確かめる。"""

import math
import unittest

from maya import cmds
import maya.api.OpenMaya as om

from mlrig.setups import RockerRoll

RADIUS = 3.0


def _world(node):
    """ノードのワールド行列。"""
    return om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


class RockerRollTest(unittest.TestCase):
    """独立計算との一致・跳ねない・滑らない・半径の変更・親の追従・軸とUI単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """回転・移動した親の下に、底が半径3cmの円弧の物体(接地点はローカル原点)を置く。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.parent = cmds.createNode("transform", name="floorSpace")
        cmds.setAttr(self.parent + ".translate", 4, 1, -2)
        cmds.setAttr(self.parent + ".rotate", 0, 35, 0)
        self.target = cmds.createNode("transform", name="rocker", parent=self.parent)
        cmds.setAttr(self.target + ".translate", 1, 0, 2)
        cmds.setAttr(self.target + ".rotateY", 20)
        self.rest = _world(self.target)
        self.setup = RockerRoll.create(self.target, RADIUS, name="rock")
        self.owner = str(self.setup.container)

    def _output(self, owner=None):
        """出力のワールド行列。"""
        return om.MMatrix(cmds.getAttr((owner or self.owner) + ".matrix"))

    def _expected(self, roll, radius=RADIUS):
        """回転の中心(接地点の上 radius)の周りに回し、中心を radius*roll だけ +Z へ送る(試験側の独立計算)。"""
        rotation = om.MTransformationMatrix()
        rotation.setRotation(om.MEulerRotation(roll, 0, 0))
        center = om.MVector(0, radius, 0)
        rotation.setTranslation(center + om.MVector(0, 0, radius * roll) - center * rotation.asMatrix(),
                                om.MSpace.kTransform)
        return rotation.asMatrix() * self.rest

    def _close(self, a, b, tolerance=1e-5):
        """2つの行列の全要素が近いことを確かめる。"""
        for i in range(16):
            self.assertAlmostEqual(a[i], b[i], delta=tolerance)

    def test_rest_and_formula(self):
        """roll=0 で生成時と一致し、正負・半回転を超える角度で独立計算・Python版と一致する。"""
        self._close(self._output(), self.rest)
        for degrees in (15.0, -40.0, 90.0, 200.0):
            with self.subTest(roll=degrees):
                cmds.setAttr(self.owner + ".roll", degrees)
                roll = math.radians(degrees)
                self._close(self._output(), self._expected(roll))
                local = om.MMatrix(list(RockerRoll.localMatrix(roll, RADIUS)))
                self._close(self._output(), local * self.rest)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".travel"), RADIUS * roll, places=5)

    def test_rolls_without_slipping(self):
        """底の最下点は常に床の高さにあり、床に触れている円弧の点は転がった弧の長さだけ前の床の点に一致する。"""
        floor = om.MVector(0, 1, 0) * self.rest
        for degrees in (10.0, 35.0, -60.0):
            roll = math.radians(degrees)
            cmds.setAttr(self.owner + ".roll", degrees)
            matrix = self._output()
            # 生成時のローカルで、角度 roll の位置の円弧の点(中心から下へ回した点)。
            touching = om.MPoint(0, RADIUS - RADIUS * math.cos(roll), RADIUS * math.sin(roll))
            ground = om.MPoint(0, 0, RADIUS * roll) * self.rest
            self.assertLess((touching * matrix - ground).length(), 1e-5)
            # 中心はいつも床から radius の高さ。
            center = om.MPoint(0, RADIUS, 0) * matrix
            base = om.MPoint(0, 0, 0) * self.rest
            self.assertAlmostEqual((center - base) * floor.normal(), RADIUS, places=5)

    def test_radius_and_parent(self):
        """radius を変えると式の半径が変わり、親を動かすと出力が付いていく。"""
        cmds.setAttr(self.owner + ".radius", 5.0)
        cmds.setAttr(self.owner + ".roll", 30.0)
        self._close(self._output(), self._expected(math.radians(30.0), 5.0))
        cmds.setAttr(self.parent + ".translateX", 10)
        cmds.setAttr(self.parent + ".rotateZ", 15)
        self.rest = om.MMatrix(cmds.getAttr(self.target + ".worldMatrix[0]"))
        self._close(self._output(), self._expected(math.radians(30.0), 5.0))

    def test_axes_contact_and_units(self):
        """axis=z・upAxis=y と接地点の指定で Python版と一致し(-Xへ転がる)、UI単位 mm・rad でも結果が同じ。"""
        cmds.currentUnit(linear="mm", angle="rad")
        conversions = set(cmds.ls(type="unitConversion"))
        joint = cmds.createNode("joint", name="footJoint")
        cmds.setAttr(joint + ".translate", 20, 0, 0)
        setup = RockerRoll.create(joint, 4.0, name="zRoll", axis="z", contact=(0, -0.5, 0))  # 引数は常にcm
        owner = str(setup.container)
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        cmds.setAttr(owner + ".roll", 0.5)
        cmds.currentUnit(linear="cm", angle="deg")
        self.assertAlmostEqual(cmds.getAttr(owner + ".radius"), 4.0, places=5)
        rest = om.MMatrix(cmds.getAttr(joint + ".worldMatrix[0]"))
        local = om.MMatrix(list(RockerRoll.localMatrix(0.5, 4.0, axis="z", contact=(0, -0.5, 0))))
        self._close(om.MMatrix(cmds.getAttr(owner + ".matrix")), local * rest)
        self.assertLess(om.MMatrix(cmds.getAttr(owner + ".matrix"))[12], rest[12])

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("rock_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.file(new=True, force=True)
        node = cmds.createNode("transform", name="undoRocker")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        RockerRoll.create(node, 2.0, name="undoRock")
        self.assertTrue(cmds.objExists("undoRock.matrix"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoRock"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoRock.matrix"))

    def test_arguments(self):
        """transform以外・半径・軸・接地点・名前の重複を拒否する。"""
        other = cmds.createNode("multiplyDivide")
        cases = (
            ((other, 1.0), {}),
            ((self.target, 0.0), {}),
            ((self.target, float("inf")), {}),
            ((self.target, 1.0), {"axis": "y"}),
            ((self.target, 1.0), {"axis": "w"}),
            ((self.target, 1.0), {"contact": (0, 0)}),
            ((self.target, 1.0), {"contact": (0, float("nan"), 0)}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                RockerRoll.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            RockerRoll.create(self.target, 1.0, name="rock")


if __name__ == "__main__":
    unittest.main()
