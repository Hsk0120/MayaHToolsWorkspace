"""10.4.0 で足したルートからのクラス取得(``mlib.Joint`` 等)の契約を固定する。

- 各パッケージの公開クラスを ``mlib.<クラス名>`` で取得でき、所属パッケージと同じクラスを返す。
- 名前が重なるときの優先順位、定数・関数・Object を対象にしないこと。
- 登録の無い型の生成クラス、``__all__``・``dir``・import 文、再読み込み後に現在のクラスを返すこと。
- 実行時の対象と、スタブ(``mlib/__init__.pyi``)に書き出した再公開が一致すること。
"""

import ast
import unittest
from pathlib import Path

import mlib
mlib.reload()

PACKAGES = ("nodes", "plugs", "components", "maths", "common")


class RootClassTest(unittest.TestCase):
    """``mlib.<クラス名>`` の取得と公開。"""

    def test_classes_match_packages(self):
        """各パッケージの公開クラスを、所属パッケージと同じオブジェクトで返す。"""
        self.assertIs(mlib.Joint, mlib.nodes.Joint)
        self.assertIs(mlib.Plug, mlib.plugs.Plug)
        self.assertIs(mlib.Vertex, mlib.components.Vertex)
        self.assertIs(mlib.Vector, mlib.maths.Vector)
        self.assertIs(mlib.Namespace, mlib.common.Namespace)
        self.assertIs(mlib.ProgressCancelled, mlib.common.ProgressCancelled)
        for name, package_name in mlib._classes.items():
            with self.subTest(name=name):
                value = getattr(mlib, name)
                self.assertIsInstance(value, type)
                self.assertIs(value, getattr(getattr(mlib, package_name), name))

    def test_all_package_classes_are_covered(self):
        """各パッケージの __all__ のクラスは、名前の重なりを除いて全てルートから取得できる。"""
        for package_name in PACKAGES:
            package = getattr(mlib, package_name)
            for name in package.__all__:
                value = getattr(package, name)
                if not isinstance(value, type) or name == "Object":
                    continue
                with self.subTest(package=package_name, name=name):
                    self.assertIn(name, mlib._classes)
                    self.assertIn(name, mlib.__all__)

    def test_non_classes_and_object_are_excluded(self):
        """定数・関数・Object はルートから取得できない。"""
        for name in ("LOADED", "MISSING", "progressBar", "units", "easing", "Object"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(mlib, name))
                self.assertNotIn(name, mlib.__all__)
        self.assertTrue(issubclass(mlib.Node, mlib.core.object.Object))

    def test_priority(self):
        """名前が重なるときは _CLASS_PACKAGES の先にあるパッケージを優先する。"""
        class Joint(object):
            pass

        class Vector(object):
            pass

        plugs, common = mlib.plugs, mlib.common
        saved = list(plugs.__all__)
        try:
            plugs.Joint = Joint
            plugs.__all__ = saved + ["Joint"]
            self.assertEqual(mlib._class_sources()["Joint"], "nodes")
        finally:
            plugs.__all__ = saved
            del plugs.Joint
        saved = dict(common._exports)
        try:
            common._exports["Vector"] = ("version", "Version")
            common.__all__ = sorted(common._exports)
            self.assertEqual(mlib._class_sources()["Vector"], "maths")
        finally:
            common._exports.clear()
            common._exports.update(saved)
            common.__all__ = sorted(common._exports)
        self.assertEqual(mlib._CLASS_PACKAGES, PACKAGES)

    def test_generated_classes(self):
        """登録の無い型の生成クラスも mlib.nodes と同じクラスを返す。認識しない名前はAttributeError。"""
        self.assertIs(mlib.PointLight, mlib.nodes.PointLight)
        self.assertNotIn("PointLight", mlib.__all__)
        for name in ("MlibNoSuchTypeXYZ", "joint", "pointLight", "_Joint"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(mlib, name))
        with self.assertRaisesRegex(AttributeError, "module 'mlib' has no attribute 'MlibNoSuchTypeXYZ'"):
            mlib.MlibNoSuchTypeXYZ

    def test_all_dir_and_import(self):
        """__all__・dir・import文・star importでクラスを扱える。"""
        self.assertIn("Joint", mlib.__all__)
        self.assertIn("Joint", dir(mlib))
        self.assertIn("ls", dir(mlib))
        self.assertEqual(len(mlib.__all__), len(set(mlib.__all__)))
        namespace = {}
        exec("from mlib import Joint, Vector", namespace)
        self.assertIs(namespace["Joint"], mlib.nodes.Joint)
        namespace = {}
        exec("from mlib import *", namespace)
        self.assertIs(namespace["Transform"], mlib.nodes.Transform)
        self.assertIs(namespace["ls"], mlib.cmds.ls)

    def test_reload_returns_current_class(self):
        """再読み込み後は新しい定義のクラスを返す。"""
        before = mlib.Joint
        mlib.reload()
        self.assertIsNot(mlib.Joint, before)
        self.assertIs(mlib.Joint, mlib.nodes.Joint)
        self.assertIs(mlib.PointLight, mlib.nodes.PointLight)

    def test_stub_matches_runtime(self):
        """スタブの再公開と __all__ が、実行時の対象と一致する。"""
        path = Path(mlib.__file__).with_suffix(".pyi")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        exported = {}
        stub_all = None
        for stmt in tree.body:
            if isinstance(stmt, ast.ImportFrom) and stmt.level == 1 and stmt.module in PACKAGES:
                for alias in stmt.names:
                    if alias.asname == alias.name:
                        exported[alias.name] = stmt.module
            elif isinstance(stmt, ast.Assign) and stmt.targets[0].id == "__all__":
                stub_all = ast.literal_eval(stmt.value)
        self.assertEqual(exported, mlib._classes)
        self.assertEqual(stub_all, mlib.__all__)


if __name__ == "__main__":
    unittest.main()
