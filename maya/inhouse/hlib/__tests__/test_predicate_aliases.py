"""is省略入口の委譲・型・方向フラグと既存の同名APIを検証する。"""

import ast
import importlib
import inspect
import re
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import hlib
import maya.cmds as cmds


_PRESERVED_NAMES = {
    ("Node", "isType"), ("Nodes", "isType"),
    ("Node", "isRoot"), ("Nodes", "isRoot"),
    ("Plug", "isSource"), ("Plug", "isElement"),
    ("Plugin", "isLoaded"), ("Scene", "isNew"),
    ("WorkspaceLayout", "isCurrent"),
}


def _predicate_definitions():
    """実装の判定定義を列挙し、外部の棚卸しファイルへ依存しない。"""
    root = Path(hlib.__file__).resolve().parent
    for path in sorted(root.rglob("*.py")):
        if any(part in {"__tests__", "_docs"} for part in path.parts):
            continue
        module = "hlib." + ".".join(path.relative_to(root).with_suffix("").parts)
        for statement in ast.parse(path.read_text(encoding="utf-8-sig")).body:
            owner = statement.name if isinstance(statement, ast.ClassDef) else None
            for method in statement.body if owner else [statement]:
                if isinstance(method, ast.FunctionDef) and re.fullmatch(r"is[A-Z]\w*", method.name):
                    yield module, owner, method.name


