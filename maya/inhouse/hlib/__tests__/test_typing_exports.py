"""静的解析向けの `if TYPE_CHECKING:` 宣言が、実行時の動的な公開名と一致することを検証する。

hlib.createNode などは実行時にグローバルへ動的に設定されるため、エディターは名前を解決できない。
各 __init__.py の TYPE_CHECKING ブロックがその代わりになるので、公開名を増減したときの更新漏れを検出する。
"""

import ast
from pathlib import Path
import sys
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


class TypingExportsTest(unittest.TestCase):
    def test_root_commands(self):
        self.assertEqual(typing_names("__init__.py"), set(hlib.cmds.__all__))

    def test_cmds_package(self):
        self.assertEqual(typing_names("cmds/__init__.py"), set(hlib.cmds.__all__))

    def test_nodes_package(self):
        # Node/Shape/Transform は通常の import で解決される。
        expected = set(hlib.nodes.__all__) - {"Node", "Shape", "Transform"}
        self.assertEqual(typing_names("nodes/__init__.py"), expected)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
