"""公開パッケージと再読み込み後のコマンド入口を検証する。"""

import importlib
import inspect
import sys
import types
import unittest
from pathlib import Path

import mlib


class PackageLayoutTest(unittest.TestCase):
    def test_common_exports_use_current_definitions_after_reload(self):
        """遅延公開名を列挙・importでき、reload後に古いクラスを返さない。"""
        common = mlib.common
        self.assertTrue(set(common.__all__).issubset(dir(common)))
        previous = {name: getattr(common, name) for name in common.__all__}
        namespace = {}
        exec("from mlib.common import *", namespace)
        for name, value in previous.items():
            self.assertIs(namespace[name], value, name)
        mlib.reload()
        for name, value in previous.items():
            with self.subTest(export=name):
                current = getattr(mlib.common, name)
                if inspect.isclass(value) or inspect.isfunction(value):
                    self.assertIsNot(current, value)
                    owner = importlib.import_module(current.__module__)
                    self.assertIs(current, getattr(owner, name))

    def test_exports_and_command_identity_after_reload(self):
        importlib.reload(mlib)
        mlib.reload()
        for package, names in {
            "common": ("Namespace", "Selection", "DrivenKey", "Plugin", "ScriptJob", "ScriptJobs", "Deferred"),
            "decorator": ("undoChunk", "undoTransaction", "preservedSelection", "preservedSkinShape", "viewportOff", "nativeUnits"),
            "logger": ("getLogger", "debug", "info", "warning", "error", "print", "raiseWithNotify"),
            "util": ("legalizeName", "measure", "mirrorArguments"),
            "core": ("NodeRegistry", "reload_package"),
        }.items():
            module = importlib.import_module("mlib." + package)
            self.assertIs(getattr(mlib, package), module)
            for name in names:
                self.assertTrue(hasattr(module, name), (package, name))
        for name in ("getNode", "getPlug", "createNode", "ls", "delete", "duplicate", "select"):
            self.assertIs(getattr(mlib, name), getattr(mlib.cmds, name))
        self.assertIs(mlib.core.object.Object, importlib.import_module("mlib.core.object").Object)
        self.assertIs(mlib.core.extensions, importlib.import_module("mlib.core.extensions"))
        for name in ("Object", "extensions", "json"):
            self.assertFalse(hasattr(mlib, name))
            self.assertNotIn(name, mlib.__all__)
        for cls in (mlib.nodes.Node, mlib.plugs.Plug, mlib.components.Component):
            self.assertTrue(issubclass(cls, mlib.core.object.Object))
        for cls in (mlib.common.Selection, mlib.maths.Vector):
            self.assertFalse(issubclass(cls, mlib.core.object.Object))

    def test_reload_removes_obsolete_package_names(self):
        # 旧版を読み込んでいたセッションの残存モジュール参照を再現する。
        obsolete = ("_core", "scenes", "session", "context", "files", "editors", "general",
                    "namespaces", "plugins", "animation", "scene", "environment",
                    "ui", "events", "utils", "decorators", "object", "extensions", "json")
        obsolete_modules = ["mlib." + name for name in obsolete]
        obsolete_modules += ["mlib.scene.selection", "mlib.environment.plugin",
                             "mlib.ui.viewport", "mlib.events.scriptJob",
                             "mlib.utils.logger", "mlib.decorators.undo"]
        for name in obsolete:
            module = types.ModuleType("mlib." + name)
            sys.modules[module.__name__] = module
            setattr(mlib, name, module)
        for fullname in obsolete_modules:
            sys.modules[fullname] = types.ModuleType(fullname)
        mlib.Object = object
        mlib.reload()
        for name in obsolete:
            self.assertFalse(hasattr(mlib, name))
        for fullname in obsolete_modules:
            self.assertNotIn(fullname, sys.modules)
        self.assertFalse(hasattr(mlib, "Object"))
        self.assertNotIn("Object", mlib.__all__)
        self.assertIs(mlib.core.extensions, importlib.import_module("mlib.core.extensions"))

    def test_obsolete_import_paths_are_removed(self):
        """Object/extensionsと汎用関数の旧配置を互換入口として復活させない。"""
        for name in ("scene", "environment", "ui", "events", "utils", "decorators",
                     "object", "extensions", "_core", "common._fast", "common._safe",
                     "common.naming", "common.evaluation", "common.mirror", "core.flags",
                     "core.mathValue", "core.space", "core.unitValue", "core.typeHierarchy",
                     "core.bulkExecution", "core.commandResult"):
            with self.subTest(module=name), self.assertRaises(ModuleNotFoundError):
                importlib.import_module("mlib." + name)

    def test_library_does_not_import_rig_setups(self):
        """ライブラリ本体からmlrigへの逆依存を作らない。"""
        import ast
        root = Path(mlib.__file__).parent
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
                self.assertFalse(any(name == "mlrig" or name.startswith("mlrig.") for name in names), str(path))

    def test_public_directory_roles(self):
        """新しい機能は既存の役割へ置き、旧互換パッケージを復活させない。"""
        root = Path(mlib.__file__).parent
        packages = {path.name for path in root.iterdir()
                    if path.is_dir() and (path / "__init__.py").exists()
                    and not path.name.startswith("_")}
        self.assertEqual(packages, {"cmds", "nodes", "plugs", "maths",
                                   "common", "components", "core"})
        for name in ("decorator.py", "logger.py", "util.py", "core/object.py", "core/extensions.py"):
            self.assertTrue((root / name).is_file(), name)
        self.assertEqual(set(mlib.util.__all__), {"legalizeName", "measure", "mirrorArguments"})
        self.assertFalse(hasattr(mlib.common, "legalizeName"))
        self.assertTrue((root / "_docs").is_dir())
        self.assertFalse((root / "docs").exists())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
