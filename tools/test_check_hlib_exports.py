"""一時ソースを使い、Maya不要のhlib公開漏れ検査を検証する。"""

from pathlib import Path
import tempfile
import unittest

from check_hlib_exports import CLASS_PACKAGES, check


class ExportCheckerTest(unittest.TestCase):
    """公開漏れと誤った参照を、小さな独立fixtureで検出する。"""

    def setUp(self):
        """空の正常な公開パッケージを作る。"""
        self.directory = tempfile.TemporaryDirectory(prefix="hlib_exports_")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "hlib"
        self.root.mkdir()
        self.write("__init__.py", "__all__ = []\n")
        for folder in CLASS_PACKAGES + ("cmds",):
            self.write(folder + "/__init__.py", "__all__ = []\n")

    def write(self, relative, text):
        """fixtureの一つのソースを保存する。"""
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def codes(self):
        """検出した問題のコード一覧を返す。"""
        return {issue.code for issue in check(self.root)}

    def test_plain_exports_need_no_typing_duplicates(self):
        """通常import一つで実行時の公開と補完を表現できる。"""
        self.write("nodes/example.py", "class Example:\n    pass\n")
        self.write("nodes/__init__.py", "from .example import Example\n__all__ = ['Example']\n")
        self.assertEqual(check(self.root), [])

    def test_new_class_is_reported_without_importing_maya(self):
        """Mayaや実行できないコードがあってもASTで公開漏れを検出する。"""
        self.write("common/example.py", "import maya.cmds\nraise RuntimeError('must not execute')\nclass Example:\n    pass\n")
        self.assertIn("E012", self.codes())

    def test_private_classes_files_and_imported_classes_are_excluded(self):
        """内部ファイル・内部クラス・借用クラスは追加漏れにしない。"""
        self.write("common/_hidden.py", "class Hidden:\n    pass\n")
        self.write("common/helper.py", "from os import stat_result as Foreign\nclass _Internal:\n    pass\n")
        self.write("plugs/plug.py", "class DeletedAttributeError(RuntimeError):\n    pass\n")
        self.assertEqual(check(self.root), [])

    def test_all_omission_is_detected(self):
        """importだけを追加した場合も__all__の漏れを通知する。"""
        self.write("maths/vector.py", "class Vector:\n    pass\n")
        self.write("maths/__init__.py", "from .vector import Vector\n__all__ = []\n")
        self.assertTrue({"E010", "E012"}.issubset(self.codes()))

    def test_wrong_source_and_same_name_collisions_are_detected(self):
        """同じ名前を別ファイルから公開しても成功と判断しない。"""
        self.write("nodes/first.py", "class Example:\n    pass\n")
        self.write("nodes/second.py", "class Example:\n    pass\n")
        self.write("nodes/__init__.py", "from .second import Example\n__all__ = ['Example']\n")
        self.assertTrue({"E011", "E013"}.issubset(self.codes()))

    def test_missing_import_target_and_duplicate_all_are_detected(self):
        """削除済みの定義元と公開名の重複を検出する。"""
        self.write("maths/__init__.py", "from .missing import Example\n__all__ = ['Example', 'Example']\n")
        self.assertTrue({"E005", "E009"}.issubset(self.codes()))

    def test_common_lazy_class_constant_function_and_module(self):
        """commonの遅延公開と補完宣言を参照先まで照合する。"""
        self.write("common/example.py", "class Example:\n    pass\nVALUE = 1\ndef action():\n    return VALUE\n")
        self.write("common/units.py", "VALUE = 2\n")
        self.write("common/__init__.py", "from typing import TYPE_CHECKING\n_exports = {'Example': ('example', 'Example'), 'VALUE': ('example', 'VALUE'), 'action': ('example', 'action'), 'units': ('units', None)}\n__all__ = sorted(_exports)\nif TYPE_CHECKING:\n    from .example import Example, VALUE, action\n    from . import units\n")
        self.assertEqual(check(self.root), [])
        self.write("common/other.py", "class _Other:\n    pass\nVALUE = 2\n")
        path = self.root / "common/__init__.py"
        path.write_text(path.read_text(encoding="utf-8").replace("from .example import Example, VALUE, action", "from .example import Example, action\n    from .other import VALUE"), encoding="utf-8")
        self.assertIn("E007", self.codes())

    def test_commands_require_own_function_and_root_reexport(self):
        """cmdsとrootで同じ関数を公開していることを確認する。"""
        self.write("cmds/exampleCommand.py", "def exampleCommand():\n    return 1\n")
        self.assertTrue({"E015", "E016"}.issubset(self.codes()))
        self.write("cmds/__init__.py", "from .exampleCommand import exampleCommand\n__all__ = ['exampleCommand']\n")
        self.write("__init__.py", "from .cmds import exampleCommand\n__all__ = ['exampleCommand']\n")
        self.assertEqual(check(self.root), [])
        self.write("cmds/exampleCommand.py", "from os import getcwd as exampleCommand\n")
        self.assertIn("E014", self.codes())

    def test_foreign_public_class_alias_is_retained(self):
        """Maya標準クラスの既存再公開を内部クラス追加と混同しない。"""
        self.write("maths/__init__.py", "from maya.api.OpenMaya import MSpace\n__all__ = ['MSpace']\n")
        self.assertEqual(check(self.root), [])

    def test_root_function_is_protected_from_same_name_command(self):
        """rootで定義した公開関数と同名のコマンドはcmdsだけへ公開できる。"""
        self.write("cmds/reload.py", "def reload():\n    return 'command'\n")
        self.write("cmds/__init__.py", "from .reload import reload\n__all__ = ['reload']\n")
        self.write("__init__.py", "__all__ = ['reload']\ndef reload():\n    return 'package'\n")
        self.assertEqual(check(self.root), [])
        self.write("cmds/__init__.py", "__all__ = []\n")
        self.assertIn("E015", self.codes())

    def test_root_public_module_is_protected_from_same_name_command(self):
        """rootの公開サブパッケージを同名のコマンドで置き換えない。"""
        self.write("cmds/json.py", "def json():\n    return 'command'\n")
        self.write("cmds/__init__.py", "from .json import json\n__all__ = ['json']\n")
        self.write("__init__.py", "from . import json\n__all__ = ['json']\n")
        self.assertEqual(check(self.root), [])
        self.write("cmds/__init__.py", "__all__ = []\n")
        self.assertIn("E015", self.codes())

    def test_runtime_typing_double_management_is_rejected(self):
        """通常importへ移した公開名のTYPE_CHECKING二重管理を検出する。"""
        self.write("nodes/example.py", "class Example:\n    pass\n")
        self.write("nodes/__init__.py", "from typing import TYPE_CHECKING\nfrom .example import Example\n__all__ = ['Example']\nif TYPE_CHECKING:\n    from .example import Example\n")
        self.assertIn("E007", self.codes())

    def test_star_import_and_private_publication_are_rejected(self):
        """公開入口へ曖昧なimportや内部名を追加しない。"""
        self.write("nodes/__init__.py", "from .hidden import *\nclass _Hidden:\n    pass\n__all__ = ['_Hidden']\n")
        self.assertTrue({"E002", "E008"}.issubset(self.codes()))

    def test_wrapper_map_references_declared_classes(self):
        """型対応表へ未import名や関数を渡した場合を実行前に検出する。"""
        self.write("nodes/example.py", "class Example:\n    pass\ndef action():\n    return 1\n")
        self.write("nodes/__init__.py", "from .example import Example, action\n__all__ = ['Example', 'action']\n_WRAPPER_CLASSES = {'example': Example}\n")
        self.assertEqual(check(self.root), [])
        self.write("nodes/__init__.py", "from .example import Example, action\n__all__ = ['Example', 'action']\n_WRAPPER_CLASSES = {'missing': Missing, 'action': action, '': Example}\n")
        self.assertTrue({"E017", "E018"}.issubset(self.codes()))

    def test_mutating_all_is_not_an_explicit_export_declaration(self):
        """自動検出結果の後置追記を公開仕様として受け入れない。"""
        self.write("nodes/__init__.py", "__all__ = []\n__all__.append('Example')\n")
        self.assertIn("E019", self.codes())

    def test_empty_lazy_export_map_is_valid(self):
        """公開対象が空でもcommonの明示遅延表を読み取れる。"""
        self.write("common/__init__.py", "_exports = {}\n__all__ = sorted(_exports)\n")
        self.assertEqual(check(self.root), [])


if __name__ == "__main__":
    unittest.main()
