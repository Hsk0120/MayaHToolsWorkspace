"""EyeHighlightのハイライトの位置・向きを、眼球・カメラ・光のワールド位置から独立に計算した値で確かめる。"""

import math
import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import EyeHighlight

#: 位置(cm)の許容。vectorProduct・blendColors が単精度なので丸めの範囲で確かめる。
POSITION = 1e-4

#: 向き(軸の成分)の許容。
AXIS = 1e-5

VECTORS = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1), "-x": (-1, 0, 0), "-y": (0, -1, 0), "-z": (0, 0, -1)}


def _world(node):
    return om2.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _position(node):
    return om2.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))


def _row(matrix, index):
    return om2.MVector(matrix[4 * index], matrix[4 * index + 1], matrix[4 * index + 2])


def _axisOf(matrix, name):
    """行列の局所の軸 name(符号付き)のワールドの単位ベクトル。"""
    vector = _row(matrix, "xyz".index(name[-1])).normal()
    return -vector if name.startswith("-") else vector


def _expectedDirection(eye, camera, light, follow, aimAxis):
    """試験側で書いた式: カメラと光への向きの中間を、目の前の向きと follow で混ぜた単位ベクトル。"""
    center = om2.MVector(eye[12], eye[13], eye[14])
    view = (om2.MVector(camera) - center).normal()
    half = view if light is None else (view + (om2.MVector(light) - center).normal()).normal()
    forward = (om2.MVector(VECTORS[aimAxis]) * eye).normal()
    return center, (half * follow + forward * (1.0 - follow)).normal()


