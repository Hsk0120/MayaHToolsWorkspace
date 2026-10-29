"""mlib.core の Object・NodeRegistry・extensions・reload_package の約束を固定する仕様テスト(担当D)。

ObjectはMayaの対象を種類ごとに解決する入口、NodeRegistryは独立したインスタンスで
登録と祖先型の解決を確かめる。reload_packageは一時フォルダーの仮パッケージで依存順を確かめ、
mlib自体は再読み込みしない(同じセッションの他のテストの参照を壊さないため)。
"""

import importlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.components import Component
from mlib.components import Vertex
from mlib.core import NodeRegistry
from mlib.core import extensions
from mlib.core import reload_package
from mlib.core.object import Object
from mlib.nodes import Joint
from mlib.nodes import Node
from mlib.nodes import Transform
from mlib.plugs import Plug


class ObjectSpecTest(unittest.TestCase):
    """Objectの入力解決を固定する。"""

    def setUp(self):
        """一時名前空間に立方体とtransformを作る。"""
        self.ns = "mlibSpecDCore_" + uuid.uuid4().hex[:8]
        cmds.namespace(add=self.ns)
        self.cube = cmds.polyCube(name=self.ns + ":cube", constructionHistory=False)[0]
        self.shape = cmds.listRelatives(self.cube, shapes=True, fullPath=True)[0]
        self.node = cmds.createNode("transform", name=self.ns + ":node")

    def tearDown(self):
        """一時名前空間を中身ごと削除する。"""
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_common_base(self):
        """Node・Plug・Componentの共通基底。ルートへは再公開しない。"""
        self.assertTrue(issubclass(Node, Object))
        self.assertTrue(issubclass(Plug, Object))
        self.assertTrue(issubclass(Component, Object))
        self.assertFalse(hasattr(mlib, "Object"))

    def test_names_resolve_by_kind(self):
        """ノード名はNode、アトリビュート名はPlug、単一コンポーネント名はComponentへ解決する。"""
        node = Object(self.node)
        self.assertIsInstance(node, Transform)
        plug = Object(self.node + ".tx")
        self.assertIsInstance(plug, Plug)
        self.assertEqual(plug.getNode(), node)
        vertex = Object(self.cube + ".vtx[3]")
        self.assertIsInstance(vertex, Vertex)
        self.assertEqual(vertex.index, 3)
        self.assertEqual(vertex.shape.getFullName(), self.shape)

    def test_api_inputs(self):
        """MObject・MDagPathはNode、MPlugはPlug、(MDagPath, MObject)はComponentへ解決する。"""
        selection = om2.MSelectionList()
        selection.add(self.node)
        selection.add(self.node + ".ty")
        selection.add(self.cube + ".vtx[1]")
        self.assertIsInstance(Object(selection.getDependNode(0)), Node)
        self.assertIsInstance(Object(selection.getDagPath(0)), Node)
        self.assertIsInstance(Object(selection.getPlug(1)), Plug)
        component = Object(selection.getComponent(2))
        self.assertIsInstance(component, Vertex)
        self.assertEqual(component.index, 1)

    def test_existing_reference_is_returned_even_if_deleted(self):
        """既存のObjectは削除済みでも同じインスタンスを返す。asStringはstrと同じ名前。"""
        node = mlib.getNode(self.node)
        self.assertIs(Object(node), node)
        self.assertEqual(node.asString(), str(node))
        self.assertEqual(Object(self.node + ".tx").asString(), str(Object(self.node + ".tx")))
        cmds.delete(self.node)
        self.assertIs(Object(node), node)

    def test_errors(self):
        """空文字・範囲指定はValueError、未対応型はTypeError、存在しない・複数一致はRuntimeError。"""
        with self.assertRaises(ValueError):
            Object("")
        with self.assertRaises(ValueError):
            Object(self.cube + ".vtx[0:2]")
        with self.assertRaises(TypeError):
            Object(5)
        with self.assertRaises(TypeError):
            Object([self.node])
        with self.assertRaises(RuntimeError):
            Object(self.ns + ":missing")
        with self.assertRaises(RuntimeError):
            Object(self.ns + ":*")

    def test_subclass_construction_is_normal(self):
        """派生クラスの呼出しはObjectの振り分けを通らず、具体型の検証を行う。"""
        joint = cmds.createNode("joint", name=self.ns + ":joint")
        self.assertIs(type(Joint(joint)), Joint)
        with self.assertRaises(TypeError):
            Joint(self.node)


