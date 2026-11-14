"""OverShoulderCameraのカメラの位置・向き・画面の位置を、2人の頭のワールド位置から独立に計算した値で確かめる。"""

import math
import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import OverShoulderCamera

#: 位置(cm)の許容。vectorProduct・multiplyDivide が単精度なので丸めの範囲で確かめる。
POSITION = 1e-4

#: 向き(軸の成分)の許容。
AXIS = 1e-5


def _world(node):
    return om2.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _position(node):
    return om2.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))


def _expected(focus, partner, distance, angle, height, side, screenX, screenY, focal, horizontal, vertical):
    """試験側で書いた式: 水平の向きを回して基準の位置、focusへの向き、画面の位置へ平行に動かす。"""
    a, b = om2.MVector(focus), om2.MVector(partner)
    flat = om2.MVector(b.x - a.x, 0.0, b.z - a.z).normal()
    rotate = om2.MEulerRotation(0.0, math.radians(angle * side), 0.0).asMatrix()
    turned = om2.MVector(flat) * rotate
    base = a + turned * distance + om2.MVector(0.0, height, 0.0)
    back = (base - a).normal()
    right = (om2.MVector(0.0, 1.0, 0.0) ^ back).normal()
    up = back ^ right
    depth = (a - base).length()
    position = (base - right * (screenX * depth * horizontal * 25.4 / (2.0 * focal))
                - up * (screenY * depth * vertical * 25.4 / (2.0 * focal)))
    return position, right, up, back, turned


def _screen(camera, shape, point):
    """カメラの空間で、点がフィルムゲートのどこに写るか(左右・上下の端が ±1)。"""
    matrix = _world(camera)
    axes = [om2.MVector(matrix[4 * row], matrix[4 * row + 1], matrix[4 * row + 2]).normal() for row in range(3)]
    offset = om2.MVector(point) - om2.MVector(matrix[12], matrix[13], matrix[14])
    x, y, z = offset * axes[0], offset * axes[1], offset * axes[2]
    focal = cmds.getAttr(shape + ".focalLength")
    width = cmds.getAttr(shape + ".horizontalFilmAperture") * 25.4
    height = cmds.getAttr(shape + ".verticalFilmAperture") * 25.4
    return (x / -z) * focal / (width / 2.0), (y / -z) * focal / (height / 2.0)


