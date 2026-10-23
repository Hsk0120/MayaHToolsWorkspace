"""演算型の登録を維持し、Maya標準Plugだけで値と接続を操作する。"""

import unittest

from maya import cmds
import mlib


_CALCULATION_TYPES = (
    ("addDL", "AddDL"), ("addDoubleLinear", "AddDoubleLinear"),
    ("multDL", "MultDL"), ("multDoubleLinear", "MultDoubleLinear"),
    ("blendColors", "BlendColors"), ("blendWeighted", "BlendWeighted"),
    ("clamp", "Clamp"), ("condition", "Condition"),
    ("multiplyDivide", "MultiplyDivide"), ("plusMinusAverage", "PlusMinusAverage"),
    ("remapValue", "RemapValue"), ("reverse", "Reverse"),
    ("setRange", "SetRange"), ("unitConversion", "UnitConversion"),
)
_REMOVED_METHODS = {
    "getInputPlug", "setInput", "connectInput", "getResult", "getColorPlug", "getColor",
    "setColor", "connectColor", "setBlender", "getInputIndices", "getInputPlugs",
    "getWeights", "getWeight", "setWeight", "getRange", "setRange", "getOperation",
    "setOperation", "setTrueValue", "setFalseValue", "removeInput", "getOutputPlug",
    "getRampPoints", "setRampPoint", "removeRampPoint", "setFactor",
}


class ConsolidatedCalculationTests(unittest.TestCase):
    """空シーンで型選択・PlugのUndo/fast・疎配列を確認する。"""

    def setUp(self):
        """専用シーンと通常Undo、距離cmを準備する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm")

    def test_calculation_types_keep_explicit_registration_and_node_base(self):
        """14型の明示登録と継承を保ち、終了した専用defを再公開しない。"""
        for node_type, class_name in _CALCULATION_TYPES:
            with self.subTest(node_type=node_type):
                cls = getattr(mlib.nodes, class_name)
                node = mlib.createNode(node_type)
                # MayaはaddDoubleLinear等を新しい派生nodeTypeへ正規化する版がある。
                actual_type = cmds.nodeType(node.getFullName())
                registered = mlib.nodes.Node._registry.lookup(actual_type)
                if registered is None:
                    # 旧Mayaで未対応型がunknown等になった場合も、既存のNode選択を保つ。
                    self.assertNotIn(actual_type, mlib.nodes._WRAPPER_CLASSES)
                    self.assertIs(type(node), mlib.nodes.Node)
                expected = registered if registered is not None else mlib.nodes.Node
                self.assertIs(type(node), expected)
                self.assertIs(type(mlib.getNode(node.getFullName())), expected)
                self.assertIs(mlib.nodes._WRAPPER_CLASSES[node_type], cls)
                self.assertTrue(issubclass(cls, mlib.nodes.Node))
                self.assertFalse(_REMOVED_METHODS.intersection(cls.__dict__))
                self.assertIs(node.getPlug("message").getNode(), node)

    def test_standard_plugs_keep_undo_and_fast_edits(self):
        """通常の単一Plug更新はUndoでき、fastはUndo設定と履歴を変えない。"""
        node = mlib.createNode("addDoubleLinear")
        node.getPlug("input1").set(2)
        node.getPlug("input2").set(3)
        self.assertAlmostEqual(node.getPlug("output").get(), 5)
        cmds.undo()
        self.assertAlmostEqual(node.getPlug("output").get(), 2)
        cmds.redo()
        self.assertAlmostEqual(node.getPlug("output").get(), 5)
        cmds.flushUndo()
        self.assertIs(node.getPlug("input2").set(7, fast=True).getNode(), node)
        self.assertAlmostEqual(node.getPlug("output").get(), 9)
        self.assertTrue(cmds.undoInfo(query=True, state=True))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_standard_array_plugs_keep_logical_indices_and_connections(self):
        """疎配列はArrayPlugで照会し、接続を一回のUndoで解除できる。"""
        node = mlib.createNode("plusMinusAverage")
        inputs = node.getPlug("input1D")
        inputs[3].set(2)
        inputs[8].set(5)
        self.assertEqual(inputs.getIndices(), [3, 8])
        with self.assertRaises(IndexError):
            inputs.getElement(4)
        self.assertEqual(inputs.getIndices(), [3, 8])
        self.assertAlmostEqual(node.getPlug("output1D").get(), 7)
        node.getPlug("operation").set(2)
        self.assertAlmostEqual(node.getPlug("output1D").get(), -3)
        source = mlib.createNode("network").addAttr("amount", defaultValue=11)
        source.connectTo(inputs.getElement(3))
        self.assertEqual(inputs.getElement(3).getSource(skipConversionNodes=False), source)
        self.assertAlmostEqual(node.getPlug("output1D").get(), 6)
        cmds.undo()
        self.assertIsNone(inputs.getElement(3).getSource(skipConversionNodes=False))
        self.assertAlmostEqual(node.getPlug("output1D").get(), -3)

    def test_enum_and_numeric_compounds_use_native_attribute_values(self):
        """enumはMayaの番号、演算用RGBは数値複合Plugとして扱う。"""
        condition = mlib.createNode("condition")
        for name, value in (("firstTerm", 1), ("secondTerm", 2), ("operation", 4),
                            ("colorIfTrue", (.2, .4, .6)), ("colorIfFalse", (1, 0, 0))):
            condition.getPlug(name).set(value)
        self.assertEqual(condition.getPlug("operation").get(), 4)
        for actual, expected in zip(condition.getPlug("outColor").get(), (.2, .4, .6)):
            self.assertAlmostEqual(actual, expected, places=6)
        blend = mlib.createNode("blendColors")
        blend.getPlug("color1").set((1, 0, 0))
        blend.getPlug("color2").set((0, 0, 1))
        blend.getPlug("blender").set(.25)
        self.assertEqual(tuple(blend.getPlug("output").get()), (.25, 0, .75))


if __name__ == "__main__":
    unittest.main()
