"""公開パッケージと再読み込み後のコマンド入口を検証する。"""

import importlib
import inspect
import sys
import types
import unittest
from pathlib import Path

import hlib


class PackageLayoutTest(unittest.TestCase):
    def test_common_exports_use_current_definitions_after_reload(self):
        """遅延公開名を列挙・importでき、reload後に古いクラスを返さない。"""
        common = hlib.common
        self.assertTrue(set(common.__all__).issubset(dir(common)))
        previous = {name: getattr(common, name) for name in common.__all__}
        namespace = {}
        exec("from hlib.common import *", namespace)
        for name, value in previous.items():
            self.assertIs(namespace[name], value, name)
        hlib.reload()
        for name, value in previous.items():
            with self.subTest(export=name):
                current = getattr(hlib.common, name)
                if inspect.isclass(value) or inspect.isfunction(value):
                    self.assertIsNot(current, value)
                    owner = importlib.import_module(current.__module__)
                    self.assertIs(current, getattr(owner, name))

    def test_exports_and_command_identity_after_reload(self):
        importlib.reload(hlib)
        hlib.reload()
        for package, names in {
            "common": ("Scene", "Namespace", "Selection", "DrivenKey",
                       "Plugin", "Preferences", "Workspace", "ScriptJob",
                       "ScriptJobs", "Deferred", "TimeSlider", "Viewport", "Outliner"),
            "decorator": ("undoChunk", "undoTransaction", "preservedSelection",
                          "preservedSkinShape", "viewportOff", "nativeUnits"),
            "logger": ("get_logger", "debug", "info", "warning", "error", "print",
                       "raise_with_notify"),
        }.items():
            module = importlib.import_module("hlib." + package)
            self.assertIs(getattr(hlib, package), module)
            for name in names:
                self.assertTrue(hasattr(module, name), (package, name))
        self.assertIsInstance(hlib.getScene(), hlib.common.Scene)
        self.assertIsInstance(hlib.getTimeSlider(), hlib.common.TimeSlider)
        for name in ("getScene", "getTimeSlider", "getViewport", "getOutliner"):
            self.assertIs(getattr(hlib, name), getattr(hlib.cmds, name))
        self.assertIs(hlib._core.object.Object, importlib.import_module("hlib._core.object").Object)
        self.assertIs(hlib._core.extensions, importlib.import_module("hlib._core.extensions"))
        for name in ("Object", "extensions"):
            self.assertFalse(hasattr(hlib, name))
            self.assertNotIn(name, hlib.__all__)
        for cls in (hlib.nodes.Node, hlib.plugs.Plug, hlib.components.Component):
            self.assertTrue(issubclass(cls, hlib._core.object.Object))
        for cls in (hlib.common.Selection, hlib.common.Viewport, hlib.maths.Vector,
                    hlib.json.Snapshot):
            self.assertFalse(issubclass(cls, hlib._core.object.Object))

    def test_reload_removes_obsolete_package_names(self):
        # 旧版を読み込んでいたセッションの残存モジュール参照を再現する。
        obsolete = ("scenes", "session", "context", "files", "editors", "general",
                    "namespaces", "plugins", "animation", "scene", "environment",
                    "ui", "events", "utils", "decorators", "object", "extensions")
        obsolete_modules = ["hlib." + name for name in obsolete]
        obsolete_modules += ["hlib.scene.selection", "hlib.environment.plugin",
                             "hlib.ui.viewport", "hlib.events.scriptJob",
                             "hlib.utils.logger", "hlib.decorators.undo"]
        for name in obsolete:
            module = types.ModuleType("hlib." + name)
            sys.modules[module.__name__] = module
            setattr(hlib, name, module)
        for fullname in obsolete_modules:
            sys.modules[fullname] = types.ModuleType(fullname)
        hlib.Object = object
        hlib.reload()
        for name in obsolete:
            if name == "scene":
                self.assertTrue(callable(hlib.scene))
                self.assertIs(hlib.scene, hlib.cmds.scene)
            else:
                self.assertFalse(hasattr(hlib, name))
        for fullname in obsolete_modules:
            self.assertNotIn(fullname, sys.modules)
        self.assertFalse(hasattr(hlib, "Object"))
        self.assertNotIn("Object", hlib.__all__)
        self.assertIs(hlib._core.extensions, importlib.import_module("hlib._core.extensions"))

    def test_obsolete_import_paths_are_removed(self):
        """内部配置へ移したObject/extensionsも、旧ファイルのimportは復活させない。"""
        for name in ("scene", "environment", "ui", "events", "utils", "decorators",
                     "object", "extensions"):
            with self.subTest(module=name), self.assertRaises(ModuleNotFoundError):
                importlib.import_module("hlib." + name)

    def test_library_does_not_import_rig_setups(self):
        """ライブラリ本体からhrigへの逆依存を作らない。"""
        import ast
        root = Path(hlib.__file__).parent
        for path in root.rglob("*.py"):
            if "__tests__" in path.parts or "_docs" in path.parts:
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
        self.assertEqual(packages, {"cmds", "nodes", "plugs", "maths", "json",
                                   "common", "components"})
        for name in ("decorator.py", "logger.py", "_core/object.py", "_core/extensions.py"):
            self.assertTrue((root / name).is_file(), name)
        self.assertTrue((root / "_docs").is_dir())
        self.assertFalse((root / "docs").exists())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
