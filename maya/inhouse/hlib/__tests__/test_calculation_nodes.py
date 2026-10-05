"""計算ノードを実際のMaya DGで評価し、継承・単位・Undoを検証する。"""
import math
import sys
import unittest
import maya.cmds as cmds
import hlib
from hlib.maths import Matrix


class CalculationNodesTest(unittest.TestCase):
    """専用namespaceに作成し、終了時に対象だけを削除する。"""

    def setUp(self):
        """Maya付属の行列ノードとテスト専用namespaceを用意する。"""
        cmds.loadPlugin("matrixNodes", quiet=True)
        self.old_namespace = cmds.namespaceInfo(currentNamespace=True)
        self.namespace = cmds.namespace(add="hlibCalculationTest")
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        """テスト対象を削除し、namespaceを復元する。"""
        cmds.namespace(set=self.old_namespace)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def assertVector(self, actual, expected):
        """3要素の計算結果を許容誤差付きで比較する。"""
        self.assertEqual(len(tuple(actual)), len(tuple(expected)))
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=5)

    def test_native_types(self):
        """公開クラスとMayaの実型・継承列が一致する。"""
        types = "multiplyDivide plusMinusAverage condition clamp reverse remapValue setRange vectorProduct angleBetween composeMatrix inverseMatrix pickMatrix blendMatrix aimMatrix fourByFourMatrix pairBlend addDoubleLinear multDoubleLinear unitConversion curveInfo pointOnCurveInfo pointOnSurfaceInfo".split()
        for kind in types:
            with self.subTest(kind=kind):
                node = hlib.createNode(kind)
                actual = cmds.nodeType(node.fullName())
                self.assertEqual(type(node).__dict__["__hlib_node_type__"], actual)
                native = cmds.nodeType(node.fullName(), inherited=True)
                for cls in type(node).__mro__:
                    name = cls.__dict__.get("__hlib_node_type__")
                    if name and name != "dependNode":
                        self.assertIn(name, native)

    def test_multiply_and_connections(self):
        """モード・値設定・名前による接続・Undo/Redoを検証する。"""
        node = hlib.createNode("multiplyDivide")
        node.setInput(1, (2, 4, 8)).setInput(2, (2, 2, 2))
        node.setOperation("divide")
        self.assertVector(node.result(), (1, 2, 4))
        self.assertEqual(node.getOperation(), "divide")
        node.setOperation("power")
        self.assertVector(node.result(), (4, 16, 64))
        cmds.undo()
        self.assertEqual(node.getOperation(), "divide")
        cmds.redo()
        source = hlib.createNode("transform")
        source.plug("translate").set((3, 3, 3))
        node.connectInput(1, source.plug("translate").fullName())
        self.assertVector(node.result(), (9, 9, 9))
        with self.assertRaises((ValueError, RuntimeError)):
            node.setInput(1, (1, 1, 1))
        with self.assertRaises(ValueError):
            node.setOperation("unknown")
        with self.assertRaises(ValueError):
            node.setInput(True, (1, 1, 1))

    def test_sparse_sum(self):
        """入力参照で配列を作成せず、2D/3Dと疎な番号を保つ。"""
        node = hlib.createNode("plusMinusAverage")
        before = node.inputIndices()
        with self.assertRaises(IndexError):
            node.inputPlug(19)
        self.assertEqual(node.inputIndices(), before)
        node.setInput(2, 8).setInput(8, 2)
        self.assertEqual(node.result(), 10)
        node.setOperation("subtract")
        self.assertEqual(node.result(), 6)
        node.removeInput(8)
        cmds.undo()
        self.assertEqual(node.getInput(8), 2)
        node.setOperation("sum")
        node.setInput(4, (1, 2), dimension=2)
        self.assertVector(node.result(2), (1, 2))
        node.setInput(3, (1, 2, 3), dimension=3)
        self.assertVector(node.result(3), (1, 2, 3))
        with self.assertRaises(ValueError):
            node.setInput(2**32, 1)

    def test_condition_ranges(self):
        """条件分岐、clamp、線形変換、1-xを検証する。"""
        condition = hlib.createNode("condition")
        condition.setInput(1, 3).setInput(2, 2).setOperation("greater")
        condition.setTrueValue((1, 2, 3)).setFalseValue((4, 5, 6))
        self.assertVector(condition.result(), (1, 2, 3))
        condition.setOperation("less")
        self.assertVector(condition.result(), (4, 5, 6))
        clamp = hlib.createNode("clamp")
        clamp.setRange((0, 0, 0), (1, 1, 1)).setInput((-2, .5, 3))
        self.assertVector(clamp.result(), (0, .5, 1))
        remap = hlib.createNode("setRange")
        remap.setRange((0, 0, 0), (10, 10, 10), (0, 0, 0), (1, 1, 1))
        remap.setInput((0, 5, 10))
        self.assertVector(remap.result(), (0, .5, 1))
        reverse = hlib.createNode("reverse")
        reverse.connectInput(remap.outputPlug())
        self.assertVector(reverse.result(), (1, .5, 0))

    def test_vector_and_angle(self):
        """内積・外積と角度出力を検証する。"""
        node = hlib.createNode("vectorProduct")
        node.setInput(1, (1, 0, 0)).setInput(2, (0, 1, 0)).setOperation("cross")
        self.assertVector(node.result(), (0, 0, 1))
        node.setOperation("dot")
        self.assertVector(node.result(), (0, 0, 0))
        angle = hlib.createNode("angleBetween")
        angle.setInput(1, (1, 0, 0)).setInput(2, (0, 1, 0))
        self.assertAlmostEqual(angle.result(), math.pi / 2)
        self.assertVector(angle.getAxis(), (0, 0, 1))

    def test_matrix_nodes(self):
        """行列の合成・逆行列・成分選択・16要素設定を検証する。"""
        compose = hlib.createNode("composeMatrix")
        compose.setTranslation((3, 4, 5)).setScale((2, 2, 2))
        matrix = compose.result()
        inverse = hlib.createNode("inverseMatrix")
        inverse.connectInput(compose.outputPlug())
        self.assertVector(tuple(matrix * inverse.result()), tuple(Matrix()))
        pick = hlib.createNode("pickMatrix")
        pick.connectInput(compose.outputPlug()).setUseScale(False)
        self.assertAlmostEqual(pick.result()[0], 1)
        self.assertAlmostEqual(pick.result()[12], 3)
        four = hlib.createNode("fourByFourMatrix")
        four.setMatrix(matrix)
        self.assertVector(tuple(four.result()), tuple(matrix))
        cmds.undo()
        self.assertVector(tuple(four.getMatrix()), tuple(Matrix()))
        compose.setRotation((0, 0, math.pi / 2))
        self.assertAlmostEqual(compose.result()[1], 2)
        compose.setQuaternion((0, 0, 0, 1)).setUseEulerRotation(False)
        self.assertAlmostEqual(compose.result()[0], 2)

    def test_blend_and_aim(self):
        """行列ブレンドの重みとAimの向きを検証する。"""
        compose = hlib.createNode("composeMatrix")
        compose.setTranslation((10, 0, 0))
        blend = hlib.createNode("blendMatrix")
        blend.setTarget(3, compose.result(), .25)
        self.assertAlmostEqual(blend.result()[12], 2.5)
        self.assertEqual(blend.targetIndices(), [3])
        self.assertEqual(blend.getTarget(3)["weight"], .25)
        blend.removeTarget(3)
        cmds.undo()
        self.assertAlmostEqual(blend.result()[12], 2.5)
        aim = hlib.createNode("aimMatrix")
        compose.setTranslation((0, 10, 0))
        aim.connectPrimaryMatrix(compose.outputPlug())
        aim.setPrimaryAxis((1, 0, 0)).setPrimaryMode("aim").setSecondaryMode("none")
        self.assertAlmostEqual(aim.result()[1], 1)

    def test_ramp(self):
        """値・色ランプの編集、評価、削除Undoを検証する。"""
        node = hlib.createNode("remapValue")
        node.setRampPoint(0, 0, 0).setRampPoint(1, 1, 1)
        node.setRange(0, 10, 0, 100).setInput(5)
        self.assertAlmostEqual(node.result(), 50)
        node.setRampPoint(7, .5, .25, "smooth")
        self.assertEqual(node.rampPoints()[7]["value"], .25)
        node.removeRampPoint(7)
        cmds.undo()
        self.assertIn(7, node.rampPoints())
        node.setRampPoint(4, .2, (1, 0, 0), kind="color")
        self.assertVector(node.rampPoints("color")[4]["value"], (1, 0, 0))
        with self.assertRaises(ValueError):
            node.setRampPoint(9, 2, 0)
        self.assertNotIn(9, node.rampPoints())

    def test_pair_blend(self):
        """移動とQuaternion補間の回転結果を検証する。"""
        node = hlib.createNode("pairBlend")
        node.setTranslation(1, (0, 0, 0)).setTranslation(2, (10, 0, 0))
        node.setRotation(1, (0, 0, 0)).setRotation(2, (0, 0, math.pi / 2))
        node.setRotationInterpolation("quaternion").setWeight(.5)
        self.assertVector(node.result(), (5, 0, 0))
        self.assertVector(node.result("rotate"), (0, 0, math.pi / 4))

    def test_scalar_and_fast(self):
        """距離型ノード、単位変換、fast値更新を検証する。"""
        for kind, expected in (("addDoubleLinear", 5), ("multDoubleLinear", 6)):
            node = hlib.createNode(kind)
            node.setInput(1, 2).setInput(2, 3)
            self.assertAlmostEqual(node.result(), expected)
        node = hlib.createNode("unitConversion")
        node.setInput(3).setFactor(2)
        self.assertAlmostEqual(node.result(), 6)
        node.setFactor(4, fast=True)
        self.assertAlmostEqual(node.result(), 12)
        self.assertAlmostEqual(node.getFactor(), 4)
        with self.assertRaises(TypeError):
            node.setFactor(1, fast=1)

    def test_curve_queries(self):
        """ローカル/ワールド空間のカーブ長・位置と接線を検証する。"""
        curve = hlib.getNode(cmds.curve(d=1, p=[(0, 0, 0), (10, 0, 0)]))
        curve.plug("scale").set((2, 2, 2))
        info = hlib.createNode("curveInfo")
        info.connectCurve(curve, ws=False)
        self.assertAlmostEqual(info.arcLength(), 10)
        info.connectCurve(curve, force=True)
        self.assertAlmostEqual(info.arcLength(), 20)
        point = hlib.createNode("pointOnCurveInfo")
        point.connectCurve(curve).setParameter(.5, percentage=True)
        self.assertVector(point.getPosition(), (10, 0, 0))
        self.assertVector(point.getTangent(), (1, 0, 0))

    def test_surface_queries(self):
        """サーフェスの位置・法線・接線を実形状で検証する。"""
        surface = hlib.getNode(cmds.nurbsPlane(axis=(0, 1, 0), width=4)[0])
        point = hlib.createNode("pointOnSurfaceInfo")
        point.connectSurface(surface).setParameters(.5, .5, percentage=True)
        self.assertVector(point.getPosition(), (0, 0, 0))
        self.assertAlmostEqual(point.getNormal().length(), 1)
        self.assertAlmostEqual(point.getTangent("u").length(), 1)
        self.assertAlmostEqual(point.getTangent("v").length(), 1)
        with self.assertRaises(TypeError):
            point.connectSurface(hlib.getNode(cmds.polyCube()[0]).shape())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