class EyeHighlightTest(unittest.TestCase):
    """作成時に跳ねないこと、式との一致、follow・光・軸・評価の方式、所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転・非一様スケールの頭の下に眼球、眼球の子にハイライトの板、離れた所にカメラと光を作る。"""
        cmds.file(new=True, force=True)
        head = cmds.createNode("transform", name="head")
        cmds.setAttr(head + ".translate", 1, 15, -2)
        cmds.setAttr(head + ".rotate", 5, 20, -10)
        cmds.setAttr(head + ".scale", 1.0, 1.2, 0.9)
        self.head = cmds.ls(head, long=True)[0]
        self.eye = cmds.ls(cmds.createNode("joint", name="eye", parent=head), long=True)[0]
        cmds.setAttr(self.eye + ".translate", 1.5, 2, 3)
        cmds.setAttr(self.eye + ".rotate", 10, -15, 0)
        self.highlight = cmds.ls(cmds.createNode("transform", name="highlight", parent=self.eye), long=True)[0]
        cmds.setAttr(self.highlight + ".translate", 0.1, 0.2, 1.1)
        cmds.setAttr(self.highlight + ".rotate", 3, 4, 5)
        cmds.setAttr(self.highlight + ".scale", 0.3, 0.3, 0.05)
        self.camera = cmds.ls(cmds.camera(name="shotCam")[0], long=True)[0]
        cmds.setAttr(self.camera + ".translate", 10, 20, 40)
        self.light = cmds.ls(cmds.createNode("transform", name="keyLight"), long=True)[0]
        cmds.setAttr(self.light + ".translate", -30, 40, 20)
        self.rest = _world(self.highlight)
        self.radius = (_position(self.highlight) - _position(self.eye)).length()
        self.local0 = self._local()
        self.setup = EyeHighlight.create(self.eye, self.camera, self.highlight, name="eh", light=self.light)
        self.owner = str(self.setup.container)

    def _check(self, light=True, aimAxis="z", upAxis="y", msg=""):
        """出力のワールド行列を試験側の式・Python版と比べ、ハイライトに作成時の局所の差が上乗せされることを確かめる。"""
        radius = cmds.getAttr(self.owner + ".radius")
        follow = cmds.getAttr(self.owner + ".follow")
        eye = _world(self.eye)
        camera, lamp = _position(self.camera), _position(self.light) if light else None
        output = om2.MMatrix(cmds.getAttr(self.owner + ".highlightMatrix"))
        center, direction = _expectedDirection(eye, camera, lamp, follow, aimAxis)
        point = center + direction * radius
        aim = _axisOf(output, aimAxis)
        up = _axisOf(output, upAxis)
        eyeUp = (om2.MVector(VECTORS[upAxis]) * eye).normal()
        for index in range(3):
            self.assertAlmostEqual(output[12 + index], point[index], delta=POSITION, msg=msg)
            self.assertAlmostEqual(aim[index], direction[index], delta=AXIS, msg=msg)
        # 上の軸は前の軸に直交し、眼球の上の向きと前の軸が張る面の中で上を向く。
        self.assertAlmostEqual(up * aim, 0.0, delta=AXIS, msg=msg)
        self.assertAlmostEqual((aim ^ up) * eyeUp, 0.0, delta=AXIS, msg=msg)
        self.assertGreater(up * eyeUp, 0.0, msg=msg)
        # 右手系(det > 0)で scale 1。
        self.assertAlmostEqual((_row(output, 0) ^ _row(output, 1)) * _row(output, 2), 1.0, delta=AXIS, msg=msg)
        python = EyeHighlight.placement(eye, camera, lamp, radius, follow, aimAxis, upAxis)
        for index in range(16):
            self.assertAlmostEqual(python[index], output[index], delta=AXIS * 10, msg=msg)
        return output

    def _local(self):
        """作成時のハイライトのローカル行列(眼球の子の translate・rotate・scale)。"""
        return om2.MMatrix(cmds.getAttr(self.highlight + ".matrix"))

    def _assertOnHighlight(self, output, msg=""):
        """weight=1 のとき、ハイライトのワールド行列 = L · L0^-1 · M(L はハイライトの現在のローカル行列)。"""
        world = _world(self.highlight)
        expected = self._local() * self.local0.inverse() * output
        for index in range(16):
            self.assertAlmostEqual(world[index], expected[index], delta=POSITION, msg=msg)

    def test_rest_does_not_jump(self):
        """既定の weight=0 では作成直後のハイライトが動かず、radius の既定は眼球の中心からの距離。"""
        after = _world(self.highlight)
        for index in range(16):
            self.assertAlmostEqual(after[index], self.rest[index], delta=1e-6)
        self.assertEqual(cmds.getAttr(self.owner + ".weight"), 0.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".radius"), self.radius, delta=1e-9)
        self.assertEqual(cmds.getAttr(self.owner + ".follow"), 1.0)

    def test_random_moves(self):
        """眼球・頭・カメラ・光を乱数で動かすと、ハイライトは式どおり眼球の表面の中間の向きの点に来る。"""
        cmds.setAttr(self.owner + ".weight", 1.0)
        self._assertOnHighlight(self._check(msg="weight 1"))
        generator = random.Random(30)
        for index in range(25):
            cmds.setAttr(self.head + ".rotate", *[generator.uniform(-40, 40) for _ in range(3)])
            cmds.setAttr(self.eye + ".rotate", generator.uniform(-30, 30), generator.uniform(-40, 40), 0.0)
            cmds.setAttr(self.camera + ".translate", generator.uniform(-40, 40), generator.uniform(0, 40),
                         generator.uniform(10, 60))
            cmds.setAttr(self.light + ".translate", generator.uniform(-40, 40), generator.uniform(20, 60),
                         generator.uniform(0, 40))
            cmds.setAttr(self.owner + ".radius", generator.uniform(0.5, 2.0))
            cmds.setAttr(self.owner + ".follow", generator.uniform(0.3, 1.0))
            output = self._check(msg="move {}".format(index))
            self._assertOnHighlight(output, "move {}".format(index))
        cmds.setAttr(self.owner + ".follow", 1.0)
        output = self._check(msg="follow 1")
        # 光と follow=1 のとき、ハイライトの向きはカメラ・光への向きと同じ角度をなす(鏡の反射の条件)。
        center = _position(self.eye)
        aim = _axisOf(output, "z")
        view = (_position(self.camera) - center).normal()
        light = (_position(self.light) - center).normal()
        self.assertAlmostEqual(aim * view, aim * light, delta=AXIS)
        # ハイライトの板を手で動かすと、計算した配置の上に上乗せされる。
        cmds.setAttr(self.highlight + ".translateX", 0.4)
        cmds.setAttr(self.highlight + ".rotateZ", 30.0)
        self._assertOnHighlight(output, "local edit")

    def test_follow_zero_stays_on_the_eye(self):
        """follow=0 ではカメラ・光を動かしてもハイライトは目の前に留まり、眼球の回転だけに付いていく。"""
        cmds.setAttr(self.owner + ".weight", 1.0)
        cmds.setAttr(self.owner + ".follow", 0.0)
        before = self._check(msg="follow 0")
        cmds.setAttr(self.camera + ".translate", -40, 5, 10)
        cmds.setAttr(self.light + ".translate", 30, -5, 50)
        after = self._check(msg="moved camera")
        for index in range(16):
            self.assertAlmostEqual(before[index], after[index], delta=AXIS)
        cmds.setAttr(self.eye + ".rotateY", 25.0)
        rotated = self._check(msg="rotated eye")
        forward = (om2.MVector(0, 0, 1) * _world(self.eye)).normal()
        for index in range(3):
            self.assertAlmostEqual(_axisOf(rotated, "z")[index], forward[index], delta=AXIS)

    def test_without_light_faces_the_camera(self):
        """light を指定しないと、ハイライトは眼球のうちカメラに正対する点に来る。"""
        cmds.delete(self.owner)
        cmds.setAttr(self.highlight + ".offsetParentMatrix", list(om2.MMatrix()), type="matrix")
        setup = EyeHighlight.create(self.eye, self.camera, self.highlight, name="noLight", radius=1.2, weight=1.0)
        self.owner = str(setup.container)
        generator = random.Random(7)
        for index in range(10):
            cmds.setAttr(self.camera + ".translate", generator.uniform(-40, 40), generator.uniform(0, 40),
                         generator.uniform(10, 60))
            output = self._check(light=False, msg="camera {}".format(index))
            view = (_position(self.camera) - _position(self.eye)).normal()
            for axis in range(3):
                self.assertAlmostEqual(_axisOf(output, "z")[axis], view[axis], delta=AXIS)

    def test_axes(self):
        """前・上の軸の組み合わせで、ハイライトの同じ軸が眼球の外向き・上になる。"""
        cmds.delete(self.owner)
        cmds.setAttr(self.highlight + ".offsetParentMatrix", list(om2.MMatrix()), type="matrix")
        for aimAxis, upAxis in (("x", "y"), ("-x", "z"), ("y", "-z"), ("-z", "x"), ("z", "-y")):
            setup = EyeHighlight.create(self.eye, self.camera, self.highlight, name="axes", light=self.light,
                                        aimAxis=aimAxis, upAxis=upAxis, follow=0.6, weight=1.0)
            self.owner = str(setup.container)
            self._check(aimAxis=aimAxis, upAxis=upAxis, msg=aimAxis + upAxis)
            cmds.setAttr(self.eye + ".rotateX", 20.0)
            self._check(aimAxis=aimAxis, upAxis=upAxis, msg=aimAxis + upAxis + " rotated")
            cmds.setAttr(self.eye + ".rotateX", 10.0)
            cmds.delete(self.owner)
            cmds.setAttr(self.highlight + ".offsetParentMatrix", list(om2.MMatrix()), type="matrix")

    def test_weight_and_without_connect(self):
        """weight の補間と、connect=False で出力だけを作ること。"""
        cmds.setAttr(self.owner + ".weight", 0.5)
        blended = om2.MMatrix(cmds.getAttr(self.highlight + ".offsetParentMatrix"))
        target = self.local0.inverse() * om2.MMatrix(cmds.getAttr(self.owner + ".highlightMatrix")) * _world(
            self.eye).inverse()
        rest = om2.MTransformationMatrix(om2.MMatrix())
        half = om2.MTransformationMatrix(blended).translation(om2.MSpace.kWorld)
        goal = om2.MTransformationMatrix(target).translation(om2.MSpace.kWorld)
        for index in range(3):
            self.assertAlmostEqual(half[index], (rest.translation(om2.MSpace.kWorld)[index] + goal[index]) / 2.0,
                                   delta=POSITION)
        cmds.delete(self.owner)
        before = _world(self.highlight)
        setup = EyeHighlight.create(self.eye, self.camera, self.highlight, name="free", weight=1.0, connect=False)
        self.assertIsNone(cmds.listConnections(self.highlight + ".offsetParentMatrix", source=True,
                                               destination=False))
        after = _world(self.highlight)
        for index in range(16):
            self.assertAlmostEqual(after[index], before[index], delta=1e-9)
        self.owner = str(setup.container)
        self._check(light=False, msg="free")

    def test_evaluation_modes(self):
        """頭・眼球・時間を動かしても、DG・serial・parallelの各評価で出力に先立つハイライトの問い合わせが古くならない。"""
        cmds.setAttr(self.owner + ".weight", 1.0)
        cmds.setKeyframe(self.head, attribute="translateX", time=1, value=1.0)
        cmds.setKeyframe(self.head, attribute="translateX", time=10, value=-9.0)
        cmds.setKeyframe(self.camera, attribute="translateY", time=1, value=20.0)
        cmds.setKeyframe(self.camera, attribute="translateY", time=10, value=-5.0)
        original = cmds.evaluationManager(query=True, mode=True)[0]
        try:
            for mode in ("off", "serial", "parallel"):
                cmds.evaluationManager(mode=mode)
                generator = random.Random(31)
                for index in range(10):
                    cmds.currentTime(1 + index)
                    cmds.setAttr(self.eye + ".rotateY", generator.uniform(-40, 40))
                    cmds.setAttr(self.head + ".rotateZ", generator.uniform(-40, 40))
                    world = _world(self.highlight)
                    output = self._check(msg="{} {}".format(mode, index))
                    expected = self._local() * self.local0.inverse() * output
                    for item in range(16):
                        self.assertAlmostEqual(world[item], expected[item], delta=POSITION,
                                               msg="{} {}".format(mode, index))
        finally:
            cmds.evaluationManager(mode=original)

    def test_container_and_undo(self):
        """生成ノードはcontainerが所有し、Undoで作成前へ、Redoで作成後へ戻る。"""
        nodes = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = set(cmds.ls(type=("vectorProduct", "plusMinusAverage", "blendColors", "composeMatrix", "aimMatrix",
                                    "multiplyDivide", "multMatrix", "blendMatrix", "unitConversion")))
        self.assertTrue(created)
        self.assertEqual(created - nodes, set())
        cmds.delete(self.owner)
        cmds.setAttr(self.highlight + ".offsetParentMatrix", list(om2.MMatrix()), type="matrix")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        cmds.undoInfo(openChunk=True)
        try:
            EyeHighlight.create(self.eye, self.camera, self.highlight, name="undo", light=self.light, weight=1.0)
        finally:
            cmds.undoInfo(closeChunk=True)
        after = set(cmds.ls())
        moved = _world(self.highlight)
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)
        self.assertFalse(cmds.objExists("undo"))
        cmds.redo()
        self.assertEqual(set(cmds.ls()), after)
        again = _world(self.highlight)
        for index in range(16):
            self.assertAlmostEqual(again[index], moved[index], delta=1e-9)

    def test_arguments(self):
        """不正な引数では ValueError になり、何も残さない。"""
        free = cmds.createNode("transform", name="freeHighlight")
        locked = cmds.createNode("transform", name="lockedHighlight")
        cmds.setAttr(locked + ".offsetParentMatrix", lock=True)
        inside = cmds.createNode("transform", name="insideLight", parent=self.highlight)
        centered = cmds.createNode("transform", name="centered", parent=self.eye)
        before = set(cmds.ls())
        base = dict(eye=self.eye, camera=self.camera, highlight=free, name="bad")
        cases = [
            dict(base, highlight=self.highlight),
            dict(base, highlight=locked),
            dict(base, eye="missing"),
            dict(base, camera=self.eye),
            dict(base, light=inside, highlight=self.highlight, name="bad2"),
            dict(base, light=centered),
            dict(base, highlight=centered),
            dict(base, radius=0.0),
            dict(base, radius=float("nan")),
            dict(base, follow=1.5),
            dict(base, weight=True),
            dict(base, aimAxis="w"),
            dict(base, aimAxis="z", upAxis="-z"),
            dict(base, name="eh"),
        ]
        for case in cases:
            with self.assertRaises(ValueError, msg=str(case)):
                EyeHighlight.create(**case)
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main(argv=["eye_highlight"], exit=False, verbosity=2)
