"""Hlib Node/DAG APIを検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import Hlib
Hlib.reload_all()
from Hlib import Namespace
from Hlib.nodes import Node


class NodeApiTest(unittest.TestCase):
    """cymel相当の基本Node/DAG APIを検証する。"""

    namespace = ":hlibNodeApiTest"

    def setUp(self):
        self.created = []
        if cmds.namespace(exists=self.namespace):
            cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.namespace(add=self.namespace)

    def tearDown(self):
        for node in reversed(self.created):
            if cmds.objExists(node):
                cmds.delete(node)
        if cmds.namespace(exists=self.namespace):
            cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def create_transform(self, name):
        node = Node.create(type="transform", name=name)
        self.created.append(node.name())
        return node

    def test_dag_paths_and_shapes(self):
        transform = self.create_transform("hlibNodeApiTransform")
        shape_name = cmds.createNode("mesh", parent=transform.name())
        self.created.append(shape_name)
        shape = transform.shape()

        self.assertEqual(transform.path(), transform.name())
        self.assertEqual(transform.path(full=True), "|" + transform.name())
        self.assertEqual(transform.partial_path(), transform.name())
        self.assertEqual(transform.full_path(), "|" + transform.name())
        self.assertTrue(transform.is_root())
        self.assertEqual(len(transform.shapes()), 1)
        self.assertEqual(shape.transform().name(), transform.name())
        self.assertTrue(shape.full_path().endswith("|" + shape_name))

    def test_rename_namespace_and_add_attr(self):
        transform = self.create_transform("hlibNodeApiRename")
        renamed = transform.rename("hlibNodeApiRenamed")
        self.assertEqual(renamed, "hlibNodeApiRenamed")
        self.assertEqual(transform.name(), "hlibNodeApiRenamed")

        namespaced = transform.set_namespace(self.namespace)
        self.assertIn("hlibNodeApiRenamed", namespaced)
        self.assertEqual(transform.node_name(remove_namespace=True), "hlibNodeApiRenamed")
        self.assertEqual(transform.namespace(), Namespace(self.namespace))

        missing_namespace = ":hlibNodeApiMissing:child"
        transform.set_namespace(missing_namespace)
        self.assertTrue(Namespace(missing_namespace).exists())
        self.assertEqual(transform.namespace(), Namespace(missing_namespace))

        plug = transform.add_attr(
            "hlibNodeApiValue",
            attribute_type="double",
            default_value=1.5,
        )
        self.assertEqual(plug.name, "hlibNodeApiValue")
        self.assertEqual(plug.get(), 1.5)

    def test_parent_and_connections(self):
        parent = self.create_transform("hlibNodeApiParent")
        child = self.create_transform("hlibNodeApiChild")
        source = self.create_transform("hlibNodeApiSource")
        target = self.create_transform("hlibNodeApiTarget")

        child.set_parent(parent)
        self.assertEqual(child.parent_node().name(), parent.name())
        child.set_parent()
        self.assertIsNone(child.parent_node())

        source.plug("translateX").connect(target.plug("translateX"))
        self.assertEqual([plug.full_name for plug in target.inputs()], [source.plug("translateX").full_name])
        self.assertEqual([plug.full_name for plug in source.outputs()], [target.plug("translateX").full_name])
        self.assertEqual(len(source.connections()), 1)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
