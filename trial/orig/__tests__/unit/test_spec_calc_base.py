"""計算・ユーティリティノードの型登録の仕様を固定する。

担当A。計算ノード型とラッパークラスの対応、専用クラスを持たない計算ノード
(composeMatrix・multMatrix等)が Node 派生の自動生成クラスになり、通常のPlugで扱えることを確かめる。
"""

import math
import unittest

import maya.cmds as cmds
import mlib


# 計算・ユーティリティノードのMaya型と公開クラス・直接の基底クラス名。
_TYPE_TABLE = (
    ("blendColors", "BlendColors", "Node"),
    ("blendWeighted", "BlendWeighted", "Node"),
    ("clamp", "Clamp", "Node"),
    ("condition", "Condition", "Node"),
    ("file", "File", "Texture2d"),
    ("multiplyDivide", "MultiplyDivide", "ShadingDependNode"),
    ("place2dTexture", "Place2dTexture", "ShadingDependNode"),
    ("plusMinusAverage", "PlusMinusAverage", "ShadingDependNode"),
    ("remapValue", "RemapValue", "Node"),
    ("reverse", "Reverse", "Node"),
    ("setRange", "SetRange", "Node"),
    ("unitConversion", "UnitConversion", "Node"),
)

# 専用クラスを持たない計算ノード。登録表に無く、自動生成クラスで返る。
_GENERATED_TYPES = (
    "aimMatrix", "angleBetween", "blendMatrix", "composeMatrix", "curveInfo", "decomposeMatrix",
    "distanceBetween", "fourByFourMatrix", "inverseMatrix", "multMatrix", "pairBlend", "pickMatrix",
    "pointOnCurveInfo", "pointOnSurfaceInfo", "vectorProduct",
)


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

    def test_unregistered_calculation_types_are_generated(self):
        """専用クラスの無い計算ノードは公開名・登録表に無く、Node派生の生成クラスで返る。"""
        for kind in _GENERATED_TYPES:
            with self.subTest(kind=kind):
                name = kind[0].upper() + kind[1:]
                self.assertNotIn(name, mlib.nodes.__all__)
                self.assertNotIn(kind, mlib.nodes._WRAPPER_CLASSES)
                node = mlib.createNode(kind)
                cls = type(node)
                self.assertEqual(cls.__name__, name)
                self.assertTrue(issubclass(cls, mlib.nodes.Node))
                self.assertIs(mlib.nodes.__getattr__(name), cls)
                self.assertEqual(node.getType(), kind)
                self.assertTrue(node.hasAttr("message"))


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

    def test_multi_inputs(self):
        """plusMinusAverage・blendWeightedのマルチアトリビュートの入力。"""
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
