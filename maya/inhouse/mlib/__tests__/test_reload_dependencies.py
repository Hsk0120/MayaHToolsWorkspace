"""reloadの依存順と初期化責務を小さなパッケージで検証する。"""

import importlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import maya.cmds as cmds
import mlib


class ReloadDependenciesTest(unittest.TestCase):
    """依存の直接参照・循環・削除と、標準登録表の再初期化を保つ。"""

    def test_direct_dependencies_and_cycles(self):
        """依存先を先にし、循環しても重複や無限再帰を起こさない。"""
        reloader = importlib.import_module("mlib._core.reload")
        a, b, c = (types.ModuleType("reloadProbe." + name) for name in "abc")
        a.dependency = b
        b.dependency = c
        modules = {item.__name__: item for item in (a, b, c)}
        with patch.dict(sys.modules, modules):
            self.assertEqual(reloader._reload_order(modules), [c.__name__, b.__name__, a.__name__])
            c.dependency = a
            order = reloader._reload_order(modules)
            self.assertEqual(set(order), set(modules))
            self.assertEqual(len(order), 3)

    def test_discovery_removes_deleted_modules_and_parent_bindings(self):
        """削除ファイルはsys.modulesと親パッケージの両方から解除する。"""
        reloader = importlib.import_module("mlib._core.reload")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "reloadProbe"
            root.mkdir()
            (root / "__init__.py").write_text("", encoding="utf-8")
            child = root / "child.py"
            child.write_text("value = 7\n", encoding="utf-8")
            sys.path.insert(0, directory)
            try:
                package = importlib.import_module("reloadProbe")
                importlib.import_module("reloadProbe.child")
                self.assertEqual(package.child.value, 7)
                child.unlink()
                reloader.reload_package("reloadProbe")
                self.assertNotIn("reloadProbe.child", sys.modules)
                self.assertFalse(hasattr(package, "child"))
            finally:
                sys.path.remove(directory)
                for name in tuple(sys.modules):
                    if name == "reloadProbe" or name.startswith("reloadProbe."):
                        del sys.modules[name]

    def test_root_initialization_rebuilds_registries_without_bootstrap(self):
        """定義更新はreloader、登録表の再構築はルートが一度ずつ担当する。"""
        cmds.file(new=True, force=True)
        name = cmds.createNode("transform")
        for full in (False, True):
            mlib.nodes.Node._registry.clear()
            mlib.plugs.Plug._registry.clear()
            with patch.object(importlib, "reload", wraps=importlib.reload) as reload_module:
                mlib.reload() if full else importlib.reload(mlib)
            bootstraps = [call[0][0].__name__ for call in reload_module.call_args_list
                          if call[0][0].__name__ == "mlib._core.bootstrap"]
            self.assertEqual(bootstraps, [])
            self.assertNotIn("mlib._core.bootstrap", sys.modules)
            node = mlib.getNode(name)
            self.assertIsInstance(node, mlib.nodes.Transform)
            self.assertIsInstance(node.getPlug("translateX"), mlib.plugs.DoubleLinearPlug)
            self.assertFalse(hasattr(mlib, "getAttr"))

    def test_invalid_standard_registration_keeps_both_current_registries(self):
        """後半のPlug宣言が不正でも、Node側だけ新しい表へ切り替えない。"""
        previous = mlib.nodes.Node._registry, mlib.plugs.Plug._registry
        try:
            with patch.dict(mlib.plugs._WRAPPER_CLASSES, {"invalidFixture": object()}):
                with self.assertRaises(TypeError):
                    importlib.reload(mlib)
            self.assertIs(mlib.nodes.Node._registry, previous[0])
            self.assertIs(mlib.plugs.Plug._registry, previous[1])
        finally:
            importlib.reload(mlib)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
