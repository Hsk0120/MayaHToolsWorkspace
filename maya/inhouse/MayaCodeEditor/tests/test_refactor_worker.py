"""元ファイルを触らない抽出/移動とUnicode位置の回帰テスト。"""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("refactor_worker", ROOT / "tools/refactor_worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
sys.path.insert(0, str(Path(os.environ["LOCALAPPDATA"]) / "MayaCodeEditor/language-server/refactor-1.15.0"))


class RefactorTests(unittest.TestCase):
    """コピー解析の実結果、参照更新、元データ保持を検証する。"""

    def setUp(self):
        """専用の小規模プロジェクトを作る。"""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source.py"
        self.source.write_text("def total(x, y):\n    return x + y\n", encoding="utf-8")

    def request(self, action, text=None, **kwargs):
        """未保存本文を含む要求を組む。"""
        return {"root": str(self.root), "path": str(self.source), "action": action,
                "overlays": {str(self.source): text} if text is not None else {}, **kwargs}

    def test_variable_unicode_and_no_execution(self):
        """絵文字を含む選択の変数抽出。トップレベル副作用は実行しない。"""
        sentinel = self.root / "executed"
        text = "# 😀\nraise RuntimeError('must not execute')\ndef total(x, y):\n    return x + y\n"
        start = len(text[:text.index("x + y")].encode("utf-16-le")) // 2
        result = worker.calculate(self.request("variable", text, start=start, end=start + 5, name="sum_value"))
        after = result["edit"]["changes"][self.source.as_uri()][0]["newText"]
        self.assertIn("sum_value = x + y", after)
        self.assertIn("return sum_value", after)
        self.assertFalse(sentinel.exists())
        self.assertEqual(self.source.read_text(encoding="utf-8"), "def total(x, y):\n    return x + y\n")

    def test_function(self):
        """選択した処理を引数付き関数へ抽出する。"""
        text = "def run(x):\n    y = x * 2\n    print(y)\n"
        start = text.index("y =")
        result = worker.calculate(self.request("function", text, start=start, end=text.index("    print"), name="double_value"))
        after = result["edit"]["changes"][self.source.as_uri()][0]["newText"]
        self.assertIn("def double_value(x)", after)
        self.assertIn("y = double_value(x)", after)
        compile(after, "source.py", "exec")

    def test_move_updates_imports(self):
        """移動先と利用側のimportも編集案に含める。"""
        destination = self.root / "target.py"
        destination.write_text("", encoding="utf-8")
        consumer = self.root / "use.py"
        consumer.write_text("from source import total\nvalue = total(1, 2)\n", encoding="utf-8")
        result = worker.calculate(self.request("move", start=6, destination=str(destination)))
        changes = result["edit"]["changes"]
        self.assertIn("def total", changes[destination.as_uri()][0]["newText"])
        self.assertIn("target", changes[consumer.as_uri()][0]["newText"])
        self.assertEqual(destination.read_text(encoding="utf-8"), "")

    def test_imports(self):
        """未使用importを取り除き、利用中のimportを残す。"""
        text = "import os\nimport sys\nprint(sys.version)\n"
        result = worker.calculate(self.request("imports", text))
        after = result["edit"]["changes"][self.source.as_uri()][0]["newText"]
        self.assertNotIn("import os", after)
        self.assertIn("import sys", after)

    def test_rename_module_updates_imports(self):
        """改名とimport変更を提案し、元のディスクを維持する。"""
        consumer = self.root / "use.py"
        consumer.write_text("from source import total\nvalue = total(1, 2)\n", encoding="utf-8")
        result = worker.calculate(self.request("rename_module", name="renamed"))
        self.assertEqual(result["edit"]["documentChanges"], [{"kind": "rename", "oldUri": self.source.as_uri(),
                                                             "newUri": (self.root / "renamed.py").as_uri()}])
        self.assertIn("from renamed import total", result["edit"]["changes"][consumer.as_uri()][0]["newText"])
        self.assertTrue(self.source.exists())
        self.assertFalse((self.root / "renamed.py").exists())

    def test_move_new_and_collision(self):
        """新規モジュールへの移動案と衝突の拒否。"""
        target = self.root / "new_module.py"
        result = worker.calculate(self.request("move_new", start=6, destination=str(target)))
        self.assertEqual(result["edit"]["documentChanges"], [{"kind": "create", "uri": target.as_uri()}])
        self.assertIn("def total", result["edit"]["changes"][target.as_uri()][0]["newText"])
        self.assertFalse(target.exists())
        target.write_text("# preserve", encoding="utf-8")
        for action, kwargs in (("move_new", {"start": 6, "destination": str(target)}),
                               ("rename_module", {"name": "new_module"})):
            with self.assertRaises(ValueError):
                worker.calculate(self.request(action, **kwargs))
        self.assertEqual(target.read_text(encoding="utf-8"), "# preserve")

    def test_declared_encoding(self):
        """coding宣言のあるコピーも同じ文字を保ち、元ファイルを更新しない。"""
        text = "# coding: cp932\n# 日本語\nimport os\nimport sys\nprint(sys.version)\n"
        self.source.write_bytes(text.encode("cp932"))
        result = worker.calculate(self.request("imports"))
        after = result["edit"]["changes"][self.source.as_uri()][0]["newText"]
        self.assertIn("# 日本語", after)
        self.assertNotIn("import os", after)
        self.assertEqual(self.source.read_bytes(), text.encode("cp932"))

    def test_invalid_identifier_and_outside(self):
        """不正な名前やプロジェクト外への移動を拒否する。"""
        with self.assertRaises(ValueError):
            worker.calculate(self.request("variable", start=0, end=3, name="bad name"))
        with self.assertRaises(ValueError):
            worker.calculate(self.request("move", start=6, destination=str(self.root.parent / "outside.py")))

    def test_project_config_never_executed(self):
        """.ropeprojectのコードをコピーも読込もしない。"""
        config = self.root / ".ropeproject/config.py"
        config.parent.mkdir()
        config.write_text("raise RuntimeError('unsafe configuration')", encoding="utf-8")
        worker.calculate(self.request("imports", "import os\n"))


if __name__ == "__main__":
    unittest.main()
