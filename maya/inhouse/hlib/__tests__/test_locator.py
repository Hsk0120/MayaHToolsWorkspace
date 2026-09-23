"""hlib.nodes.locator の Locator ラッパーを検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.maths import Translate
from hlib.nodes import Node
from hlib.nodes.locator import Locator


class LocatorTest(unittest.TestCase):
    """get_position/set_position を検証する。"""

    def setUp(self):
        self.transform = cmds.spaceLocator(name="hlibLocatorTest")[0]
        self.created = [self.transform]
        shape_name = cmds.listRelatives(self.transform, shapes=True)[0]
        self.locator = Node(shape_name)

    def tearDown(self):
        for node in reversed(self.created):
            if cmds.objExists(node):
                cmds.delete(node)

    def test_node_resolves_to_locator_wrapper(self):
        self.assertIsInstance(self.locator, Locator)

    def test_get_position_default(self):
        self.assertEqual(self.locator.get_position(), Translate(0.0, 0.0, 0.0))

    def test_set_position_round_trips(self):
        result = self.locator.set_position((1.0, 2.0, 3.0))
        self.assertIs(result, self.locator)
        self.assertEqual(self.locator.get_position(), Translate(1.0, 2.0, 3.0))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
