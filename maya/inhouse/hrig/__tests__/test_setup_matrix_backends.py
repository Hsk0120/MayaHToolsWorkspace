"""明示選択するC++/Bifrost行列追従の共通契約を検証する。"""

from functools import partial
from unittest.mock import patch
import unittest
from maya import cmds

from hrig.__tests__ import test_setup_matrix_follow as shared
from hrig.setups import MatrixFollow


class CppMatrixFollowTest(shared.MatrixFollowTest):
    """共通8ケースをC++実装へ適用する。"""

    def setUp(self):
        """隔離シーンで明示バックエンドを固定する。"""
        super().setUp()
        patcher = patch.object(MatrixFollow, "create", partial(MatrixFollow.create, backend="cpp"))
        patcher.start()
        self.addCleanup(patcher.stop)


class BifrostMatrixFollowTest(shared.MatrixFollowTest):
    """共通8ケースをBifrost実装へ適用する。"""

    def setUp(self):
        """隔離シーンで明示バックエンドを固定する。"""
        super().setUp()
        cmds.undoInfo(state=False)
        patcher = patch.object(
            MatrixFollow, "create", partial(MatrixFollow.create, backend="bifrost")
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: cmds.undoInfo(state=True))

    def test_undo_redo(self):
        """未対応のUndo構築を拒否し、Mayaのクラッシュを防ぐ。"""
        cmds.undoInfo(state=True)
        with self.assertRaisesRegex(RuntimeError, "Undo disabled"):
            MatrixFollow.create(self.source, self.target)
        self.assertIsNone(self.target.getPlug("offsetParentMatrix").getSourceWithConversion())

    def test_reject_gui(self):
        """Undoを無効にしていても通常GUIからの構築を拒否する。"""
        from hrig.setups.bifrostMatrixFollow import BifrostMatrixFollow

        before = set(cmds.ls())
        with patch.object(cmds, "about", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "isolated process"):
                BifrostMatrixFollow.create("notCreated")
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main()
