"""計算ノードのクラス(Condition・MultiplyDivide・AimMatrix 等)の setInput・getResult・演算の名前・
入力の追加と削除・ランプの操作を確かめる。

setInput は値の書込みと Plug の接続をまとめ、Undo 1 回で戻ること、演算・モードは名前と番号で設定でき、
不正な名前・型は書き込まずに ValueError/TypeError になることを確かめる。
"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.maths import Matrix
from support.specCase import NamespaceCase


def _close(test, actual, expected, places=5):
    """数値または数値の列を丸めて比べる。"""
    if isinstance(expected, (int, float)):
        test.assertAlmostEqual(actual, expected, places=places)
        return
    actual, expected = list(actual), list(expected)
    test.assertEqual(len(actual), len(expected))
    for a, b in zip(actual, expected):
        test.assertAlmostEqual(a, b, places=places)


class _Case(NamespaceCase):
    PREFIX = "mlibCalcNodes_"

    def node(self, node_type, name=None):
        if node_type == "inverseMatrix":
            # inverseMatrix は matrixNodes プラグインのノード。
            cmds.loadPlugin("matrixNodes", quiet=True)
        return mlib.createNode(node_type, name=self.ns + ":" + (name or node_type))


class WrapperTypeTest(_Case):
    """手書きクラスとして取得できる。"""

    def test_registered_classes(self):
        for node_type, cls in (("aimMatrix", "AimMatrix"), ("decomposeMatrix", "DecomposeMatrix"),
                               ("composeMatrix", "ComposeMatrix"), ("multMatrix", "MultMatrix"),
                               ("blendMatrix", "BlendMatrix"), ("pickMatrix", "PickMatrix"),
                               ("inverseMatrix", "InverseMatrix"), ("fourByFourMatrix", "FourByFourMatrix"),
                               ("pairBlend", "PairBlend"), ("vectorProduct", "VectorProduct"),
                               ("distanceBetween", "DistanceBetween"), ("angleBetween", "AngleBetween"),
                               ("curveInfo", "CurveInfo"), ("pointOnCurveInfo", "PointOnCurveInfo"),
                               ("pointOnSurfaceInfo", "PointOnSurfaceInfo")):
            with self.subTest(node_type):
                self.assertIs(type(self.node(node_type)), getattr(mlib, cls))


class ScalarNodesTest(_Case):
    """値の入力と結果。"""

    def test_condition(self):
        node = self.node("condition")
        self.assertIs(node.setInput(firstTerm=2, secondTerm=1, colorIfTrue=(1, 2, 3), colorIfFalse=(4, 5, 6)), node)
        node.setOperation("greaterThan")
        self.assertEqual(node.getOperation(), "greaterThan")
        _close(self, node.getResult(), (1, 2, 3))
        node.setOperation(4)
        self.assertEqual(node.getOperation(), "lessThan")
        _close(self, node.getResult(), (4, 5, 6))
        self.assertEqual(node.getOutputPlug().getFullName(), node.getFullName() + ".outColor")

    def test_multiply_divide_and_others(self):
        md = self.node("multiplyDivide")
        md.setInput(input1=(2, 3, 4), input2=(5, 6, 7)).setOperation("multiply")
        _close(self, md.getResult(), (10, 18, 28))
        clamp = self.node("clamp")
        clamp.setInput(input=(-1, 0.5, 9), min=(0, 0, 0), max=(1, 1, 1))
        _close(self, clamp.getResult(), (0, 0.5, 1))
        set_range = self.node("setRange")
        set_range.setInput(value=(5, 0, 0), min=(0, 0, 0), max=(1, 1, 1), oldMin=(0, 0, 0), oldMax=(10, 10, 10))
        _close(self, set_range.getResult()[0], 0.5)
        reverse = self.node("reverse")
        _close(self, reverse.setInput(input=(0.25, 1, 0)).getResult(), (0.75, 0, 1))
        blend = self.node("blendColors")
        _close(self, blend.setInput(color1=(1, 1, 1), color2=(0, 0, 0), blender=0.25).getResult(), (0.25, 0.25, 0.25))
        add = self.node("addDoubleLinear", "add")
        _close(self, add.setInput(input1=2, input2=3).getResult(), 5)
        mult = self.node("multDoubleLinear", "mult")
        _close(self, mult.setInput(input1=2, input2=3).getResult(), 6)

    def test_set_input_connects_plugs_and_replaces(self):
        source = mlib.createNode("transform", name=self.ns + ":src")
        md = self.node("multiplyDivide")
        md.setInput(input1=source.getPlug("translate"), input2=(2, 2, 2))
        cmds.setAttr(source.getFullName() + ".translate", 1, 2, 3)
        _close(self, md.getResult(), (2, 4, 6))
        md.setInput(input1=(1, 1, 1))
        self.assertIsNone(md.getPlug("input1").getSource())
        _close(self, md.getResult(), (2, 2, 2))
        md.setInput(input1=source.getFullName() + ".translate")
        self.assertIsNotNone(md.getPlug("input1").getSource())

    def test_set_input_undo_once(self):
        md = self.node("multiplyDivide")
        self.flushUndo()
        md.setInput(input1=(3, 3, 3), input2=(4, 4, 4))
        cmds.undo()
        _close(self, cmds.getAttr(md.getFullName() + ".input1")[0], (0, 0, 0))
        _close(self, cmds.getAttr(md.getFullName() + ".input2")[0], (1, 1, 1))

    def test_enum_errors(self):
        node = self.node("condition")
        with self.assertRaisesRegex(ValueError, "choices: equal, notEqual"):
            node.setOperation("bigger")
        for bad in (6, -1):
            with self.assertRaises(ValueError):
                node.setOperation(bad)
        for bad in (True, 1.0, None):
            with self.assertRaises(TypeError):
                node.setOperation(bad)
        self.assertEqual(node.getOperation(), "equal")


class MultiInputTest(_Case):
    """入力の追加と削除。"""

    def test_plus_minus_average(self):
        node = self.node("plusMinusAverage")
        node.setOperation("sum")
        self.assertEqual([node.addInput(v) for v in (1, 2, 3)], [0, 1, 2])
        _close(self, node.getResult(), 6)
        node.removeInput(1)
        self.assertEqual(node.getInputIndices(), [0, 2])
        _close(self, node.getResult(), 4)
        self.assertEqual(node.addInput((1, 2, 3), dimension=3), 0)
        _close(self, node.getResult(3), (1, 2, 3))
        with self.assertRaises(ValueError):
            node.removeInput(9)
        with self.assertRaises(ValueError):
            node.addInput(1, dimension=4)
        with self.assertRaises(TypeError):
            node.removeInput(True)

    def test_blend_weighted(self):
        node = self.node("blendWeighted")
        node.addInput(2, 0.5)
        node.addInput(4)
        _close(self, node.getResult(), 5)
        self.flushUndo()
        node.removeInput(0)
        self.assertEqual(node.getInputIndices(), [1])
        cmds.undo()
        self.assertEqual(node.getInputIndices(), [0, 1])

    def test_mult_matrix_and_blend_matrix(self):
        translate = Matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 2, 3, 1])
        node = self.node("multMatrix")
        node.setInput([translate, translate])
        self.assertEqual(node.getInputIndices(), [0, 1])
        _close(self, list(node.getResult())[12:15], (2, 4, 6))
        self.assertEqual(node.addInput(translate), 2)
        node.setInput([translate])
        self.assertEqual(node.getInputIndices(), [0])
        blend = self.node("blendMatrix")
        blend.setInput(inputMatrix=Matrix())
        self.assertEqual(blend.addTarget(translate, 0.5), 0)
        _close(self, list(blend.getResult())[12:15], (0.5, 1, 1.5))
        blend.removeTarget(0)
        self.assertEqual(blend.getTargetIndices(), [])


class MatrixNodesTest(_Case):
    """マトリクスのノード。"""

    def test_compose_decompose_pick_inverse(self):
        compose = self.node("composeMatrix")
        compose.setInput(inputTranslate=(1, 2, 3), inputRotate=(0, 90, 0), inputScale=(2, 2, 2))
        compose.setRotateOrder("zxy")
        self.assertEqual(compose.getRotateOrder(), "zxy")
        decompose = self.node("decomposeMatrix")
        decompose.setInput(inputMatrix=compose.getOutputPlug())
        _close(self, decompose.getResult(), (1, 2, 3))
        _close(self, decompose.getResult("scale"), (2, 2, 2))
        _close(self, decompose.getResult("rotate"), (0, 90, 0), 4)
        self.assertEqual(len(decompose.getResult("quaternion")), 4)
        with self.assertRaises(ValueError):
            decompose.getResult("position")
        pick = self.node("pickMatrix")
        pick.setInput(inputMatrix=compose.getOutputPlug(), useRotate=False, useScale=False)
        _close(self, list(pick.getResult())[:3], (1, 0, 0))
        inverse = self.node("inverseMatrix")
        inverse.setInput(inputMatrix=compose.getOutputPlug())
        _close(self, list(inverse.getResult() * compose.getResult()), list(Matrix()))

    def test_aim_and_four_by_four(self):
        aim = self.node("aimMatrix")
        aim.setInput(primaryInputAxis=(1, 0, 0), primaryTargetVector=(0, 1, 0))
        aim.setPrimaryMode("align")
        self.assertEqual(aim.getPrimaryMode(), "align")
        aim.setSecondaryMode("none")
        self.assertEqual(aim.getSecondaryMode(), "none")
        _close(self, list(aim.getResult())[:3], (0, 1, 0))
        four = self.node("fourByFourMatrix")
        four.setInput(list(range(16)))
        _close(self, list(four.getResult()), list(range(16)))
        four.setInput(in30=7)
        self.assertAlmostEqual(list(four.getResult())[12], 7)
        with self.assertRaises(TypeError):
            four.setInput(in44=1)
        with self.assertRaises(ValueError):
            four.setInput([1, 2, 3])

    def test_pair_blend_vector_product_distance_angle(self):
        pair = self.node("pairBlend")
        pair.setInput(inTranslate1=(0, 0, 0), inTranslate2=(10, 0, 0), weight=0.3)
        pair.setRotateInterpolation("quaternion")
        self.assertEqual(pair.getRotateInterpolation(), "quaternion")
        _close(self, pair.getResult(), (3, 0, 0))
        self.assertEqual(pair.getOutputPlug("rotate").getFullName(), pair.getFullName() + ".outRotate")
        vector = self.node("vectorProduct")
        vector.setInput(input1=(1, 0, 0), input2=(0, 1, 0)).setOperation("crossProduct")
        _close(self, vector.getResult(), (0, 0, 1))
        distance = self.node("distanceBetween")
        _close(self, distance.setInput(point1=(0, 0, 0), point2=(3, 4, 0)).getResult(), 5)
        angle = self.node("angleBetween")
        angle.setInput(vector1=(1, 0, 0), vector2=(0, 1, 0))
        _close(self, angle.getResult(), 90, 3)
        _close(self, angle.getResult("axis"), (0, 0, 1))


class GeometryAndRampTest(_Case):
    """カーブ・サーフェスの入力とランプ。"""

    def test_curve_info_and_point_on_curve(self):
        curve = cmds.curve(name=self.ns + ":crv", degree=1, point=[(0, 0, 0), (4, 0, 0)])
        info = self.node("curveInfo")
        info.setInput(inputCurve=mlib.getNode(curve))
        _close(self, info.getResult(), 4)
        point = self.node("pointOnCurveInfo")
        point.setInput(inputCurve=mlib.getNode(curve).getShape(), parameter=0.25, turnOnPercentage=True)
        _close(self, point.getResult(), (1, 0, 0))
        _close(self, point.getResult("normalizedTangent"), (1, 0, 0))
        with self.assertRaises(TypeError):
            info.setInput(inputCurve=mlib.createNode("multiplyDivide", name=self.ns + ":notCurve"))

    def test_point_on_surface(self):
        plane = cmds.nurbsPlane(name=self.ns + ":plane", axis=(0, 1, 0), width=2, constructionHistory=False)[0]
        info = self.node("pointOnSurfaceInfo")
        info.setInput(inputSurface=mlib.getNode(plane), parameterU=0.5, parameterV=0.5, turnOnPercentage=True)
        _close(self, info.getResult(), (0, 0, 0))
        _close(self, [abs(v) for v in info.getResult("normalizedNormal")], (0, 1, 0))

    def test_remap_value_ramp(self):
        node = self.node("remapValue")
        node.setRampPoints([(0.0, 0.0, "linear"), (1.0, 1.0, "linear")])
        node.addRampPoint(0.5, 0.0, "linear")
        self.assertEqual([p[0] for p in node.getRampPoints()], [0.0, 0.5, 1.0])
        node.setInput(inputValue=0.75)
        _close(self, node.getResult(), 0.5)
        node.setRampPoints([(0.0, (1, 0, 0), "linear")], kind="color")
        _close(self, node.getRampPoints("color")[0][1], (1, 0, 0))
        self.assertEqual(node.getOutputPlug("color").getFullName(), node.getFullName() + ".outColor")
        with self.assertRaises(ValueError):
            node.getRampPoints("alpha")


def _snapshot(node):
    """ノードの書き込めるアトリビュートの値と入出力の接続を、比べられる形で取る。

    出力は評価のたびに変わるため比べない。
    """
    name = node.getFullName()
    values = {}
    for attribute in cmds.listAttr(name, multi=True, write=True) or []:
        try:
            values[attribute] = cmds.getAttr(name + "." + attribute)
        except (RuntimeError, ValueError, TypeError):
            continue
    connections = sorted(cmds.listConnections(name, connections=True, plugs=True) or [])
    return values, connections


class WriterUndoTest(_Case):
    """書込みのメソッドが、1回のUndoでアトリビュートと接続を元に戻す。"""

    def test_every_writer_undoes_in_one_step(self):
        cmds.loadPlugin("matrixNodes", quiet=True)
        source = mlib.createNode("transform", name=self.ns + ":src")
        curve = mlib.getNode(cmds.curve(name=self.ns + ":crv", degree=1, point=[(0, 0, 0), (1, 0, 0)]))
        plane = mlib.getNode(cmds.nurbsPlane(name=self.ns + ":pl", constructionHistory=False)[0])
        matrix = Matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 2, 3, 1])
        calls = [
            ("addDoubleLinear", lambda n: n.setInput(input1=source.getPlug("tx"), input2=2)),
            ("aimMatrix", lambda n: n.setInput(inputMatrix=matrix, primaryTargetVector=(0, 1, 0))),
            ("aimMatrix", lambda n: n.setPrimaryMode("align")),
            ("aimMatrix", lambda n: n.setSecondaryMode("align")),
            ("angleBetween", lambda n: n.setInput(vector1=(1, 0, 0), vector2=source.getPlug("translate"))),
            ("blendColors", lambda n: n.setInput(color1=(0, 1, 0), blender=0.25)),
            ("blendMatrix", lambda n: n.setInput(inputMatrix=matrix)),
            ("blendMatrix", lambda n: n.addTarget(source.getPlug("worldMatrix")[0], 0.5)),
            ("blendWeighted", lambda n: n.addInput(source.getPlug("tx"), 0.5)),
            ("clamp", lambda n: n.setInput(input=(1, 2, 3), max=(1, 1, 1))),
            ("composeMatrix", lambda n: n.setInput(inputTranslate=(1, 2, 3), useEulerRotation=False)),
            ("composeMatrix", lambda n: n.setRotateOrder("zyx")),
            ("condition", lambda n: n.setInput(firstTerm=source.getPlug("tx"), colorIfTrue=(1, 0, 0))),
            ("condition", lambda n: n.setOperation("lessThan")),
            ("curveInfo", lambda n: n.setInput(inputCurve=curve)),
            ("decomposeMatrix", lambda n: n.setInput(inputMatrix=source.getPlug("worldMatrix")[0])),
            ("decomposeMatrix", lambda n: n.setRotateOrder(3)),
            ("distanceBetween", lambda n: n.setInput(point1=(1, 0, 0), inMatrix2=matrix)),
            ("fourByFourMatrix", lambda n: n.setInput(list(range(16)), in33=source.getPlug("tx"))),
            ("inverseMatrix", lambda n: n.setInput(inputMatrix=matrix)),
            ("multDoubleLinear", lambda n: n.setInput(input1=3, input2=4)),
            ("multMatrix", lambda n: n.setInput([matrix, source.getPlug("worldMatrix")[0]])),
            ("multMatrix", lambda n: n.addInput(matrix)),
            ("multiplyDivide", lambda n: n.setInput(input1=(2, 2, 2))),
            ("multiplyDivide", lambda n: n.setOperation("power")),
            ("pairBlend", lambda n: n.setInput(inTranslate2=(1, 2, 3), weight=0.5)),
            ("pairBlend", lambda n: n.setRotateInterpolation("quaternion")),
            ("pickMatrix", lambda n: n.setInput(inputMatrix=matrix, useScale=False)),
            ("plusMinusAverage", lambda n: n.addInput((1, 2, 3), dimension=3)),
            ("plusMinusAverage", lambda n: n.setOperation("average")),
            ("pointOnCurveInfo", lambda n: n.setInput(inputCurve=curve.getShape(), parameter=0.5)),
            ("pointOnSurfaceInfo", lambda n: n.setInput(inputSurface=plane, parameterU=0.5)),
            ("remapValue", lambda n: n.setInput(inputValue=0.5, outputMax=2)),
            ("remapValue", lambda n: n.setRampPoints([(0.0, 1.0, "smooth")])),
            ("remapValue", lambda n: n.addRampPoint(0.5, 0.25)),
            ("reverse", lambda n: n.setInput(input=source.getPlug("translate"))),
            ("setRange", lambda n: n.setInput(value=(1, 1, 1), oldMax=(2, 2, 2))),
            ("unitConversion", lambda n: n.setInput(input=source.getPlug("rx"), conversionFactor=2)),
            ("vectorProduct", lambda n: n.setInput(input1=(1, 0, 0), normalizeOutput=True)),
            ("vectorProduct", lambda n: n.setOperation("crossProduct")),
        ]
        removals = [
            ("blendMatrix", lambda n: n.addTarget(matrix), lambda n: n.removeTarget(0)),
            ("blendWeighted", lambda n: n.addInput(1.0), lambda n: n.removeInput(0)),
            ("multMatrix", lambda n: n.addInput(matrix), lambda n: n.removeInput(0)),
            ("plusMinusAverage", lambda n: n.addInput(source.getPlug("tx")), lambda n: n.removeInput(0)),
        ]
        for index, (node_type, call) in enumerate(calls):
            with self.subTest(node_type=node_type, index=index):
                node = self.node(node_type, "%s%d" % (node_type, index))
                # 既定のランプ点など、初めて参照したときに作られる要素を先に作る。
                _snapshot(node)
                before = _snapshot(node)
                self.flushUndo()
                call(node)
                self.assertNotEqual(_snapshot(node), before)
                cmds.undo()
                self.assertEqual(_snapshot(node), before)
        for index, (node_type, prepare, call) in enumerate(removals):
            with self.subTest(node_type=node_type, remove=index):
                node = self.node(node_type, "%sRemove%d" % (node_type, index))
                prepare(node)
                _snapshot(node)
                before = _snapshot(node)
                self.flushUndo()
                call(node)
                self.assertNotEqual(_snapshot(node), before)
                cmds.undo()
                self.assertEqual(_snapshot(node), before)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