class NodeRegistrySpecTest(unittest.TestCase):
    """独立したNodeRegistryで登録・検証・祖先型の解決を固定する。"""

    class Fallback(object):
        """フォールバック用のクラス。"""

    class TransformLike(object):
        """transform用のクラス。"""

    class DagLike(object):
        """dagNode用のクラス。"""

    def test_exact_lookup_and_fallback(self):
        """完全一致は登録クラス、未登録はフォールバック。lookupはNoneを返す。"""
        registry = NodeRegistry(self.Fallback)
        registry.register("transform", self.TransformLike)
        self.assertIs(registry.wrapper_class("transform"), self.TransformLike)
        self.assertIs(registry.wrapper_class("transform"), self.TransformLike)
        self.assertIs(registry.wrapper_class("joint"), self.Fallback)
        self.assertIsNone(registry.lookup("joint"))
        self.assertIs(registry.lookup("transform"), self.TransformLike)

    def test_inherited_types_use_nearest_ancestor(self):
        """継承検索を有効にした表は、Mayaの型継承で最も近い登録済み祖先を返す。"""
        registry = NodeRegistry(self.Fallback, resolve_inherited_types=True)
        registry.register("dagNode", self.DagLike)
        registry.register("transform", self.TransformLike)
        self.assertIn("transform", cmds.nodeType("joint", isTypeName=True, inherited=True))
        self.assertIs(registry.wrapper_class("joint"), self.TransformLike)
        self.assertIs(registry.wrapper_class("mesh"), self.DagLike)
        self.assertIs(registry.wrapper_class("network"), self.Fallback)
        self.assertIs(registry.wrapper_class("mlibNoSuchType"), self.Fallback)
        self.assertIsNone(registry.lookup("joint"))

    def test_validation_and_atomic_replace(self):
        """キーは空でない文字列(非strはTypeError・空はValueError)、値はクラス。replaceは全件検証し、失敗時は現在の登録を保つ。"""
        registry = NodeRegistry(self.Fallback)
        with self.assertRaises(ValueError):
            registry.register("", self.TransformLike)
        for key in (None, 5):
            with self.assertRaises(TypeError):
                registry.register(key, self.TransformLike)
        with self.assertRaises(TypeError):
            registry.register("transform", self.TransformLike())
        registry.register("transform", self.TransformLike)
        registry.register("transform", self.DagLike)
        self.assertIs(registry.lookup("transform"), self.DagLike)
        with self.assertRaises(TypeError):
            registry.replace({"joint": self.TransformLike, "mesh": "notAClass"})
        self.assertIs(registry.lookup("transform"), self.DagLike)
        self.assertIsNone(registry.lookup("joint"))
        registry.replace({"joint": self.TransformLike})
        self.assertIsNone(registry.lookup("transform"))
        registry.clear()
        self.assertIsNone(registry.lookup("joint"))
        self.assertIs(registry.wrapper_class("joint"), self.Fallback)

    def test_global_node_registry(self):
        """本体のNode登録表はjointをJointへ、未登録の型を登録済みの祖先型へ解決する。"""
        registry = Node._registry
        self.assertIs(registry.lookup("joint"), Joint)
        self.assertIs(registry.wrapper_class("transform"), Transform)
        chain = cmds.nodeType("joint", isTypeName=True, inherited=True)
        self.assertEqual(chain[-1], "joint")
        resolved = registry.wrapper_class("mlibNoSuchType")
        self.assertIs(resolved, Node)


