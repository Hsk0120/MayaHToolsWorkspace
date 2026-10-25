"""標準プラグイン連携。空の隔離Maya standaloneで実行する。"""

import tempfile
import unittest
from pathlib import Path
from maya import cmds, mel
import mlib


class StandardPluginsTest(unittest.TestCase):
    """HumanIKの型登録と骨割当を検証する。"""

    def setUp(self):
        """テスト間でシーンを分離する。"""
        cmds.file(new=True, force=True)

    def test_hik_character_and_roles(self):
        """標準MELで定義を作り、型と骨割当を確認する。"""
        from mlib.nodes import HIKCharacterNode, HIKSolverNode
        character = HIKCharacterNode.createCharacter('testCharacter')
        self.assertIsInstance(character, HIKCharacterNode)
        joint = cmds.createNode('joint',name='testHips')
        character.setJoint('Hips',joint)
        self.assertEqual(character.joint('Hips').getFullName(), '|testHips')
        self.assertIsNone(character.joint('LeftHand'))
        with self.assertRaises(ValueError):
            character.setJoint('not_a_role',joint)
        self.assertIsInstance(mlib.createNode('HIKSolverNode'), HIKSolverNode)
        other = HIKCharacterNode.createCharacter('other')
        with self.assertRaises(RuntimeError):
            character.setSource(other)



if __name__ == '__main__':
    unittest.main()
