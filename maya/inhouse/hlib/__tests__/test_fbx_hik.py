"""標準プラグイン連携。空の隔離Maya standaloneで実行する。"""

import tempfile
import unittest
from pathlib import Path
from maya import cmds, mel
import hlib


class StandardPluginsTest(unittest.TestCase):
    """FBX往復とHumanIKの型登録・骨割当を検証する。"""

    def setUp(self):
        """テスト間でシーンを分離する。"""
        cmds.file(new=True, force=True)

    def test_hik_character_and_roles(self):
        """標準MELで定義を作り、型と骨割当を確認する。"""
        from hlib.nodes import HIKCharacterNode, HIKSolverNode
        character = HIKCharacterNode.create_character('testCharacter')
        self.assertIsInstance(character, HIKCharacterNode)
        joint = cmds.createNode('joint',name='testHips')
        character.set_joint('Hips',joint)
        self.assertEqual(character.joint('Hips').full_name(), '|testHips')
        self.assertIsNone(character.joint('LeftHand'))
        with self.assertRaises(ValueError):
            character.set_joint('not_a_role',joint)
        self.assertIsInstance(hlib.createNode('HIKSolverNode'), HIKSolverNode)
        other = HIKCharacterNode.create_character('other')
        with self.assertRaises(RuntimeError):
            character.set_source(other)

    def test_fbx_animation_roundtrip(self):
        """選択と設定を復元し、骨アニメーションを再読込できる。"""
        from hlib.utils.fbx import export_fbx, import_fbx
        joint = cmds.createNode('joint',name='roundtripJoint')
        cmds.setKeyframe(joint,attribute='rotateZ',time=1,value=0)
        cmds.setKeyframe(joint,attribute='rotateZ',time=10,value=45)
        cmds.select(joint)
        hlib.general.Plugin('fbxmaya').ensure_loaded()
        old = mel.eval('FBXProperty Export|IncludeGrp|Animation -q;')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'animation.fbx'
            export_fbx(path,selection=[joint])
            self.assertEqual(cmds.ls(selection=True), [joint])
            self.assertEqual(mel.eval('FBXProperty Export|IncludeGrp|Animation -q;'),old)
            with self.assertRaises(FileExistsError):
                export_fbx(path,selection=[joint])
            cmds.file(new=True,force=True)
            nodes = import_fbx(path,namespace='incoming')
            self.assertIn('|incoming:roundtripJoint',nodes)
            self.assertNotIn('time1',nodes)
            self.assertEqual(cmds.keyframe('incoming:roundtripJoint.rotateZ',query=True,valueChange=True),[0,45])


if __name__ == '__main__':
    unittest.main()
