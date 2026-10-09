"""HumanIKの成功後確認をMEL境界の模擬とnative参照で検証する。"""

import importlib
import unittest
from unittest import mock

import hlib
import maya.cmds as cmds


class HIKVerificationTest(unittest.TestCase):
    """実リターゲット成功と区別して、既存getSourceへの委譲を確認する。"""

    def setUp(self):
        """標準プラグインをロードして実HumanIKノードを用意する。"""
        cmds.file(new=True, force=True)
        self.module = importlib.import_module("hlib.nodes.HIKCharacterNode")
        self.module._prepare()
        self.target = hlib.nodes.HIKCharacterNode("verifyTarget", create=True)
        self.source = hlib.nodes.HIKCharacterNode("verifySource", create=True)

    def tearDown(self):
        """テストシーンを破棄する。"""
        cmds.file(new=True, force=True)

    def test_success_uses_existing_get_source_after_mel_command(self):
        """前提とMEL成功を模擬し、正式getterで同じsourceを検証する。"""
        with mock.patch.object(self.module, "_prepare"), mock.patch.object(
                type(self.target), "isDefinitionLocked", return_value=True), mock.patch.object(
                    self.module.mel, "eval") as mel_eval, mock.patch.object(
                        type(self.target), "getSource", return_value=self.source) as getter:
            self.assertIsNone(self.target.setSource(self.source))
            mel_eval.assert_called_once_with('hikSetCharacterInput("verifyTarget", "verifySource");')
            getter.assert_called_once_with()

    def test_mismatched_source_is_rejected_after_verification(self):
        """MEL境界が成功しても、getterが未接続を返せば既存RuntimeErrorとする。"""
        with mock.patch.object(self.module, "_prepare"), mock.patch.object(
                type(self.target), "isDefinitionLocked", return_value=True), mock.patch.object(
                    self.module.mel, "eval"), mock.patch.object(type(self.target), "getSource", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "did not connect"):
                self.target.setSource(self.source)


if __name__ == "__main__":
    unittest.main()
