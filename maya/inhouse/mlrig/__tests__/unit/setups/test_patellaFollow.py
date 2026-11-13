"""PatellaFollowの膝蓋骨・膝蓋腱・溝の角度を、溝の円の上の角度を走査する独立計算と膝蓋腱の長さで確かめる。"""

import math
import unittest

from maya import cmds
import maya.api.OpenMaya as om

from mlrig.setups import PatellaFollow

# 大腿骨の空間(X が前、Y が上、Z が外側)での溝の中心・膝蓋骨(cm)。脛骨は膝(大腿骨の原点)の子で、
# 脛骨粗面は脛骨のローカルに置く。膝の曲げは脛骨の rotateZ のマイナス(脛が後ろ)。
GROOVE = (0.0, 0.3, 0.0)
PATELLA = (1.6, 0.6, 0.0)
TUBEROSITY = (0.9, -3.0, 0.0)


def _world(node):
    """ノードのワールド行列。"""
    return om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _length(first, second):
    """2点の距離(XY)。"""
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _tuberosity(degrees):
    """脛骨の rotateZ が degrees のときの脛骨粗面(大腿骨の空間)。"""
    angle = math.radians(degrees)
    x, y = TUBEROSITY[0], TUBEROSITY[1]
    return x * math.cos(angle) - y * math.sin(angle), x * math.sin(angle) + y * math.cos(angle)


def _solve(degrees, tendon=None, previous=None):
    """膝蓋骨の位置を、溝の円の上の角度 φ の走査と二分法で求める(試験側の独立計算)。

    P = G + r (cosφ, sinφ)、f(φ) = |P - T| - L = 0 の根のうち previous の φ に最も近いもの。
    """
    radius = _length(GROOVE, PATELLA)
    tendon = _length(PATELLA, TUBEROSITY) if tendon is None else tendon
    t_point = _tuberosity(degrees)

    def point(phi):
        return GROOVE[0] + radius * math.cos(phi), GROOVE[1] + radius * math.sin(phi)

    def gap(phi):
        return _length(point(phi), t_point) - tendon

    roots = []
    steps = 720
    for index in range(steps):
        low, high = 2 * math.pi * index / steps, 2 * math.pi * (index + 1) / steps
        if gap(low) * gap(high) > 0.0:
            continue
        for _ in range(60):
            middle = 0.5 * (low + high)
            if gap(low) * gap(middle) <= 0.0:
                high = middle
            else:
                low = middle
        roots.append(0.5 * (low + high))
    if previous is None:
        previous = math.atan2(PATELLA[1] - GROOVE[1], PATELLA[0] - GROOVE[0])

    def distance(phi):
        return abs((phi - previous + math.pi) % (2 * math.pi) - math.pi)

    phi = min(roots, key=distance)
    return point(phi), t_point, phi


