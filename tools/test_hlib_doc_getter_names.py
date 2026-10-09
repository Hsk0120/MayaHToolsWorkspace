"""Maya不要で、Sphinx取得・判定APIの表記・署名・参照の保護を検証する。"""

import ast
from collections import namedtuple
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "maya/inhouse/hlib"
sys.path.insert(0, str(_PACKAGE_ROOT / "_docs"))

from _getterNames import GetterDocumentation, collect_getter_aliases
from check_hlib_doc_getter_names import _signature_parameters


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
        module = ".".join(("hlib", *parts))
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

    def test_catalog_covers_explicit_aliases_and_excludes_native_methods(self):
        """全独自getterの実宣言を検出し、標準getterを除外する。"""
        aliases = collect_getter_aliases(_PACKAGE_ROOT)
        self.assertGreaterEqual(len(aliases), 566)
        self.assertGreaterEqual(len(self.docs.command_modules), 13)
        self.assertEqual({pair.getter for pair in aliases.values()
                          if pair.getter.rsplit(".", 1)[-1].startswith("get")}, _defined_getters())
        self.assertIn("hlib.nodes.node.Node.plug", aliases)
        self.assertIn("hlib.cmds.plug.plug", aliases)
        self.assertNotIn("hlib.maths.matrix.Matrix.element", aliases)
        self.assertNotIn("get", self.docs.short_names)
        self.assertNotIn("getu", self.docs.short_names)

    def test_component_acronyms_keep_existing_lowercase_aliases(self):
        """UV/CVの正式getterを、既存のuv/cv入口のまま文書化する。"""
        aliases = collect_getter_aliases(_PACKAGE_ROOT)
        expected = {
            "hlib.nodes.mesh.Mesh.uv": "hlib.nodes.mesh.Mesh.getUV",
            "hlib.nodes.mesh.Mesh.uvs": "hlib.nodes.mesh.Mesh.getUVs",
            "hlib.nodes.nurbsCurve.NurbsCurve.cv": "hlib.nodes.nurbsCurve.NurbsCurve.getCV",
            "hlib.nodes.nurbsCurve.NurbsCurve.cvs": "hlib.nodes.nurbsCurve.NurbsCurve.getCVs",
        }
        for alias, getter in expected.items():
            with self.subTest(alias=alias):
                self.assertEqual(aliases[alias].getter, getter)
                self.assertEqual(self.docs.getters[getter], alias)
        self.assertNotIn("hlib.nodes.mesh.Mesh.uV", aliases)
        self.assertNotIn("hlib.nodes.nurbsCurve.NurbsCurve.cV", aliases)

    def test_predicate_catalog_uses_explicit_definitions_and_imported_functions(self):
        """isの名前だけで推測せず、通常defの明示委譲とimport先を照合する。"""
        with TemporaryDirectory() as directory:
            package = Path(directory) / "hlib"
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
        self.assertEqual(set(aliases), {"hlib.aliases.enabled", "hlib.aliases.Predicate.valid"})
        self.assertEqual(aliases["hlib.aliases.enabled"].getter, "hlib.source.isEnabled")
        self.assertEqual(aliases["hlib.aliases.enabled"].parameters, frozenset({"flag"}))
        self.assertEqual(aliases["hlib.aliases.Predicate.valid"].parameters, frozenset({"self", "strict"}))

    def test_predicate_method_copies_directions_signature_help_and_legacy_reference(self):
        """判定入口も正式名から引数と説明を移し、元is名の参照を残す。"""
        identifier = "hlib.plugs.plug.Plug"
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
        entry = entry_type("autoapi/hlib/plugs/plug/Plug", alias.id, "method", False)
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
            package = Path(directory) / "hlib"
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
            "Plugin.isLoaded() / hlib.common.Plugin.isLoaded() / plugin.isLoaded()\n"
            "WorkspaceLayout.isCurrent() / hlib.common.WorkspaceLayout.isCurrent()\n"
            "layout.isCurrent() / workspace_layout.isCurrent() / workspaceLayout.isCurrent()\n"
            "Reference.isLoaded() / reference.isLoaded() / Scene.isCurrent() / scene.isCurrent()\n"
            "unknown.isLoaded() / unknown.isCurrent() / isLoaded() / isCurrent()\n"
        )
        result = docs.rewrite_docstring(before)
        for preserved in (
            "Plugin.isLoaded()", "hlib.common.Plugin.isLoaded()", "plugin.isLoaded()",
            "WorkspaceLayout.isCurrent()", "hlib.common.WorkspaceLayout.isCurrent()",
            "layout.isCurrent()", "workspace_layout.isCurrent()", "workspaceLayout.isCurrent()",
            "unknown.isLoaded()", "unknown.isCurrent()", " / isLoaded() / isCurrent()",
        ):
            self.assertIn(preserved, result)
        self.assertIn("Reference.loaded() / reference.loaded() / Scene.current() / scene.current()", result)
        for owner, name, expected in (
            ("hlib.common.plugin.Plugin.isLoaded", "isLoaded", "isLoaded"),
            ("hlib.common.workspaceLayout.WorkspaceLayout.activate", "isCurrent", "isCurrent"),
            ("hlib.nodes.reference.Reference.load", "isLoaded", "loaded"),
            ("hlib.common.scene.Scene.open", "isCurrent", "current"),
        ):
            with self.subTest(owner=owner, name=name):
                text = f"self.{name}() cls.{name}() {name}なら"
                self.assertEqual(docs.rewrite_docstring(text, owner=owner),
                                 f"self.{expected}() cls.{expected}() {expected}なら")

    def test_math_equivalent_references_require_hlib_definition_or_owner(self):
        """数学値の同名native判定を、hlibで明示した入口と混同しない。"""
        before = (
            "hlib.maths.matrix.Matrix.isEquivalent(other) / hlib.maths.Matrix.isEquivalent(other)\n"
            "Matrix.isEquivalent(other) / Transformation.isEquivalent(other)\n"
            "self.isEquivalent(other) / cls.isEquivalent(other) / isEquivalent(other)\n"
            "om2.MMatrix.isEquivalent(other) / om2.MVector(v).isEquivalent(other)\n"
            "MQuaternion.isEquivalent(other) / Quaternion.isEquivalent(other)\n"
            "hlib.maths.Quaternion.isEquivalent(other) / native.isEquivalent(other)\n"
        )
        result = self.docs.rewrite_docstring(before, owner="hlib.maths.matrix.Matrix.inverse")
        for short in (
            "hlib.maths.matrix.Matrix.equivalent(other)", "hlib.maths.Matrix.equivalent(other)",
            "Matrix.equivalent(other)", "Transformation.equivalent(other)",
            "self.equivalent(other)", "cls.equivalent(other)", " / equivalent(other)",
        ):
            self.assertIn(short, result)
        for preserved in (
            "om2.MMatrix.isEquivalent(other)", "om2.MVector(v).isEquivalent(other)",
            "MQuaternion.isEquivalent(other)", "Quaternion.isEquivalent(other)",
            "hlib.maths.Quaternion.isEquivalent(other)", "native.isEquivalent(other)",
        ):
            self.assertIn(preserved, result)
        self.assertEqual(self.docs.rewrite_docstring("self.isEquivalent(other) isEquivalent(other)",
                                                   owner="hlib.nodes.node.Node"),
                         "self.isEquivalent(other) isEquivalent(other)")

    def test_docstrings_use_short_references_and_preserve_flags_native_calls_and_keys(self):
        """getPlug引数、Maya標準、OpenMaya、JSONキーを取得メソッド名と区別する。"""
        before = (
            "hlib.getPlug('node.tx') / hlib.cmds.getAttr('node.tx') / node.getPlug('tx')\n"
            ":meth:`Node.getPlug` :meth:`getPlug` / getFullName()\n"
            "cmds.getAttr('node.tx') / maya.cmds.getAttr('node.tx')\n"
            "om2.MFnDependencyNode.getName() / MFnSkinCluster.getWeights()\n"
            "MItMeshVertex.getNormal() / pm.getAttr('node.tx')\n"
            "matrix.getElement(0, 0) / plug.get() / plug.getu()\n"
            "getPlug=False / :param getPlug: / getPlug (bool)\n"
            "{'getName': 1, \"getPlug\": 2}\n"
            "getFullNameで取得する。getPlug引数。\n"
            ":func:`hlib.cmds.getAttr.getAttr`\n"
        )
        result = self.docs.rewrite_docstring(before, {"getPlug"})
        self.assertIn("hlib.plug('node.tx') / hlib.cmds.attr('node.tx') / node.plug('tx')", result)
        self.assertIn(":meth:`Node.plug` :meth:`getPlug` / fullName()", result)
        self.assertIn("fullNameで取得する。getPlug引数。", result)
        self.assertIn(":func:`hlib.cmds.attr.attr`", result)
        for preserved in (
            "cmds.getAttr('node.tx')", "maya.cmds.getAttr('node.tx')",
            "om2.MFnDependencyNode.getName()", "MFnSkinCluster.getWeights()",
            "MItMeshVertex.getNormal()", "pm.getAttr('node.tx')",
            "matrix.getElement(0, 0)", "plug.get()", "plug.getu()", "getPlug=False",
            ":param getPlug:", "getPlug (bool)", "'getName'", '"getPlug"',
        ):
            self.assertIn(preserved, result)

    def test_short_method_receives_canonical_signature_docstring_and_return_type(self):
        """短名の汎用委譲文と可変引数を正式getterの情報へ置き換える。"""
        identifier = "hlib.nodes.node.Node"
        getter = _object(identifier + ".getPlug", args="self, name", docstring="node.getPlug(name)\n:param name: アトリビュート名。")
        getter.return_annotation = "Plug"
        alias = _object(identifier + ".plug", args="self, *args, **kwargs", docstring="正式getterへ委譲する。")
        owner = _object(identifier, children=[getter, alias])
        owner.app = SimpleNamespace(env=SimpleNamespace(autoapi_all_objects={getter.id: getter}))
        self.docs.skip_member(None, "class", owner.id, owner, False, None)
        self.assertTrue(self.docs.skip_member(None, "method", getter.id, getter, False, None))
        self.assertIsNone(self.docs.skip_member(None, "method", alias.id, alias, False, None))
        self.docs.prepare_object(owner)
        self.assertEqual(alias.args, "self, name")
        self.assertEqual(alias.return_annotation, "Plug")
        self.assertEqual(alias.docstring, "node.plug(name)\n:param name: アトリビュート名。")
        self.assertEqual(alias.hlib_getter_id, getter.id)

    def test_plug_context_distinguishes_its_get_element_from_native_math(self):
        """Plug内のbare/self参照を省略し、同じ説明内の数学受け手を保つ。"""
        text = (
            "getElement() self.getElement() cls.getElement() array_plug.getElement()\n"
            "matrix.getElement() Matrix.getElement() om2.MMatrix.getElement()"
        )
        result = self.docs.rewrite_docstring(text, owner="hlib.plugs.arrayPlug.ArrayPlug")
        self.assertIn("element() self.element() cls.element() array_plug.element()", result)
        self.assertIn("matrix.getElement() Matrix.getElement() om2.MMatrix.getElement()", result)
        self.assertEqual(self.docs.rewrite_docstring("getElement() self.getElement()", owner="hlib.maths.matrix.Matrix"), "getElement() self.getElement()")

    def test_chained_hlib_calls_use_short_names_and_openmaya_chains_are_preserved(self):
        """取得戻り値/型生成の後続メソッドを揃え、標準APIの同名を保つ。"""
        text = "mesh.getTransform().getPlug('translateX').getFullName() / Joints(joints).getSkinClusters() / om2.MFnSkinCluster(node).getWeights()"
        result = self.docs.rewrite_docstring(text)
        self.assertIn("mesh.transform().plug('translateX').fullName()", result)
        self.assertIn("Joints(joints).skinClusters()", result)
        self.assertIn("om2.MFnSkinCluster(node).getWeights()", result)

    def test_short_command_copies_function_and_module_help(self):
        """省略コマンドにはモジュールの使用例と関数の詳細が揃う。"""
        getter = _object("hlib.cmds.getViewport.getViewport", args="panel=None", docstring="Viewportを取得する。\n:param panel: modelPanel。")
        source = _object("hlib.cmds.getViewport", children=[getter], docstring="with hlib.getViewport().suspend():")
        alias = _object("hlib.cmds.viewport.viewport", args="*args, **kwargs", docstring="正式getterへ委譲する。")
        owner = _object("hlib.cmds.viewport", children=[alias], docstring="getViewportへ委譲するget省略入口。")
        reexport = _object(source.id, docstring=":param panel: 関数の引数説明。")
        owner.app = SimpleNamespace(env=SimpleNamespace(
            autoapi_all_objects={getter.id: getter, source.id: reexport},
            autoapi_objects={source.id: source},
        ))
        self.docs.prepare_object(owner)
        self.assertEqual(alias.args, "panel=None")
        self.assertEqual(alias.docstring, getter.docstring)
        self.assertEqual(owner.docstring, "with hlib.viewport().suspend():")
        self.assertFalse(self.docs.preferred_command(source))
        self.assertTrue(self.docs.preferred_command(owner))
        self.assertEqual(self.docs.short_command(source), "viewport")

    def test_existing_get_references_resolve_to_short_help(self):
        """正式名のxrefと省略コマンドの完全名が同じ説明へ解決する。"""
        entry_type = namedtuple("ObjectEntry", "docname node_id objtype aliased")
        entry = entry_type("autoapi/hlib/nodes/node/Node", "hlib.nodes.node.Node.plug", "method", False)
        function_entry = entry_type("autoapi/hlib/cmds/plug/index", "hlib.plug", "function", False)
        cmds_entry = function_entry._replace(node_id="hlib.cmds.plug")
        alias = _object("hlib.nodes.node.Node.plug")
        alias.hlib_getter_id = "hlib.nodes.node.Node.getPlug"
        domain = SimpleNamespace(objects={alias.id: entry, "hlib.plug": function_entry,
                                          "hlib.cmds.plug": cmds_entry})
        env = SimpleNamespace(autoapi_all_objects={alias.id: alias}, get_domain=lambda name: domain)
        self.docs.register_reference_aliases(None, env)
        self.assertEqual(domain.objects[alias.hlib_getter_id].node_id, alias.id)
        self.assertTrue(domain.objects[alias.hlib_getter_id].aliased)
        for name in ("hlib.getPlug", "hlib.cmds.getPlug.getPlug", "hlib.cmds.plug.plug"):
            self.assertEqual(domain.objects[name].node_id, "hlib.plug")
        for name in ("hlib.cmds.plug", "hlib.cmds.getPlug"):
            self.assertEqual(domain.objects[name].node_id, "hlib.cmds.plug")
            self.assertEqual(domain.objects[name].docname, function_entry.docname)
        self.assertTrue(domain.objects["hlib.cmds.getPlug"].aliased)

    def test_command_signature_comparison_keeps_defaults_and_keyword_boundaries(self):
        """二つの公開名の引数表示を照合し、名前・アンカー・本文と区別する。"""
        html = (
            '<dl class="py function"><dt id="hlib.plug"><span>hlib.plug</span>'
            '<span>(</span><em>value</em>, <em>*, strict=True</em>)¶</dt>'
            '<dt id="hlib.cmds.plug"><span>hlib.cmds.plug</span>'
            '<span>(</span><em>value</em>, <em>*, strict=True</em>)¶</dt>'
            '<dd>異なる関数の説明(value, strict=False)</dd></dl>'
            '<dl><dt id="hlib.attr">hlib.attr(value, *, strict=False)¶</dt></dl>'
            '<span id="hlib.getPlug"></span>'
        )
        self.assertEqual(_signature_parameters(html, "hlib.plug"),
                         _signature_parameters(html, "hlib.cmds.plug"))
        self.assertNotEqual(_signature_parameters(html, "hlib.plug"),
                            _signature_parameters(html, "hlib.attr"))
        self.assertIsNone(_signature_parameters(html, "hlib.getPlug"))
        self.assertIsNone(_signature_parameters(html, "hlib.cmds.attr"))


if __name__ == "__main__":
    unittest.main()
