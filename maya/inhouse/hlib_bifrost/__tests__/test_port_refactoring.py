"""Node/Compoundのポート追加・重複拒否・native Undoを実Mayaで検証する。"""

import sys
import unittest

import maya.cmds as cmds
from hlib_bifrost.common import Bifrost
from hlib_bifrost.nodes import Graph


class PortCreationTest(unittest.TestCase):
    """隔離した空シーンで、VNNの更新結果を検査する。"""

    @classmethod
    def setUpClass(cls):
        """対応プラグインを明示的にロードする。"""
        Bifrost.ensure_available()

    def setUp(self):
        """グラフと演算ノードを用意し、ポート追加前のUndo履歴を分離する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        self.graph = Graph.create()
        self.internal = self.graph.root.add_node("BifrostGraph,Core::Math,multiply")
        cmds.flushUndo()

    def names(self, reference):
        """VNNポート名の末尾を照会する。

        Args:
            reference (Node): 照会するNodeまたはCompound。

        Returns:
            tuple[str]: パスを除いたポート名。
        """
        return tuple(name.rsplit(".", 1)[-1] for name in reference.ports())

    def verify_creation(self, reference, output):
        """追加したポートの参照と、Undo/Redo後の有無を検査する。

        Args:
            reference (Node): ポートを追加するNodeまたはCompound。
            output (bool): 出力ポートならTrue。
        """
        port = reference.add_port("refactorAmount", "float", output=output)
        self.assertIs(port.node, reference)
        self.assertEqual(port.name, "refactorAmount")
        self.assertIn(port.name, self.names(reference))
        cmds.undo()
        self.assertNotIn(port.name, self.names(reference))
        cmds.redo()
        self.assertIn(port.name, self.names(reference))

    def test_internal_node_input_port_undo_and_redo(self):
        """内部Nodeの入力追加はvnnNodeのUndo/Redoで戻る。"""
        self.verify_creation(self.internal, False)

    def test_compound_output_port_undo_and_redo(self):
        """Compoundの境界出力追加はvnnCompoundのUndo/Redoで戻る。"""
        self.verify_creation(self.graph.root, True)

    def test_duplicate_port_rejection_keeps_native_state_and_undo_history(self):
        """両参照で同名追加を拒否し、既存ポートとUndo先を変えない。"""
        for reference in (self.internal, self.graph.root):
            reference.add_port("refactorExisting", "float")
            before = self.names(reference)
            undo_name = cmds.undoInfo(query=True, undoName=True)
            with self.assertRaisesRegex(ValueError, "Port already exists"):
                reference.add_port("refactorExisting", "float", output=True)
            self.assertEqual(self.names(reference), before)
            self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
