"""通常importで公開名を補完でき、commonの遅延公開宣言が一致することを検証する。"""

import ast
from pathlib import Path
import sys
from types import ModuleType
import unittest

import hlib

PACKAGE = Path(hlib.__file__).resolve().parent


def typing_names(relative):
    """`if TYPE_CHECKING:` 内で import されている名前の集合を返す。"""
    tree = ast.parse((PACKAGE / relative).read_text(encoding="utf-8-sig"))
    names = set()
    for node in tree.body:
        if isinstance(node, ast.If) and getattr(node.test, "id", None) == "TYPE_CHECKING":
            for child in ast.walk(node):
                if isinstance(child, ast.ImportFrom):
                    names.update(alias.asname or alias.name for alias in child.names)
    return names


def direct_names(relative):
    """通常importとトップレベル定義から静的に解決できる名前を返す。"""
    tree = ast.parse((PACKAGE / relative).read_text(encoding="utf-8-sig"))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.ImportFrom, ast.Import)):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


class TypingExportsTest(unittest.TestCase):
    def test_root_commands(self):
        self.assertTrue(set(hlib.__all__).issubset(direct_names("__init__.py")))
        self.assertEqual(typing_names("__init__.py"), set())
        tree = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8-sig"))
        root_functions = {node.name for node in tree.body
                          if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in hlib.cmds.__all__:
            root_value = getattr(hlib, name)
            if name in root_functions or isinstance(root_value, ModuleType):
                self.assertIsNot(root_value, getattr(hlib.cmds, name))
            else:
                self.assertIs(root_value, getattr(hlib.cmds, name))

    def test_cmds_package(self):
        self.assertTrue(set(hlib.cmds.__all__).issubset(direct_names("cmds/__init__.py")))
        self.assertEqual(typing_names("cmds/__init__.py"), set())

    def test_nodes_package(self):
        self.assertTrue(set(hlib.nodes.__all__).issubset(direct_names("nodes/__init__.py")))
        self.assertEqual(typing_names("nodes/__init__.py"), set())

    def test_other_class_packages(self):
        """各クラスパッケージが二重宣言なしに公開名を補完できる。"""
        for name in ("plugs", "components", "maths", "json"):
            package = getattr(hlib, name)
            path = name + "/__init__.py"
            self.assertTrue(set(package.__all__).issubset(direct_names(path)), name)
            self.assertEqual(typing_names(path), set(), name)

    def test_common_package(self):
        """遅延公開するクラス・関数・定数・moduleを静的補完でも取得できる。"""
        self.assertEqual(typing_names("common/__init__.py"), set(hlib.common.__all__))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
