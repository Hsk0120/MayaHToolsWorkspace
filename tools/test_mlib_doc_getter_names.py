"""Maya不要で、正式get/is名と基礎7コマンドのSphinx検査を確認する。"""

from pathlib import Path
import pickle
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from check_mlib_doc_getter_names import (
    _COMMAND_NAMES, _canonical_definitions, _signature_parameters, check,
)


class GetterDocumentationTest(unittest.TestCase):
    """実名の掲載だけを検査し、省略名への投影や補完をしない。"""

    def setUp(self):
        """Mayaを必要としない最小ソースとビルド結果を準備する。"""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.package = self.root / "mlib"
        (self.package / "nodes").mkdir(parents=True)
        (self.package / "nodes/example.py").write_text(
            "class Example:\n"
            "    def getValue(self, *, unit=None):\n        return 1\n"
            "    def isReady(self, strict=False):\n        return True\n"
            "    def length(self):\n        return 1\n", encoding="utf-8")
        self.build = self.root / "html"
        (self.build / ".doctrees").mkdir(parents=True)
        self.objects, self.references, self.pages = {}, {}, {}
        for name in ("getValue", "isReady"):
            identifier = "mlib.nodes.example.Example." + name
            self.objects[identifier] = SimpleNamespace(display=True)
            self.add_entry(identifier, "example", "self, *, unit=None")
        for name in _COMMAND_NAMES:
            for prefix in ("mlib.", "mlib.cmds."):
                self.add_entry(prefix + name, "commands/" + name, "value=None, *, fast=False")

    def add_entry(self, identifier, page, parameters):
        """正式アンカーと署名だけを持つページを組み立てる。"""
        self.references[identifier] = SimpleNamespace(docname=page, node_id=identifier)
        self.pages[page] = self.pages.get(page, "") + (
            f'<dl><dt id="{identifier}">{identifier}({parameters})¶</dt></dl>'
        )

    def save(self):
        """検証用のAutoAPI環境とHTMLを保存する。"""
        environment = SimpleNamespace(
            autoapi_all_objects=self.objects,
            domaindata={"py": {"objects": self.references}},
        )
        with (self.build / ".doctrees/environment.pickle").open("wb") as stream:
            pickle.dump(environment, stream)
        for name, html in self.pages.items():
            path = self.build / (name + ".html")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")

    def errors(self):
        """保存したfixtureを通常の検査入口へ渡す。"""
        self.save()
        return check(self.build, self.package)

    def test_canonical_definitions_and_commands_are_displayed(self):
        """正式get/isと7コマンドは名前の投影なしで照合できる。"""
        (self.package / "cmds").mkdir()
        (self.package / "cmds/getPlug.py").write_text(
            "def getPlug(value):\n    return value\n", encoding="utf-8")
        definitions, forbidden = _canonical_definitions(self.package)
        self.assertEqual(definitions, {
            "mlib.nodes.example.Example.getValue", "mlib.nodes.example.Example.isReady",
        })
        self.assertEqual(forbidden, {"mlib.nodes.example.Example.ready"})
        self.assertNotIn("mlib.nodes.example.Example.length", definitions)
        self.assertEqual(self.errors(), [])

    def test_missing_or_hidden_canonical_object_is_reported(self):
        """正式名を非表示にしたり短名だけを残したビルドを拒否する。"""
        identifier = "mlib.nodes.example.Example.isReady"
        self.objects[identifier].display = False
        self.assertTrue(any("AutoAPI" in error for error in self.errors()))
        self.objects.pop(identifier)
        self.assertTrue(any(identifier in error for error in self.errors()))

    def test_missing_reference_and_html_anchor_are_reported(self):
        """AutoAPIに存在しても参照登録とHTMLを別々に確認する。"""
        identifier = "mlib.nodes.example.Example.getValue"
        self.references.pop(identifier)
        self.assertTrue(any("公開参照" in error for error in self.errors()))
        self.add_entry(identifier, "example", "self")
        self.pages["example"] = "<p>no method anchors</p>"
        self.assertTrue(any("HTMLアンカー" in error for error in self.errors()))

    def test_removed_alias_entry_is_rejected(self):
        """終了した判定省略名の再登録を検出する。"""
        identifier = "mlib.nodes.example.Example.ready"
        self.objects[identifier] = SimpleNamespace(display=True)
        self.assertTrue(any("判定省略入口" in error for error in self.errors()))

    def test_same_name_independent_api_is_preserved(self):
        """Plugin.loadedのような別処理の同名APIを判定別名と混同しない。"""
        path = self.package / "nodes/example.py"
        path.write_text(path.read_text(encoding="utf-8") +
                        "    def ready(self):\n        return []\n", encoding="utf-8")
        _, forbidden = _canonical_definitions(self.package)
        self.assertEqual(forbidden, set())
        self.assertEqual(self.errors(), [])

    def test_reintroduced_forwarder_is_not_independent_api(self):
        """正式判定をそのまま呼ぶだけの短名は、明示defでも終了対象とする。"""
        path = self.package / "nodes/example.py"
        path.write_text(path.read_text(encoding="utf-8") +
                        "    def ready(self, *args, **kwargs):\n"
                        "        return self.isReady(*args, **kwargs)\n", encoding="utf-8")
        _, forbidden = _canonical_definitions(self.package)
        self.assertIn("mlib.nodes.example.Example.ready", forbidden)

    def test_command_signatures_preserve_defaults_and_keyword_boundaries(self):
        """root/cmdsの二重署名は既定値とキーワード境界も一致させる。"""
        html = ('<dl><dt id="mlib.getPlug">mlib.getPlug(value, *, strict=True)¶</dt>'
                '<dt id="mlib.cmds.getPlug">mlib.cmds.getPlug(value, *, strict=True)¶</dt></dl>')
        self.assertEqual(_signature_parameters(html, "mlib.getPlug"),
                         _signature_parameters(html, "mlib.cmds.getPlug"))
        self.assertIsNone(_signature_parameters(html, "mlib.getNode"))
        self.pages["commands/getPlug"] = self.pages["commands/getPlug"].replace(
            "mlib.cmds.getPlug(value=None", "mlib.cmds.getPlug(value=1")
        self.assertTrue(any("構文・引数" in error for error in self.errors()))

    def test_each_command_needs_both_public_references(self):
        """get以外を含む7コマンドすべてで二つの公開入口を確認する。"""
        self.references.pop("mlib.cmds.select")
        self.assertTrue(any("select" in error for error in self.errors()))


if __name__ == "__main__":
    unittest.main()
