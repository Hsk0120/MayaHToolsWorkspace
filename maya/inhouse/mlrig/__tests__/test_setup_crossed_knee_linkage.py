"""CrossedKneeLinkageの脛骨・靭帯・瞬間回転中心を、靭帯の角度を走査する独立計算と靭帯の長さで確かめる。"""

import math
import unittest

from maya import cmds
import maya.api.OpenMaya as om

from mlrig.setups import CrossedKneeLinkage

# 大腿骨の空間(X が前、Y が上、Z が外側)での付着点(cm)。前の靭帯 A→B と後ろの靭帯 D→C が交差する。
ACL_FEMUR = (-1.0, 0.5, 0.0)
ACL_TIBIA = (1.2, -2.5, 0.0)
PCL_FEMUR = (0.8, 0.8, 0.0)
PCL_TIBIA = (-1.5, -2.8, 0.0)


def _world(node):
    """ノードのワールド行列。"""
    return om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _length(first, second):
    """2点の距離。"""
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _solve(degrees, acl=None, pcl=None, previous=None):
    """曲げ角 θ(-Z 回りが正、つまり脛が後ろへ)での B・C を、前の靭帯の角度 φ の走査と二分法で求める(試験側の独立計算)。

    B = A + a (cosφ, sinφ)、C = B + v(θ)、f(φ) = |C - D| - p = 0 の根のうち previous の φ に最も近いもの。
    """
    acl = _length(ACL_FEMUR, ACL_TIBIA) if acl is None else acl
    pcl = _length(PCL_FEMUR, PCL_TIBIA) if pcl is None else pcl
    angle = -math.radians(degrees)
    vx0, vy0 = PCL_TIBIA[0] - ACL_TIBIA[0], PCL_TIBIA[1] - ACL_TIBIA[1]
    vx = vx0 * math.cos(angle) - vy0 * math.sin(angle)
    vy = vx0 * math.sin(angle) + vy0 * math.cos(angle)

    def point(phi):
        bx, by = ACL_FEMUR[0] + acl * math.cos(phi), ACL_FEMUR[1] + acl * math.sin(phi)
        return (bx, by), (bx + vx, by + vy)

    def gap(phi):
        return _length(point(phi)[1], PCL_FEMUR) - pcl

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
        previous = math.atan2(ACL_TIBIA[1] - ACL_FEMUR[1], ACL_TIBIA[0] - ACL_FEMUR[0]) % (2 * math.pi)

    def distance(phi):
        return abs((phi - previous + math.pi) % (2 * math.pi) - math.pi)

    phi = min(roots, key=distance)
    b_point, c_point = point(phi)
    return b_point, c_point, phi


def _crossing(b_point, c_point):
    """線 A-B と線 D-C の交点(クラメルの公式)。"""
    ax, ay = ACL_FEMUR[0], ACL_FEMUR[1]
    dx, dy = PCL_FEMUR[0], PCL_FEMUR[1]
    e1 = (b_point[0] - ax, b_point[1] - ay)
    e2 = (c_point[0] - dx, c_point[1] - dy)
    determinant = e1[0] * -e2[1] - (-e2[0]) * e1[1]
    t = ((dx - ax) * -e2[1] - (-e2[0]) * (dy - ay)) / determinant
    return ax + t * e1[0], ay + t * e1[1]