class ExtensionsSpecTest(unittest.TestCase):
    """extensionsの照会が記録を変更しないことを固定する。"""

    def test_status_is_a_copy(self):
        """status()は初期化記録のコピーを返し、変更しても記録は変わらない。"""
        first = extensions.status()
        self.assertIsInstance(first, dict)
        first["mlib_spec_d_fake"] = {"state": "loaded"}
        for record in first.values():
            record["state"] = "changed"
        self.assertNotIn("mlib_spec_d_fake", extensions.status())
        self.assertNotIn("changed", [record.get("state") for record in extensions.status().values()])

    def test_diagnostics_shape_and_no_side_effects(self):
        """getDiagnostics()は拡張名ごとにinitialization・available・reasonを返し、記録を変えない。"""
        before = extensions.status()
        diagnostics = extensions.getDiagnostics()
        self.assertIsInstance(diagnostics, dict)
        for name, record in diagnostics.items():
            self.assertTrue(name.startswith("mlib_"))
            self.assertEqual(set(record), {"initialization", "available", "reason"})
            self.assertIn(record["available"], (True, False, None))
        self.assertEqual(extensions.status(), before)
        self.assertEqual(sorted(extensions.__all__), ["getDiagnostics", "status"])


class ReloadPackageSpecTest(unittest.TestCase):
    """reload_packageの依存順・新規モジュールの取込み・削除済みモジュールの除去を固定する。"""

    def setUp(self):
        """一時フォルダーに仮パッケージを作り、探索パスへ加える。"""
        self.root = Path(tempfile.mkdtemp(prefix="mlib_spec_d_reload_"))
        self.package = "mlib_spec_d_reload_" + uuid.uuid4().hex[:8]
        folder = self.root / self.package
        folder.mkdir()
        (folder / "__init__.py").write_text("", encoding="utf-8")
        # zbaseが依存先、aleafが依存元。名前順とは逆の依存にする。
        (folder / "zbase.py").write_text("VALUE = 1\n", encoding="utf-8")
        (folder / "aleaf.py").write_text("from . import zbase\nVALUE = zbase.VALUE + 1\n", encoding="utf-8")
        (folder / "obsolete.py").write_text("VALUE = 0\n", encoding="utf-8")
        sys.path.insert(0, str(self.root))
        importlib.invalidate_caches()
        importlib.import_module(self.package + ".aleaf")
        importlib.import_module(self.package + ".obsolete")

    def tearDown(self):
        """仮パッケージをsys.modulesと探索パスから除き、フォルダーを消す。"""
        for name in list(sys.modules):
            if name == self.package or name.startswith(self.package + "."):
                del sys.modules[name]
        sys.path.remove(str(self.root))
        shutil.rmtree(str(self.root), ignore_errors=True)

    def test_dependency_order_new_and_removed_modules(self):
        """依存先を先に再読み込みし、新規ファイルを取り込み、削除したファイルを除く。"""
        folder = self.root / self.package
        (folder / "obsolete.py").unlink()
        (folder / "added.py").write_text("VALUE = 3\n", encoding="utf-8")
        (folder / "zbase.py").write_text("VALUE = 10\n", encoding="utf-8")
        for cached in folder.glob("__pycache__/*"):
            cached.unlink()
        reloaded = reload_package(self.package)
        self.assertIsInstance(reloaded, tuple)
        names = [module.__name__ for module in reloaded]
        self.assertLess(names.index(self.package + ".zbase"), names.index(self.package + ".aleaf"))
        self.assertIn(self.package + ".added", names)
        self.assertNotIn(self.package + ".obsolete", sys.modules)
        self.assertFalse(hasattr(sys.modules[self.package], "obsolete"))
        self.assertEqual(sys.modules[self.package + ".aleaf"].VALUE, 11)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