class PredicateAliasesTest(unittest.TestCase):
    """省略名が元の判定契約を保ち、取得・編集APIへ干渉しないことを確認する。"""

    def setUp(self):
        """空シーンと接続検査用のノードを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        self.first = hlib.createNode("transform", name="predicateAliasFirst")
        self.second = hlib.createNode("transform", name="predicateAliasSecond")

    def test_declared_and_inherited_aliases_keep_canonical_signatures_and_flags(self):
        """全判定を棚卸しし、追加漏れ・衝突上書き・署名欠落を検出する。"""
        definitions = list(_predicate_definitions())
        self.assertGreaterEqual(len(definitions), 68)
        added = 0
        for module_name, owner_name, name in definitions:
            if (owner_name, name) in _PRESERVED_NAMES:
                continue
            module = importlib.import_module(module_name)
            owner = module if owner_name is None else getattr(module, owner_name)
            short = name[2].lower() + name[3:]
            with self.subTest(owner=owner_name, method=name):
                predicate, alias = getattr(owner, name), getattr(owner, short)
                self.assertEqual(alias.__name__, short)
                self.assertEqual(alias.__hlib_getter_name__, name)
                self.assertEqual(inspect.signature(alias), inspect.signature(predicate))
                self.assertEqual(alias.__annotations__, predicate.__annotations__)
                self.assertEqual(alias.__hlib_flag_aliases__, getattr(predicate, "__hlib_flag_aliases__", {}))
                self.assertEqual(alias.__hlib_maya_command__, getattr(predicate, "__hlib_maya_command__", None))
            added += 1
        self.assertGreaterEqual(added, 59)
        for package_name in ("nodes", "plugs", "maths", "common"):
            package = getattr(hlib, package_name)
            for public_name in package.__all__:
                cls = getattr(package, public_name)
                if not inspect.isclass(cls):
                    continue
                for base in cls.__mro__:
                    if not base.__module__.startswith("hlib."):
                        continue
                    for name in base.__dict__:
                        if not re.fullmatch(r"is[A-Z]\w*", name) or (base.__name__, name) in _PRESERVED_NAMES:
                            continue
                        short = name[2].lower() + name[3:]
                        with self.subTest(public_class=public_name, method=name):
                            self.assertEqual(getattr(cls, short).__hlib_getter_name__, name)
                            self.assertEqual(inspect.signature(getattr(cls, short)), inspect.signature(getattr(cls, name)))

    def test_instance_replacement_and_subclass_override_are_resolved_at_call_time(self):
        """元の判定を固定せず、raw引数と派生実装を呼出し時に引き継ぐ。"""
        marker = object()
        plug = self.first.getPlug("translateX")
        with patch.object(plug, "isConnected", return_value=marker) as predicate:
            self.assertIs(plug.connected(src=False, destination=True), marker)
            predicate.assert_called_once_with(src=False, destination=True)

        class DerivedTransform(hlib.nodes.Transform):
            """派生型の判定が継承した省略入口から呼ばれることを調べる。"""

            def isLocked(self, *args, **kwargs):
                """検査用の引数を変更せず返す。"""
                return args, kwargs

        derived = object.__new__(DerivedTransform)
        self.assertEqual(derived.locked(4, marker="raw"), ((4,), {"marker": "raw"}))

    def test_connection_aliases_keep_direction_booleans_and_source_getter(self):
        """方向・別名競合と、既存sourceのPlug返却を実接続で確認する。"""
        src, dst = self.first.getPlug("translateX"), self.second.getPlug("translateX")
        dst.connect(src)
        self.assertTrue(src.connected(src=False, dst=True))
        self.assertFalse(src.connected(src=True, dst=False))
        self.assertTrue(dst.connected(source=True, destination=False))
        self.assertTrue(src.connectedTo(dst, source=False, destination=True))
        self.assertFalse(dst.connectedTo(src, src=False, dst=True))
        self.assertFalse(dst.connected(src=False, dst=False))
        self.assertEqual(dst.source(), src)
        self.assertTrue(src.isSource())
        self.assertTrue(dst.destination())
        with self.assertRaises(TypeError):
            dst.connected(src=True, source=True)
        with self.assertRaises(TypeError):
            src.connectedTo(dst, dst=True, destination=True)
        with self.assertRaises(TypeError):
            dst.connected(src=1)

    def test_collection_aliases_keep_order_empty_results_and_prevalidation(self):
        """複数形とcallEachが本体の署名を事前検査し、戻り値順を保つ。"""
        nodes = hlib.nodes.Transforms([self.first, self.second])
        cmds.lockNode(str(self.second), lock=True)
        self.assertEqual(nodes.valid(), [True, True])
        self.assertEqual(nodes.locked(), [False, True])
        self.assertEqual(nodes.callEach("locked", [(), ()]), [False, True])
        self.assertEqual(hlib.nodes.Nodes().valid(), [])
        self.assertEqual(hlib.nodes.Nodes().callEach("valid", []), [])
        first = Mock(return_value=False)
        with patch.object(self.first, "isLocked", first):
            with self.assertRaises(TypeError):
                nodes.callEach("locked", [(), (1,)])
        first.assert_not_called()
        cmds.lockNode(str(self.second), lock=False)

    def test_removed_references_and_plug_structure_keep_original_results(self):
        """削除済み参照と未実体化配列要素の判定に評価を追加しない。"""
        scalar = self.first.getPlug("translateX")
        array = self.first.getPlug("worldMatrix")
        child = self.first.getPlug("translateX")
        self.assertTrue(array.array())
        self.assertTrue(self.first.getPlug("translate").compound())
        self.assertTrue(child.child())
        self.assertTrue(array[0].isElement())
        self.assertEqual(array.element(0), array.getElement(0))
        self.first.delete()
        self.assertFalse(self.first.valid())
        self.assertEqual(self.first.alive(), self.first.isAlive())
        self.assertFalse(scalar.valid())
        with self.assertRaises(RuntimeError):
            scalar.locked()

    def test_static_and_module_aliases_keep_binding_and_current_state(self):
        """静的入口はクラス/個体/派生から呼べ、Undo照会は状態を変えない。"""
        cls = hlib.common.Viewport
        instance = object.__new__(cls)
        self.assertEqual(inspect.signature(cls.enabled), inspect.signature(cls.isEnabled))
        self.assertEqual(inspect.signature(instance.enabled), inspect.signature(instance.isEnabled))
        predicate = Mock(return_value=True)
        with patch.object(cls, "isEnabled", staticmethod(predicate)):
            self.assertTrue(cls.enabled())
            self.assertTrue(instance.enabled())
        self.assertEqual(predicate.call_count, 2)
        undo = importlib.import_module("hlib.common.undo")
        self.assertEqual(undo.enabled(), undo.isEnabled())
        cmds.undoInfo(state=False)
        try:
            self.assertFalse(undo.enabled())
            self.assertFalse(cmds.undoInfo(query=True, state=True))
        finally:
            cmds.undoInfo(state=True)

    def test_math_aliases_keep_tolerance_results_and_native_names(self):
        """hlibで定義した等価判定は許容誤差と既存is名を維持する。"""
        pairs = (
            (hlib.maths.Vector(1, 2, 3), hlib.maths.Vector(1 + 1e-8, 2, 3)),
            (hlib.maths.Matrix(), hlib.maths.Matrix()),
            (hlib.maths.EulerRotate(), hlib.maths.EulerRotate()),
            (hlib.maths.Transformation(), hlib.maths.Transformation()),
        )
        for value, other in pairs:
            with self.subTest(value=type(value).__name__):
                self.assertEqual(value.equivalent(other), value.isEquivalent(other))
                self.assertEqual(value.equivalent(other, tolerance=1e-6), value.isEquivalent(other, tolerance=1e-6))
                self.assertEqual(value.isEquivalent.__name__, "isEquivalent")

    def test_colliding_names_keep_existing_getters_and_scene_creation(self):
        """同名の取得・編集APIと、派生クラス側のroot/elementを維持する。"""
        self.assertEqual(self.first.type(), "transform")
        self.assertTrue(self.first.isType("dagNode"))
        self.assertEqual(self.first.root(), self.first.getRoot())
        self.assertTrue(self.first.isRoot())
        transforms = hlib.nodes.Transforms([self.first])
        self.assertEqual(transforms.root(), transforms.getRoot())
        self.assertEqual(transforms.isRoot(), [True])
        scene = hlib.common.Scene()
        self.assertTrue(scene.isNew())
        self.assertIs(scene.new(force=True, prompt=False), scene)
        self.assertIsInstance(hlib.common.Plugin.loaded(), list)
        layout = hlib.common.WorkspaceLayout
        self.assertEqual(layout.current.__func__.__hlib_getter_name__, "getCurrent")
        self.assertEqual(hlib.nodes.Reference.root.__hlib_getter_name__, "getRoot")


if __name__ == "__main__":
    unittest.main()
