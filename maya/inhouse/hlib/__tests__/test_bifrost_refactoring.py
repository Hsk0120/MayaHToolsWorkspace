"""VNNポート追加の事前検証と、Node/Compound固有の更新先を確認する。"""

import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import maya.cmds as cmds
from hlib_bifrost.nodes.node import Node
from hlib_bifrost.nodes.compound import Compound


class BifrostPortValidationTest(unittest.TestCase):
    """プラグインをロードせず、nativeコマンド境界の入力を検証する。"""

    def reference(self, cls):
        """DGノードを作成せず、内部パス参照を用意する。

        Args:
            cls (type): NodeまたはCompound。

        Returns:
            Node: 模擬Graph内の参照。
        """
        return cls(SimpleNamespace(getName=lambda: "fixtureGraph"), "/fixture")

    def test_invalid_names_are_rejected_without_query_or_write(self):
        """不正な識別子はVNNコマンドを呼ぶ前に拒否する。"""
        for cls in (Node, Compound):
            for name in ("a.b", "a/b", "", 1):
                with self.subTest(cls=cls.__name__, name=name), \
                        mock.patch.object(cmds, "vnnNode", create=True) as node_command, \
                        mock.patch.object(cmds, "vnnCompound", create=True) as compound_command:
                    with self.assertRaisesRegex(ValueError, "Expected a simple identifier"):
                        self.reference(cls).add_port(name, "float")
                    node_command.assert_not_called()
                    compound_command.assert_not_called()

    def test_existing_port_suffix_is_rejected_before_any_write(self):
        """VNNが完全名を返す場合も同じ末尾名での追加を拒否する。"""
        for cls in (Node, Compound):
            with self.subTest(cls=cls.__name__), \
                    mock.patch.object(cmds, "vnnNode", return_value=["input.amount"], create=True) as node_command, \
                    mock.patch.object(cmds, "vnnCompound", create=True) as compound_command:
                with self.assertRaisesRegex(ValueError, "Port already exists: amount"):
                    self.reference(cls).add_port("amount", "float")
                node_command.assert_called_once_with("fixtureGraph", "/fixture", listPorts=True)
                compound_command.assert_not_called()

    def test_creation_uses_each_native_command_and_retains_direction_truthiness(self):
        """検証後は固有コマンドへ、従来どおりoutputの真偽でフラグを渡す。"""
        for cls in (Node, Compound):
            for output in (False, True, "truthy"):
                with self.subTest(cls=cls.__name__, output=output), \
                        mock.patch.object(cmds, "vnnNode", return_value=(), create=True) as node_command, \
                        mock.patch.object(cmds, "vnnCompound", create=True) as compound_command:
                    reference = self.reference(cls)
                    port = reference.add_port("amount", "float", output=output)
                    self.assertIs(port.node, reference)
                    self.assertEqual(port.name, "amount")
                    creation = mock.call("fixtureGraph", "/fixture", **{
                        "createOutputPort" if output else "createInputPort": ("amount", "float")})
                    if cls is Node:
                        self.assertEqual(node_command.call_args_list, [
                            mock.call("fixtureGraph", "/fixture", listPorts=True), creation])
                        compound_command.assert_not_called()
                    else:
                        node_command.assert_called_once_with("fixtureGraph", "/fixture", listPorts=True)
                        self.assertEqual(compound_command.call_args_list, [creation])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
