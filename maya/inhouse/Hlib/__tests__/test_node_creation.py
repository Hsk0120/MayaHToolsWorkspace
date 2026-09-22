"""Hlib のノード作成APIを検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import Hlib
Hlib.reload_all()
from Hlib.nodes import Node
from Hlib.nodes.joint import Joint


class NodeCreationTest(unittest.TestCase):
    """Node.create と Hlib.create_node の基本動作を検証する。"""

    def tearDown(self):
        for name in ("hlibCreateJoint", "hlibCreateTransform"):
            if cmds.objExists(name):
                cmds.delete(name)

    def test_create_node_returns_registered_wrapper(self):
        joint = Hlib.create_node(type="joint", name="hlibCreateJoint")

        self.assertIsInstance(joint, Joint)
        self.assertEqual(joint.name(), "hlibCreateJoint")
        self.assertEqual(joint.type(), "joint")

    def test_node_create_forwards_create_node_flags(self):
        transform = Node.create(type="transform", name="hlibCreateTransform")

        self.assertIsInstance(transform, Node)
        self.assertEqual(transform.name(), "hlibCreateTransform")
        self.assertEqual(transform.type(), "transform")

    def test_create_node_rejects_invalid_node_type(self):
        with self.assertRaises(ValueError):
            Hlib.create_node(type="")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])