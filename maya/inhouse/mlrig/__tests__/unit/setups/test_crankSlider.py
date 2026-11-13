"""CrankSliderのピストンとロッドを、往復スライダー・クランク機構の閉じた式と、ロッドの長さが保たれることで確かめる。"""

import math
import unittest

from maya import cmds
import maya.api.OpenMaya as om

from mlrig.setups import CrankSlider

RADIUS = 2.0
LENGTH = 6.0
START = 30.0


def _world(node):
    """ノードのワールド行列。"""
    return om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _height(degrees, radius=RADIUS, length=LENGTH):
    """クランクの角度(+Yから+Z回り)でのピストンのピンの高さ(閉じた式 r*cos + sqrt(L^2 - r^2*sin^2))。"""
    angle = math.radians(degrees)
    return radius * math.cos(angle) + math.sqrt(length * length - (radius * math.sin(angle)) ** 2)


class CrankSliderTest(unittest.TestCase):
    """跳ねない・閉じた式と一致・ロッドの長さ・ロッドの向き・長さの変更と届かない場合・親の移動・UI単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """回転・移動したエンジンの下に、Z回りに回るクランク(ピンは半径2)と、Y軸の上のピストンを置く。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.engine = cmds.createNode("transform", name="engine")
        cmds.setAttr(self.engine + ".translate", 3, 1, -2)
        cmds.setAttr(self.engine + ".rotate", 10, 40, -15)
        self.crank = cmds.createNode("transform", name="crank", parent=self.engine)
        self.pin = cmds.createNode("transform", name="pin", parent=self.crank)
        cmds.setAttr(self.pin + ".translateY", RADIUS)
        cmds.setAttr(self.crank + ".rotateZ", START)
        self.piston = cmds.createNode("transform", name="piston", parent=self.engine)
        cmds.setAttr(self.piston + ".translateY", _height(START))
        cmds.setAttr(self.piston + ".rotateY", 25)
        self.rest = _world(self.piston)
        self.setup = CrankSlider.create(self.pin, self.piston, name="crankSlider", axis="y")
        self.owner = str(self.setup.container)

    def _matrix(self, attribute, owner=None):
        """containerの出力行列。"""
        return om.MMatrix(cmds.getAttr((owner or self.owner) + "." + attribute))

    def _close(self, a, b, tolerance=1e-5):
        """2つの行列の全要素が近いことを確かめる。"""
        for i in range(16):
            self.assertAlmostEqual(a[i], b[i], delta=tolerance)

    def _point(self, matrix):
        """行列の位置。"""
        return om.MPoint(matrix[12], matrix[13], matrix[14])

    def _expected(self, degrees, radius=RADIUS, length=LENGTH):
        """エンジンの空間でY方向に閉じた式の高さの差だけ動かしたピストンのワールド行列(試験側の独立計算)。"""
        shift = om.MMatrix()
        shift.setElement(3, 1, _height(degrees, radius, length) - _height(START))
        local = om.MMatrix(cmds.getAttr(self.piston + ".matrix"))
        return local * shift * om.MMatrix(cmds.getAttr(self.engine + ".worldMatrix[0]"))

    def test_rest(self):
        """作成直後、ピストンの出力は生成時と一致し、ロッドはピンの位置からピストンのピンへ向く。"""
        self._close(self._matrix("pistonMatrix"), self.rest)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".stroke"), 0.0, places=5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".rodLength"), LENGTH, places=5)
        rod = self._matrix("rodMatrix")
        pin = self._point(_world(self.pin))
        self.assertLess((self._point(rod) - pin).length(), 1e-5)
        toward = (self._point(self.rest) - pin).normal()
        self.assertAlmostEqual(om.MVector(rod[0], rod[1], rod[2]).normal() * toward, 1.0, places=5)

    def test_full_turn_matches_closed_form(self):
        """クランクを一周回すと、ピストンは閉じた式の高さに来て、ピンとの距離はロッドの長さに保たれる。"""
        engine = om.MMatrix(cmds.getAttr(self.engine + ".worldMatrix[0]"))
        axis = om.MVector(0, 1, 0) * engine
        foot = self._point(self.rest)
        for degrees in range(0, 361, 15):
            with self.subTest(angle=degrees):
                cmds.setAttr(self.crank + ".rotateZ", degrees)
                piston = self._matrix("pistonMatrix")
                self._close(piston, self._expected(degrees))
                pin = self._point(_world(self.pin))
                self.assertAlmostEqual((self._point(piston) - pin).length(), LENGTH, places=4)
                offset = self._point(piston) - foot
                self.assertLess((offset - axis.normal() * (offset * axis.normal())).length(), 1e-5)
                stroke = cmds.getAttr(self.owner + ".stroke")
                self.assertAlmostEqual(stroke, _height(degrees) - _height(START), places=4)
                local_pin = om.MPoint(0, 0, 0) * _world(self.pin) * engine.inverse()
                python = CrankSlider.pistonOffset(list(local_pin)[:3], (0, _height(START), 0), (0, 1, 0), LENGTH)
                self.assertAlmostEqual(stroke, python, places=4)
                rod = self._matrix("rodMatrix")
                self.assertLess((self._point(rod) - pin).length(), 1e-5)
                toward = (self._point(piston) - pin).normal()
                self.assertAlmostEqual(om.MVector(rod[0], rod[1], rod[2]).normal() * toward, 1.0, places=5)
                # ロッドのZは機構の面の法線(エンジンのZ)のまま。
                normal = (om.MVector(0, 0, 1) * engine).normal()
                self.assertAlmostEqual(abs(om.MVector(rod[8], rod[9], rod[10]).normal() * normal), 1.0, places=5)

    def test_given_rod_keeps_its_pose(self):
        """ロッドのtransformを渡すと、作成直後のロッドの出力はそのワールド行列と一致し、回してもピストンへ向き続ける。"""
        cmds.setAttr(self.crank + ".rotateZ", START)
        rod = cmds.createNode("transform", name="rod", parent=self.engine)
        pin = om.MPoint(0, 0, 0) * _world(self.pin) * _world(self.engine).inverse()
        cmds.setAttr(rod + ".translate", pin.x, pin.y, pin.z)
        cmds.setAttr(rod + ".rotate", 5, 12, 33)
        setup = CrankSlider.create(self.pin, self.piston, name="withRod", rod=rod)
        owner = str(setup.container)
        rest = _world(rod)
        self._close(self._matrix("rodMatrix", owner), rest)
        aim = (self._point(self.rest) - self._point(rest)).normal() * rest.inverse()
        cmds.setAttr(self.crank + ".rotateZ", 140)
        output = self._matrix("rodMatrix", owner)
        toward = (self._point(self._matrix("pistonMatrix", owner)) - self._point(_world(self.pin))).normal()
        self.assertAlmostEqual((aim * output).normal() * toward, 1.0, places=5)

    def test_rod_length_and_short_rod(self):
        """rodLengthを変えると閉じた式の長さで動き、軸に届かない短いロッドでは軸の上の最も近い点に止まる。"""
        cmds.setAttr(self.owner + ".rodLength", 8.0)
        cmds.setAttr(self.crank + ".rotateZ", 75)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".stroke"), _height(75, length=8.0) - _height(START), places=4)
        cmds.setAttr(self.owner + ".rodLength", 1.0)
        angle = math.radians(75)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".stroke"), RADIUS * math.cos(angle) - _height(START),
                               places=4)

    def test_engine_moves(self):
        """作成後にエンジンを動かし回しても、ピストンはエンジンの空間で同じ式に従う。"""
        cmds.setAttr(self.engine + ".translate", -5, 2, 7)
        cmds.setAttr(self.engine + ".rotate", -30, 15, 60)
        cmds.setAttr(self.crank + ".rotateZ", 200)
        self._close(self._matrix("pistonMatrix"), self._expected(200))

    def test_axis_and_units(self):
        """軸を -x で作る場合と、UI単位を mm・rad にした場合も同じ結果になる。"""
        cmds.setAttr(self.crank + ".rotateZ", START)
        base = cmds.createNode("transform", name="sideBase")
        crank = cmds.createNode("transform", name="sideCrank", parent=base)
        pin = cmds.createNode("transform", name="sidePin", parent=crank)
        cmds.setAttr(pin + ".translateY", RADIUS)
        cmds.setAttr(crank + ".rotateZ", 90 + START)
        piston = cmds.createNode("transform", name="sidePiston", parent=base)
        cmds.setAttr(piston + ".translateX", -_height(START))
        cmds.currentUnit(angle="rad", linear="mm")
        owner = str(CrankSlider.create(pin, piston, name="sideSlider", axis="-x").container)
        cmds.currentUnit(angle="deg", linear="cm")
        for degrees in (0.0, 100.0, 250.0):
            cmds.setAttr(crank + ".rotateZ", 90 + degrees)
            position = self._point(self._matrix("pistonMatrix", owner))
            self.assertAlmostEqual(position.x, -_height(degrees), places=4)
            self.assertAlmostEqual(cmds.getAttr(owner + ".stroke"), _height(degrees) - _height(START), places=4)

    def test_ownership_and_undo(self):
        """生成したノードはcontainerが所有し、1回のUndoで消え、Redoで戻る。"""
        owned = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        self.assertIn("aimMatrix", {cmds.nodeType(node) for node in owned})
        cmds.undoInfo(state=True, infinity=True)
        before = set(cmds.ls())
        setup = CrankSlider.create(self.pin, self.piston, name="again")
        created = set(cmds.ls()) - before - set(cmds.ls(type="hyperLayout"))
        owned = set(cmds.container(str(setup.container), query=True, nodeList=True) or [])
        self.assertEqual(created - owned, {"again"})
        cmds.undo()
        self.assertFalse(cmds.objExists("again"))
        cmds.redo()
        self.assertTrue(cmds.objExists("again"))

    def test_bad_arguments(self):
        """不正な引数はValueErrorになる。"""
        with self.assertRaises(ValueError):
            CrankSlider.create(self.pin, self.piston, name="crankSlider")
        with self.assertRaises(ValueError):
            CrankSlider.create(self.pin, self.piston, name="bad", axis="w")
        with self.assertRaises(ValueError):
            CrankSlider.create(self.pin, self.piston, name="bad", axis=(0, 0, 0))
        with self.assertRaises(ValueError):
            CrankSlider.create(self.pin, self.piston, name="bad", axis="-y")
        with self.assertRaises(ValueError):
            CrankSlider.create(self.pin, self.piston, name="bad", normal=(0, 1, 0))
        cmds.setAttr(self.crank + ".rotateZ", 0)
        with self.assertRaises(ValueError):
            CrankSlider.create(self.pin, self.piston, name="bad")
        CrankSlider.create(self.pin, self.piston, name="deadCenter", normal=(0, 0, 1))
        with self.assertRaises(ValueError):
            CrankSlider.create(self.engine + ".translate", self.piston, name="bad")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
