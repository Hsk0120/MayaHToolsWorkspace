"""ノードのアウトライナー表示設定を検証する。GUIの描画確認ではない。"""
import sys
import unittest
import maya.cmds as cmds
import hlib
hlib.reload()
from hlib.nodes import DagNodes


class OutlinerVisibilityTest(unittest.TestCase):
    """設定値とUndo、一括操作を検証する。"""

    def test_visibility_and_undo(self):
        nodes = DagNodes([hlib.createNode("transform"), hlib.createNode("joint")])
        try:
            self.assertEqual(nodes.get_outliner_visibility(), [True, True])
            nodes.set_outliner_visibility(False)
            self.assertEqual(nodes.get_outliner_visibility(), [False, False])
            for node in nodes:
                self.assertTrue(cmds.getAttr(node.full_name() + ".hiddenInOutliner"))
                self.assertTrue(cmds.getAttr(node.full_name() + ".visibility"))
            cmds.undo()
            self.assertEqual(nodes.get_outliner_visibility(), [True, True])
            cmds.redo()
            self.assertEqual(nodes.get_outliner_visibility(), [False, False])
            self.assertIs(nodes[0].set_outliner_visibility(True, fast=True), nodes[0])
            self.assertTrue(nodes[0].get_outliner_visibility())
            nodes.set_visibility(False)
            self.assertEqual(nodes.get_visibility(), [False, False])
            self.assertTrue(nodes[0].get_outliner_visibility())
            cmds.undo()
            self.assertEqual(nodes.get_visibility(), [True, True])
            nodes.set_visibility(False)
            self.assertEqual(nodes.get_visibility(), [False, False])
            self.assertTrue(nodes[0].get_outliner_visibility())
            cmds.undo()
            self.assertEqual(nodes.get_visibility(), [True, True])
            with self.assertRaises(TypeError):
                nodes[0].set_outliner_visibility(1)
        finally:
            cmds.delete([node.full_name() for node in nodes])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
