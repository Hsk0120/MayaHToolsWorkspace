"""CameraAngleReaderの角度と重みを、OpenMayaで独立に求めたカメラの方向と区分線形の補間と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import CameraAngleReader
from mlrig.setups.cameraAngleReader import WEIGHTS


def _expected_angles(head, camera, forward=(0, 0, 1), up=(0, 1, 0)):
    """OpenMayaで、頭の空間でのカメラの水平角・垂直角(度)を求める。"""
    inverse = om.MMatrix(cmds.getAttr(head + ".worldInverseMatrix[0]"))
    world = om.MMatrix(cmds.getAttr(camera + ".worldMatrix[0]"))
    point = om.MPoint(world[12], world[13], world[14]) * inverse
    vector = om.MVector(point)
    forward, up = om.MVector(*forward), om.MVector(*up)
    left = up ^ forward
    f, u, l = vector * forward, vector * up, vector * left
    return math.degrees(math.atan2(l, f)), math.degrees(math.atan2(u, math.hypot(f, l)))


def _expected_weights(yaw, pitch, yawRange=90.0, pitchRange=60.0, backFade=30.0):
    """十字に置いた5点の区分線形の補間と、後ろへの移行を場合分けで求める(実装の式とは独立に書く)。"""
    a = min(abs(yaw) / yawRange, 1.0)
    b = min(abs(pitch) / pitchRange, 1.0)
    if a + b <= 1.0:
        # 正面・横・上下の三角形の中: 重心座標。
        front, side, level = 1.0 - a - b, a, b
    else:
        # 三角形の外: 中心から横の点と上下の点へ引いた線に挟まれた領域で、2点の間を補間する。
        front, side, level = 0.0, a / (a + b), b / (a + b)
    values = dict.fromkeys(WEIGHTS, 0.0)
    values["weightFront"] = front
    values["weightLeft" if yaw >= 0 else "weightRight"] = side
    values["weightAbove" if pitch >= 0 else "weightBelow"] = level
    k = 1.0 if abs(yaw) <= 180.0 - backFade else max(0.0, (180.0 - abs(yaw)) / backFade)
    for key in values:
        values[key] *= k
    values["weightBack"] = 1.0 - k
    return values


def _place(camera, head, yaw, pitch, distance=30.0):
    """頭の生成時の空間で、指定した水平角・垂直角の方向へカメラを置く。"""
    world = om.MMatrix(cmds.getAttr(head + ".worldMatrix[0]"))
    local = om.MPoint(distance * math.cos(math.radians(pitch)) * math.sin(math.radians(yaw)),
                      distance * math.sin(math.radians(pitch)),
                      distance * math.cos(math.radians(pitch)) * math.cos(math.radians(yaw)))
    point = local * world
    cmds.xform(camera, worldSpace=True, translation=(point.x, point.y, point.z))


class CameraAngleReaderTest(unittest.TestCase):
    """角度と重みの一致・主な方向・連続性・アトリビュート・頭の動き・軸・所有・Undo・引数を確認する。"""

    def setUp(self):
        """移動・回転した頭と、カメラのtransformを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.head = cmds.createNode("joint", name="head")
        cmds.setAttr(self.head + ".translate", 2, 15, -3)
        cmds.setAttr(self.head + ".rotate", 10, 35, -5)
        self.camera = cmds.createNode("transform", name="shotCam")
        _place(self.camera, self.head, 0.0, 0.0)
        self.setup = CameraAngleReader.create(self.head, self.camera, name="reader")
        self.owner = str(self.setup.container)

    def _check(self, yawRange=90.0, pitchRange=60.0, backFade=30.0, forward=(0, 0, 1), up=(0, 1, 0)):
        """現在の出力が、独立に求めた角度・重みと一致し、和が1であることを確かめる。"""
        yaw, pitch = _expected_angles(self.head, self.camera, forward, up)
        actualYaw = cmds.getAttr(self.owner + ".yaw")
        self.assertAlmostEqual(math.cos(math.radians(actualYaw)), math.cos(math.radians(yaw)), delta=1e-5)
        self.assertAlmostEqual(math.sin(math.radians(actualYaw)), math.sin(math.radians(yaw)), delta=1e-5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".pitch"), pitch, delta=1e-3)
        expected = _expected_weights(yaw, pitch, yawRange, pitchRange, backFade)
        actual = {name: cmds.getAttr(self.owner + "." + name) for name in WEIGHTS}
        for name in WEIGHTS:
            self.assertAlmostEqual(actual[name], expected[name], delta=1e-4, msg="{} {} {}".format(name, yaw, pitch))
            self.assertGreaterEqual(actual[name], -1e-6)
        self.assertAlmostEqual(sum(actual.values()), 1.0, delta=1e-5)
        python = CameraAngleReader.weights(yaw, pitch, yawRange, pitchRange, backFade)
        for name in WEIGHTS:
            self.assertAlmostEqual(python[name], expected[name], delta=1e-9)
        return actual

    def test_grid(self):
        """水平角・垂直角の格子の全ての方向で、角度と重みが独立計算と一致する。"""
        for yaw in range(-175, 180, 25):
            for pitch in (-80, -50, -20, 0, 15, 45, 75):
                with self.subTest(yaw=yaw, pitch=pitch):
                    _place(self.camera, self.head, yaw, pitch, distance=10.0 + abs(yaw) * 0.1)
                    self._check()

    def test_named_directions(self):
        """正面・左・右・上・下・後ろでは、その重みだけが1になる。"""
        for yaw, pitch, name in ((0, 0, "weightFront"), (90, 0, "weightLeft"), (-100, 0, "weightRight"),
                                 (0, 70, "weightAbove"), (0, -60, "weightBelow"), (180.0, 0, "weightBack")):
            with self.subTest(name=name):
                _place(self.camera, self.head, yaw, pitch)
                actual = self._check()
                self.assertAlmostEqual(actual[name], 1.0, delta=1e-3)
        # 正面と左の中間は半分ずつ、左上の斜めは左と上の2つだけ。
        _place(self.camera, self.head, 45, 0)
        actual = self._check()
        self.assertAlmostEqual(actual["weightFront"], 0.5, delta=1e-4)
        self.assertAlmostEqual(actual["weightLeft"], 0.5, delta=1e-4)
        _place(self.camera, self.head, 80, 50)
        actual = self._check()
        self.assertAlmostEqual(actual["weightFront"], 0.0, delta=1e-6)
        self.assertAlmostEqual(actual["weightLeft"] + actual["weightAbove"], 1.0, delta=1e-5)

    def test_continuous(self):
        """カメラを頭の周りに1度ずつ回しても、真後ろの左右の入れ替わりを含めて重みが跳ねない。"""
        for pitch in (0.0, 30.0, -40.0):
            previous = None
            for step in range(0, 361):
                _place(self.camera, self.head, -180.0 + step, pitch)
                current = [cmds.getAttr(self.owner + "." + name) for name in WEIGHTS]
                if previous is not None:
                    jump = max(abs(a - b) for a, b in zip(current, previous))
                    # 最大の傾きは後ろへの移行の 1/backFade = 1/30 毎度。
                    self.assertLess(jump, 1.0 / 30.0 + 1e-3, msg="pitch {} step {}".format(pitch, step))
                previous = current
        previous = None
        for step in range(0, 179):
            _place(self.camera, self.head, 60.0, -89.0 + step)
            current = [cmds.getAttr(self.owner + "." + name) for name in WEIGHTS]
            if previous is not None:
                self.assertLess(max(abs(a - b) for a, b in zip(current, previous)), 0.05)
            previous = current

    def test_attributes(self):
        """yawRange・pitchRange・backFade を変えると、独立に求めた重みと一致する。"""
        cmds.setAttr(self.owner + ".yawRange", 45.0)
        cmds.setAttr(self.owner + ".pitchRange", 30.0)
        cmds.setAttr(self.owner + ".backFade", 60.0)
        for yaw, pitch in ((30, 10), (60, -20), (-130, 25), (150, 5), (-20, -40)):
            with self.subTest(yaw=yaw, pitch=pitch):
                _place(self.camera, self.head, yaw, pitch)
                self._check(45.0, 30.0, 60.0)

    def test_head_moves(self):
        """カメラを止めて頭を回すと、頭から見た角度が変わり、独立計算と一致する。"""
        _place(self.camera, self.head, 0, 0)
        cmds.setAttr(self.head + ".rotateY", 35 + 60)
        actual = self._check()
        self.assertGreater(actual["weightRight"], 0.5)
        cmds.setAttr(self.head + ".rotateX", 10 + 40)
        self._check()
        cmds.setAttr(self.head + ".translateY", 40)
        self._check()

    def test_axes(self):
        """forwardAxis=-x・upAxis=z の頭でも、その軸を正面・上として角度を測る。"""
        cmds.file(new=True, force=True)
        self.head = cmds.createNode("transform", name="sideHead")
        cmds.setAttr(self.head + ".rotate", 20, 0, 30)
        self.camera = cmds.createNode("transform", name="sideCam")
        self.setup = CameraAngleReader.create(self.head, self.camera, name="sideReader", forwardAxis="-x", upAxis="z")
        self.owner = str(self.setup.container)
        world = om.MMatrix(cmds.getAttr(self.head + ".worldMatrix[0]"))
        for local in ((-10, 0, 0), (-5, 5, 2), (3, -6, 4), (2, 1, -9)):
            point = om.MPoint(*local) * world
            cmds.xform(self.camera, worldSpace=True, translation=(point.x, point.y, point.z))
            self._check(forward=(-1, 0, 0), up=(0, 0, 1))
        point = om.MPoint(-10, 0, 0) * world
        cmds.xform(self.camera, worldSpace=True, translation=(point.x, point.y, point.z))
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".weightFront"), 1.0, delta=1e-5)

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = set()
        for name in WEIGHTS + ("yaw", "pitch"):
            upstream.update(cmds.listHistory(self.owner + "." + name, pruneDagObjects=True) or [])
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "joint", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        head = cmds.createNode("joint", name="undoHead")
        camera = cmds.createNode("transform", name="undoCam")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        CameraAngleReader.create(head, camera, name="undoReader")
        self.assertTrue(cmds.objExists("undoReader"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoReader"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoReader.weightFront"))

    def test_arguments(self):
        """軸・範囲・有限でない値・transform以外・同じノード・名前の重複を拒否する。"""
        for kwargs in ({"forwardAxis": "w"}, {"upAxis": "-z", "forwardAxis": "z"}, {"yawRange": 0.0},
                       {"yawRange": 200.0}, {"pitchRange": 95.0}, {"backFade": -1.0},
                       {"pitchRange": float("nan")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CameraAngleReader.create(self.head, self.camera, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            CameraAngleReader.create(node, self.camera, name="bad")
        with self.assertRaises(ValueError):
            CameraAngleReader.create(self.head, self.head, name="bad")
        with self.assertRaises(ValueError):
            CameraAngleReader.create(self.head, self.camera, name="reader")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
