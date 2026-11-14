"""BoxRollの転がりを、箱の角の位置(床へ潜らない・支点の縁が動かない・90度ごとに平らに着く)で独立に確かめる。"""

import math
import random
import unittest

from maya import cmds
import maya.api.OpenMaya as om

from mlrig.setups import BoxRoll

SIZE = 4.0
TOLERANCE = 1e-5


def _world(node):
    """ノードのワールド行列。"""
    return om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _corners(size=SIZE):
    """生成時のローカルで、断面(YZ面)の正方形の4つの角(底の中心が原点、上が+Y)。"""
    half = size / 2.0
    return [om.MPoint(0, y, z) for y in (0.0, size) for z in (-half, half)]


class BoxRollTest(unittest.TestCase):
    """跳ねない・潜らない・滑らない・90度ごとの着地・連続性・Python版・軸とUI単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """回転・移動した親の下に、一辺4cmの箱(底の中心がローカル原点)を置く。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.parent = cmds.createNode("transform", name="floorSpace")
        cmds.setAttr(self.parent + ".translate", 4, 1, -2)
        cmds.setAttr(self.parent + ".rotate", 0, 35, 0)
        self.target = cmds.createNode("transform", name="box", parent=self.parent)
        cmds.setAttr(self.target + ".translate", 1, 0, 2)
        cmds.setAttr(self.target + ".rotateY", 20)
        self.rest = _world(self.target)
        self.setup = BoxRoll.create(self.target, SIZE, name="roll")
        self.owner = str(self.setup.container)

    def _output(self, owner=None):
        """出力のワールド行列。"""
        return om.MMatrix(cmds.getAttr((owner or self.owner) + ".matrix"))

    def _floor(self, point):
        """生成時の床(箱のローカルのY=0の面)から見た、点の高さと前(+Z)の位置。"""
        local = point * self.rest.inverse()
        return local.y, local.z

    def _close(self, a, b, tolerance=TOLERANCE):
        """2つの行列の全要素が近いことを確かめる。"""
        for i in range(16):
            self.assertAlmostEqual(a[i], b[i], delta=tolerance)

    def test_rest(self):
        """roll=0 で生成時のワールド行列と一致し、step・travel が0。"""
        self._close(self._output(), self.rest)
        self.assertEqual(cmds.getAttr(self.owner + ".step"), 0.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".travel"), 0.0)

    def test_never_sinks_and_pivot_edge_stays(self):
        """乱数の角度で、角は床より下へ行かず、床に触れる縁(支点)は段の初めの位置から動かない。"""
        rng = random.Random(33)
        for _ in range(25):
            degrees = rng.uniform(-400.0, 400.0)
            with self.subTest(roll=degrees):
                cmds.setAttr(self.owner + ".roll", degrees)
                matrix = self._output()
                heights = [self._floor(corner * matrix) for corner in _corners()]
                self.assertGreater(min(h for h, _ in heights), -TOLERANCE)
                # 段 n の支点の縁は、床の上の前 (n + 1/2)·size の位置(負の向きでも同じ式)。
                step = math.floor(degrees / 90.0)
                self.assertEqual(cmds.getAttr(self.owner + ".step"), float(step))
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".travel"), step * SIZE, places=5)
                pivot = (step + 0.5) * SIZE
                touching = [z for h, z in heights if abs(h) < 1e-4]
                self.assertTrue(any(abs(z - pivot) < 1e-4 for z in touching), (heights, pivot))
                # 箱の向きは roll だけ軸の周りに回っている(中心からの角の向きで確かめる)。
                center = om.MPoint(0, SIZE / 2.0, 0) * matrix
                corner = om.MPoint(0, SIZE, SIZE / 2.0) * matrix
                local = (corner - center) * self.rest.inverse()
                angle = math.atan2(local.z, local.y) - math.radians(45.0)
                difference = (angle - math.radians(degrees) + math.pi) % (2.0 * math.pi) - math.pi
                self.assertAlmostEqual(difference, 0.0, places=5)

    def test_lands_flat_and_continuous(self):
        """90度の倍数では底が床に平らに着いて size ずつ前へ進み、段の切り替わりの前後で値が連続する。"""
        for quarter in (-3, -1, 1, 2, 5):
            cmds.setAttr(self.owner + ".roll", 90.0 * quarter)
            matrix = self._output()
            heights = sorted(self._floor(corner * matrix) for corner in _corners())
            self.assertAlmostEqual(heights[0][0], 0.0, places=5)
            self.assertAlmostEqual(heights[1][0], 0.0, places=5)
            center = self._floor(om.MPoint(0, SIZE / 2.0, 0) * matrix)
            self.assertAlmostEqual(center[0], SIZE / 2.0, places=5)
            self.assertAlmostEqual(center[1], quarter * SIZE, places=5)
            for offset in (-1e-4, 1e-4):
                cmds.setAttr(self.owner + ".roll", 90.0 * quarter + offset)
                self._close(self._output(), matrix, 1e-3)

    def test_python_version_and_parent(self):
        """Python版と一致し、親を動かすと出力が付いていく。"""
        for degrees in (30.0, 135.0, -100.0):
            cmds.setAttr(self.owner + ".roll", degrees)
            local = om.MMatrix(list(BoxRoll.localMatrix(math.radians(degrees), SIZE)))
            self._close(self._output(), local * self.rest)
        cmds.setAttr(self.parent + ".translateX", 10)
        cmds.setAttr(self.parent + ".rotateZ", 15)
        rest = _world(self.target)
        local = om.MMatrix(list(BoxRoll.localMatrix(math.radians(-100.0), SIZE)))
        self._close(self._output(), local * rest)

    def test_axes_contact_and_units(self):
        """axis=z・upAxis=y と底の中心の指定で Python版と一致し(-Xへ転がる)、UI単位 mm・rad でも結果が同じ。"""
        cmds.currentUnit(linear="mm", angle="rad")
        conversions = set(cmds.ls(type="unitConversion"))
        joint = cmds.createNode("joint", name="boxJoint")
        cmds.setAttr(joint + ".translate", 20, 0, 0)
        setup = BoxRoll.create(joint, 3.0, name="zRoll", axis="z", contact=(0, -0.5, 0))  # 引数は常にcm
        owner = str(setup.container)
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        cmds.setAttr(owner + ".roll", 2.0)
        cmds.currentUnit(linear="cm", angle="deg")
        self.assertAlmostEqual(cmds.getAttr(owner + ".travel"), 3.0, places=5)
        rest = _world(joint)
        local = om.MMatrix(list(BoxRoll.localMatrix(2.0, 3.0, axis="z", contact=(0, -0.5, 0))))
        self._close(self._output(owner), local * rest)
        self.assertLess(self._output(owner)[12], rest[12])

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、入力へ接続せず、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("roll_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        self.assertFalse(cmds.listConnections(self.target, source=True, destination=False))
        cmds.file(new=True, force=True)
        node = cmds.createNode("transform", name="undoBox")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        BoxRoll.create(node, 2.0, name="undoRoll")
        self.assertTrue(cmds.objExists("undoRoll.matrix"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoRoll"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoRoll.matrix"))

    def test_arguments(self):
        """transform以外・一辺・軸・底の中心・名前の重複を拒否し、何も残さない。"""
        other = cmds.createNode("multiplyDivide")
        before = set(cmds.ls())
        cases = (
            ((other, 1.0), {}),
            ((self.target, 0.0), {}),
            ((self.target, -1.0), {}),
            ((self.target, float("inf")), {}),
            ((self.target, 1.0), {"axis": "y"}),
            ((self.target, 1.0), {"axis": "w"}),
            ((self.target, 1.0), {"contact": (0, 0)}),
            ((self.target, 1.0), {"contact": (0, float("nan"), 0)}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                BoxRoll.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            BoxRoll.create(self.target, 1.0, name="roll")
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main()
