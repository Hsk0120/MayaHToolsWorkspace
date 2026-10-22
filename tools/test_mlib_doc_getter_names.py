"""Maya不要で、Sphinx取得・判定APIの表記・署名・参照の保護を検証する。"""

import ast
from collections import namedtuple
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "maya/inhouse/mlib"
sys.path.insert(0, str(_PACKAGE_ROOT / "_docs"))

from _getterNames import GetterDocumentation, collect_getter_aliases
from check_mlib_doc_getter_names import _signature_parameters


def _object(identifier, *, children=(), docstring="", args="", original_path=None):
    """AutoAPIがテンプレートへ渡す表示情報だけをfixtureで表す。"""
    data = {"args": []}
    if original_path:
        data["original_path"] = original_path
    return SimpleNamespace(
        id=identifier, short_name=identifier.rsplit(".", 1)[-1],
        obj=data, children=list(children), docstring=docstring,
        args=args, overloads=[], return_annotation=None, type_params="",
    )


def _defined_getters():
    """省略名宣言とは独立に、製品の独自getter定義をASTから列挙する。"""
    getters = set()
    for path in _PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(_PACKAGE_ROOT)
        if any(part in {"_docs", "__tests__", "maths"} for part in relative.parts):
            continue
        parts = relative.with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        module = ".".join(("mlib", *parts))
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for statement in tree.body:
            owner = module + "." + statement.name if isinstance(statement, ast.ClassDef) else module
            members = statement.body if isinstance(statement, ast.ClassDef) else [statement]
            for member in members:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and re.fullmatch(r"get[A-Z][A-Za-z0-9_]*", member.name):
                    getters.add(owner + "." + member.name)
    return getters


