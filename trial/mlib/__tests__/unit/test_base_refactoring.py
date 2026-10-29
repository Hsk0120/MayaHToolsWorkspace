"""共通基底への集約後も単数の契約を維持する。"""
import unittest
from maya import cmds
import mlib


class BaseRefactoringTest(unittest.TestCase):
    """Undo単位を確認する。"""

    def setUp(self):
        """専用シーンに独立したjointを作る。"""
        cmds.file(new=True, force=True)
        self.names = [cmds.createNode("joint") for _ in range(2)]

    def test_single_undo(self):
        """freezeRotateは自身を返し、1回のUndoで戻る。"""
        for name in self.names:
            cmds.setAttr(name + ".rotate", 10, 20, 30)
        single = mlib.getNode(self.names[0])
        before = [cmds.getAttr(name + ".rotate")[0] for name in self.names]
        self.assertIs(single.freezeRotate(), single)
        cmds.undo()
        for name, values in zip(self.names, before):
            self.assertEqual(cmds.getAttr(name + ".rotate")[0], values)


if __name__ == "__main__":
    unittest.main()
