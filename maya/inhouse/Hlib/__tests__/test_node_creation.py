"""Hlib のノード作成APIを検証するMaya内テスト。"""

import sys
import unittest
import importlib

import maya.cmds as cmds

import Hlib
Hlib.reload()
hlib_cmds = importlib.import_module("Hlib.cmds")
from Hlib.nodes import Node
from Hlib.nodes.joint import Joint


class NodeCreationTest(unittest.TestCase):
    """Node.create と Hlib.cmds.create_node の基本動作を検証する。"""

    def setUp(self):
        self.previous_namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        cmds.namespace(set=":")

    def tearDown(self):
        for name in ("hlibCreateJoint", "hlibCreateTransform"):
            if cmds.objExists(name):
                cmds.delete(name)
        cmds.namespace(set=self.previous_namespace)

    def test_create_node_returns_registered_wrapper(self):
        joint = hlib_cmds.create_node(type="joint", name="hlibCreateJoint")

        self.assertIsInstance(joint, Joint)
        self.assertEqual(joint.name(), "hlibCreateJoint")
        self.assertEqual(joint.type(), "joint")

    def test_cmds_package_reexports_node_commands(self):
        self.assertTrue(callable(hlib_cmds.create_node))
        self.assertTrue(callable(hlib_cmds.ls))
        self.assertIs(Hlib.create_node, hlib_cmds.create_node)
        self.assertIs(Hlib.ls, hlib_cmds.ls)
        transform = hlib_cmds.create_node(type="transform", name="hlibCreateTransform")

        self.assertIsInstance(transform, Node)
        self.assertEqual(transform.name(), "hlibCreateTransform")

    def test_node_create_forwards_create_node_flags(self):
        transform = Node.create(type="transform", name="hlibCreateTransform")

        self.assertIsInstance(transform, Node)
        self.assertEqual(transform.name(), "hlibCreateTransform")
        self.assertEqual(transform.type(), "transform")

    def test_create_node_rejects_invalid_node_type(self):
        with self.assertRaises(ValueError):
            hlib_cmds.create_node(type="")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])