"""LipZipの閉じる割合と、閉じ合わせた上唇・下唇の行列を、OpenMayaで求めた期待値と比較する。"""

import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import LipZip

COUNT = 5


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _blend(first, second, weight):
    """位置は線形、回転はslerpで2つの行列を補間する(scale・shearは1・0の前提)。"""
    a, b = om.MTransformationMatrix(first), om.MTransformationMatrix(second)
    translate = a.translation(om.MSpace.kWorld) * (1.0 - weight) + b.translation(om.MSpace.kWorld) * weight
    rotation = om.MQuaternion.slerp(a.rotation(asQuaternion=True), b.rotation(asQuaternion=True), weight)
    result = om.MTransformationMatrix()
    result.setRotation(rotation)
    result.setTranslation(translate, om.MSpace.kWorld)
    return result.asMatrix()


class LipZipTest(unittest.TestCase):
    """作成時の姿勢・割合の式・閉じる順序・合わさる高さ・入力の移動・位置の変更・所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転した頭の下に、少し開いた口の上唇・下唇の点を5組作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.head = cmds.createNode("transform", name="head")
        cmds.setAttr(self.head + ".translate", 1, 20, -2)
        cmds.setAttr(self.head + ".rotate", 10, 25, -5)
        self.upper, self.lower = [], []
        for index in range(COUNT):
            x = -2.0 + index
            curve = 0.4 * (1.0 - (x / 2.0) ** 2)
            upper = cmds.createNode("transform", name="upper{}".format(index), parent=self.head)
            cmds.setAttr(upper + ".translate", x, 0.2 + curve, curve)
            cmds.setAttr(upper + ".rotate", 15, 8 * x, 0)
            lower = cmds.createNode("transform", name="lower{}".format(index), parent=self.head)
            cmds.setAttr(lower + ".translate", x, -0.3 - curve, curve * 0.8)
            cmds.setAttr(lower + ".rotate", -20, 6 * x, 3)
            self.upper.append(upper)
            self.lower.append(lower)
        self.setup = LipZip.create(self.upper, self.lower, name="zip")
        self.owner = str(self.setup.container)

    def _attr(self, attr):
        return cmds.getAttr(self.owner + "." + attr)

    def _assertMatrix(self, actual, expected, tolerance=1e-5):
        for index, (a, b) in enumerate(zip(actual, expected)):
            self.assertAlmostEqual(a, b, delta=tolerance, msg="element {}".format(index))

    def _assertAll(self):
        """全組の割合と行列が独立に計算した期待値と一致することを確かめる。"""
        zipLeft, zipRight = self._attr("zipLeft"), self._attr("zipRight")
        falloff, height = self._attr("falloff"), self._attr("meetHeight")
        for index in range(COUNT):
            position = self._attr("position" + str(index))
            weight = LipZip.response(position, zipLeft, zipRight, falloff)
            self.assertAlmostEqual(self._attr("weight" + str(index)), weight, delta=1e-6)
            upper = _matrix(self.upper[index] + ".worldMatrix[0]")
            lower = _matrix(self.lower[index] + ".worldMatrix[0]")
            meet = _blend(lower, upper, height)
            self._assertMatrix(_matrix(self.owner + ".upperMatrix" + str(index)), _blend(upper, meet, weight))
            self._assertMatrix(_matrix(self.owner + ".lowerMatrix" + str(index)), _blend(lower, meet, weight))

    def test_rest(self):
        """作成直後は全組が開いたままで、出力が入力の点のワールド行列と一致する(跳ねない)。"""
        for index in range(COUNT):
            self.assertAlmostEqual(self._attr("weight" + str(index)), 0.0, delta=1e-9)
            self.assertAlmostEqual(self._attr("position" + str(index)), (index + 1.0) / (COUNT + 1.0))
            self._assertMatrix(_matrix(self.owner + ".upperMatrix" + str(index)),
                               _matrix(self.upper[index] + ".worldMatrix[0]"), 1e-6)
            self._assertMatrix(_matrix(self.owner + ".lowerMatrix" + str(index)),
                               _matrix(self.lower[index] + ".worldMatrix[0]"), 1e-6)

    def test_response(self):
        """左右・両側・幅の組み合わせで、割合と行列が式と一致する。"""
        for zipLeft, zipRight, falloff, height in (
            (0.3, 0.0, 0.3, 0.5), (0.0, 0.6, 0.3, 0.5), (0.45, 0.45, 0.2, 0.5),
            (0.8, 0.1, 0.6, 0.3), (0.2, 0.9, 0.05, 0.7), (1.0, 0.0, 0.3, 0.5),
        ):
            with self.subTest(zipLeft=zipLeft, zipRight=zipRight, falloff=falloff):
                cmds.setAttr(self.owner + ".zipLeft", zipLeft)
                cmds.setAttr(self.owner + ".zipRight", zipRight)
                cmds.setAttr(self.owner + ".falloff", falloff)
                cmds.setAttr(self.owner + ".meetHeight", height)
                self._assertAll()

    def test_order_and_full(self):
        """左から閉じると左の口角に近い組ほど先に閉じ、1では全組が合わさる。"""
        cmds.setAttr(self.owner + ".zipLeft", 0.5)
        weights = [self._attr("weight" + str(index)) for index in range(COUNT)]
        self.assertEqual(weights, sorted(weights))
        self.assertAlmostEqual(weights[-1], 1.0, delta=1e-9)
        self.assertAlmostEqual(weights[0], 0.0, delta=1e-9)
        self.assertTrue(any(0.0 < value < 1.0 for value in weights), weights)
        cmds.setAttr(self.owner + ".zipLeft", 0.0)
        cmds.setAttr(self.owner + ".zipRight", 0.5)
        mirrored = [self._attr("weight" + str(index)) for index in range(COUNT)]
        for index in range(COUNT):
            self.assertAlmostEqual(mirrored[index], weights[COUNT - 1 - index], delta=1e-6)
        cmds.setAttr(self.owner + ".zipRight", 1.0)
        cmds.setAttr(self.owner + ".meetHeight", 0.0)
        for index in range(COUNT):
            lower = _matrix(self.lower[index] + ".worldMatrix[0]")
            self._assertMatrix(_matrix(self.owner + ".upperMatrix" + str(index)), lower)
            self._assertMatrix(_matrix(self.owner + ".lowerMatrix" + str(index)), lower)

    def test_follow_inputs_and_positions(self):
        """閉じた後も入力の点と頭の動きに付いてきて、positionの変更で閉じる順序が変わる。"""
        cmds.setAttr(self.owner + ".zipLeft", 0.6)
        cmds.setAttr(self.owner + ".zipRight", 0.2)
        cmds.setAttr(self.upper[3] + ".translateY", 1.2)
        cmds.setAttr(self.lower[1] + ".rotateX", -40)
        cmds.setAttr(self.head + ".rotateY", -30)
        cmds.setAttr(self.head + ".translateZ", 4)
        self._assertAll()
        cmds.setAttr(self.owner + ".position0", 0.95)
        self.assertGreater(self._attr("weight0"), 0.99)
        self._assertAll()

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        kinds = {cmds.nodeType(node) for node in members}
        self.assertTrue({"blendMatrix", "setRange", "clamp", "reverse"} <= kinds, kinds)
        upstream = cmds.listHistory(self.owner + ".upperMatrix2", pruneDagObjects=True) or []
        # containerの作成でMayaが付けるhyperLayoutと、入力の点・頭のtransformは所有の対象外。
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        head = cmds.createNode("transform", name="head")
        upper = [cmds.createNode("transform", name="u{}".format(i), parent=head) for i in range(2)]
        lower = [cmds.createNode("transform", name="l{}".format(i), parent=head) for i in range(2)]
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        LipZip.create(upper, lower, name="undoZip")
        self.assertTrue(cmds.objExists("undoZip"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoZip"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoZip"))
        self.assertTrue(cmds.objExists("undoZip.upperMatrix1"))

    def test_arguments(self):
        """空・数の違い・範囲外・transform以外・名前の重複を拒否する。"""
        cases = (
            ([], []),
            (self.upper, self.lower[:-1]),
        )
        for upper, lower in cases:
            with self.assertRaises(ValueError):
                LipZip.create(upper, lower, name="bad")
        for kwargs in (
            {"positions": [0.5]}, {"positions": [0.1, 0.2, 0.3, 0.4, 1.5]}, {"zipLeft": -0.1},
            {"zipRight": 1.1}, {"falloff": 0.0}, {"falloff": 2.0}, {"meetHeight": float("nan")},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                LipZip.create(self.upper, self.lower, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            LipZip.create([node], [self.lower[0]], name="bad")
        with self.assertRaises(ValueError):
            LipZip.create(self.upper, self.lower, name="zip")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
