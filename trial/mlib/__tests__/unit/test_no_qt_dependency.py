"""mlibへQt依存を持ち込まない境界を検証する。"""
import ast
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import mlib


class NoQtDependencyTest(unittest.TestCase):
    """実装・テストともにQt bindingsやMQtUtilを直接使用しない。"""

    def test_import_boundary(self):
        """遅延importも含め、全Pythonソースの依存を検査する。"""
        forbidden = ("PySide", "PyQt", "shiboken", "qtpy", "Qt")
        violations = []
        for path in Path(mlib.__file__).parent.rglob("*.py"):
            if any(part in (".venv", "_build", "_docs", "__tests__", "__pycache__") for part in path.parts):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                if any(module.split(".")[0].startswith(forbidden) for module in modules):
                    violations.append(str(path) + ":" + str(node.lineno))
                if isinstance(node, ast.Attribute) and node.attr == "MQtUtil":
                    violations.append(str(path) + ":" + str(node.lineno))
        self.assertEqual(violations, [])



if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
