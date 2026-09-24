"""実ノードでの属性解決と、UI照会境界を分けて検証する。"""

import importlib
import sys
import unittest
import uuid
from unittest.mock import patch
import maya.cmds as cmds
import hlib

hlib.reload()
module = importlib.import_module("hlib.editors.channelBox")


class ChannelBoxTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibChannel_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.a = cmds.createNode("transform", name=self.ns + ":a")
        self.b = cmds.createNode("transform", name=self.ns + ":b")
        cmds.addAttr(self.a, longName="amount", attributeType="double")
        cmds.aliasAttr("customAlias", self.a + ".amount")
        self.responses = {
            "mainObjectList": [self.a, self.b],
            "selectedMainAttributes": ["tx", "customAlias"],
            "shapeObjectList": [], "selectedShapeAttributes": [],
            "historyObjectList": [self.a], "selectedHistoryAttributes": ["tx"],
            "outputObjectList": [], "selectedOutputAttributes": [],
        }

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def query(self, name, **kwargs):
        if kwargs.get("exists"):
            return name == "testChannelBox"
        for flag, value in kwargs.items():
            if flag in self.responses:
                return self.responses[flag]
        return None

    def test_section_mapping_alias_and_missing_attribute(self):
        with patch.object(module.cmds, "about", return_value=False), patch.object(module.cmds, "channelBox", side_effect=self.query):
            channel = hlib.channelBox("testChannelBox")
            self.assertEqual(len(channel.displayed_nodes()), 2)
            names = [plug.full_name for plug in channel.selected_plugs()]
            self.assertEqual(len(names), 3)
            self.assertIn(self.a + ".customAlias", names)
            cmds.setAttr(self.a + ".amount", 2.5)
            alias_plug = next(plug for plug in channel.selected_plugs() if plug.full_name.endswith(".customAlias"))
            self.assertEqual(alias_plug.get(), 2.5)
            self.assertIn(self.b + ".translateX", names)
            self.assertEqual(channel.selected_attributes(), ["tx", "customAlias"])
            with self.assertRaises(ValueError):
                channel.selected_plugs("invalid")

    def test_no_selection_and_gui_unavailable(self):
        with patch.object(module.cmds, "about", return_value=True):
            with self.assertRaises(RuntimeError):
                hlib.channelBox()
        self.responses["selectedMainAttributes"] = []
        self.responses["selectedHistoryAttributes"] = []
        with patch.object(module.cmds, "about", return_value=False), patch.object(module.cmds, "channelBox", side_effect=self.query):
            self.assertEqual(hlib.channelBox("testChannelBox").selected_plugs(), [])
            with self.assertRaises(RuntimeError):
                hlib.channelBox("missing")


@unittest.skipIf(cmds.about(batch=True), "Requires Maya GUI")
class ChannelBoxGuiTest(unittest.TestCase):
    def test_selection_and_clear_in_isolated_control(self):
        previous = hlib.captureSelection()
        node = cmds.createNode("transform", name="hlibChannelGuiTest")
        window = cmds.window()
        try:
            cmds.columnLayout()
            control = cmds.channelBox()
            cmds.showWindow(window)
            cmds.select(node)
            cmds.refresh()
            channel = hlib.channelBox(control)
            cmds.channelBox(control, edit=True, select=node + ".translateX")
            self.assertEqual([plug.full_name for plug in channel.selected_plugs()], [node + ".translateX"])
            channel.clear_selection()
            self.assertEqual(channel.selected_plugs(), [])
            self.assertEqual(cmds.ls(selection=True), [node])
        finally:
            cmds.deleteUI(window)
            cmds.delete(node)
            previous.restore()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
