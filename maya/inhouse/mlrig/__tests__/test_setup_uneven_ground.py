"""UnevenGroundの足・腰の補正を、地面の平面の式から独立に立てた条件で確かめる。"""

import math
import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import UnevenGround

#: 位置(cm)の許容。vectorProduct・plusMinusAverage が単精度なので丸めの範囲で確かめる。
POSITION = 1e-4

#: 向き(軸の成分)の許容。
AXIS = 1e-5

UP = om2.MVector(0.0, 1.0, 0.0)


def _world(node):
    return om2.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _matrix(plug):
    return om2.MMatrix(cmds.getAttr(plug))


def _point(matrix):
    return om2.MVector(matrix[12], matrix[13], matrix[14])


def _row(matrix, index):
    return om2.MVector(matrix[4 * index], matrix[4 * index + 1], matrix[4 * index + 2])


def _rotation(matrix):
    """行列の回転だけ(scaleを除き、位置0)。"""
    return om2.MTransformationMatrix(matrix).asRotateMatrix()


def _flat(vector):
    return om2.MVector(vector.x, 0.0, vector.z)


class UnevenGroundTest(unittest.TestCase):
    """地面の上へ載ること、腰を低い方へ下げること、割合・軸・評価の方式、所有・Undo・引数を確認する。"""

    def setUp(self):
        """腰・左右の足(回転したコントロール)と、回転した親の下の2枚の地面を作る。"""
        cmds.file(new=True, force=True)
        self.hips = cmds.createNode("transform", name="hipsCtrl")
        cmds.setAttr(self.hips + ".translate", 0, 90, 2)
        cmds.setAttr(self.hips + ".rotate", 4, 10, -3)
        self.left = cmds.createNode("transform", name="leftFootCtrl")
        cmds.setAttr(self.left + ".translate", 10, 3, 5)
        cmds.setAttr(self.left + ".rotate", 5, 20, 2)
        self.right = cmds.createNode("transform", name="rightFootCtrl")
        cmds.setAttr(self.right + ".translate", -10, 0, -5)
        cmds.setAttr(self.right + ".rotate", 0, -15, 0)
        stage = cmds.createNode("transform", name="stage")
        cmds.setAttr(stage + ".translate", 1, 2, -1)
        cmds.setAttr(stage + ".rotateY", 30)
        self.leftGround = cmds.ls(cmds.createNode("transform", name="leftGround", parent=stage), long=True)[0]
        cmds.setAttr(self.leftGround + ".translate", 12, 15, 4)
        cmds.setAttr(self.leftGround + ".rotate", 15, 0, -10)
        self.rightGround = cmds.ls(cmds.createNode("transform", name="rightGround", parent=stage), long=True)[0]
        cmds.setAttr(self.rightGround + ".translate", -8, -6, -3)
        cmds.setAttr(self.rightGround + ".rotate", -8, 40, 12)
        self.setup = UnevenGround.create(self.hips, self.left, self.right, self.leftGround, self.rightGround,
                                         name="ug")
        self.owner = str(self.setup.container)

    def _check(self, groundAxis="y", forwardAxis="z", msg=""):
        """出力を試験側の条件・Python版と比べ、左右の持ち上げを返す。

        条件(height=1 のとき): 足の位置を床からの高さの分だけ下げた点が地面の平面の上にあり、
        足の回転の差 D は世界の上を地面の法線へ移し、足の前の水平の向きを、足の前を地面の面へ投影した向きへ移す。
        """
        floor = cmds.getAttr(self.owner + ".floorHeight")
        height = cmds.getAttr(self.owner + ".height")
        align = cmds.getAttr(self.owner + ".align")
        weight = cmds.getAttr(self.owner + ".hips")
        axes = {"x": 0, "y": 1, "z": 2}
        lifts = []
        for side, foot, ground in (("left", self.left, self.leftGround), ("right", self.right, self.rightGround)):
            name = "{} {}".format(msg, side)
            before, plane = _world(foot), _world(ground)
            output = _matrix(self.owner + "." + side + "FootMatrix")
            point, out = _point(before), _point(output)
            lift = cmds.getAttr(self.owner + "." + side + "Offset")
            lifts.append(lift)
            for index in (0, 2):
                self.assertAlmostEqual(out[index], point[index], delta=POSITION, msg=name)
            self.assertAlmostEqual(out.y - point.y, lift, delta=POSITION, msg=name)
            normal = _row(plane, axes[groundAxis[-1]]).normal() * (-1.0 if groundAxis.startswith("-") else 1.0)
            if height == 1.0:
                # 足の真下の地面の点 = 出力の位置から床からの高さ(p.y - floor)を引いた点。
                surface = out - UP * (point.y - floor)
                self.assertAlmostEqual((surface - _point(plane)) * normal, 0.0, delta=POSITION, msg=name)
            delta = _rotation(before).inverse() * _rotation(output)
            if align == 1.0:
                moved = UP * delta
                for index in range(3):
                    self.assertAlmostEqual(moved[index], normal[index], delta=AXIS, msg=name)
                forward = _row(before, axes[forwardAxis[-1]]) * (-1.0 if forwardAxis.startswith("-") else 1.0)
                # 足の前の水平の向きは、足の前を法線の方向に地面の面へ投影した向きへ移る。
                heading = _flat(forward).normal()
                along = (forward - normal * (forward * normal)).normal()
                turned = heading * delta
                for index in range(3):
                    self.assertAlmostEqual(turned[index], along[index], delta=AXIS, msg=name)
            elif align == 0.0:
                for index in range(16):
                    self.assertAlmostEqual(delta[index], om2.MMatrix()[index], delta=AXIS, msg=name)
        hipsOut = _matrix(self.owner + ".hipsMatrix")
        hipsIn = _world(self.hips)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".hipsOffset"), weight * min(lifts), delta=POSITION, msg=msg)
        for index in range(12):
            self.assertAlmostEqual(hipsOut[index], hipsIn[index], delta=AXIS, msg=msg)
        self.assertAlmostEqual(hipsOut[13] - hipsIn[13], weight * min(lifts), delta=POSITION, msg=msg)
        self.assertAlmostEqual(hipsOut[12], hipsIn[12], delta=POSITION, msg=msg)
        self.assertAlmostEqual(hipsOut[14], hipsIn[14], delta=POSITION, msg=msg)
        python = UnevenGround.placement(hipsIn, _world(self.left), _world(self.right), _world(self.leftGround),
                                        _world(self.rightGround), floorHeight=floor, height=height, align=align,
                                        hipsWeight=weight, groundAxis=groundAxis, forwardAxis=forwardAxis)
        for key, plug in (("left", "leftFootMatrix"), ("right", "rightFootMatrix"), ("hips", "hipsMatrix")):
            output = _matrix(self.owner + "." + plug)
            for index in range(16):
                self.assertAlmostEqual(python[key][index], output[index], delta=POSITION, msg=msg + " python " + key)
        self.assertAlmostEqual(python["hipsOffset"], cmds.getAttr(self.owner + ".hipsOffset"), delta=POSITION)
        return lifts

    def test_flat_ground_does_not_move(self):
        """地面が床の高さで水平なら、作成直後の出力は入力と同じ(跳ねない)。"""
        cmds.delete(self.owner)
        grounds = []
        for name in ("flatLeft", "flatRight"):
            ground = cmds.createNode("transform", name=name)
            cmds.setAttr(ground + ".translate", 3.0, 0.0, -7.0)
            cmds.setAttr(ground + ".rotateY", 70.0)
            grounds.append(ground)
        setup = UnevenGround.create(self.hips, self.left, self.right, grounds[0], grounds[1], name="flat")
        self.owner, self.leftGround, self.rightGround = str(setup.container), grounds[0], grounds[1]
        for side, foot in (("left", self.left), ("right", self.right)):
            self.assertAlmostEqual(cmds.getAttr(self.owner + "." + side + "Offset"), 0.0, delta=POSITION)
            output, before = _matrix(self.owner + "." + side + "FootMatrix"), _world(foot)
            for index in range(16):
                self.assertAlmostEqual(output[index], before[index], delta=POSITION, msg=side)
        self._check(msg="flat")

    def test_matches_formula(self):
        """乱数の足・腰・地面の配置で、地面の平面の上へ載り、腰が低い方の足に合わせて上下する。"""
        generator = random.Random(7)
        lows = set()
        for index in range(25):
            for foot in (self.left, self.right):
                cmds.setAttr(foot + ".translate", generator.uniform(-20, 20), generator.uniform(0, 12),
                             generator.uniform(-20, 20))
                cmds.setAttr(foot + ".rotate", generator.uniform(-30, 30), generator.uniform(-180, 180),
                             generator.uniform(-30, 30))
            for ground in (self.leftGround, self.rightGround):
                cmds.setAttr(ground + ".translate", generator.uniform(-20, 20), generator.uniform(-15, 15),
                             generator.uniform(-20, 20))
                cmds.setAttr(ground + ".rotate", generator.uniform(-35, 35), generator.uniform(-180, 180),
                             generator.uniform(-35, 35))
            cmds.setAttr(self.hips + ".translate", generator.uniform(-5, 5), generator.uniform(80, 100), 0)
            cmds.setAttr(self.owner + ".floorHeight", generator.uniform(-2, 2))
            lifts = self._check(msg=str(index))
            lows.add(lifts[0] < lifts[1])
        self.assertEqual(lows, {True, False})

    def test_same_ground_for_both_feet(self):
        """左右に同じ1枚の坂を使うと、坂の上の高い方の足が持ち上がり、腰は低い方へ合わせる。"""
        cmds.delete(self.owner)
        slope = cmds.createNode("transform", name="slope")
        cmds.setAttr(slope + ".rotateZ", 20.0)
        setup = UnevenGround.create(self.hips, self.left, self.right, slope, slope, name="slopeSetup")
        self.owner, self.leftGround, self.rightGround = str(setup.container), slope, slope
        lifts = self._check(msg="slope")
        # +X 側(左足)は坂を上る。
        self.assertGreater(lifts[0], 0.0)
        self.assertLess(lifts[1], 0.0)
        self.assertAlmostEqual(lifts[0], 10.0 * math.tan(math.radians(20.0)), delta=POSITION)

    def test_weights(self):
        """height・align・hips の割合を変えても式どおりで、align=0 は回転を変えない。"""
        for height, align, hips in ((0.5, 0.0, 1.0), (1.0, 0.5, 0.0), (2.0, 1.0, 0.5), (0.0, 0.25, 1.0)):
            cmds.setAttr(self.owner + ".height", height)
            cmds.setAttr(self.owner + ".align", align)
            cmds.setAttr(self.owner + ".hips", hips)
            self._check(msg="{} {} {}".format(height, align, hips))
        cmds.setAttr(self.owner + ".height", 1.0)
        cmds.setAttr(self.owner + ".align", 0.5)
        delta = _rotation(_world(self.left)).inverse() * _rotation(_matrix(self.owner + ".leftFootMatrix"))
        normal = _row(_world(self.leftGround), 1).normal()
        full = math.acos(max(-1.0, min(1.0, normal * UP)))
        half = math.acos(max(-1.0, min(1.0, (UP * delta) * UP)))
        self.assertAlmostEqual(half, full / 2.0, delta=1e-4)

    def test_axes(self):
        """地面の法線・足の前の軸を変えても式どおり。"""
        cmds.delete(self.owner)
        for groundAxis, forwardAxis in (("z", "x"), ("-x", "-z"), ("y", "x")):
            if groundAxis == "z":
                cmds.setAttr(self.leftGround + ".rotate", -75, 0, -10)
                cmds.setAttr(self.rightGround + ".rotate", -100, 40, 12)
            elif groundAxis == "-x":
                cmds.setAttr(self.leftGround + ".rotate", 0, 0, -80)
                cmds.setAttr(self.rightGround + ".rotate", 10, 40, -100)
            else:
                cmds.setAttr(self.leftGround + ".rotate", 15, 0, -10)
                cmds.setAttr(self.rightGround + ".rotate", -8, 40, 12)
            setup = UnevenGround.create(self.hips, self.left, self.right, self.leftGround, self.rightGround,
                                        name="axes", groundAxis=groundAxis, forwardAxis=forwardAxis)
            self.owner = str(setup.container)
            self._check(groundAxis, forwardAxis, msg=groundAxis + forwardAxis)
            cmds.delete(self.owner)

    def test_evaluation_modes(self):
        """足・地面・時間を動かしても、DG・serial・parallelの各評価で出力が古くならない。"""
        cmds.setKeyframe(self.left, attribute="translateX", time=1, value=10.0)
        cmds.setKeyframe(self.left, attribute="translateX", time=10, value=-5.0)
        cmds.setKeyframe(self.rightGround, attribute="translateY", time=1, value=-6.0)
        cmds.setKeyframe(self.rightGround, attribute="translateY", time=10, value=8.0)
        original = cmds.evaluationManager(query=True, mode=True)[0]
        try:
            for mode in ("off", "serial", "parallel"):
                cmds.evaluationManager(mode=mode)
                generator = random.Random(3)
                for index in range(10):
                    cmds.currentTime(1 + index)
                    cmds.setAttr(self.leftGround + ".rotateX", generator.uniform(-30, 30))
                    cmds.setAttr(self.right + ".rotateY", generator.uniform(-90, 90))
                    self._check(msg="{} {}".format(mode, index))
        finally:
            cmds.evaluationManager(mode=original)

    def test_container_and_undo(self):
        """生成ノードはcontainerが所有し、入力は書き換えず、Undoで作成前へ、Redoで作成後へ戻る。"""
        nodes = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = set(cmds.ls(type=("vectorProduct", "plusMinusAverage", "clamp", "multiplyDivide", "aimMatrix",
                                    "fourByFourMatrix", "multMatrix", "blendMatrix", "composeMatrix", "condition",
                                    "unitConversion")))
        self.assertTrue(created)
        self.assertEqual(created - nodes, set())
        for node in (self.hips, self.left, self.right, self.leftGround, self.rightGround):
            self.assertFalse(cmds.listConnections(node, source=True, destination=False), node)
        cmds.delete(self.owner)
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        cmds.undoInfo(openChunk=True)
        try:
            UnevenGround.create(self.hips, self.left, self.right, self.leftGround, self.rightGround, name="undo")
        finally:
            cmds.undoInfo(closeChunk=True)
        after = set(cmds.ls())
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)
        self.assertFalse(cmds.objExists("undo"))
        cmds.redo()
        self.assertEqual(set(cmds.ls()), after)
        self.owner = "undo"
        self._check(msg="redo")

    def test_arguments(self):
        """不正な引数では ValueError になり、何も残さない。"""
        down = cmds.createNode("transform", name="downGround")
        cmds.setAttr(down + ".rotateX", 180.0)
        wall = cmds.createNode("transform", name="wallGround")
        cmds.setAttr(wall + ".rotateX", 90.0)
        upright = cmds.createNode("transform", name="uprightFoot")
        cmds.setAttr(upright + ".rotateX", -90.0)
        before = set(cmds.ls())
        base = dict(hips=self.hips, leftFoot=self.left, rightFoot=self.right, leftGround=self.leftGround,
                    rightGround=self.rightGround, name="bad")
        cases = [
            dict(base, hips="missing"),
            dict(base, rightFoot=self.left),
            dict(base, leftGround=self.left),
            dict(base, rightGround=down),
            dict(base, leftGround=wall),
            dict(base, leftFoot=upright),
            dict(base, floorHeight=float("nan")),
            dict(base, height=True),
            dict(base, align=1.5),
            dict(base, hipsWeight="1"),
            dict(base, groundAxis="w"),
            dict(base, forwardAxis="up"),
            dict(base, name="ug"),
        ]
        for case in cases:
            with self.assertRaises(ValueError, msg=str(case)):
                UnevenGround.create(**case)
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main(argv=["uneven_ground"], exit=False, verbosity=2)
