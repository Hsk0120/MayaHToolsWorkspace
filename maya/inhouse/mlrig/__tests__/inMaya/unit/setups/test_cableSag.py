"""CableSagの点の位置・向き・垂れの深さを、OpenMayaで独立に計算した値・数値で解いた懸垂線・弧長で確かめる。"""

import math
import unittest

from maya import cmds
import maya.api.OpenMaya as om

from mlrig.setups import CableSag

COUNT = 7


def _world_position(node):
    """ノードのワールド位置。"""
    matrix = om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))
    return om.MVector(matrix[12], matrix[13], matrix[14])


def _pos(matrix):
    """行列の位置。"""
    return om.MVector(matrix[12], matrix[13], matrix[14])


def _expected(a, b, length, count, gravity=om.MVector(0, -1, 0)):
    """放物線の近似で垂れた点の位置と接線を、DGと別の手順(OpenMaya)で求める。"""
    chord = b - a
    span = chord.length()
    g = om.MVector(gravity).normal()
    unit = om.MVector(chord).normal()
    down = g - unit * (g * unit)
    down = down.normal() if down.length() > 1e-12 else om.MVector()
    depth = math.sqrt(max((length - span) * (2.0 * length + span) / 8.0, 0.0))
    result = []
    for index in range(count):
        u = index / float(count - 1)
        point = a + chord * u + down * (depth * 4.0 * u * (1.0 - u))
        tangent = chord + down * (depth * 4.0 * (1.0 - 2.0 * u))
        result.append((point, tangent))
    return result, depth


def _catenary_sag(span, length):
    """長さlengthのケーブルを水平な距離spanで張った懸垂線の中央の深さを、2a·sinh(span/2a)=length の二分法で求める。"""
    low, high = 1e-6, 1e6
    for _ in range(200):
        a = math.sqrt(low * high)
        if 2.0 * a * math.sinh(span / (2.0 * a)) > length:
            low = a
        else:
            high = a
    return a * math.cosh(span / (2.0 * a)) - a


def _arc(a, b, depth, gravity=om.MVector(0, -1, 0), samples=4000):
    """深さdepthの放物線の弧長を細かい折れ線で求める。"""
    chord = b - a
    unit = om.MVector(chord).normal()
    down = gravity - unit * (gravity * unit)
    down = down.normal()
    total = 0.0
    previous = a
    for index in range(1, samples + 1):
        u = index / float(samples)
        point = a + chord * u + down * (depth * 4.0 * u * (1.0 - u))
        total += (point - previous).length()
        previous = point
    return total


