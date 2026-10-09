"""Namespaceの作成先・返却・Maya標準の名前解決を実Mayaで検証する。"""
import unittest
import uuid

from maya import cmds
import hlib


class NamespaceWorkflowsTest(unittest.TestCase):
    def setUp(self):
        self.previous = hlib.common.Namespace.getCurrent()
        self.relative_names = cmds.namespace(query=True, relativeNames=True)
        self.name = "hlibNamespaceWorkflow_" + uuid.uuid4().hex
        self.root = hlib.common.Namespace.create(":" + self.name)
        self.top_level = [self.root.name]

    def tearDown(self):
        cmds.namespace(relativeNames=self.relative_names)
        self.previous.setCurrent()
        for name in reversed(self.top_level):
            if cmds.namespace(exists=name):
                cmds.namespace(removeNamespace=name, deleteNamespaceContent=True)

    def test_parent_reference_and_root_collision_use_child_full_name(self):
        """ルートの同名を取り違えず、返却から続けて利用できる。"""
        leaf = self.name + "Leaf"
        global_namespace = hlib.common.Namespace.create(":" + leaf)
        self.top_level.append(global_namespace.name)
        child = hlib.common.Namespace.create(leaf, parent=self.root)
        self.assertEqual(child.name, self.root.name + ":" + leaf)
        self.assertTrue(child.exists())
        self.assertEqual(hlib.common.Namespace.create(leaf, parent=self.root), child)
        with child.asCurrent():
            self.assertEqual(hlib.common.Namespace.getCurrent(), child)

    def test_relative_multi_level_name_and_relative_parent_use_current_namespace(self):
        """相対多段名を指定親へ、相対親をカレント名前空間へ解決する。"""
        with self.root.asCurrent():
            child = hlib.common.Namespace.create("group:child", parent="parent")
            self.assertEqual(child.name, self.root.name + ":parent:group:child")
            self.assertTrue(child.exists())
            self.assertEqual(hlib.common.Namespace.getCurrent(), self.root)
        self.assertEqual(hlib.common.Namespace.getCurrent(), self.previous)

    def test_absolute_and_namespace_inputs_ignore_parent(self):
        """絶対名と参照の保持名を別parentの配下へ移さない。"""
        namespace_type = hlib.common.Namespace
        for name in (self.root.name + ":absolute", namespace_type(self.root.name + ":reference")):
            with self.subTest(name=str(name)):
                result = namespace_type.create(name, parent=self.root.name + ":ignored")
                self.assertEqual(result.name, str(namespace_type(name)))
                self.assertTrue(result.exists())
        self.assertFalse(namespace_type(self.root.name + ":ignored").exists())

    def test_default_parent_is_root_even_in_another_current_namespace(self):
        """既定の明示親 : をカレント名前空間へ変更しない。"""
        with self.root.asCurrent():
            created = hlib.common.Namespace.create(self.name + "Default")
            self.top_level.append(created.name)
            self.assertEqual(created.name, ":" + self.name + "Default")
            self.assertTrue(created.exists())

    def test_recursive_create_undo_redo(self):
        """親の再帰作成を含め一回のUndoで戻す。"""
        child = hlib.common.Namespace.create("branch:leaf", parent=self.root)
        cmds.undo()
        self.assertFalse(child.exists())
        self.assertFalse(hlib.common.Namespace(self.root.name + ":branch").exists())
        cmds.redo()
        self.assertTrue(child.exists())

    def test_relative_name_display_mode_does_not_change_returned_identity(self):
        """relativeNames表示中も絶対参照を返す。"""
        with self.root.asCurrent():
            cmds.namespace(relativeNames=True)
            child = hlib.common.Namespace.create("displayChild", parent=self.root)
            self.assertEqual(child.name, self.root.name + ":displayChild")
            self.assertTrue(child.exists())
            root_child = hlib.common.Namespace.create(self.name + "DisplayRoot")
            self.top_level.append(root_child.name)
            self.assertEqual(root_child.name, ":" + self.name + "DisplayRoot")
            self.assertTrue(root_child.exists())


if __name__ == "__main__":
    unittest.main()
