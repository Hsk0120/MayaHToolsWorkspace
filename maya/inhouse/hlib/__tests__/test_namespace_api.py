"""hlib Namespace APIを検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.common import Namespace
from hlib.nodes import Node


class NamespaceApiTest(unittest.TestCase):
    """NamespaceとNodeの相互運用を検証する。"""

    root_name = ":hlibNamespaceTest"

    def _cleanup(self):
        names = cmds.namespaceInfo(
            listOnlyNamespaces=True,
            recurse=True,
            absoluteName=True,
        ) or []
        for name in sorted(names, key=lambda item: item.count(":"), reverse=True):
            if (
                name == self.root_name
                or name.startswith(self.root_name + ":")
                or name in (":hlibNamespaceDestination", ":child", ":renamed")
            ):
                if cmds.namespace(exists=name):
                    cmds.namespace(removeNamespace=name, deleteNamespaceContent=True)
        if cmds.namespace(exists=self.root_name):
            cmds.namespace(removeNamespace=self.root_name, deleteNamespaceContent=True)

    def setUp(self):
        self._cleanup()
        self.root = Namespace.create(self.root_name)

    def tearDown(self):
        self._cleanup()

    def test_namespace_hierarchy(self):
        child = Namespace.create(f"{self.root_name}:child")
        self.assertTrue(self.root.exists())
        self.assertEqual(str(child), self.root_name + ":child")
        self.assertEqual(child.getParent(), self.root)
        self.assertIn(child, self.root.getChildren())

    def test_nodes_and_node_namespace(self):
        node = Node.create(type="transform", name="namespaceNode")
        node.setNamespace(self.root)
        self.assertEqual(node.getNamespace(), self.root)
        self.assertIn(node.getName(), [item.getName() for item in self.root.getNodes()])
        cmds.delete(node.getName())

    def test_nodes_recurse_includes_child_namespace_nodes(self):
        child = Namespace.create(f"{self.root_name}:child")
        top_node = Node.create(type="transform", name="hlibNamespaceRecurseTop")
        top_node.setNamespace(self.root)
        child_node = Node.create(type="transform", name="hlibNamespaceRecurseChild")
        child_node.setNamespace(child)

        direct_names = [item.getName() for item in self.root.getNodes()]
        self.assertIn(top_node.getName(), direct_names)
        self.assertNotIn(child_node.getName(), direct_names)

        recursive_names = [item.getName() for item in self.root.getNodes(recurse=True)]
        self.assertIn(top_node.getName(), recursive_names)
        self.assertIn(child_node.getName(), recursive_names)

        cmds.delete(top_node.getName(), child_node.getName())

    def test_children_returns_only_direct_child_namespaces(self):
        child = Namespace.create(f"{self.root_name}:child")
        Namespace.create(f"{self.root_name}:child:grandchild")

        children = self.root.getChildren()
        self.assertEqual(children, [child])

    def test_exists_is_false_for_unknown_namespace(self):
        self.assertFalse(Namespace(":hlibNamespaceDoesNotExist").exists())

    def test_current_set_as_current_and_as_current_context(self):
        root_current = Namespace.getCurrent()
        try:
            self.root.setCurrent()
            self.assertEqual(Namespace.getCurrent(), self.root)

            child = Namespace.create(f"{self.root_name}:child")
            with child.asCurrent():
                self.assertEqual(Namespace.getCurrent(), child)
            self.assertEqual(Namespace.getCurrent(), self.root)

            try:
                with child.asCurrent():
                    raise RuntimeError("boom")
            except RuntimeError:
                pass
            self.assertEqual(Namespace.getCurrent(), self.root)
        finally:
            if root_current.exists():
                root_current.setCurrent()

    def test_set_as_current_raises_for_missing_namespace(self):
        try:
            Namespace(":hlibNamespaceDoesNotExist").setCurrent()
        except RuntimeError:
            pass
        else:
            raise AssertionError("setCurrent on a missing namespace should raise RuntimeError")

    def test_rename_move_and_remove(self):
        child = Namespace.create(f"{self.root_name}:child")
        destination = Namespace.create(":hlibNamespaceDestination")
        try:
            child.rename("renamed")
            self.assertTrue(Namespace(f"{self.root_name}:renamed").exists())
            child.move(destination)
            moved = Namespace(":hlibNamespaceDestination:renamed")
            self.assertTrue(moved.exists())
            moved.remove()
            self.assertFalse(moved.exists())
        finally:
            if destination.exists():
                cmds.namespace(removeNamespace=destination.name, deleteNamespaceContent=True)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
