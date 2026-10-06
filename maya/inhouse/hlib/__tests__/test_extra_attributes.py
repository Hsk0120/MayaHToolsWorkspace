"""ユーザー定義アトリビュートの追加・列挙・型付きPlugを検証する。"""
import sys
import unittest
from unittest.mock import patch
import maya.cmds as cmds
import hlib
hlib.reload()


class ExtraAttributesTest(unittest.TestCase):
    """専用ノードのアトリビュートのみ操作する。"""

    def setUp(self):
        self.node = hlib.createNode("transform")

    def tearDown(self):
        cmds.delete(self.node.getFullName())

    def test_types_values_and_list(self):
        cases = [("double", "DoublePlug", 1.5), ("float", "FloatPlug", 2.5),
                 ("long", "LongPlug", 3), ("short", "ShortPlug", 4),
                 ("bool", "BoolPlug", True), ("doubleAngle", "DoubleAnglePlug", 35),
                 ("doubleLinear", "DoubleLinearPlug", 7), ("time", "TimePlug", 10)]
        for index, (kind, class_name, value) in enumerate(cases):
            plug = self.node.addAttr("extra%d" % index, at=kind, keyable=True)
            self.assertEqual(type(plug).__name__, class_name)
            plug.set(value)
            self.assertAlmostEqual(plug.get(), value)
        string = self.node.addAttr("textValue", dataType="string")
        self.assertIsInstance(string, hlib.plugs.StringPlug)
        string.set("日本語")
        self.assertEqual(string.get(), "日本語")
        enum = self.node.addAttr("mode", attributeType="enum", enumName="off:on", defaultValue=1)
        self.assertIsInstance(enum, hlib.plugs.EnumPlug)
        self.assertEqual(enum.getEnumName(), "on")
        self.assertEqual(enum.getEnumValue("off"), 0)
        message = self.node.addAttr("link", attributeType="message")
        self.assertIsInstance(message, hlib.plugs.MessagePlug)
        self.node.getPlug("message").connectTo(message)
        self.assertEqual(message.getSourceWithConversion(), self.node.getPlug("message"))
        self.assertEqual(len(self.node.getExtraAttrs()), len(cases) + 3)
        self.assertNotIn(self.node.getPlug("translate"), self.node.getExtraAttrs())

    def test_compound_array_and_undo(self):
        compound = self.node.addAttr("vectorValue", attributeType="double3")
        self.assertIsInstance(compound, hlib.plugs.Double3Plug)
        self.assertEqual(len(self.node.getExtraAttrs()), 1)
        self.assertEqual(len(self.node.getExtraAttrs(include_children=True)), 4)
        array = self.node.addAttr("weights", attributeType="double", multi=True)
        self.assertIsInstance(array, hlib.plugs.ArrayPlug)
        self.assertIsInstance(array.getElement(0, create=True), hlib.plugs.DoublePlug)
        self.node.addAttr("undoValue", attributeType="long")
        cmds.undo()
        self.assertFalse(self.node.hasAttr("undoValue"))
        with self.assertRaises(TypeError):
            self.node.addAttr("duplicateFlags", attributeType="double", at="double")

    def test_api_order_children_and_live_changes(self):
        """定義順・子・改名・削除Undoをcmds照会なしで反映する。"""
        self.node.addAttr("first", at="double", hidden=True)
        self.node.addAttr("vector", at="double3")
        self.node.addAttr("last", dt="string")
        expected = cmds.listAttr(self.node.getFullName(), userDefined=True)
        with patch.object(cmds, "listAttr", side_effect=AssertionError("listAttr")):
            self.assertEqual(self.node.getExtraAttrNames(), ["first", "vector", "last"])
            self.assertEqual([p.getLongName() for p in self.node.getExtraAttrs(True)], expected)
        cmds.renameAttr(self.node.getFullName() + ".first", "renamed")
        cmds.deleteAttr(self.node.getFullName() + ".vector")
        self.assertEqual(self.node.getExtraAttrNames(), ["renamed", "last"])
        cmds.undo()
        # Mayaは削除Undoで定義を末尾へ再追加する。元の順序を仮定せず標準照会と比較する。
        restored = cmds.listAttr(self.node.getFullName(), userDefined=True)
        self.assertEqual(self.node.getExtraAttrNames(), [p for p in restored if p in {"renamed", "vector", "last"}])
        self.assertEqual([p.getLongName() for p in self.node.getExtraAttrs(True)], restored)
        cmds.redo()
        self.assertEqual(self.node.getExtraAttrNames(), ["renamed", "last"])

    def test_sparse_compound_array_roots_do_not_expand(self):
        """複合配列の子を解決せず、空配列・疎な配列を維持する。"""
        name = self.node.getFullName()
        cmds.addAttr(name, longName="items", attributeType="compound", numberOfChildren=1, multi=True)
        cmds.addAttr(name, longName="amount", attributeType="double", parent="items")
        self.node.addAttr("empty", at="double", multi=True)
        cmds.setAttr(name + ".items[7].amount", 2)
        undo_name = cmds.undoInfo(query=True, undoName=True)
        with patch.object(cmds, "listAttr", side_effect=AssertionError("listAttr")):
            self.assertEqual(self.node.getExtraAttrNames(), ["items", "empty"])
            roots = self.node.getExtraAttrs()
            self.assertTrue(all(isinstance(p, hlib.plugs.ArrayPlug) for p in roots))
            # 番号なしの複合配列の子は、通常のNode.plugと同じく公開Plugにできない。
            with self.assertRaises(RuntimeError):
                self.node.getExtraAttrs(include_children=True)
        self.assertEqual(cmds.getAttr(name + ".items", multiIndices=True), [7])
        self.assertIsNone(cmds.getAttr(name + ".empty", multiIndices=True))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)

    def test_nested_compound_order(self):
        """入れ子の複合定義でもMayaの列挙順と型を保持する。"""
        name = self.node.getFullName()
        cmds.addAttr(name, longName="outer", attributeType="compound", numberOfChildren=2)
        cmds.addAttr(name, longName="inner", attributeType="double3", parent="outer")
        for axis in "XYZ":
            cmds.addAttr(name, longName="inner" + axis, attributeType="double", parent="inner")
        cmds.addAttr(name, longName="enabled", attributeType="bool", parent="outer")
        expected = [self.node.getPlug(p) for p in cmds.listAttr(name, userDefined=True)]
        self.assertEqual(self.node.getExtraAttrs(True), expected)
        self.assertEqual(self.node.getExtraAttrNames(), ["outer"])

    def test_invalid_node_and_include_children(self):
        """無効入力をAPIに渡す前に拒否する。"""
        with self.assertRaises(TypeError):
            self.node.getExtraAttrs(include_children=1)
        deleted = hlib.createNode("network")
        cmds.delete(deleted.getFullName())
        for method in (deleted.getExtraAttrNames, deleted.getExtraAttrs):
            with self.assertRaises(RuntimeError):
                method()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
