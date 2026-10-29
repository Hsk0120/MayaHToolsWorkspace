"""ノードのアウトライナー表示設定を検証する。GUIの描画確認ではない。"""
import sys
import unittest
import maya.cmds as cmds
import mlib
mlib.reload()
from mlib.decorator import undoChunk


class OutlinerVisibilityTest(unittest.TestCase):
    """設定値とUndo、複数ノードへの順次操作を検証する。"""

    def test_visibility_and_undo(self):
        nodes = [mlib.createNode("transform"), mlib.createNode("joint")]

        def outliner():
            return [node.getOutlinerVisibility() for node in nodes]

        def visibility():
            return [node.getVisibility() for node in nodes]

        try:
            self.assertEqual(outliner(), [True, True])
            with undoChunk("mlibOutlinerVisibilityTest"):
                for node in nodes:
                    self.assertIs(node.setOutlinerVisibility(False), node)
            self.assertEqual(outliner(), [False, False])
            for node in nodes:
                self.assertTrue(cmds.getAttr(node.getFullName() + ".hiddenInOutliner"))
                self.assertTrue(cmds.getAttr(node.getFullName() + ".visibility"))
            cmds.undo()
            self.assertEqual(outliner(), [True, True])
            cmds.redo()
            self.assertEqual(outliner(), [False, False])
            self.assertIs(nodes[0].setOutlinerVisibility(True, fast=True), nodes[0])
            self.assertTrue(nodes[0].getOutlinerVisibility())
            for _ in range(2):
                with undoChunk("mlibOutlinerVisibilityTest"):
                    for node in nodes:
                        node.setVisibility(False)
                self.assertEqual(visibility(), [False, False])
                self.assertTrue(nodes[0].getOutlinerVisibility())
                cmds.undo()
                self.assertEqual(visibility(), [True, True])
            with self.assertRaises(TypeError):
                nodes[0].setOutlinerVisibility(1)
        finally:
            cmds.delete([node.getFullName() for node in nodes])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