class GetterDocumentationTest(unittest.TestCase):
    """実在する委譲だけを使い、製品定義を変更せずに説明を移す。"""

    @classmethod
    def setUpClass(cls):
        """Mayaを読み込まず製品の明示宣言を収集する。"""
        cls.docs = GetterDocumentation(_PACKAGE_ROOT)



    def test_canonical_getters_are_displayed_without_short_aliases(self):
        """getの署名と説明は正式名のままSphinxへ掲載する。"""
        aliases = collect_getter_aliases(_PACKAGE_ROOT)
        self.assertTrue(aliases)
        self.assertTrue(all(pair.getter.rsplit(".", 1)[-1].startswith("is") for pair in aliases.values()))
        self.assertEqual(self.docs.command_modules, {})
        for identifier in ("mlib.nodes.node.Node.getPlug", "mlib.nodes.mesh.Mesh.getUVs", "mlib.cmds.getNode.getNode"):
            obj = _object(identifier, args="self, value=None", docstring="get付きの正式取得。")
            self.assertIsNone(self.docs.skip_member(None, "method", identifier, obj, False, None))
            obj.app = SimpleNamespace(env=SimpleNamespace(autoapi_all_objects={identifier: obj}))
            self.docs.prepare_object(obj)
            self.assertEqual(obj.args, "self, value=None")
            self.assertEqual(obj.docstring, "get付きの正式取得。")

    def test_canonical_references_and_native_names_are_preserved(self):
        """getを省略名へ書き換えずMaya標準名も維持する。"""
        source = "node.getPlug('translate').get() / mesh.getCVs() / om2.MVector().length()"
        self.assertEqual(self.docs.rewrite_docstring(source, owner="mlib.nodes.node.Node"), source)

    def test_predicate_catalog_uses_explicit_definitions_and_imported_functions(self):
        """isの名前だけで推測せず、通常defの明示委譲とimport先を照合する。"""
        with TemporaryDirectory() as directory:
            package = Path(directory) / "mlib"
            package.mkdir()
            (package / "source.py").write_text(
                "def isEnabled(flag=False):\n    return flag\n", encoding="utf-8")
            (package / "aliases.py").write_text(
                "from .source import isEnabled as _is_enabled\n"
                "@_is_alias(_is_enabled)\n"
                "def enabled(*args, **kwargs):\n    return _is_enabled(*args, **kwargs)\n"
                "class Predicate:\n"
                "    def isValid(self, strict=True):\n        return strict\n"
                "    @_is_alias(isValid)\n"
                "    def valid(self, *args, **kwargs):\n        return self.isValid(*args, **kwargs)\n"
                "    def isSkipped(self):\n        return True\n", encoding="utf-8")
            aliases = collect_getter_aliases(package)
        self.assertEqual(set(aliases), {"mlib.aliases.enabled", "mlib.aliases.Predicate.valid"})
        self.assertEqual(aliases["mlib.aliases.enabled"].getter, "mlib.source.isEnabled")
        self.assertEqual(aliases["mlib.aliases.enabled"].parameters, frozenset({"flag"}))
        self.assertEqual(aliases["mlib.aliases.Predicate.valid"].parameters, frozenset({"self", "strict"}))

    def test_predicate_method_copies_directions_signature_help_and_legacy_reference(self):
        """判定入口も正式名から引数と説明を移し、元is名の参照を残す。"""
        identifier = "mlib.plugs.plug.Plug"
        getter = _object(identifier + ".isConnected", args="self, *, src=True, dst=True",
                         docstring="plug.isConnected(src=False)\n:param src: 入力接続を調べる。")
        getter.return_annotation = "bool"
        getter.overloads = [("self, *, source=True, destination=True", "bool")]
        alias = _object(identifier + ".connected", args="self, *args, **kwargs",
                        docstring="正式判定へ委譲する。")
        owner = _object(identifier, children=[getter, alias])
        owner.app = SimpleNamespace(env=SimpleNamespace(autoapi_all_objects={getter.id: getter}))
        self.docs.skip_member(None, "class", owner.id, owner, False, None)
        self.assertTrue(self.docs.skip_member(None, "method", getter.id, getter, False, None))
        self.assertIsNone(self.docs.skip_member(None, "method", alias.id, alias, False, None))
        self.docs.prepare_object(owner)
        self.assertEqual(alias.args, getter.args)
        self.assertEqual(alias.return_annotation, getter.return_annotation)
        self.assertEqual(alias.overloads, getter.overloads)
        self.assertEqual(alias.docstring, "plug.connected(src=False)\n:param src: 入力接続を調べる。")
        entry_type = namedtuple("ObjectEntry", "docname node_id objtype aliased")
        entry = entry_type("autoapi/mlib/plugs/plug/Plug", alias.id, "method", False)
        domain = SimpleNamespace(objects={alias.id: entry})
        environment = SimpleNamespace(autoapi_all_objects={alias.id: alias}, get_domain=lambda name: domain)
        self.docs.register_reference_aliases(None, environment)
        self.assertEqual(domain.objects[getter.id].node_id, alias.id)
        self.assertTrue(domain.objects[getter.id].aliased)

    def test_predicate_references_preserve_native_api_flags_and_saved_keys(self):
        """is判定も省略名へ揃え、MPlugプロパティや標準メソッド・保存名を保つ。"""
        before = (
            "node.isValid() / :meth:`Node.isValid` / isValidなら\n"
            "plug.isConnected(src=False, dst=True) / :param isConnected: / isConnected=False\n"
            "om2.MObjectHandle.isValid() / MPlug.isConnected / MFnDependencyNode.isLocked\n"
            "cmds.isConnected('source.tx', 'target.tx') / pm.isConnected()\n"
            "om2.MObjectHandle(node).isValid() / {'isValid': True}\n"
            "{'isConnected': True, \"isLocked\": False}\n"
        )
        result = self.docs.rewrite_docstring(before, {"isConnected"})
        self.assertIn("node.valid() / :meth:`Node.valid` / validなら", result)
        self.assertIn("plug.connected(src=False, dst=True)", result)
        for preserved in (
            ":param isConnected:", "isConnected=False", "om2.MObjectHandle.isValid()",
            "MPlug.isConnected", "MFnDependencyNode.isLocked", "cmds.isConnected(",
            "pm.isConnected()", "om2.MObjectHandle(node).isValid()", "'isValid'",
            "'isConnected'", '"isLocked"',
        ):
            self.assertIn(preserved, result)

    def test_predicate_reference_context_preserves_conflicting_classes(self):
        """別クラスの短名を、既存メソッドと衝突して省略していない判定へ適用しない。"""
        with TemporaryDirectory() as directory:
            package = Path(directory) / "mlib"
            for module, class_name, method, alias in (
                ("common/plugin", "Plugin", "isLoaded", None),
                ("common/workspaceLayout", "WorkspaceLayout", "isCurrent", None),
                ("nodes/reference", "Reference", "isLoaded", "loaded"),
                ("common/scene", "Scene", "isCurrent", "current"),
            ):
                path = package / (module + ".py")
                path.parent.mkdir(parents=True, exist_ok=True)
                source = f"class {class_name}:\n    def {method}(self):\n        return True\n"
                if alias:
                    source += (f"    @_is_alias({method})\n"
                               f"    def {alias}(self, *args, **kwargs):\n"
                               f"        return self.{method}(*args, **kwargs)\n")
                path.write_text(source, encoding="utf-8")
            docs = GetterDocumentation(package)
        before = (
            "Plugin.isLoaded() / mlib.common.Plugin.isLoaded() / plugin.isLoaded()\n"
            "WorkspaceLayout.isCurrent() / mlib.common.WorkspaceLayout.isCurrent()\n"
            "layout.isCurrent() / workspace_layout.isCurrent() / workspaceLayout.isCurrent()\n"
            "Reference.isLoaded() / reference.isLoaded() / Scene.isCurrent() / scene.isCurrent()\n"
            "unknown.isLoaded() / unknown.isCurrent() / isLoaded() / isCurrent()\n"
        )
        result = docs.rewrite_docstring(before)
        for preserved in (
            "Plugin.isLoaded()", "mlib.common.Plugin.isLoaded()", "plugin.isLoaded()",
            "WorkspaceLayout.isCurrent()", "mlib.common.WorkspaceLayout.isCurrent()",
            "layout.isCurrent()", "workspace_layout.isCurrent()", "workspaceLayout.isCurrent()",
            "unknown.isLoaded()", "unknown.isCurrent()", " / isLoaded() / isCurrent()",
        ):
            self.assertIn(preserved, result)
        self.assertIn("Reference.loaded() / reference.loaded() / Scene.current() / scene.current()", result)
        for owner, name, expected in (
            ("mlib.common.plugin.Plugin.isLoaded", "isLoaded", "isLoaded"),
            ("mlib.common.workspaceLayout.WorkspaceLayout.activate", "isCurrent", "isCurrent"),
            ("mlib.nodes.reference.Reference.load", "isLoaded", "loaded"),
            ("mlib.common.scene.Scene.open", "isCurrent", "current"),
        ):
            with self.subTest(owner=owner, name=name):
                text = f"self.{name}() cls.{name}() {name}なら"
                self.assertEqual(docs.rewrite_docstring(text, owner=owner),
                                 f"self.{expected}() cls.{expected}() {expected}なら")

    def test_math_equivalent_references_require_mlib_definition_or_owner(self):
        """数学値の同名native判定を、mlibで明示した入口と混同しない。"""
        before = (
            "mlib.maths.matrix.Matrix.isEquivalent(other) / mlib.maths.Matrix.isEquivalent(other)\n"
            "Matrix.isEquivalent(other) / Transformation.isEquivalent(other)\n"
            "self.isEquivalent(other) / cls.isEquivalent(other) / isEquivalent(other)\n"
            "om2.MMatrix.isEquivalent(other) / om2.MVector(v).isEquivalent(other)\n"
            "MQuaternion.isEquivalent(other) / Quaternion.isEquivalent(other)\n"
            "mlib.maths.Quaternion.isEquivalent(other) / native.isEquivalent(other)\n"
        )
        result = self.docs.rewrite_docstring(before, owner="mlib.maths.matrix.Matrix.inverse")
        for short in (
            "mlib.maths.matrix.Matrix.equivalent(other)", "mlib.maths.Matrix.equivalent(other)",
            "Matrix.equivalent(other)", "Transformation.equivalent(other)",
            "self.equivalent(other)", "cls.equivalent(other)", " / equivalent(other)",
        ):
            self.assertIn(short, result)
        for preserved in (
            "om2.MMatrix.isEquivalent(other)", "om2.MVector(v).isEquivalent(other)",
            "MQuaternion.isEquivalent(other)", "Quaternion.isEquivalent(other)",
            "mlib.maths.Quaternion.isEquivalent(other)", "native.isEquivalent(other)",
        ):
            self.assertIn(preserved, result)
        self.assertEqual(self.docs.rewrite_docstring("self.isEquivalent(other) isEquivalent(other)",
                                                   owner="mlib.nodes.node.Node"),
                         "self.isEquivalent(other) isEquivalent(other)")







    def test_command_signature_comparison_keeps_defaults_and_keyword_boundaries(self):
        """二つの公開名の引数表示を照合し、名前・アンカー・本文と区別する。"""
        html = (
            '<dl class="py function"><dt id="mlib.plug"><span>mlib.plug</span>'
            '<span>(</span><em>value</em>, <em>*, strict=True</em>)¶</dt>'
            '<dt id="mlib.cmds.plug"><span>mlib.cmds.plug</span>'
            '<span>(</span><em>value</em>, <em>*, strict=True</em>)¶</dt>'
            '<dd>異なる関数の説明(value, strict=False)</dd></dl>'
            '<dl><dt id="mlib.attr">mlib.attr(value, *, strict=False)¶</dt></dl>'
            '<span id="mlib.getPlug"></span>'
        )
        self.assertEqual(_signature_parameters(html, "mlib.plug"),
                         _signature_parameters(html, "mlib.cmds.plug"))
        self.assertNotEqual(_signature_parameters(html, "mlib.plug"),
                            _signature_parameters(html, "mlib.attr"))
        self.assertIsNone(_signature_parameters(html, "mlib.getPlug"))
        self.assertIsNone(_signature_parameters(html, "mlib.cmds.attr"))


if __name__ == "__main__":
    unittest.main()
