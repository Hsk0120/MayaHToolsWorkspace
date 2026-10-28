"""正式is判定の動作を維持し、終了した省略入口を再公開しない。"""

import ast
import importlib
import inspect
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from maya import cmds
import maya.api.OpenMaya as om2
import mlib


_PRESERVED_NAMES = {
    ("Node", "isType"),
    ("Node", "isRoot"),
    ("Plug", "isSource"), ("Plug", "isMultiElement"),
    ("Plugin", "isLoaded"),
}


def _predicate_definitions():
    """製品の正式判定を、Mayaを追加評価せずソースから列挙する。"""
    root = Path(mlib.__file__).resolve().parent
    for path in sorted(root.rglob("*.py")):
        if any(part in {"__tests__", "_docs"} for part in path.parts):
            continue
        module = "mlib." + ".".join(path.relative_to(root).with_suffix("").parts)
        for statement in ast.parse(path.read_text(encoding="utf-8-sig")).body:
            owner = statement.name if isinstance(statement, ast.ClassDef) else None
            for method in statement.body if owner else [statement]:
                if isinstance(method, ast.FunctionDef) and re.fullmatch(r"is[A-Z]\w*", method.name):
                    yield module, owner, method.name


class PredicateAliasesTest(unittest.TestCase):
    """型・方向・保持順・削除検出は正式判定へ集約して確認する。"""

    def setUp(self):
        """空シーンと接続検査用ノードを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        self.first = mlib.createNode("transform", name="canonicalPredicateFirst")
        self.second = mlib.createNode("transform", name="canonicalPredicateSecond")

    def test_canonical_predicates_exist_without_short_aliases(self):
        """正式判定を型ごとに残し、同名の別APIを除く省略入口は公開しない。"""
        definitions = list(_predicate_definitions())
        # isChildOf・sameInstance・isJoint の廃止(mlib 2.0)で 3 件、
        # DagPose・Transformation 等の縮小(mlib 3.0)で 4 件、複数形の一括転送の廃止(mlib 3.0)で 10 件減った。
        self.assertGreaterEqual(len(definitions), 47)
        for module_name, owner_name, name in definitions:
            module = importlib.import_module(module_name)
            owner = module if owner_name is None else getattr(module, owner_name)
            with self.subTest(owner=owner_name, method=name):
                self.assertTrue(callable(getattr(owner, name)))
                if (owner_name, name) in _PRESERVED_NAMES:
                    continue
                short = name[2].lower() + name[3:]
                self.assertNotIn(short, vars(owner))
                if owner_name is not None:
                    with self.assertRaises(AttributeError):
                        inspect.getattr_static(owner, short)
        self.assertFalse((Path(mlib.__file__).parent / "core/getterAlias.py").exists())

    def test_canonical_override_and_instance_replacement_remain_available(self):
        """通常のPython差替えと派生メソッドを追加する方法を維持する。"""
        marker = object()
        plug = self.first.getPlug("translateX")
        with patch.object(plug, "isConnected", return_value=marker) as predicate:
            self.assertIs(plug.isConnected(source=False, destination=True), marker)
            predicate.assert_called_once_with(source=False, destination=True)

        class DerivedTransform(mlib.nodes.Transform):
            """正式判定を通常のdefで追加する検証用派生型。"""

            def isLocked(self, *args, **kwargs):
                """受け取った独自引数をそのまま返す。"""
                return args, kwargs

        derived = object.__new__(DerivedTransform)
        self.assertEqual(derived.isLocked(4, marker="raw"), ((4,), {"marker": "raw"}))

    def test_connections_keep_direction_booleans_and_source_getter(self):
        """正式判定は接続方向・bool検証を維持する。"""
        src, dst = self.first.getPlug("translateX"), self.second.getPlug("translateX")
        dst.connect(src)
        self.assertTrue(src.isConnected(source=False, destination=True))
        self.assertFalse(src.isConnected(source=True, destination=False))
        self.assertTrue(dst.isConnected(source=True, destination=False))
        self.assertTrue(src.isConnectedTo(dst, source=False, destination=True))
        self.assertFalse(dst.isConnectedTo(src, source=False, destination=True))
        self.assertFalse(dst.isConnected(source=False, destination=False))
        self.assertEqual(dst.getSource(), src)
        self.assertTrue(src.isSource())
        self.assertTrue(dst.isDestination())
        with self.assertRaises(TypeError):
            dst.isConnected(source=1)

    def test_removed_references_and_plug_structure_keep_results(self):
        """参照の有効性と未実体化要素の構造判定に評価を追加しない。"""
        scalar = self.first.getPlug("translateX")
        array = self.first.getPlug("worldMatrix")
        self.assertTrue(array.isMulti())
        self.assertTrue(self.first.getPlug("translate").isCompound())
        self.assertTrue(scalar.isChild())
        self.assertTrue(array[0].isMultiElement())
        self.assertEqual(array.getElement(0), array.getElement(0))
        self.first.delete()
        self.assertFalse(self.first.isValid())
        self.assertFalse(scalar.isValid())
        with self.assertRaises(RuntimeError):
            scalar.isLocked()

    def test_module_predicate_keeps_current_undo_state(self):
        """正式Undo判定は現在の記録設定を変更しない。"""
        undo = importlib.import_module("mlib.common.undo")
        self.assertTrue(undo.isEnabled())
        cmds.undoInfo(state=False)
        try:
            self.assertFalse(undo.isEnabled())
            self.assertFalse(cmds.undoInfo(query=True, state=True))
        finally:
            cmds.undoInfo(state=True)

    def test_math_predicates_keep_tolerance_and_native_names(self):
        """数学値の正式等価判定は戻り値と許容誤差を維持する。"""
        pairs = (
            (mlib.maths.Vector(1, 2, 3), mlib.maths.Vector(1 + 1e-8, 2, 3), om2.MVector),
            (mlib.maths.Matrix(), mlib.maths.Matrix(), om2.MMatrix),
            (mlib.maths.EulerRotate(), mlib.maths.EulerRotate(), om2.MEulerRotation),
        )
        for value, other, native_type in pairs:
            with self.subTest(value=type(value).__name__):
                tolerance = inspect.signature(value.isEquivalent).parameters["tolerance"].default
                if native_type is not None:
                    expected = native_type(value).isEquivalent(native_type(other), tolerance)
                    self.assertEqual(value.isEquivalent(other), expected)
                else:
                    self.assertTrue(value.isEquivalent(other))
                self.assertTrue(value.isEquivalent(value))
                self.assertTrue(value.isEquivalent(other, tolerance=1e-6))
                self.assertEqual(value.isEquivalent.__name__, "isEquivalent")

    def test_colliding_names_and_dynamic_attributes_keep_existing_meanings(self):
        """取得API・Plugin.loadedと動的アトリビュート参照を変更しない。"""
        self.assertEqual(self.first.getType(), "transform")
        self.assertTrue(self.first.isType("dagNode"))
        self.assertTrue(self.first.isRoot())
        self.assertEqual(self.first.getRoot(), self.first)
        self.assertIsInstance(mlib.common.Plugin.loaded(), list)
        self.assertTrue(callable(mlib.nodes.Reference.getRoot))
        attribute = self.first.addAttr("valid", attributeType="bool")
        self.assertEqual(self.first.valid, attribute)
        self.assertTrue(self.first.isValid())


if __name__ == "__main__":
    unittest.main()