class PatellaFollowTest(unittest.TestCase):
    """生成時と一致・曲げの走査で独立計算と一致・溝の角度・長さの変更と届かない場合・大腿骨の移動・UI単位・
    法線の向き・所有とUndo・引数を確認する。"""

    def setUp(self):
        """移動・回転・scaleした腰の下の大腿骨と、その子の脛骨・溝の中心・膝蓋骨・脛骨粗面を置く。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.hip = cmds.createNode("transform", name="hip")
        cmds.setAttr(self.hip + ".translate", 2, 40, -3)
        cmds.setAttr(self.hip + ".rotate", 5, -20, 10)
        cmds.setAttr(self.hip + ".scale", 1.5, 1.5, 1.5)
        self.femur = cmds.createNode("transform", name="femur", parent=self.hip)
        cmds.setAttr(self.femur + ".translate", 1, -4, 0.5)
        cmds.setAttr(self.femur + ".rotate", 0, 15, -8)
        self.groove = cmds.createNode("transform", name="groove", parent=self.femur)
        cmds.setAttr(self.groove + ".translate", *GROOVE)
        self.patella = cmds.createNode("transform", name="patella", parent=self.femur)
        cmds.setAttr(self.patella + ".translate", *PATELLA)
        cmds.setAttr(self.patella + ".rotate", 10, 0, 25)
        self.tibia = cmds.createNode("transform", name="tibia", parent=self.femur)
        self.tuberosity = cmds.createNode("transform", name="tuberosity", parent=self.tibia)
        cmds.setAttr(self.tuberosity + ".translate", *TUBEROSITY)
        self.rest = _world(self.patella)
        self.restLocal = self.rest * _world(self.femur).inverse()
        self.args = (self.femur, self.tibia, self.groove, self.patella, self.tuberosity)
        self.setup = PatellaFollow.create(*self.args, name="patellaRig")
        self.owner = str(self.setup.container)

    def _matrix(self, attribute, owner=None):
        """containerの出力行列。"""
        return om.MMatrix(cmds.getAttr((owner or self.owner) + "." + attribute))

    def _close(self, a, b, tolerance=1e-4):
        """2つの行列の全要素が近いことを確かめる。"""
        for i in range(16):
            self.assertAlmostEqual(a[i], b[i], delta=tolerance)

    def _local(self, matrix):
        """行列の位置を大腿骨の空間へ。"""
        return om.MPoint(matrix[12], matrix[13], matrix[14]) * _world(self.femur).inverse()

    def _check(self, degrees, previous=None, owner=None):
        """膝蓋骨・膝蓋腱・溝の角度が独立計算と一致することを確かめ、φ と位置を返す。"""
        cmds.setAttr(self.tibia + ".rotateZ", degrees)
        p_point, t_point, phi = _solve(degrees, previous=previous)
        rest_phi = math.atan2(PATELLA[1] - GROOVE[1], PATELLA[0] - GROOVE[0])
        patella = self._matrix("patellaMatrix", owner)
        femur = _world(self.femur)
        position = self._local(patella)
        self.assertAlmostEqual(position.x, p_point[0], delta=1e-4)
        self.assertAlmostEqual(position.y, p_point[1], delta=1e-4)
        self.assertAlmostEqual(position.z, 0.0, delta=1e-4)
        # 膝蓋骨の回転は生成時から +Z 回りに φ - φ0(既定の法線は -Z なので grooveAngle は -(φ - φ0))。
        turn = (phi - rest_phi + math.pi) % (2 * math.pi) - math.pi
        relative = om.MTransformationMatrix(self.restLocal.inverse() * patella * femur.inverse())
        rotation = relative.rotation(asQuaternion=True)
        expected = om.MQuaternion(turn, om.MVector(0, 0, 1))
        self.assertAlmostEqual(abs(rotation.x * expected.x + rotation.y * expected.y + rotation.z * expected.z
                                   + rotation.w * expected.w), 1.0, places=5)
        self.assertAlmostEqual(cmds.getAttr((owner or self.owner) + ".grooveAngle"), -math.degrees(turn),
                               delta=1e-3)
        tendon = self._matrix("tendonMatrix", owner)
        self.assertLess((self._local(tendon) - position).length(), 1e-5)
        axis = (om.MVector(tendon[0], tendon[1], tendon[2]) * femur.inverse()).normal()
        toward = om.MVector(t_point[0] - p_point[0], t_point[1] - p_point[1], 0).normal()
        self.assertAlmostEqual(axis * toward, 1.0, places=5)
        z_axis = (om.MVector(tendon[8], tendon[9], tendon[10]) * femur.inverse()).normal()
        self.assertAlmostEqual(z_axis.z, -1.0, places=5)
        self.assertAlmostEqual(cmds.getAttr((owner or self.owner) + ".excess"), 0.0, places=5)
        return phi, p_point, t_point

    def test_rest(self):
        """作成直後、膝蓋骨の出力は生成時と一致し、半径・長さは生成時の距離、届かない量と角度は0。"""
        self._close(self._matrix("patellaMatrix"), self.rest, 1e-5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".grooveRadius"), _length(GROOVE, PATELLA), places=5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".tendonLength"), _length(PATELLA, TUBEROSITY), places=5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".grooveAngle"), 0.0, places=4)
        self._check(0.0)

    def test_flexion_sweep(self):
        """0〜-130度の曲げで独立計算・Python版と一致し、膝蓋腱の長さが保たれ、膝蓋骨が溝に沿って下へ回り続ける。"""
        previous = None
        angles = []
        for degrees in range(0, -131, -10):
            with self.subTest(flexion=degrees):
                previous, p_point, t_point = self._check(degrees, previous)
                self.assertAlmostEqual(_length(p_point, t_point), _length(PATELLA, TUBEROSITY), delta=1e-6)
                point, excess, angle = PatellaFollow.patellaPose(GROOVE, PATELLA, TUBEROSITY, t_point + (0.0,),
                                                                 (0, 0, -1))
                self.assertLess(math.hypot(point[0] - p_point[0], point[1] - p_point[1]), 1e-4)
                self.assertEqual(excess, 0.0)
                self.assertAlmostEqual(angle, cmds.getAttr(self.owner + ".grooveAngle"), delta=1e-3)
                angles.append(angle)
        for before, after in zip(angles, angles[1:]):
            self.assertGreater(after, before)
        self.assertGreater(angles[-1], 30.0)

    def test_lengths_and_out_of_reach(self):
        """半径・膝蓋腱の長さを変えると新しい長さで解け、届かない場合は excess に不足を出す。"""
        tendon = _length(PATELLA, TUBEROSITY)
        cmds.setAttr(self.owner + ".tendonLength", tendon + 0.3)
        cmds.setAttr(self.tibia + ".rotateZ", -40)
        p_point, t_point, _ = _solve(-40, tendon=tendon + 0.3)
        position = self._local(self._matrix("patellaMatrix"))
        self.assertAlmostEqual(position.x, p_point[0], delta=1e-4)
        self.assertAlmostEqual(position.y, p_point[1], delta=1e-4)
        cmds.setAttr(self.owner + ".tendonLength", 10.0)
        _, excess, _ = PatellaFollow.patellaPose(GROOVE, PATELLA, TUBEROSITY, t_point + (0.0,), (0, 0, -1),
                                                 tendonLength=10.0)
        self.assertGreater(excess, 0.1)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".excess"), excess, delta=1e-4)
        cmds.setAttr(self.owner + ".tendonLength", tendon)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".excess"), 0.0, places=5)
        cmds.setAttr(self.owner + ".grooveRadius", 2.0)
        point, _, _ = PatellaFollow.patellaPose(GROOVE, PATELLA, TUBEROSITY, t_point + (0.0,), (0, 0, -1),
                                                grooveRadius=2.0, tendonLength=tendon)
        position = self._local(self._matrix("patellaMatrix"))
        self.assertAlmostEqual(_length((position.x, position.y), GROOVE), 2.0, delta=1e-4)
        self.assertLess(math.hypot(position.x - point[0], position.y - point[1]), 1e-4)

    def test_femur_moves(self):
        """作成後に腰・大腿骨を動かし回しても、膝蓋骨と膝蓋腱は大腿骨の空間で同じ式に従う。"""
        cmds.setAttr(self.hip + ".rotate", -30, 15, 60)
        cmds.setAttr(self.femur + ".rotate", 20, -10, 45)
        cmds.setAttr(self.femur + ".translate", -3, 2, 1)
        self._check(-70)

    def test_tibia_outside_hierarchy(self):
        """脛骨が大腿骨の子でなくても、ワールド行列で追従する。"""
        cmds.setAttr(self.tibia + ".rotateZ", -50)
        cmds.parent(self.tibia, world=True)
        p_point, _, _ = _solve(-50)
        position = self._local(self._matrix("patellaMatrix"))
        self.assertAlmostEqual(position.x, p_point[0], delta=1e-4)
        self.assertAlmostEqual(position.y, p_point[1], delta=1e-4)

    def test_units_and_normal(self):
        """UI単位 mm・rad で作っても同じ結果になり、法線を逆にすると grooveAngle の符号が逆になる。"""
        cmds.currentUnit(angle="rad", linear="mm")
        owner = str(PatellaFollow.create(*self.args, name="units").container)
        cmds.currentUnit(angle="deg", linear="cm")
        self.assertAlmostEqual(cmds.getAttr(owner + ".tendonLength"), _length(PATELLA, TUBEROSITY), places=5)
        self._check(-60, owner=owner)
        conversions = [node for node in cmds.container(owner, query=True, nodeList=True)
                       if cmds.nodeType(node) == "unitConversion"]
        for node in conversions:
            self.assertAlmostEqual(cmds.getAttr(node + ".conversionFactor"), 1.0)
        cmds.setAttr(self.tibia + ".rotateZ", 0)
        flipped = str(PatellaFollow.create(*self.args, name="flipped", normal=(0, 0, 1)).container)
        cmds.setAttr(self.tibia + ".rotateZ", -60)
        self._close(self._matrix("patellaMatrix", flipped), self._matrix("patellaMatrix", owner), 1e-4)
        self.assertAlmostEqual(cmds.getAttr(flipped + ".grooveAngle"), -cmds.getAttr(owner + ".grooveAngle"),
                               delta=1e-3)

    def test_ownership_and_undo(self):
        """生成したノードはcontainerが所有し、膝蓋骨・目印へは接続せず、1回のUndoで消え、Redoで戻る。"""
        owned = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        self.assertIn("angleBetween", {cmds.nodeType(node) for node in owned})
        for node in (self.patella, self.groove, self.tuberosity):
            self.assertFalse(cmds.listConnections(node, source=True, destination=False) or [])
        cmds.undoInfo(state=True, infinity=True)
        before = set(cmds.ls())
        setup = PatellaFollow.create(*self.args, name="again")
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
            PatellaFollow.create(*self.args, name="patellaRig")
        with self.assertRaises(ValueError):
            PatellaFollow.create(cmds.createNode("multiplyDivide"), *self.args[1:], name="bad")
        with self.assertRaises(ValueError):
            PatellaFollow.create(self.femur, self.femur, *self.args[2:], name="bad")
        with self.assertRaises(ValueError):
            PatellaFollow.create(*self.args, name="bad", normal=(0, 0, 0))
        with self.assertRaises(ValueError):
            PatellaFollow.create(*self.args, name="bad", normal=(0, "a", 1))
        with self.assertRaises(ValueError):
            PatellaFollow.create(self.femur, self.tibia, self.groove, self.groove, self.tuberosity, name="bad")
        # 3点が一直線なら法線が要る。
        line = cmds.createNode("transform", name="line", parent=self.tibia)
        cmds.setAttr(line + ".translate", 3.2, 0.9, 0)
        with self.assertRaises(ValueError):
            PatellaFollow.create(self.femur, self.tibia, self.groove, self.patella, line, name="bad")
        PatellaFollow.create(self.femur, self.tibia, self.groove, self.patella, line, name="inLine",
                             normal=(0, 0, -1))
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
