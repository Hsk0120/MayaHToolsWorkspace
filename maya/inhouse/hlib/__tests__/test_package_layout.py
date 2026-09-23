"""公開パッケージと再読み込み後のコマンド入口を検証する。"""

import importlib
import sys
import types
import unittest

import hlib


class PackageLayoutTest(unittest.TestCase):
    def test_exports_and_command_identity_after_reload(self):
        importlib.reload(hlib)
        hlib.reload()
        for package, names in {
            "files": ("Scene", "list_references"),
            "namespaces": ("Namespace",),
            "plugins": ("Plugin", "Plugins"),
            "units": ("Units", "native_units"),
            "workspace": ("Workspace",),
            "editors": ("TimeSlider", "Viewport", "Outliner"),
        }.items():
            module = importlib.import_module("hlib." + package)
            self.assertIs(getattr(hlib, package), module)
            for name in names:
                self.assertTrue(hasattr(module, name), (package, name))
        self.assertIsInstance(hlib.scene(), hlib.files.Scene)
        self.assertIsInstance(hlib.timeSlider(), hlib.editors.TimeSlider)
        for name in ("scene", "timeSlider", "viewport", "outliner"):
            self.assertIs(getattr(hlib, name), getattr(hlib.cmds, name))

    def test_reload_removes_obsolete_package_names(self):
        # 旧版を読み込んでいたセッションの残存モジュール参照を再現する。
        for name in ("scenes", "session"):
            module = types.ModuleType("hlib." + name)
            sys.modules[module.__name__] = module
            setattr(hlib, name, module)
        hlib.reload()
        for name in ("scenes", "session"):
            self.assertFalse(hasattr(hlib, name))
            self.assertNotIn("hlib." + name, sys.modules)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
