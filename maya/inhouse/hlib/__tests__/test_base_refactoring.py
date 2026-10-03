"""共通基底への集約後も事前検証と単数/複数の契約を維持する。"""
import unittest
from maya import cmds
import hlib


class BaseRefactoringTest(unittest.TestCase):
    """シーン編集前の失敗とUndo単位を確認する。"""

    def setUp(self):
        """専用シーンに独立したjointを作る。"""
        cmds.file(new=True, force=True)
        self.names = [cmds.createNode("joint") for _ in range(2)]

    def test_bulk_arguments_before_edit(self):
        """後半の不正な引数でも先頭を編集しない。"""
        joints = hlib.nodes.Joints(self.names)
        with self.assertRaises(TypeError):
            joints.callEach("setTranslation", [((1, 2, 3),), ((4, 5, 6),)], [{}, {"bad_flag": True}])
        self.assertEqual(cmds.getAttr(self.names[0] + ".translate")[0], (0, 0, 0))

    def test_rotation_validation_before_edit(self):
        """後半jointの書込み拒否で先頭の回転は変わらない。"""
        for name in self.names:
            cmds.setAttr(name + ".rotate", 10, 20, 30)
        cmds.setAttr(self.names[1] + ".jointOrientX", lock=True)
        before = cmds.getAttr(self.names[0] + ".rotate")[0]
        with self.assertRaises(RuntimeError):
            hlib.nodes.Joints(self.names).freezeRotation()
        self.assertEqual(cmds.getAttr(self.names[0] + ".rotate")[0], before)

    def test_single_and_plural_undo(self):
        """両入口で自身返却と1回のUndoを保つ。"""
        for name in self.names:
            cmds.setAttr(name + ".rotate", 10, 20, 30)
        single = hlib.getNode(self.names[0])
        many = hlib.nodes.Joints(self.names)
        before = [cmds.getAttr(name + ".rotate")[0] for name in self.names]
        for target in (single, many):
            self.assertIs(target.freezeRotation(), target)
            cmds.undo()
            for name, values in zip(self.names, before):
                self.assertEqual(cmds.getAttr(name + ".rotate")[0], values)


if __name__ == "__main__":
    unittest.main()
