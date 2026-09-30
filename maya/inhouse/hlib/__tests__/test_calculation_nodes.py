"""計算ノードを実際のMaya DGで評価し、継承・単位・Undoを検証する。"""
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
                actual = cmds.nodeType(node.full_name())
                self.assertEqual(type(node).__dict__["__hlib_node_type__"], actual)
                native = cmds.nodeType(node.full_name(), inherited=True)
                for cls in type(node).__mro__:
                    name = cls.__dict__.get("__hlib_node_type__")
                    if name and name != "dependNode":
                        self.assertIn(name, native)

    def test_multiply_and_connections(self):
        """モード・値設定・名前による接続・Undo/Redoを検証する。"""
        node = hlib.createNode("multiplyDivide")
        node.set_input(1, (2, 4, 8)).set_input(2, (2, 2, 2))
        node.set_operation("divide")
        self.assertVector(node.result(), (1, 2, 4))
        self.assertEqual(node.get_operation(), "divide")
        node.set_operation("power")
        self.assertVector(node.result(), (4, 16, 64))
        cmds.undo()
        self.assertEqual(node.get_operation(), "divide")
        cmds.redo()
        source = hlib.createNode("transform")
        source.plug("translate").set((3, 3, 3))
        node.connect_input(1, source.plug("translate").full_name())
        self.assertVector(node.result(), (9, 9, 9))
        with self.assertRaises((ValueError, RuntimeError)):
            node.set_input(1, (1, 1, 1))
        with self.assertRaises(ValueError):
            node.set_operation("unknown")
        with self.assertRaises(ValueError):
            node.set_input(True, (1, 1, 1))

    def test_sparse_sum(self):
        """入力参照で配列を作成せず、2D/3Dと疎な番号を保つ。"""
        node = hlib.createNode("plusMinusAverage")
        before = node.input_indices()
        with self.assertRaises(IndexError):
            node.input_plug(19)
        self.assertEqual(node.input_indices(), before)
        node.set_input(2, 8).set_input(8, 2)
        self.assertEqual(node.result(), 10)
        node.set_operation("subtract")
        self.assertEqual(node.result(), 6)
        node.remove_input(8)
        cmds.undo()
        self.assertEqual(node.get_input(8), 2)
        node.set_operation("sum")
        node.set_input(4, (1, 2), dimension=2)
        self.assertVector(node.result(2), (1, 2))
        node.set_input(3, (1, 2, 3), dimension=3)
        self.assertVector(node.result(3), (1, 2, 3))
        with self.assertRaises(ValueError):
            node.set_input(2**32, 1)

    def test_condition_ranges(self):
        """条件分岐、clamp、線形変換、1-xを検証する。"""
        condition = hlib.createNode("condition")
        condition.set_input(1, 3).set_input(2, 2).set_operation("greater")
        condition.set_true_value((1, 2, 3)).set_false_value((4, 5, 6))
        self.assertVector(condition.result(), (1, 2, 3))
        condition.set_operation("less")
        self.assertVector(condition.result(), (4, 5, 6))
        clamp = hlib.createNode("clamp")
        clamp.set_range((0, 0, 0), (1, 1, 1)).set_input((-2, .5, 3))
        self.assertVector(clamp.result(), (0, .5, 1))
        remap = hlib.createNode("setRange")
        remap.set_range((0, 0, 0), (10, 10, 10), (0, 0, 0), (1, 1, 1))
        remap.set_input((0, 5, 10))
        self.assertVector(remap.result(), (0, .5, 1))
        reverse = hlib.createNode("reverse")
        reverse.connect_input(remap.output_plug())
        self.assertVector(reverse.result(), (1, .5, 0))

    def test_vector_and_angle(self):
        """内積・外積と角度出力を検証する。"""
        node = hlib.createNode("vectorProduct")
        node.set_input(1, (1, 0, 0)).set_input(2, (0, 1, 0)).set_operation("cross")
        self.assertVector(node.result(), (0, 0, 1))
        node.set_operation("dot")
        self.assertVector(node.result(), (0, 0, 0))
        angle = hlib.createNode("angleBetween")
        angle.set_input(1, (1, 0, 0)).set_input(2, (0, 1, 0))
        self.assertAlmostEqual(angle.result(), 90)
        self.assertVector(angle.get_axis(), (0, 0, 1))

    def test_matrix_nodes(self):
        """行列の合成・逆行列・成分選択・16要素設定を検証する。"""
        compose = hlib.createNode("composeMatrix")
        compose.set_translate((3, 4, 5)).set_scale((2, 2, 2))
        matrix = compose.result()
        inverse = hlib.createNode("inverseMatrix")
        inverse.connect_input(compose.output_plug())
        self.assertVector(tuple(matrix * inverse.result()), tuple(Matrix()))
        pick = hlib.createNode("pickMatrix")
        pick.connect_input(compose.output_plug()).set_use_scale(False)
        self.assertAlmostEqual(pick.result()[0], 1)
        self.assertAlmostEqual(pick.result()[12], 3)
        four = hlib.createNode("fourByFourMatrix")
        four.set_matrix(matrix)
        self.assertVector(tuple(four.result()), tuple(matrix))
        cmds.undo()
        self.assertVector(tuple(four.get_matrix()), tuple(Matrix()))
        compose.set_rotate((0, 0, 90))
        self.assertAlmostEqual(compose.result()[1], 2)
        compose.set_quaternion((0, 0, 0, 1)).set_use_euler_rotation(False)
        self.assertAlmostEqual(compose.result()[0], 2)

    def test_blend_and_aim(self):
        """行列ブレンドの重みとAimの向きを検証する。"""
        compose = hlib.createNode("composeMatrix")
        compose.set_translate((10, 0, 0))
        blend = hlib.createNode("blendMatrix")
        blend.set_target(3, compose.result(), .25)
        self.assertAlmostEqual(blend.result()[12], 2.5)
        self.assertEqual(blend.target_indices(), [3])
        self.assertEqual(blend.get_target(3)["weight"], .25)
        blend.remove_target(3)
        cmds.undo()
        self.assertAlmostEqual(blend.result()[12], 2.5)
        aim = hlib.createNode("aimMatrix")
        compose.set_translate((0, 10, 0))
        aim.connect_primary_matrix(compose.output_plug())
        aim.set_primary_axis((1, 0, 0)).set_primary_mode("aim").set_secondary_mode("none")
        self.assertAlmostEqual(aim.result()[1], 1)

    def test_ramp(self):
        """値・色ランプの編集、評価、削除Undoを検証する。"""
        node = hlib.createNode("remapValue")
        node.set_ramp_point(0, 0, 0).set_ramp_point(1, 1, 1)
        node.set_range(0, 10, 0, 100).set_input(5)
        self.assertAlmostEqual(node.result(), 50)
        node.set_ramp_point(7, .5, .25, "smooth")
        self.assertEqual(node.ramp_points()[7]["value"], .25)
        node.remove_ramp_point(7)
        cmds.undo()
        self.assertIn(7, node.ramp_points())
        node.set_ramp_point(4, .2, (1, 0, 0), kind="color")
        self.assertVector(node.ramp_points("color")[4]["value"], (1, 0, 0))
        with self.assertRaises(ValueError):
            node.set_ramp_point(9, 2, 0)
        self.assertNotIn(9, node.ramp_points())

    def test_pair_blend(self):
        """移動とQuaternion補間の回転結果を検証する。"""
        node = hlib.createNode("pairBlend")
        node.set_translate(1, (0, 0, 0)).set_translate(2, (10, 0, 0))
        node.set_rotate(1, (0, 0, 0)).set_rotate(2, (0, 0, 90))
        node.set_rotation_interpolation("quaternion").set_weight(.5)
        self.assertVector(node.result(), (5, 0, 0))
        self.assertVector(node.result("rotate"), (0, 0, 45))

    def test_scalar_and_fast(self):
        """距離型ノード、単位変換、fast値更新を検証する。"""
        for kind, expected in (("addDoubleLinear", 5), ("multDoubleLinear", 6)):
            node = hlib.createNode(kind)
            node.set_input(1, 2).set_input(2, 3)
            self.assertAlmostEqual(node.result(), expected)
        node = hlib.createNode("unitConversion")
        node.set_input(3).set_factor(2)
        self.assertAlmostEqual(node.result(), 6)
        node.set_factor(4, fast=True)
        self.assertAlmostEqual(node.result(), 12)
        self.assertAlmostEqual(node.get_factor(), 4)
        with self.assertRaises(TypeError):
            node.set_factor(1, fast=1)

    def test_curve_queries(self):
        """ローカル/ワールド空間のカーブ長・位置と接線を検証する。"""
        curve = hlib.getNode(cmds.curve(d=1, p=[(0, 0, 0), (10, 0, 0)]))
        curve.plug("scale").set((2, 2, 2))
        info = hlib.createNode("curveInfo")
        info.connect_curve(curve, world_space=False)
        self.assertAlmostEqual(info.arc_length(), 10)
        info.connect_curve(curve, force=True)
        self.assertAlmostEqual(info.arc_length(), 20)
        point = hlib.createNode("pointOnCurveInfo")
        point.connect_curve(curve).set_parameter(.5, percentage=True)
        self.assertVector(point.get_position(), (10, 0, 0))
        self.assertVector(point.get_tangent(), (1, 0, 0))

    def test_surface_queries(self):
        """サーフェスの位置・法線・接線を実形状で検証する。"""
        surface = hlib.getNode(cmds.nurbsPlane(axis=(0, 1, 0), width=4)[0])
        point = hlib.createNode("pointOnSurfaceInfo")
        point.connect_surface(surface).set_parameters(.5, .5, percentage=True)
        self.assertVector(point.get_position(), (0, 0, 0))
        self.assertAlmostEqual(point.get_normal().length(), 1)
        self.assertAlmostEqual(point.get_tangent("u").length(), 1)
        self.assertAlmostEqual(point.get_tangent("v").length(), 1)
        with self.assertRaises(TypeError):
            point.connect_surface(hlib.getNode(cmds.polyCube()[0]).shape())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
