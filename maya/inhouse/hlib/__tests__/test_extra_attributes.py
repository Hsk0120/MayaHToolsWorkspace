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
        cmds.delete(self.node.full_name())

    def test_types_values_and_list(self):
        cases = [("double", "DoublePlug", 1.5), ("float", "FloatPlug", 2.5),
                 ("long", "LongPlug", 3), ("short", "ShortPlug", 4),
                 ("bool", "BoolPlug", True), ("doubleAngle", "DoubleAnglePlug", 35),
                 ("doubleLinear", "DoubleLinearPlug", 7), ("time", "TimePlug", 10)]
        for index, (kind, class_name, value) in enumerate(cases):
            plug = self.node.add_attribute("extra%d" % index, at=kind, keyable=True)
            self.assertEqual(type(plug).__name__, class_name)
            plug.set(value)
            self.assertAlmostEqual(plug.get(), value)
        string = self.node.add_attribute("textValue", data_type="string")
        self.assertIsInstance(string, hlib.plugs.StringPlug)
        string.set("日本語")
        self.assertEqual(string.get(), "日本語")
        enum = self.node.add_attribute("mode", attribute_type="enum", enumName="off:on", default_value=1)
        self.assertIsInstance(enum, hlib.plugs.EnumPlug)
        self.assertEqual(enum.enum_name(), "on")
        self.assertEqual(enum.enum_value("off"), 0)
        message = self.node.add_attribute("link", attribute_type="message")
        self.assertIsInstance(message, hlib.plugs.MessagePlug)
        self.node.plug("message").connect(message)
        self.assertEqual(message.source(), self.node.plug("message"))
        self.assertEqual(len(self.node.get_extra_attributes()), len(cases) + 3)
        self.assertNotIn(self.node.plug("translate"), self.node.get_extra_attributes())

    def test_compound_array_and_undo(self):
        compound = self.node.add_attribute("vectorValue", attribute_type="double3")
        self.assertIsInstance(compound, hlib.plugs.Double3Plug)
        self.assertEqual(len(self.node.get_extra_attributes()), 1)
        self.assertEqual(len(self.node.get_extra_attributes(include_children=True)), 4)
        array = self.node.add_attribute("weights", attribute_type="double", multi=True)
        self.assertIsInstance(array, hlib.plugs.ArrayPlug)
        self.assertIsInstance(array.element(0, create=True), hlib.plugs.DoublePlug)
        self.node.add_attribute("undoValue", attribute_type="long")
        cmds.undo()
        self.assertFalse(self.node.has_attribute("undoValue"))
        with self.assertRaises(TypeError):
            self.node.add_attribute("duplicateFlags", attribute_type="double", at="double")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
