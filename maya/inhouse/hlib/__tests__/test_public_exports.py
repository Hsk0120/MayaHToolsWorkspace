"""公開一覧の追加漏れを、製品ソースのASTと実行時オブジェクトで検証する。"""

import importlib
from pathlib import Path
import sys
import unittest

import hlib

TOOLS = Path(__file__).resolve().parents[4] / "tools"


class PublicExportsTest(unittest.TestCase):
    """公開入口とクラス・コマンドの定義元が一致することを確認する。"""

    def test_source_exports_have_no_omissions(self):
        """新規クラスやコマンドの公開漏れをMaya内の既存テスト経路でも拾う。"""
        sys.path.insert(0, str(TOOLS))
        try:
            from check_hlib_exports import check
            issues = check(Path(hlib.__file__).resolve().parent)
        finally:
            sys.path.remove(str(TOOLS))
        self.assertEqual(issues, [], "\n".join(str(issue) for issue in issues))

    def test_public_classes_are_current_definition_objects(self):
        """明示importの公開クラスが定義元やreload前の別クラスにずれない。"""
        for package_name in ("nodes", "plugs", "components", "maths", "common", "json"):
            package = getattr(hlib, package_name)
            for name in package.__all__:
                value = getattr(package, name)
                if isinstance(value, type) and value.__module__.startswith(hlib.__name__ + "."):
                    module = importlib.import_module(value.__module__)
                    self.assertIs(value, getattr(module, value.__name__), package_name + "." + name)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
