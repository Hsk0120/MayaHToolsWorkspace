"""ユーザー定義アトリビュートの追加・列挙・型付きPlugを検証する。"""
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
