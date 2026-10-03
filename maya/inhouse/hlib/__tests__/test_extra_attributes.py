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
        cmds.delete(self.node.fullName())

    def test_types_values_and_list(self):
        cases = [("double", "DoublePlug", 1.5), ("float", "FloatPlug", 2.5),
                 ("long", "LongPlug", 3), ("short", "ShortPlug", 4),
                 ("bool", "BoolPlug", True), ("doubleAngle", "DoubleAnglePlug", 35),
                 ("doubleLinear", "DoubleLinearPlug", 7), ("time", "TimePlug", 10)]
        for index, (kind, class_name, value) in enumerate(cases):
            plug = self.node.addAttribute("extra%d" % index, at=kind, keyable=True)
            self.assertEqual(type(plug).__name__, class_name)
            plug.set(value)
            self.assertAlmostEqual(plug.get(), value)
        string = self.node.addAttribute("textValue", dataType="string")
        self.assertIsInstance(string, hlib.plugs.StringPlug)
        string.set("日本語")
        self.assertEqual(string.get(), "日本語")
        enum = self.node.addAttribute("mode", attributeType="enum", enumName="off:on", defaultValue=1)
        self.assertIsInstance(enum, hlib.plugs.EnumPlug)
        self.assertEqual(enum.enumName(), "on")
        self.assertEqual(enum.enumValue("off"), 0)
        message = self.node.addAttribute("link", attributeType="message")
        self.assertIsInstance(message, hlib.plugs.MessagePlug)
        self.node.plug("message").connect(message)
        self.assertEqual(message.source(), self.node.plug("message"))
        self.assertEqual(len(self.node.getExtraAttributes()), len(cases) + 3)
        self.assertNotIn(self.node.plug("translate"), self.node.getExtraAttributes())

    def test_compound_array_and_undo(self):
        compound = self.node.addAttribute("vectorValue", attributeType="double3")
        self.assertIsInstance(compound, hlib.plugs.Double3Plug)
        self.assertEqual(len(self.node.getExtraAttributes()), 1)
        self.assertEqual(len(self.node.getExtraAttributes(include_children=True)), 4)
        array = self.node.addAttribute("weights", attributeType="double", multi=True)
        self.assertIsInstance(array, hlib.plugs.ArrayPlug)
        self.assertIsInstance(array.element(0, create=True), hlib.plugs.DoublePlug)
        self.node.addAttribute("undoValue", attributeType="long")
        cmds.undo()
        self.assertFalse(self.node.hasAttribute("undoValue"))
        with self.assertRaises(TypeError):
            self.node.addAttribute("duplicateFlags", attributeType="double", at="double")

    def test_api_order_children_and_live_changes(self):
        """定義順・子・改名・削除Undoをcmds照会なしで反映する。"""
        self.node.addAttribute("first", at="double", hidden=True)
        self.node.addAttribute("vector", at="double3")
        self.node.addAttribute("last", dt="string")
        expected = cmds.listAttr(self.node.fullName(), userDefined=True)
        with patch.object(cmds, "listAttr", side_effect=AssertionError("listAttr")):
            self.assertEqual(self.node.userAttributeNames(), ["first", "vector", "last"])
            self.assertEqual([p.attributeName() for p in self.node.getExtraAttributes(True)], expected)
        cmds.renameAttr(self.node.fullName() + ".first", "renamed")
        cmds.deleteAttr(self.node.fullName() + ".vector")
        self.assertEqual(self.node.userAttributeNames(), ["renamed", "last"])
        cmds.undo()
        # Mayaは削除Undoで定義を末尾へ再追加する。元の順序を仮定せず標準照会と比較する。
        restored = cmds.listAttr(self.node.fullName(), userDefined=True)
        self.assertEqual(self.node.userAttributeNames(), [p for p in restored if p in {"renamed", "vector", "last"}])
        self.assertEqual([p.attributeName() for p in self.node.getExtraAttributes(True)], restored)
        cmds.redo()
        self.assertEqual(self.node.userAttributeNames(), ["renamed", "last"])

    def test_sparse_compound_array_roots_do_not_expand(self):
        """複合配列の子を解決せず、空配列・疎な配列を維持する。"""
        name = self.node.fullName()
        cmds.addAttr(name, longName="items", attributeType="compound", numberOfChildren=1, multi=True)
        cmds.addAttr(name, longName="amount", attributeType="double", parent="items")
        self.node.addAttribute("empty", at="double", multi=True)
        cmds.setAttr(name + ".items[7].amount", 2)
        undo_name = cmds.undoInfo(query=True, undoName=True)
        with patch.object(cmds, "listAttr", side_effect=AssertionError("listAttr")):
            self.assertEqual(self.node.userAttributeNames(), ["items", "empty"])
            roots = self.node.getExtraAttributes()
            self.assertTrue(all(isinstance(p, hlib.plugs.ArrayPlug) for p in roots))
            # 番号なしの複合配列の子は、通常のNode.plugと同じく公開Plugにできない。
            with self.assertRaises(RuntimeError):
                self.node.getExtraAttributes(include_children=True)
        self.assertEqual(cmds.getAttr(name + ".items", multiIndices=True), [7])
        self.assertIsNone(cmds.getAttr(name + ".empty", multiIndices=True))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)

    def test_nested_compound_order(self):
        """入れ子の複合定義でもMayaの列挙順と型を保持する。"""
        name = self.node.fullName()
        cmds.addAttr(name, longName="outer", attributeType="compound", numberOfChildren=2)
        cmds.addAttr(name, longName="inner", attributeType="double3", parent="outer")
        for axis in "XYZ":
            cmds.addAttr(name, longName="inner" + axis, attributeType="double", parent="inner")
        cmds.addAttr(name, longName="enabled", attributeType="bool", parent="outer")
        expected = [self.node.plug(p) for p in cmds.listAttr(name, userDefined=True)]
        self.assertEqual(self.node.getExtraAttributes(True), expected)
        self.assertEqual(self.node.userAttributeNames(), ["outer"])

    def test_invalid_node_and_include_children(self):
        """無効入力をAPIに渡す前に拒否する。"""
        with self.assertRaises(TypeError):
            self.node.getExtraAttributes(include_children=1)
        deleted = hlib.createNode("network")
        cmds.delete(deleted.fullName())
        for method in (deleted.userAttributeNames, deleted.getExtraAttributes):
            with self.assertRaises(RuntimeError):
                method()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
