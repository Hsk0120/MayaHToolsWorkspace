"""計算ノードの共通基底(_Calculation)と、計算・ユーティリティノードの型登録の仕様を固定する。

担当A。`nodes/_calculation.py` の検証・解決規則と、計算ノード型とラッパークラスの対応、
メソッドを持たない計算ノード(multiplyDivide等)が通常のPlugで扱えることを確かめる。
"""

import math
import unittest
from unittest import mock

import maya.cmds as cmds
import mlib
from mlib.nodes._calculation import _Calculation


# 計算・ユーティリティノードのMaya型と公開クラス・直接の基底クラス名。
_TYPE_TABLE = (
    ("aimMatrix", "AimMatrix", "Node"),
    ("angleBetween", "AngleBetween", "Node"),
    ("blendColors", "BlendColors", "Node"),
    ("blendMatrix", "BlendMatrix", "Node"),
    ("blendWeighted", "BlendWeighted", "Node"),
    ("clamp", "Clamp", "Node"),
    ("composeMatrix", "ComposeMatrix", "Node"),
    ("condition", "Condition", "Node"),
    ("curveInfo", "CurveInfo", "AbstractBaseCreate"),
    ("decomposeMatrix", "DecomposeMatrix", "Node"),
    ("distanceBetween", "DistanceBetween", "Node"),
    ("file", "File", "Texture2d"),
    ("fourByFourMatrix", "FourByFourMatrix", "Node"),
    ("inverseMatrix", "InverseMatrix", "THDependNode"),
    ("multMatrix", "MultMatrix", "Node"),
    ("multiplyDivide", "MultiplyDivide", "ShadingDependNode"),
    ("pairBlend", "PairBlend", "Node"),
    ("pickMatrix", "PickMatrix", "Node"),
    ("place2dTexture", "Place2dTexture", "ShadingDependNode"),
    ("plusMinusAverage", "PlusMinusAverage", "ShadingDependNode"),
    ("pointOnCurveInfo", "PointOnCurveInfo", "AbstractBaseCreate"),
    ("pointOnSurfaceInfo", "PointOnSurfaceInfo", "AbstractBaseCreate"),
    ("remapValue", "RemapValue", "Node"),
    ("reverse", "Reverse", "Node"),
    ("setRange", "SetRange", "Node"),
    ("unitConversion", "UnitConversion", "Node"),
    ("vectorProduct", "VectorProduct", "ShadingDependNode"),
)


