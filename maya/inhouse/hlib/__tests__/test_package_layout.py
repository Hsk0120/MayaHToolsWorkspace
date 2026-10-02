"""公開パッケージと再読み込み後のコマンド入口を検証する。"""

import importlib
import sys
import types
import unittest
from pathlib import Path

import hlib


class PackageLayoutTest(unittest.TestCase):
    def test_exports_and_command_identity_after_reload(self):
        importlib.reload(hlib)
        hlib.reload()
        for package, names in {
            "scene": ("Scene", "Namespace", "Selection", "DrivenKey"),
            "environment": ("Plugin", "Preferences", "Workspace"),
            "events": ("ScriptJob", "ScriptJobs", "Deferred"),
            "ui": ("TimeSlider", "Viewport", "Outliner"),
            "decorators": ("undo_chunk", "preserved_selection", "viewport_off"),
        }.items():
            module = importlib.import_module("hlib." + package)
            self.assertIs(getattr(hlib, package), module)
            for name in names:
                self.assertTrue(hasattr(module, name), (package, name))
        self.assertIsInstance(hlib.getScene(), hlib.scene.Scene)
        self.assertIsInstance(hlib.getTimeSlider(), hlib.ui.TimeSlider)
        for name in ("getScene", "getTimeSlider", "getViewport", "getOutliner"):
            self.assertIs(getattr(hlib, name), getattr(hlib.cmds, name))

    def test_reload_removes_obsolete_package_names(self):
        # 旧版を読み込んでいたセッションの残存モジュール参照を再現する。
        obsolete = ("scenes", "session", "context", "files", "editors", "general",
                    "namespaces", "plugins", "animation")
        for name in obsolete:
            module = types.ModuleType("hlib." + name)
            sys.modules[module.__name__] = module
            setattr(hlib, name, module)
        hlib.reload()
        for name in obsolete:
            self.assertFalse(hasattr(hlib, name))
            self.assertNotIn("hlib." + name, sys.modules)

    def test_library_does_not_import_rig_setups(self):
        """ライブラリ本体からhrigへの逆依存を作らない。"""
        import ast
        root = Path(hlib.__file__).parent
        for path in root.rglob("*.py"):
            if "__tests__" in path.parts or "docs" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.Import):
                    names = [item.name for item in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                self.assertFalse(any(name == "hrig" or name.startswith("hrig.") for name in names), str(path))

    def test_public_directory_roles(self):
        """新しい機能は既存の役割へ置き、旧互換パッケージを復活させない。"""
        root = Path(hlib.__file__).parent
        packages = {path.name for path in root.iterdir()
                    if path.is_dir() and (path / "__init__.py").exists()
                    and not path.name.startswith("_")}
        self.assertEqual(packages, {"cmds", "nodes", "plugs", "maths", "json", "utils",
                                    "scene", "ui", "environment", "events", "components", "decorators"})


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