class OverShoulderCameraTest(unittest.TestCase):
    """作成時に跳ねないこと、式との一致、画面の位置、線の側、所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転・移動した親の下にカメラ、別の親(回転・非一様スケール)の下に2人の頭を作る。"""
        cmds.file(new=True, force=True)
        rig = cmds.createNode("transform", name="cameraRig")
        cmds.setAttr(rig + ".translate", 3, 2, -4)
        cmds.setAttr(rig + ".rotate", 10, 25, -5)
        cmds.setAttr(rig + ".scale", 1.2, 1.2, 1.2)
        camera = cmds.camera(name="shotCam")[0]
        camera = cmds.parent(camera, rig)[0]
        self.shape = cmds.listRelatives(camera, shapes=True, fullPath=True)[0]
        self.camera = cmds.listRelatives(self.shape, parent=True, fullPath=True)[0]
        cmds.setAttr(self.camera + ".translate", 5, 4, 30)
        cmds.setAttr(self.camera + ".rotate", -10, 20, 3)
        cmds.setAttr(self.shape + ".focalLength", 40.0)
        stage = cmds.createNode("transform", name="stage")
        cmds.setAttr(stage + ".rotate", 0, 30, 0)
        cmds.setAttr(stage + ".scale", 1.0, 0.8, 1.3)
        self.focus = cmds.createNode("transform", name="heroHead", parent=stage)
        self.partner = cmds.createNode("transform", name="friendHead", parent=stage)
        cmds.setAttr(self.focus + ".translate", 0, 16, 0)
        cmds.setAttr(self.partner + ".translate", 2, 15, 9)
        self.rest = _world(self.camera)
        self.setup = OverShoulderCamera.create(self.camera, self.focus, self.partner, name="ots", angle=20.0,
                                               height=2.0, screenX=1.0 / 3.0, screenY=0.2)
        self.owner = str(self.setup.container)

    def _values(self):
        return [cmds.getAttr(self.owner + "." + attr) for attr in ("distance", "angle", "height", "side",
                                                                    "screenX", "screenY")]

    def _check(self, msg=""):
        """カメラのワールド行列を、試験側の式・Python版と比べ、focusが指定の画面の位置へ写ることを確かめる。"""
        distance, angle, height, side, screenX, screenY = self._values()
        focal = cmds.getAttr(self.shape + ".focalLength")
        horizontal = cmds.getAttr(self.shape + ".horizontalFilmAperture")
        vertical = cmds.getAttr(self.shape + ".verticalFilmAperture")
        a, b = _position(self.focus), _position(self.partner)
        position, right, up, back, turned = _expected(a, b, distance, angle, height, side, screenX, screenY, focal,
                                                      horizontal, vertical)
        matrix = _world(self.camera)
        for index in range(3):
            self.assertAlmostEqual(matrix[12 + index], position[index], delta=POSITION, msg=msg)
            for row, axis in enumerate((right, up, back)):
                scale = om2.MVector(matrix[4 * row], matrix[4 * row + 1], matrix[4 * row + 2]).length()
                self.assertAlmostEqual(matrix[4 * row + index] / scale, axis[index], delta=AXIS, msg=msg)
        python = OverShoulderCamera.placement(a, b, distance, angle, height, side, screenX, screenY, focal,
                                              horizontal, vertical)
        for index in range(16):
            expected = list(right) + [0] + list(up) + [0] + list(back) + [0] + list(position) + [1]
            self.assertAlmostEqual(python[index], expected[index], delta=1e-9, msg=msg)
        x, y = _screen(self.camera, self.shape, a)
        self.assertAlmostEqual(x, screenX, delta=1e-5, msg=msg)
        self.assertAlmostEqual(y, screenY, delta=1e-5, msg=msg)
        base = a + turned * distance + om2.MVector(0, height, 0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".focusDistance"), (base - a).length(), delta=POSITION,
                               msg=msg)
        return position, turned

    def test_rest_does_not_jump(self):
        """既定の weight=0 では作成直後のカメラの姿勢が変わらない。"""
        after = _world(self.camera)
        for index in range(16):
            self.assertAlmostEqual(after[index], self.rest[index], delta=1e-5)
        self.assertEqual(cmds.getAttr(self.owner + ".weight"), 0.0)
        # 既定の距離は作成時の2人の水平の距離の1.5倍。
        a, b = _position(self.focus), _position(self.partner)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".distance"), 1.5 * math.hypot(b.x - a.x, b.z - a.z),
                               delta=1e-6)

    def test_random_moves(self):
        """2人を乱数で動かすと、カメラは式どおりに付いていき、focusは常に画面の同じ位置に写る。"""
        cmds.setAttr(self.owner + ".weight", 1.0)
        self._check("weight 1")
        generator = random.Random(28)
        for index in range(20):
            for node in (self.focus, self.partner):
                cmds.setAttr(node + ".translate", generator.uniform(-20, 20), generator.uniform(10, 20),
                             generator.uniform(-20, 20))
            cmds.setAttr(self.owner + ".angle", generator.uniform(0, 80))
            cmds.setAttr(self.owner + ".height", generator.uniform(-5, 5))
            cmds.setAttr(self.owner + ".distance", generator.uniform(5, 40))
            cmds.setAttr(self.owner + ".screenX", generator.uniform(-1, 1))
            cmds.setAttr(self.owner + ".screenY", generator.uniform(-1, 1))
            if math.hypot(*(cmds.getAttr(self.partner + ".translate")[0][axis] - cmds.getAttr(
                    self.focus + ".translate")[0][axis] for axis in (0, 2))) < 1.0:
                continue
            self._check("move {}".format(index))
        cmds.setAttr(self.shape + ".focalLength", 85.0)
        cmds.setAttr(self.shape + ".verticalFilmAperture", 0.6)
        self._check("lens")

    def test_camera_parent_and_evaluation_modes(self):
        """カメラの親・offsetParentMatrix・時間を動かしても、DG・serial・parallelの各評価で古い値にならない。

        connect=True の translate はカメラ自身の parentInverseMatrix から計算する。parentInverseMatrix は
        offsetParentMatrix と親のワールド行列だけで決まり、駆動される translate・rotate には依存しないので
        循環は無い(LiveMirror の offsetParentMatrix を駆動する形とは異なる)。出力に先立ってカメラの
        ワールド行列を問い合わせ、式と比べる。
        """
        rig = cmds.listRelatives(self.camera, parent=True, fullPath=True)[0]
        stage = cmds.listRelatives(self.focus, parent=True, fullPath=True)[0]
        cmds.setAttr(self.owner + ".weight", 1.0)
        cmds.setKeyframe(rig, attribute="translateX", time=1, value=3.0)
        cmds.setKeyframe(rig, attribute="translateX", time=10, value=-12.0)
        cmds.setKeyframe(self.focus, attribute="translateZ", time=1, value=0.0)
        cmds.setKeyframe(self.focus, attribute="translateZ", time=10, value=-8.0)
        original = cmds.evaluationManager(query=True, mode=True)[0]
        try:
            for mode in ("off", "serial", "parallel"):
                cmds.evaluationManager(mode=mode)
                generator = random.Random(29)
                for index in range(12):
                    cmds.currentTime(1 + index % 10)
                    cmds.setAttr(rig + ".rotate", generator.uniform(-60, 60), generator.uniform(-90, 90), 0.0)
                    cmds.setAttr(stage + ".rotateY", generator.uniform(-45, 45))
                    offset = om2.MEulerRotation(0.0, generator.uniform(-1, 1), 0.3).asMatrix()
                    offset[12], offset[14] = generator.uniform(-5, 5), generator.uniform(-5, 5)
                    cmds.setAttr(self.camera + ".offsetParentMatrix", list(offset), type="matrix")
                    self._check("{} {}".format(mode, index))
        finally:
            cmds.evaluationManager(mode=original)

    def test_side_of_the_line(self):
        """side の符号で線のどちら側にカメラが来るかが決まり、2人を動かしても同じ側に留まる。"""
        cmds.setAttr(self.owner + ".weight", 1.0)
        for side in (1.0, -1.0):
            cmds.setAttr(self.owner + ".side", side)
            for offset in ((0, 0, 0), (12, 0, -7), (-30, 3, 15)):
                cmds.setAttr(self.partner + ".translate", 2 + offset[0], 15 + offset[1], 9 + offset[2])
                _, turned = self._check("side {} {}".format(side, offset))
                a, b, c = _position(self.focus), _position(self.partner), _position(self.camera)
                line = om2.MVector(b.x - a.x, 0, b.z - a.z)
                cross = (line ^ om2.MVector(c.x - a.x, 0, c.z - a.z)).y
                self.assertGreater(cross * side, 0.0)
        # side=0 なら、上から見てカメラは2人を結ぶ線の延長上(partnerの後ろ)。
        cmds.setAttr(self.owner + ".side", 0.0)
        cmds.setAttr(self.owner + ".screenX", 0.0)
        cmds.setAttr(self.owner + ".screenY", 0.0)
        cmds.setAttr(self.owner + ".height", 0.0)
        self._check("on the line")
        a, b, c = _position(self.focus), _position(self.partner), _position(self.camera)
        flat = om2.MVector(b.x - a.x, 0, b.z - a.z)
        self.assertAlmostEqual((flat ^ om2.MVector(c.x - a.x, 0, c.z - a.z)).y, 0.0, delta=1e-3)
        self.assertGreater(flat * om2.MVector(c.x - a.x, 0, c.z - a.z), 0.0)

    def test_weight_blend(self):
        """weight の途中の値は、作成時の姿勢と肩越しの配置の位置を線形に補間する。"""
        cmds.setAttr(self.owner + ".weight", 1.0)
        target, _ = self._check("full")
        cmds.setAttr(self.owner + ".weight", 0.25)
        rest = om2.MVector(self.rest[12], self.rest[13], self.rest[14])
        expected = rest + (target - rest) * 0.25
        position = _position(self.camera)
        for index in range(3):
            self.assertAlmostEqual(position[index], expected[index], delta=POSITION)

    def test_without_connect(self):
        """connect=False ではカメラへ接続せず、出力の行列だけを作る。カメラのシェイプも受け付ける。"""
        cmds.delete(self.owner)
        owner = str(OverShoulderCamera.create(self.shape, self.focus, self.partner, name="ots2", connect=False,
                                              weight=1.0).container)
        self.assertFalse(cmds.listConnections(self.camera + ".translate", source=True, destination=False))
        matrix = om2.MMatrix(cmds.getAttr(owner + ".matrix"))
        a, b = _position(self.focus), _position(self.partner)
        distance = cmds.getAttr(owner + ".distance")
        python = OverShoulderCamera.placement(
            a, b, distance, 15.0, focalLength=40.0,
            horizontalAperture=cmds.getAttr(self.shape + ".horizontalFilmAperture"),
            verticalAperture=cmds.getAttr(self.shape + ".verticalFilmAperture"))
        for index in range(16):
            self.assertAlmostEqual(matrix[index], python[index], delta=POSITION)

    def test_container_and_undo(self):
        """演算ノードはcontainerが所有し(単位変換のノードを挟まない)、1回のUndoで全体が消えRedoで戻る。"""
        nodes = cmds.container(self.owner, query=True, nodeList=True) or []
        allowed = ("vectorProduct", "plusMinusAverage", "multiplyDivide", "composeMatrix", "aimMatrix",
                   "distanceBetween", "pickMatrix", "multMatrix", "blendMatrix", "decomposeMatrix")
        self.assertEqual(sorted(set(map(cmds.nodeType, nodes))), sorted(allowed))
        self.assertFalse(cmds.ls(type="unitConversion"))
        cmds.delete(self.owner)
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        OverShoulderCamera.create(self.camera, self.focus, self.partner, name="ots3")
        self.assertTrue(cmds.objExists("ots3"))
        cmds.undo()
        self.assertFalse(cmds.objExists("ots3"))
        self.assertFalse(cmds.listConnections(self.camera + ".translate", source=True, destination=False))
        cmds.redo()
        self.assertTrue(cmds.objExists("ots3"))
        self.assertTrue(cmds.listConnections(self.camera + ".translate", source=True, destination=False))

    def test_arguments(self):
        """不正な引数は ValueError で、何も残さない。"""
        other = cmds.createNode("transform", name="notCamera")
        free = cmds.camera(name="freeCam")[0]
        above = cmds.createNode("transform", name="above", parent=self.focus)
        cmds.setAttr(above + ".translate", 0, 5, 0)
        base = dict(camera=free, focus=self.focus, partner=self.partner)
        cases = [
            dict(base, camera="missing"),
            dict(base, camera=other),
            dict(base, focus="missing"),
            dict(base, partner=self.focus),
            dict(base, focus=free),
            dict(base, partner=above),
            dict(base, angle=95.0),
            dict(base, side=2.0),
            dict(base, screenX=float("nan")),
            dict(base, screenY=-1.5),
            dict(base, weight=1.5),
            dict(base, distance=0.0),
            dict(base, height=True),
            dict(base, camera=self.camera),
            dict(base, name="ots"),
        ]
        before = set(cmds.ls())
        for case in cases:
            with self.assertRaises(ValueError, msg=str(case)):
                OverShoulderCamera.create(**case)
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main(argv=["over_shoulder_camera"], exit=False, verbosity=2)