class CableSagTest(unittest.TestCase):
    """独立計算との一致・枠の向き・弧長・張った場合・長さの変更・重力の向き・UI単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """回転・移動した柱の子の始点と、ワールド直下の終点を置き、7点のケーブルを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.pole = cmds.createNode("transform", name="pole")
        cmds.setAttr(self.pole + ".translate", -3, 2, 1)
        cmds.setAttr(self.pole + ".rotate", 15, 30, -10)
        self.start = cmds.createNode("transform", name="hook", parent=self.pole)
        cmds.setAttr(self.start + ".translate", 0, 4, 0)
        self.end = cmds.createNode("transform", name="plug")
        cmds.setAttr(self.end + ".translate", 6, 3, 2)
        self.span = (_world_position(self.end) - _world_position(self.start)).length()
        self.setup = CableSag.create(self.start, self.end, COUNT, name="cable")
        self.owner = str(self.setup.container)

    def _matrix(self, index, owner=None):
        """containerの点の行列。"""
        return om.MMatrix(cmds.getAttr("{}.matrix{}".format(owner or self.owner, index)))

    def _check(self, owner=None, count=COUNT, gravity=om.MVector(0, -1, 0), tolerance=1e-4):
        """全点の位置と枠を独立計算と比べる。"""
        owner = owner or self.owner
        a, b = _world_position(self.start), _world_position(self.end)
        length = cmds.getAttr(owner + ".length")
        expected, depth = _expected(a, b, length, count, gravity)
        self.assertAlmostEqual(cmds.getAttr(owner + ".sag"), depth, delta=tolerance)
        self.assertAlmostEqual(cmds.getAttr(owner + ".span"), (b - a).length(), delta=tolerance)
        python = CableSag.points(a, b, length, count, gravity)
        for index, (point, tangent) in enumerate(expected):
            matrix = self._matrix(index, owner)
            position = om.MVector(matrix[12], matrix[13], matrix[14])
            self.assertLess((position - point).length(), tolerance, msg="point {}".format(index))
            self.assertLess((om.MVector(python[index]) - point).length(), 1e-9)
            x = om.MVector(matrix[0], matrix[1], matrix[2])
            y = om.MVector(matrix[4], matrix[5], matrix[6])
            z = om.MVector(matrix[8], matrix[9], matrix[10])
            for axis in (x, y, z):
                self.assertAlmostEqual(axis.length(), 1.0, delta=1e-5)
            self.assertAlmostEqual(x * y, 0.0, delta=1e-5)
            self.assertAlmostEqual(y * z, 0.0, delta=1e-5)
            self.assertLess(((x ^ y) - z).length(), 1e-5)
            self.assertGreater(x * tangent.normal(), 1.0 - 1e-6)
            self.assertAlmostEqual(z * gravity.normal(), 0.0, delta=1e-5)
            self.assertLess(y * gravity.normal(), 0.0)
        return expected, depth

    def test_rest_and_positions(self):
        """作成直後と、終点を上下前後へ動かした各姿勢で、独立計算と一致し両端は留めた位置にある。"""
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".length"), self.span * 1.1, places=6)
        for translate in ((6, 3, 2), (4, 8, -1), (2, -2, 3), (8, 4, 6), (1, 5, 0.5), (12, 3, 2)):
            cmds.setAttr(self.end + ".translate", *translate)
            expected, depth = self._check()
            self.assertLess((expected[0][0] - _world_position(self.start)).length(), 1e-4)
            self.assertLess((expected[-1][0] - _world_position(self.end)).length(), 1e-4)
            distance = (_world_position(self.end) - _world_position(self.start)).length()
            if distance < self.span * 1.1:
                self.assertGreater(depth, 0.0)
            else:
                self.assertEqual(depth, 0.0)

    def test_sag_hangs_below_the_chord(self):
        """水平に張ると中央が弦から真下へ深さsagだけ垂れ、両端を近づけるほど深くなる。"""
        cmds.setAttr(self.pole + ".rotate", 0, 0, 0)
        cmds.setAttr(self.end + ".translate", 7, 6, 1)
        a = _world_position(self.start)
        b = _world_position(self.end)
        self.assertAlmostEqual(a.y, b.y, places=6)
        middle = self._matrix(COUNT // 2)
        sag = cmds.getAttr(self.owner + ".sag")
        mid = (a + b) * 0.5
        self.assertAlmostEqual(middle[13], mid.y - sag, places=4)
        self.assertAlmostEqual(middle[12], mid.x, places=4)
        self.assertAlmostEqual(middle[14], mid.z, places=4)
        previous = sag
        for x in (5, 3, 1):
            cmds.setAttr(self.end + ".translateX", x)
            current = cmds.getAttr(self.owner + ".sag")
            self.assertGreater(current, previous)
            previous = current

    def test_arc_length(self):
        """出力の放物線の弧長は長さLより短く、L/Dが1.02・1.1・1.2・1.4・2で誤差0.02%・0.2%・0.5%・1.2%・2.4%以内(近似の精度)。"""
        a = _world_position(self.start)
        b = _world_position(self.end)
        span = (b - a).length()
        for ratio, error in ((1.02, 0.0002), (1.1, 0.002), (1.2, 0.005), (1.4, 0.012), (2.0, 0.024)):
            cmds.setAttr(self.owner + ".length", span * ratio)
            depth = cmds.getAttr(self.owner + ".sag")
            arc = _arc(a, b, depth)
            self.assertLess(arc, span * ratio)
            self.assertLess((span * ratio - arc) / (span * ratio), error)
            # 出力の点の折れ線は弧長以下で、弦以上。
            points = [_pos(self._matrix(i)) for i in range(COUNT)]
            polyline = sum((points[i + 1] - points[i]).length() for i in range(COUNT - 1))
            self.assertLessEqual(polyline, arc + 1e-6)
            self.assertGreater(polyline, span)

    def test_catenary_depth(self):
        """水平に張った場合の深さsagは、数値で解いた懸垂線の中央の深さより浅く、差は1/117未満(閉じた近似の精度)。"""
        cmds.setAttr(self.pole + ".rotate", 0, 0, 0)
        cmds.setAttr(self.end + ".translate", 7, 6, 1)
        span = cmds.getAttr(self.owner + ".span")
        for ratio in (1.01, 1.1, 1.3, 2.0, 4.0):
            cmds.setAttr(self.owner + ".length", span * ratio)
            sag = cmds.getAttr(self.owner + ".sag")
            exact = _catenary_sag(span, span * ratio)
            self.assertLessEqual(sag, exact + 1e-6)
            self.assertLess((exact - sag) / exact, 1.0 / 117.0)

    def test_taut(self):
        """両端の距離が長さ以上になると垂れは0で、点は弦の上に等間隔に並ぶ。"""
        cmds.setAttr(self.owner + ".length", self.span * 0.5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".sag"), 0.0, places=6)
        a = _world_position(self.start)
        b = _world_position(self.end)
        for index in range(COUNT):
            u = index / float(COUNT - 1)
            point = _pos(self._matrix(index))
            self.assertLess((point - (a + (b - a) * u)).length(), 1e-4)
        self._check()

    def test_gravity_and_count(self):
        """重力の向き(-Z)と点の数2・12でも独立計算と一致する。"""
        gravity = om.MVector(0, 0, -1)
        owner = str(CableSag.create(self.start, self.end, 12, name="sideways", gravity=(0, 0, -2)).container)
        self._check(owner, 12, gravity)
        cmds.setAttr(self.end + ".translate", 3, 7, 5)
        self._check(owner, 12, gravity)
        pair = str(CableSag.create(self.start, self.end, 2, name="pair", length=3.0).container)
        self._check(pair, 2)

    def test_units(self):
        """UI単位mm/radで作っても、長さの引数はcmのままで点もcmで作った場合と同じで、自動の単位変換が入らない。"""
        cmds.currentUnit(angle="rad", linear="mm")
        owner = str(CableSag.create(self.start, self.end, COUNT, name="metric", length=9.9).container)
        cmds.currentUnit(angle="deg", linear="cm")
        self.assertAlmostEqual(cmds.getAttr(owner + ".length"), 9.9, places=6)
        self._check(owner)
        cmds.setAttr(self.end + ".translate", 3, 1, 4)
        self._check(owner)
        owned = cmds.container(owner, query=True, nodeList=True) or []
        conversions = [node for node in owned if cmds.nodeType(node) == "unitConversion"]
        for node in conversions:
            self.assertAlmostEqual(cmds.getAttr(node + ".conversionFactor"), 1.0)

    def test_ownership_and_undo(self):
        """生成したノードはcontainerが所有し、1回のUndoで消え、Redoで戻る。"""
        cmds.undoInfo(state=True, infinity=True)
        before = set(cmds.ls())
        setup = CableSag.create(self.start, self.end, 4, name="again")
        created = set(cmds.ls()) - before - set(cmds.ls(type="hyperLayout"))
        owned = set(cmds.container(str(setup.container), query=True, nodeList=True) or [])
        self.assertIn("fourByFourMatrix", {cmds.nodeType(node) for node in owned})
        self.assertEqual(created - owned, {"again"})
        cmds.undo()
        self.assertFalse(cmds.objExists("again"))
        cmds.redo()
        self.assertTrue(cmds.objExists("again"))

    def test_bad_arguments(self):
        """不正な引数はValueErrorになる。"""
        with self.assertRaises(ValueError):
            CableSag.create(self.start, self.end, name="cable")
        with self.assertRaises(ValueError):
            CableSag.create(self.start, self.end, 1, name="bad")
        with self.assertRaises(ValueError):
            CableSag.create(self.start, self.end, 2.5, name="bad")
        with self.assertRaises(ValueError):
            CableSag.create(self.start, self.end, name="bad", length=-1.0)
        with self.assertRaises(ValueError):
            CableSag.create(self.start, self.end, name="bad", gravity=(0, 0, 0))
        with self.assertRaises(ValueError):
            CableSag.create(self.start, self.start, name="bad")
        with self.assertRaises(ValueError):
            CableSag.create(cmds.createNode("multiplyDivide", name="notTransform"), self.end, name="bad")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
