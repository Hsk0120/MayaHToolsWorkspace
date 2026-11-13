"""FourBarLinkageの関節・ロッカー・カプラーを、四節リンクの閉じた式(Freudensteinの形)と棒の長さで確かめる。"""

import math
import unittest

from maya import cmds
import maya.api.OpenMaya as om

from mlrig.setups import FourBarLinkage

CRANK = 2.0
GROUND = 6.0
COUPLER = 5.0
ROCKER = 4.0
START = 60.0


def _world(node):
    """ノードのワールド行列。"""
    return om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _pin(degrees, crank=CRANK):
    """クランクの角度(+X から +Z 回り)でのピン B の位置(機構の面 XY)。"""
    angle = math.radians(degrees)
    return crank * math.cos(angle), crank * math.sin(angle)


def _joint(degrees, branch=1.0, coupler=COUPLER, rocker=ROCKER):
    """ロッカーの角度 ψ を K1 cosψ + K2 sinψ = K3 から求め、関節 C の位置を返す(試験側の独立計算)。

    C = D + c (cosψ, sinψ)、|C - B| = b より 2c(Dx - Bx) cosψ + 2c(Dy - By) sinψ = b^2 - c^2 - |D - B|^2。
    branch=+1 は C が B→D の線の左(+Z 側)の解。
    """
    bx, by = _pin(degrees)
    k1 = 2.0 * rocker * (GROUND - bx)
    k2 = 2.0 * rocker * (0.0 - by)
    k3 = coupler * coupler - rocker * rocker - (GROUND - bx) ** 2 - by ** 2
    base = math.atan2(k2, k1)
    spread = math.acos(max(-1.0, min(1.0, k3 / math.hypot(k1, k2))))
    for psi in (base + spread, base - spread):
        cx, cy = GROUND + rocker * math.cos(psi), rocker * math.sin(psi)
        left = (GROUND - bx) * (cy - by) - (0.0 - by) * (cx - bx)
        if left * branch > 0.0:
            return cx, cy
    raise AssertionError("no branch")