class CrossedKneeLinkageTest(unittest.TestCase):
    """生成時と一致・曲げの走査で独立計算と一致・瞬間回転中心・長さの変更と届かない場合・大腿骨の移動・UI単位・
    法線の向き・所有とUndo・引数を確認する。"""

    def setUp(self):
        """移動・回転・scaleした腰の下の大腿骨と、ワールド直下の脛骨・4つの付着点を置く。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.hip = cmds.createNode("transform", name="hip")
        cmds.setAttr(self.hip + ".translate", 2, 40, -3)
        cmds.setAttr(self.hip + ".rotate", 5, -20, 10)
        cmds.setAttr(self.hip + ".scale", 1.5, 1.5, 1.5)
        self.femur = cmds.createNode("transform", name="femur", parent=self.hip)
        cmds.setAttr(self.femur + ".translate", 1, -4, 0.5)
        cmds.setAttr(self.femur + ".rotate", 0, 15, -8)
        self.points = []
        for label, value in (("aclFemur", ACL_FEMUR), ("aclTibia", ACL_TIBIA), ("pclFemur", PCL_FEMUR),
                             ("pclTibia", PCL_TIBIA)):
            node = cmds.createNode("transform", name=label, parent=self.femur)
            cmds.setAttr(node + ".translate", *value)
            self.points.append(node)
        self.tibia = cmds.createNode("transform", name="tibia")
        anchor = om.MPoint(0.2, -2.6, 0.0) * _world(self.femur)
        cmds.setAttr(self.tibia + ".translate", anchor.x, anchor.y, anchor.z)
        cmds.setAttr(self.tibia + ".rotate", 12, -4, 30)
        self.rest = _world(self.tibia)
        # 生成時の脛骨の、大腿骨の空間での行列(大腿骨を後から動かしても基準はこれ)。
        self.restLocal = self.rest * _world(self.femur).inverse()
        self.setup = CrossedKneeLinkage.create(self.femur, self.tibia, *self.points, name="knee")
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
        """脛骨・靭帯・瞬間回転中心が独立計算と一致することを確かめ、前の靭帯の角度 φ を返す。"""
        b_point, c_point, phi = _solve(degrees, previous=previous)
        tibia = self._matrix("tibiaMatrix", owner)
        femur = _world(self.femur)
        # 脛骨の上の B0・C0(生成時の脛骨のローカル)が B・C へ動く。
        rest_inverse = self.restLocal.inverse()
        for rest, expected in ((ACL_TIBIA, b_point), (PCL_TIBIA, c_point)):
            local = om.MPoint(*rest) * rest_inverse
            moved = local * tibia * femur.inverse()
            self.assertAlmostEqual(moved.x, expected[0], delta=1e-4)
            self.assertAlmostEqual(moved.y, expected[1], delta=1e-4)
            self.assertAlmostEqual(moved.z, 0.0, delta=1e-4)
        # 脛骨の回転は生成時から n(-Z)回りに θ。
        relative = om.MTransformationMatrix(self.restLocal.inverse() * tibia * femur.inverse())
        rotation = relative.rotation(asQuaternion=True)
        expected = om.MQuaternion(math.radians(degrees), om.MVector(0, 0, -1))
        self.assertAlmostEqual(abs(rotation.x * expected.x + rotation.y * expected.y + rotation.z * expected.z
                                   + rotation.w * expected.w), 1.0, places=5)
        for attribute, origin, target in (("aclMatrix", ACL_FEMUR, b_point), ("pclMatrix", PCL_FEMUR, c_point)):
            ligament = self._matrix(attribute, owner)
            self.assertLess((self._local(ligament) - om.MPoint(*origin)).length(), 1e-5)
            axis = (om.MVector(ligament[0], ligament[1], ligament[2]) * femur.inverse()).normal()
            toward = om.MVector(target[0] - origin[0], target[1] - origin[1], 0).normal()
            self.assertAlmostEqual(axis * toward, 1.0, places=5)
        center = self._local(self._matrix("instantCenterMatrix", owner))
        expected_center = _crossing(b_point, c_point)
        self.assertAlmostEqual(center.x, expected_center[0], delta=1e-3)
        self.assertAlmostEqual(center.y, expected_center[1], delta=1e-3)
        self.assertAlmostEqual(cmds.getAttr((owner or self.owner) + ".excess"), 0.0, places=5)
        return phi, b_point, c_point, center

    def test_rest(self):
        """作成直後、脛骨の出力は生成時と一致し、靭帯の長さは付着点の距離、届かない量は0。"""
        self._close(self._matrix("tibiaMatrix"), self.rest, 1e-5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".aclLength"), _length(ACL_FEMUR, ACL_TIBIA), places=5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".pclLength"), _length(PCL_FEMUR, PCL_TIBIA), places=5)
        self._check(0.0)

    def test_flexion_sweep(self):
        """0〜120度の曲げで独立計算・Python版と一致し、靭帯の長さが保たれ、瞬間回転中心が後ろ・上へ移る。"""
        previous = None
        centers = []
        for degrees in range(0, 121, 10):
            with self.subTest(flexion=degrees):
                cmds.setAttr(self.owner + ".flexion", degrees)
                previous, b_point, c_point, center = self._check(degrees, previous)
                self.assertAlmostEqual(_length(ACL_FEMUR, b_point), _length(ACL_FEMUR, ACL_TIBIA), delta=1e-6)
                b, c, excess, crossing = CrossedKneeLinkage.tibiaPose(ACL_FEMUR, ACL_TIBIA, PCL_FEMUR, PCL_TIBIA,
                                                                       degrees, (0, 0, -1))
                self.assertLess(math.hypot(b[0] - b_point[0], b[1] - b_point[1]), 1e-4)
                self.assertLess(math.hypot(c[0] - c_point[0], c[1] - c_point[1]), 1e-4)
                self.assertLess(math.hypot(crossing[0] - center.x, crossing[1] - center.y), 1e-3)
                self.assertEqual(excess, 0.0)
                centers.append((center.x, center.y))
        # この配置では、瞬間回転中心は 0〜70度で後ろ(-X)へ、10〜120度で上(+Y)へ移る。
        for before, after in zip(centers[:8], centers[1:8]):
            self.assertLess(after[0], before[0])
        for before, after in zip(centers[1:], centers[2:]):
            self.assertGreater(after[1], before[1])

    def test_tibia_rolls_back(self):
        """曲げると脛骨は付着点の周りの固定軸ではなく、転がりながら後ろへ滑る(B0 の移動が回転だけより大きい)。"""
        cmds.setAttr(self.owner + ".flexion", 90)
        b_point, _, _ = _solve(90)
        self.assertGreater(_length(b_point, ACL_TIBIA), 0.5)

    def test_lengths_and_out_of_reach(self):
        """靭帯の長さを変えると新しい長さで解け、届かない場合は excess に不足を出す。"""
        acl = _length(ACL_FEMUR, ACL_TIBIA)
        pcl = _length(PCL_FEMUR, PCL_TIBIA)
        cmds.setAttr(self.owner + ".pclLength", pcl + 0.2)
        cmds.setAttr(self.owner + ".flexion", 30)
        b_point, c_point, _ = _solve(30, pcl=pcl + 0.2)
        b = self._local(om.MMatrix(cmds.getAttr(self.owner + ".aclMatrix")))
        self.assertLess(math.hypot(b.x - ACL_FEMUR[0], b.y - ACL_FEMUR[1]), 1e-5)
        pcl_matrix = self._matrix("pclMatrix")
        axis = (om.MVector(pcl_matrix[0], pcl_matrix[1], pcl_matrix[2]) * _world(self.femur).inverse()).normal()
        toward = om.MVector(c_point[0] - PCL_FEMUR[0], c_point[1] - PCL_FEMUR[1], 0).normal()
        self.assertAlmostEqual(axis * toward, 1.0, places=4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".excess"), 0.0, places=5)
        cmds.setAttr(self.owner + ".pclLength", pcl)
        cmds.setAttr(self.owner + ".aclLength", 10.0)
        # |D - v - A| < |a - p| なら不足は |a - p| - |D - v - A|。
        _, _, excess, _ = CrossedKneeLinkage.tibiaPose(ACL_FEMUR, ACL_TIBIA, PCL_FEMUR, PCL_TIBIA, 30, (0, 0, -1),
                                                       aclLength=10.0)
        self.assertGreater(excess, 0.1)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".excess"), excess, delta=1e-4)
        cmds.setAttr(self.owner + ".aclLength", acl)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".excess"), 0.0, places=5)

    def test_femur_moves(self):
        """作成後に腰・大腿骨を動かし回しても、脛骨と靭帯は大腿骨の空間で同じ式に従う。"""
        cmds.setAttr(self.hip + ".rotate", -30, 15, 60)
        cmds.setAttr(self.femur + ".rotate", 20, -10, 45)
        cmds.setAttr(self.femur + ".translate", -3, 2, 1)
        cmds.setAttr(self.owner + ".flexion", 70)
        self._check(70)

    def test_units_and_normal(self):
        """UI単位 mm・rad で作っても同じ結果になり、法線を逆にすると曲げの向きが逆になる。"""
        cmds.currentUnit(angle="rad", linear="mm")
        owner = str(CrossedKneeLinkage.create(self.femur, self.tibia, *self.points, name="units").container)
        cmds.currentUnit(angle="deg", linear="cm")
        self.assertAlmostEqual(cmds.getAttr(owner + ".aclLength"), _length(ACL_FEMUR, ACL_TIBIA), places=5)
        cmds.setAttr(owner + ".flexion", 50)
        self._check(50, owner=owner)
        conversions = [node for node in cmds.container(owner, query=True, nodeList=True)
                       if cmds.nodeType(node) == "unitConversion"]
        for node in conversions:
            self.assertAlmostEqual(cmds.getAttr(node + ".conversionFactor"), 1.0)
        flipped = str(CrossedKneeLinkage.create(self.femur, self.tibia, *self.points, name="flipped",
                                                normal=(0, 0, 1)).container)
        cmds.setAttr(flipped + ".flexion", -50)
        self._close(self._matrix("tibiaMatrix", flipped), self._matrix("tibiaMatrix", owner), 1e-4)

    def test_ownership_and_undo(self):
        """生成したノードはcontainerが所有し、入力へは接続せず、1回のUndoで消え、Redoで戻る。"""
        owned = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        self.assertIn("aimMatrix", {cmds.nodeType(node) for node in owned})
        for node in [self.tibia] + self.points:
            self.assertFalse(cmds.listConnections(node, source=True, destination=False) or [])
        cmds.undoInfo(state=True, infinity=True)
        before = set(cmds.ls())
        setup = CrossedKneeLinkage.create(self.femur, self.tibia, *self.points, name="again")
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
            CrossedKneeLinkage.create(self.femur, self.tibia, *self.points, name="knee")
        with self.assertRaises(ValueError):
            CrossedKneeLinkage.create(cmds.createNode("multiplyDivide"), self.tibia, *self.points, name="bad")
        with self.assertRaises(ValueError):
            CrossedKneeLinkage.create(self.femur, self.tibia, *self.points, name="bad", normal=(0, 0, 0))
        with self.assertRaises(ValueError):
            CrossedKneeLinkage.create(self.femur, self.tibia, *self.points, name="bad", normal=(0, "a", 1))
        a, b, d, _ = self.points
        with self.assertRaises(ValueError):
            CrossedKneeLinkage.create(self.femur, self.tibia, a, b, d, b, name="bad")
        # 2本の靭帯が平行なら法線が要る。
        parallel = cmds.createNode("transform", name="parallel", parent=self.femur)
        cmds.setAttr(parallel + ".translate", PCL_FEMUR[0] + 2.2, PCL_FEMUR[1] - 3.0, 0)
        with self.assertRaises(ValueError):
            CrossedKneeLinkage.create(self.femur, self.tibia, a, b, d, parallel, name="bad")
        CrossedKneeLinkage.create(self.femur, self.tibia, a, b, d, parallel, name="inParallel", normal=(0, 0, -1))
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
