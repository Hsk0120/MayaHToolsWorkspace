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
            self.assertEqual(nodes.getOutlinerVisibility(), [True, True])
            nodes.setOutlinerVisibility(False)
            self.assertEqual(nodes.getOutlinerVisibility(), [False, False])
            for node in nodes:
                self.assertTrue(cmds.getAttr(node.fullName() + ".hiddenInOutliner"))
                self.assertTrue(cmds.getAttr(node.fullName() + ".visibility"))
            cmds.undo()
            self.assertEqual(nodes.getOutlinerVisibility(), [True, True])
            cmds.redo()
            self.assertEqual(nodes.getOutlinerVisibility(), [False, False])
            self.assertIs(nodes[0].setOutlinerVisibility(True, fast=True), nodes[0])
            self.assertTrue(nodes[0].getOutlinerVisibility())
            nodes.setVisibility(False)
            self.assertEqual(nodes.getVisibility(), [False, False])
            self.assertTrue(nodes[0].getOutlinerVisibility())
            cmds.undo()
            self.assertEqual(nodes.getVisibility(), [True, True])
            nodes.setVisibility(False)
            self.assertEqual(nodes.getVisibility(), [False, False])
            self.assertTrue(nodes[0].getOutlinerVisibility())
            cmds.undo()
            self.assertEqual(nodes.getVisibility(), [True, True])
            with self.assertRaises(TypeError):
                nodes[0].setOutlinerVisibility(1)
        finally:
            cmds.delete([node.fullName() for node in nodes])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