class FourBarLinkageTest(unittest.TestCase):
    """生成時と一致・一周で閉じた式と一致・枝・長さの変更と届かない場合・親の移動・UI単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """回転・移動した台の下に、Z回りに回るクランク(半径2)・支点が X=6 のロッカー・関節の位置を置く。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.base = cmds.createNode("transform", name="base")
        cmds.setAttr(self.base + ".translate", 3, 1, -2)
        cmds.setAttr(self.base + ".rotate", 10, 40, -15)
        self.crank = cmds.createNode("transform", name="crank", parent=self.base)
        self.pin = cmds.createNode("transform", name="pin", parent=self.crank)
        cmds.setAttr(self.pin + ".translateX", CRANK)
        cmds.setAttr(self.crank + ".rotateZ", START)
        self.rocker = cmds.createNode("transform", name="rocker", parent=self.base)
        cmds.setAttr(self.rocker + ".translateX", GROUND)
        cmds.setAttr(self.rocker + ".rotate", 0, 0, 70)
        self.end = cmds.createNode("transform", name="end", parent=self.base)
        cx, cy = _joint(START)
        cmds.setAttr(self.end + ".translate", cx, cy, 0)
        self.rest = _world(self.rocker)
        self.setup = FourBarLinkage.create(self.pin, self.rocker, self.end, name="fourBar")
        self.owner = str(self.setup.container)

    def _matrix(self, attribute, owner=None):
        """containerの出力行列。"""
        return om.MMatrix(cmds.getAttr((owner or self.owner) + "." + attribute))

    def _close(self, a, b, tolerance=1e-4):
        """2つの行列の全要素が近いことを確かめる。"""
        for i in range(16):
            self.assertAlmostEqual(a[i], b[i], delta=tolerance)

    def _point(self, matrix):
        """行列の位置。"""
        return om.MPoint(matrix[12], matrix[13], matrix[14])

    def _local(self, point):
        """ワールドの点を台の空間へ。"""
        return point * _world(self.base).inverse()

    def _check(self, degrees, owner=None, branch=1.0, rest_aim=None):
        """関節が独立計算と一致し、棒の長さが保たれ、ロッカーとカプラーが関節へ向くことを確かめる。"""
        joint = self._local(self._point(self._matrix("jointMatrix", owner)))
        cx, cy = _joint(degrees, branch)
        self.assertAlmostEqual(joint.x, cx, delta=1e-4)
        self.assertAlmostEqual(joint.y, cy, delta=1e-4)
        self.assertAlmostEqual(joint.z, 0.0, delta=1e-4)
        bx, by = _pin(degrees)
        self.assertAlmostEqual(math.hypot(cx - bx, cy - by), COUPLER, delta=1e-4)
        rocker = self._matrix("rockerMatrix", owner)
        self.assertLess((self._local(self._point(rocker)) - om.MPoint(GROUND, 0, 0)).length(), 1e-5)
        world_joint = self._point(self._matrix("jointMatrix", owner))
        aim = rest_aim if rest_aim is not None else self._rest_aim
        toward = (world_joint - self._point(rocker)).normal()
        self.assertAlmostEqual((aim * rocker).normal() * toward, 1.0, places=5)
        coupler = self._matrix("couplerMatrix", owner)
        pin = self._point(_world(self.pin))
        self.assertLess((self._point(coupler) - pin).length(), 1e-5)
        toward = (world_joint - pin).normal()
        self.assertAlmostEqual(om.MVector(coupler[0], coupler[1], coupler[2]).normal() * toward, 1.0, places=5)
        normal = (om.MVector(0, 0, 1) * _world(self.base)).normal()
        self.assertAlmostEqual(abs(om.MVector(coupler[8], coupler[9], coupler[10]).normal() * normal), 1.0,
                               places=5)
        # 伝達角は余弦定理で |B - D|^2 = b^2 + c^2 - 2bc cosμ。
        dd = (GROUND - bx) ** 2 + by ** 2
        mu = math.degrees(math.acos((COUPLER ** 2 + ROCKER ** 2 - dd) / (2 * COUPLER * ROCKER)))
        self.assertAlmostEqual(cmds.getAttr((owner or self.owner) + ".transmissionAngle"), mu, delta=1e-3)
        self.assertAlmostEqual(cmds.getAttr((owner or self.owner) + ".excess"), 0.0, places=5)

    @property
    def _rest_aim(self):
        """生成時の D→C の向き(ロッカーのローカル)。"""
        cx, cy = _joint(START)
        return om.MVector(cx - GROUND, cy, 0).normal() * om.MMatrix(cmds.getAttr(self.rocker + ".matrix")).inverse()

    def test_rest(self):
        """作成直後、ロッカーの出力は生成時と一致し、関節は end の位置、届かない量は0。"""
        self._close(self._matrix("rockerMatrix"), self.rest, 1e-5)
        self.assertLess((self._point(self._matrix("jointMatrix")) - self._point(_world(self.end))).length(), 1e-5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".couplerLength"), COUPLER, places=5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".rockerLength"), ROCKER, places=5)
        self._check(START)

    def test_full_turn_matches_closed_form(self):
        """クランクを一周回すと(Grashofのクランク・ロッカー)、関節は閉じた式に一致し、Python版とも一致する。"""
        base = _world(self.base)
        for degrees in range(0, 361, 15):
            with self.subTest(angle=degrees):
                cmds.setAttr(self.crank + ".rotateZ", degrees)
                self._check(degrees)
                pin = self._local(self._point(_world(self.pin)))
                python, excess = FourBarLinkage.jointPosition((pin.x, pin.y, pin.z), (GROUND, 0, 0), COUPLER, ROCKER,
                                                               (0, 0, 1), 1.0)
                joint = self._point(self._matrix("jointMatrix")) * base.inverse()
                self.assertLess((om.MPoint(*python) - joint).length(), 1e-4)
                self.assertEqual(excess, 0.0)

    def test_other_branch(self):
        """関節を B→D の線の反対側(交差した配置)で作ると、一周してもその枝のまま。"""
        cx, cy = _joint(START, -1.0)
        cmds.setAttr(self.end + ".translate", cx, cy, 0)
        owner = str(FourBarLinkage.create(self.pin, self.rocker, self.end, name="crossed").container)
        aim = om.MVector(cx - GROUND, cy, 0).normal() * om.MMatrix(cmds.getAttr(self.rocker + ".matrix")).inverse()
        for degrees in range(0, 361, 30):
            with self.subTest(angle=degrees):
                cmds.setAttr(self.crank + ".rotateZ", degrees)
                self._check(degrees, owner, -1.0, aim)

    def test_lengths_and_out_of_reach(self):
        """棒の長さを変えると新しい長さで解け、届かない場合は B→D の線の上で止まり excess に不足を出す。"""
        cmds.setAttr(self.owner + ".rockerLength", 5.0)
        cmds.setAttr(self.crank + ".rotateZ", 100)
        bx, by = _pin(100)
        joint = self._local(self._point(self._matrix("jointMatrix")))
        self.assertAlmostEqual(math.hypot(joint.x - bx, joint.y - by), COUPLER, delta=1e-4)
        self.assertAlmostEqual(math.hypot(joint.x - GROUND, joint.y), 5.0, delta=1e-4)
        cmds.setAttr(self.owner + ".rockerLength", ROCKER)
        cmds.setAttr(self.owner + ".couplerLength", 1.0)
        cmds.setAttr(self.crank + ".rotateZ", 180)
        # d = 8 > b + c = 5: 不足は3、C = B + 1 * u。
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".excess"), 3.0, delta=1e-4)
        joint = self._local(self._point(self._matrix("jointMatrix")))
        self.assertAlmostEqual(joint.x, -1.0, delta=1e-4)
        self.assertAlmostEqual(joint.y, 0.0, delta=1e-4)
        # d < |b - c|: b = 12、c = 4、d = 4 なら 8 - 4 = 4 不足、C は B から D の向きへ b(D の先)。
        cmds.setAttr(self.owner + ".couplerLength", 12.0)
        cmds.setAttr(self.crank + ".rotateZ", 0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".excess"), 4.0, delta=1e-4)
        joint = self._local(self._point(self._matrix("jointMatrix")))
        self.assertAlmostEqual(joint.x, 2.0 + 12.0, delta=1e-3)

    def test_base_moves(self):
        """作成後に台を動かし回しても、関節は台の空間で同じ式に従う。"""
        cmds.setAttr(self.base + ".translate", -5, 2, 7)
        cmds.setAttr(self.base + ".rotate", -30, 15, 60)
        cmds.setAttr(self.crank + ".rotateZ", 200)
        self._check(200)

    def test_given_coupler_and_units(self):
        """カプラーのtransformを渡すと作成直後の出力はその行列と一致し、UI単位 mm・rad で作っても同じ結果になる。"""
        coupler = cmds.createNode("transform", name="coupler", parent=self.base)
        bx, by = _pin(START)
        cmds.setAttr(coupler + ".translate", bx, by, 0)
        cmds.setAttr(coupler + ".rotate", 5, 12, 33)
        cmds.currentUnit(angle="rad", linear="mm")
        owner = str(FourBarLinkage.create(self.pin, self.rocker, self.end, name="units", coupler=coupler).container)
        cmds.currentUnit(angle="deg", linear="cm")
        self._close(self._matrix("couplerMatrix", owner), _world(coupler), 1e-5)
        self.assertAlmostEqual(cmds.getAttr(owner + ".couplerLength"), COUPLER, places=5)
        for degrees in (0.0, 140.0, 290.0):
            cmds.setAttr(self.crank + ".rotateZ", degrees)
            joint = self._local(self._point(self._matrix("jointMatrix", owner)))
            cx, cy = _joint(degrees)
            self.assertAlmostEqual(joint.x, cx, delta=1e-4)
            self.assertAlmostEqual(joint.y, cy, delta=1e-4)
        conversions = [node for node in cmds.container(owner, query=True, nodeList=True)
                       if cmds.nodeType(node) == "unitConversion"]
        for node in conversions:
            self.assertAlmostEqual(cmds.getAttr(node + ".conversionFactor"), 1.0)

    def test_ownership_and_undo(self):
        """生成したノードはcontainerが所有し、入力へは接続せず、1回のUndoで消え、Redoで戻る。"""
        owned = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        self.assertIn("aimMatrix", {cmds.nodeType(node) for node in owned})
        for node in (self.pin, self.rocker, self.end):
            self.assertFalse(cmds.listConnections(node, source=True, destination=False) or [])
        cmds.undoInfo(state=True, infinity=True)
        before = set(cmds.ls())
        setup = FourBarLinkage.create(self.pin, self.rocker, self.end, name="again")
        created = set(cmds.ls()) - before - set(cmds.ls(type="hyperLayout"))
        owned = set(cmds.container(str(setup.container), query=True, nodeList=True) or [])
        self.assertEqual(created - owned, {"again"})
        cmds.undo()
        self.assertFalse(cmds.objExists("again"))
        cmds.redo()
        self.assertTrue(cmds.objExists("again"))

    def test_bad_arguments(self):
        """不正な引数はValueErrorになり、何も残さない。"""
        with self.assertRaises(ValueError):
            FourBarLinkage.create(self.pin, self.rocker, self.end, name="fourBar")
        with self.assertRaises(ValueError):
            FourBarLinkage.create(cmds.createNode("multiplyDivide"), self.rocker, self.end, name="bad")
        with self.assertRaises(ValueError):
            FourBarLinkage.create(self.pin, self.rocker, self.end, name="bad", normal=(0, 0, 0))
        with self.assertRaises(ValueError):
            FourBarLinkage.create(self.pin, self.rocker, self.end, name="bad", normal=(0, "a", 1))
        with self.assertRaises(ValueError):
            FourBarLinkage.create(self.pin, self.rocker, self.rocker, name="bad")
        # B・C・D が一直線なら法線が要る。
        line = cmds.createNode("transform", name="line", parent=self.base)
        bx, by = _pin(START)
        cmds.setAttr(line + ".translate", bx + (bx - GROUND), by + by, 0)
        with self.assertRaises(ValueError):
            FourBarLinkage.create(self.pin, self.rocker, line, name="bad")
        FourBarLinkage.create(self.pin, self.rocker, line, name="inLine", normal=(0, 0, 1))
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
