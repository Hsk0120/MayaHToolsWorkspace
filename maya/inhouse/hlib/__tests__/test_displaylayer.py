"""hlib.nodes.displayLayer の DisplayLayer ラッパーを検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.nodes import Node
from hlib.nodes.displayLayer import DisplayLayer


class DisplayLayerTest(unittest.TestCase):
    """メンバー追加・除外・カレントレイヤー切り替えを検証する。"""

    def setUp(self):
        self.created = []
        self.a = Node.create(type="transform", name="hlibDisplayLayerA")
        self.b = Node.create(type="transform", name="hlibDisplayLayerB")
        self.created.extend([self.a.getName(), self.b.getName()])
        layer_name = cmds.createDisplayLayer(name="hlibDisplayLayerTest", empty=True)
        self.created.append(layer_name)
        self.layer = Node(layer_name)
        self.previous_current = cmds.editDisplayLayerGlobals(query=True, currentDisplayLayer=True)

    def tearDown(self):
        if cmds.objExists("defaultLayer"):
            cmds.editDisplayLayerGlobals(currentDisplayLayer=self.previous_current or "defaultLayer")
        for node in reversed(self.created):
            if cmds.objExists(node):
                cmds.delete(node)

    def test_node_resolves_to_display_layer_wrapper(self):
        self.assertIsInstance(self.layer, DisplayLayer)

    def test_members_empty_by_default(self):
        self.assertEqual(self.layer.getMembers(), [])

    def test_add_members_and_members(self):
        result = self.layer.addMembers(self.a, self.b)
        self.assertIs(result, self.layer)
        self.assertEqual(
            {member.getName() for member in self.layer.getMembers()},
            {self.a.getName(), self.b.getName()},
        )

    def test_remove_members_moves_back_to_default_layer(self):
        self.layer.addMembers(self.a, self.b)
        result = self.layer.removeMembers(self.a)
        self.assertIs(result, self.layer)
        self.assertEqual([member.getName() for member in self.layer.getMembers()], [self.b.getName()])
        self.assertIn(self.a.getName(), cmds.editDisplayLayerMembers("defaultLayer", query=True) or [])

    def test_set_current(self):
        self.layer.setCurrent()
        self.assertEqual(cmds.editDisplayLayerGlobals(query=True, currentDisplayLayer=True), self.layer.getName())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