class _FakePlug:
    """enum_nameへ渡す最小のPlug代用。get()だけを持つ。"""

    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class CalculationValidatorTest(unittest.TestCase):
    """_Calculationの検証関数。シーンを変更しない。"""

    def test_index_accepts_logical_range(self):
        """0から2147483647までの整数をそのまま返す。"""
        self.assertEqual(_Calculation.index(0), 0)
        self.assertEqual(_Calculation.index(2147483647), 2147483647)
        self.assertEqual(_Calculation.index(2, (1, 2)), 2)

    def test_index_rejects_invalid(self):
        """bool・負数・範囲外・非整数・許可外はValueError。"""
        for value in (True, False, -1, 2 ** 31, 1.0, "1", None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Expected an integer index"):
                    _Calculation.index(value)
        with self.assertRaisesRegex(ValueError, "outside the allowed values"):
            _Calculation.index(3, (1, 2))
        with self.assertRaisesRegex(ValueError, "outside the allowed values"):
            _Calculation.index(0, range(1, 3))

    def test_scalar(self):
        """有限な数値をfloatへ変換する。数値文字列はfloat()の規則で受け付ける。"""
        self.assertIsInstance(_Calculation.scalar(2), float)
        self.assertEqual(_Calculation.scalar(2), 2.0)
        self.assertEqual(_Calculation.scalar("1.5"), 1.5)
        self.assertEqual(_Calculation.scalar(-0.0), 0.0)
        for value in (float("nan"), float("inf"), float("-inf"), "inf"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "finite"):
                    _Calculation.scalar(value)
        with self.assertRaises(ValueError):
            _Calculation.scalar("x")
        with self.assertRaises(TypeError):
            _Calculation.scalar(None)

    def test_vector(self):
        """固定長の有限なfloatのtupleを返す。長さ・数値の不正はValueError。"""
        values = _Calculation.vector([1, 2, 3])
        self.assertEqual(values, (1.0, 2.0, 3.0))
        self.assertIsInstance(values, tuple)
        self.assertTrue(all(isinstance(v, float) for v in values))
        self.assertEqual(_Calculation.vector((v for v in (0, 0, 0, 1)), 4), (0.0, 0.0, 0.0, 1.0))
        with self.assertRaisesRegex(ValueError, "Expected 3 components"):
            _Calculation.vector((1, 2))
        with self.assertRaisesRegex(ValueError, "Expected 4 components"):
            _Calculation.vector((1, 2, 3), 4)
        with self.assertRaisesRegex(ValueError, "finite"):
            _Calculation.vector((1, float("nan"), 3))
        with self.assertRaises(ValueError):
            _Calculation.vector("abc")
        with self.assertRaises(TypeError):
            _Calculation.vector(None)

    def test_boolean(self):
        """bool型だけを受け付け、0/1や文字列はTypeError。"""
        self.assertIs(_Calculation.boolean(True), True)
        self.assertIs(_Calculation.boolean(False), False)
        for value in (0, 1, "True", None, 1.0):
            with self.subTest(value=value):
                with self.assertRaisesRegex(TypeError, "Expected bool"):
                    _Calculation.boolean(value)

    def test_enum_value(self):
        """名前は大文字小文字を問わず番号へ、番号は範囲内だけを受け付ける。"""
        names = ("lock", "aim", "align")
        self.assertEqual(_Calculation.enum_value("aim", names), 1)
        self.assertEqual(_Calculation.enum_value("ALIGN", names), 2)
        self.assertEqual(_Calculation.enum_value(0, names), 0)
        # 未対応の名前はValueError。文言に不正な値と選択肢を示す。
        for value in ("none", "", "1"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as caught:
                    _Calculation.enum_value(value, names)
                self.assertEqual(str(caught.exception),
                                 "Unsupported value %r (choices: lock, aim, align)" % value)
        for value in (3, -1, True, 1.0, None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _Calculation.enum_value(value, names)

    def test_enum_name(self):
        """Plugの番号を名前へ変換し、範囲外の番号はValueError。"""
        names = ("euler", "quaternion")
        self.assertEqual(_Calculation.enum_name(_FakePlug(1), names), "quaternion")
        with self.assertRaises(ValueError):
            _Calculation.enum_name(_FakePlug(2), names)

    def test_set_value_validates_before_target(self):
        """検証の失敗時は対象Plugを解決しない。成功時はfastをPlug.setへ渡す。"""
        target = mock.Mock()
        with self.assertRaises(ValueError):
            _Calculation.set_value((1, 2), _Calculation.vector, target, 1, fast=True)
        target.assert_not_called()
        _Calculation.set_value((1, 2, 3), _Calculation.vector, target, 2, fast=True)
        target.assert_called_once_with(2)
        target.return_value.set.assert_called_once_with((1.0, 2.0, 3.0), fast=True)

    def test_connect_resolves_source_before_target(self):
        """接続元の解決に失敗した場合は接続先を取得しない。"""
        target = mock.Mock()
        with self.assertRaises(TypeError):
            _Calculation.connect(5, target)
        target.assert_not_called()


class GeometryOutputTest(unittest.TestCase):
    """_Calculation.geometry_outputのシェイプ解決。専用名前空間で行う。"""

    def setUp(self):
        self.old_namespace = cmds.namespaceInfo(currentNamespace=True)
        self.namespace = cmds.namespace(add="mlibSpecACalcBase")
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        cmds.namespace(set=self.old_namespace)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def test_transform_and_shape(self):
        """Transformは唯一の対応シェイプへ解決し、worldSpaceはインスタンス番号の要素を返す。"""
        curve = cmds.curve(d=1, p=[(0, 0, 0), (1, 0, 0)])
        shape = cmds.listRelatives(curve, shapes=True, fullPath=True)[0]
        plug = _Calculation.geometry_output(curve, "nurbsCurve", True)
        self.assertEqual(plug.getNode().getFullName(), shape)
        self.assertTrue(str(plug).endswith(".worldSpace[0]"))
        local = _Calculation.geometry_output(shape, "nurbsCurve", False)
        self.assertTrue(str(local).endswith(".local"))
        # 2番目のインスタンスパスではworldSpace[1]を返す。
        group = cmds.group(empty=True)
        instance = cmds.instance(curve)[0]
        cmds.parent(instance, group)
        instanced = _Calculation.geometry_output(instance, "nurbsCurve", True)
        self.assertTrue(str(instanced).endswith(".worldSpace[1]"))

    def test_errors(self):
        """worldSpaceの型→シェイプ数→シェイプ型の順に検証する。"""
        curve = cmds.curve(d=1, p=[(0, 0, 0), (1, 0, 0)])
        with self.assertRaisesRegex(TypeError, "Expected bool"):
            _Calculation.geometry_output("noSuchNode", "nurbsCurve", 1)
        cube = cmds.polyCube()[0]
        with self.assertRaisesRegex(ValueError, "exactly one matching shape"):
            _Calculation.geometry_output(cube, "nurbsCurve", True)
        mesh = cmds.listRelatives(cube, shapes=True, fullPath=True)[0]
        with self.assertRaisesRegex(TypeError, "Expected a nurbsCurve"):
            _Calculation.geometry_output(mesh, "nurbsCurve", True)
        second = cmds.curve(d=1, p=[(0, 0, 0), (0, 1, 0)])
        second_shape = cmds.listRelatives(second, shapes=True, fullPath=True)[0]
        cmds.parent(second_shape, curve, shape=True, relative=True)
        with self.assertRaisesRegex(ValueError, "exactly one matching shape"):
            _Calculation.geometry_output(curve, "nurbsCurve", True)
        with self.assertRaises((ValueError, RuntimeError)):
            _Calculation.geometry_output("noSuchNode_specA", "nurbsCurve", True)


class CalculationTypeTest(unittest.TestCase):
    """計算ノードの作成・型選択・公開名。"""

    def setUp(self):
        cmds.loadPlugin("matrixNodes", quiet=True)
        self.old_namespace = cmds.namespaceInfo(currentNamespace=True)
        self.namespace = cmds.namespace(add="mlibSpecACalcType")
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        cmds.namespace(set=self.old_namespace)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def test_create_and_get_select_wrapper(self):
        """createNodeとgetNodeが同じ公開クラスを返し、直接の基底も固定する。"""
        for kind, class_name, base_name in _TYPE_TABLE:
            with self.subTest(kind=kind):
                cls = getattr(mlib.nodes, class_name)
                self.assertIn(class_name, mlib.nodes.__all__)
                self.assertIs(mlib.nodes._WRAPPER_CLASSES[kind], cls)
                node = mlib.createNode(kind)
                self.assertIs(type(node), cls)
                self.assertEqual(cmds.nodeType(node.getFullName()), kind)
                self.assertIs(type(mlib.getNode(node.getFullName())), cls)
                self.assertEqual(cls.__mro__[1].__name__, base_name)

    def test_double_linear_by_version(self):
        """addDoubleLinear/multDoubleLinearは、Mayaが実際に作った型のクラスになる。"""
        for legacy, modern in (("addDoubleLinear", "addDL"), ("multDoubleLinear", "multDL")):
            with self.subTest(kind=legacy):
                node = mlib.createNode(legacy)
                actual = cmds.nodeType(node.getFullName())
                self.assertIn(actual, (legacy, modern))
                self.assertIs(type(node), mlib.nodes._WRAPPER_CLASSES[actual])

    def test_texture2d_family(self):
        """登録されていない2Dテクスチャ型は、Texture2dを親にした自動生成クラスになる。"""
        for kind in ("checker", "ramp"):
            with self.subTest(kind=kind):
                cls = type(mlib.createNode(kind))
                self.assertEqual(cls.__name__, kind[0].upper() + kind[1:])
                self.assertIs(cls.__mro__[1], mlib.nodes.Texture2d)
                self.assertTrue(issubclass(cls, mlib.nodes.Texture2d))

    def test_nodes_collection_does_not_forward_calculation_methods(self):
        """Nodesは計算ノード固有のメソッドを一括転送しない(現在の仕様)。"""
        nodes = mlib.nodes.Nodes([mlib.createNode("composeMatrix"), mlib.createNode("composeMatrix")])
        self.assertFalse(hasattr(nodes, "setRotateOrder"))
        for method in ("setTranslate", "getResult", "connectInput"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(ValueError, "Unsupported instance method"):
                    nodes.callEach(method, [(), ()])


class PlainCalculationNodeTest(unittest.TestCase):
    """固有メソッドを持たない計算ノードを、通常のPlugで設定・評価する。"""

    def setUp(self):
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))
        cmds.currentUnit(linear="cm", angle="rad")
        self.old_namespace = cmds.namespaceInfo(currentNamespace=True)
        self.namespace = cmds.namespace(add="mlibSpecAPlain")
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        cmds.namespace(set=self.old_namespace)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.currentUnit(linear=self.units[0], angle=self.units[1])

    def evaluate(self, kind, values, output):
        """Plug.setで入力し、出力をPlug.getとcmds.getAttrの両方で取得する。"""
        node = mlib.createNode(kind)
        for name, value in values:
            node.getPlug(name).set(value)
        actual = node.getPlug(output).get()
        raw = cmds.getAttr(node.getFullName() + "." + output)
        return actual, raw

    def assertValues(self, actual, expected):
        """スカラーまたは成分列を許容誤差付きで比較する。"""
        if isinstance(expected, (tuple, list)):
            self.assertEqual(len(tuple(actual)), len(expected))
            for a, e in zip(actual, expected):
                self.assertAlmostEqual(a, e, places=5)
        else:
            self.assertAlmostEqual(actual, expected, places=5)

    def test_formula_table(self):
        """各ノードの出力がMayaの既知の式と一致する。"""
        table = (
            ("multiplyDivide", (("operation", 1), ("input1", (2, 3, 4)), ("input2", (5, 6, 7))), "output", (10, 18, 28)),
            ("multiplyDivide", (("operation", 2), ("input1", (2, 3, 4)), ("input2", (4, 6, 8))), "output", (0.5, 0.5, 0.5)),
            ("multiplyDivide", (("operation", 3), ("input1", (2, 3, 4)), ("input2", (2, 2, 0.5))), "output", (4, 9, 2)),
            ("blendColors", (("blender", 0.25), ("color1", (1, 0, 0)), ("color2", (0, 0, 1))), "output", (0.25, 0, 0.75)),
            ("clamp", (("min", (0, 0, 0)), ("max", (1, 1, 1)), ("input", (-1, 0.5, 2))), "output", (0, 0.5, 1)),
            ("reverse", (("input", (0.25, 1, 0)),), "output", (0.75, 0, 1)),
            ("condition", (("operation", 2), ("firstTerm", 3), ("secondTerm", 1),
                           ("colorIfTrue", (1, 2, 3)), ("colorIfFalse", (4, 5, 6))), "outColor", (1, 2, 3)),
            ("condition", (("operation", 4), ("firstTerm", 3), ("secondTerm", 1),
                           ("colorIfTrue", (1, 2, 3)), ("colorIfFalse", (4, 5, 6))), "outColor", (4, 5, 6)),
            ("setRange", (("value", (5, 0, 10)), ("oldMin", (0, 0, 0)), ("oldMax", (10, 10, 10)),
                          ("min", (0, 0, 0)), ("max", (1, 2, 3))), "outValue", (0.5, 0, 3)),
            ("remapValue", (("inputValue", 0.25), ("inputMin", 0), ("inputMax", 1),
                            ("outputMin", 0), ("outputMax", 10)), "outValue", 2.5),
            ("unitConversion", (("input", 3.0), ("conversionFactor", 2.0)), "output", 6.0),
        )
        for kind, values, output, expected in table:
            with self.subTest(kind=kind, values=values):
                actual, raw = self.evaluate(kind, values, output)
                self.assertValues(actual, expected)
                self.assertValues(raw[0] if isinstance(raw, list) else raw, expected)

    def test_array_inputs(self):
        """plusMinusAverage・blendWeightedの配列入力。"""
        node = mlib.createNode("plusMinusAverage")
        node.getPlug("operation").set(3)
        node.getPlug("input1D")[0].set(2.0)
        node.getPlug("input1D")[4].set(6.0)
        self.assertAlmostEqual(node.getPlug("output1D").get(), 4.0)
        node.getPlug("operation").set(2)
        self.assertAlmostEqual(node.getPlug("output1D").get(), -4.0)
        weighted = mlib.createNode("blendWeighted")
        weighted.getPlug("input")[0].set(2.0)
        weighted.getPlug("weight")[0].set(0.5)
        weighted.getPlug("input")[1].set(4.0)
        weighted.getPlug("weight")[1].set(0.25)
        self.assertAlmostEqual(weighted.getPlug("output").get(), 2.0)

    def test_double_linear(self):
        """addDoubleLinear/multDoubleLinear(2026以降はaddDL/multDL)の計算。"""
        add = mlib.createNode("addDoubleLinear")
        add.getPlug("input1").set(1.5)
        add.getPlug("input2").set(2.0)
        self.assertAlmostEqual(add.getPlug("output").get(), 3.5)
        mult = mlib.createNode("multDoubleLinear")
        mult.getPlug("input1").set(1.5)
        mult.getPlug("input2").set(2.0)
        self.assertAlmostEqual(mult.getPlug("output").get(), 3.0)

    def test_plain_node_undo(self):
        """Plug.setの通常更新は1回のUndoで戻る。"""
        node = mlib.createNode("multiplyDivide")
        node.getPlug("input1").set((7, 8, 9))
        cmds.undo()
        self.assertEqual(tuple(node.getPlug("input1").get()), (0.0, 0.0, 0.0))
        cmds.redo()
        self.assertEqual(tuple(node.getPlug("input1").get()), (7.0, 8.0, 9.0))
        self.assertTrue(math.isfinite(node.getPlug("outputX").get()))


if __name__ == "__main__":
    unittest.main()
