"""Mayaを起動せず、docstring から型スタブ(.pyi)を作れること、各 .py の隣のスタブが最新であることを検証する。

``tools/generate_mlib_stubs.py`` は VS Code(Pylance)の補完用に、docstring の型を注釈として書き出す。
docstring の型がPythonの型の式として読めない、または名前を解決できないと、その注釈は省かれて
エディター上で型不明になるため、省いた注釈が無いことも確かめる。
"""

import ast
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

GENERATOR = Path(__file__).resolve().parents[5] / "tools" / "generate_mlib_stubs.py"


def load_generator():
    """生成スクリプトをモジュールとして読み込む。

    Returns:
        module: ``generate_mlib_stubs``。
    """
    spec = importlib.util.spec_from_file_location("generate_mlib_stubs", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(sys.version_info < (3, 9), "the stub generator needs ast.unparse (Python 3.9+)")
class StubGenerationTest(unittest.TestCase):
    """全モジュールのスタブを作り、主要な入口の型を確かめる。"""

    @classmethod
    def setUpClass(cls):
        cls.generator = load_generator()
        cls.work = tempfile.TemporaryDirectory()
        cls.dest = Path(cls.work.name) / "mlib"
        cls.unresolved = cls.generator.generate(cls.dest)

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def stub(self, relative):
        """生成したスタブの内容を返す。"""
        return (self.dest / relative).read_text(encoding="utf-8")

    def test_every_module_has_a_parsable_stub(self):
        """本体の各 .py に対応する .pyi があり、Pythonの構文として読める。"""
        sources = [path for _, path in self.generator._modules(self.generator.SOURCE)]
        stubs = sorted(self.dest.rglob("*.pyi"))
        self.assertEqual(len(stubs), len(sources) + 1)  # 補助の _stubtypes.pyi を含む
        for path in stubs:
            with self.subTest(path=path.relative_to(self.dest)):
                ast.parse(path.read_text(encoding="utf-8"))

    def test_committed_stubs_are_current(self):
        """各 .py の隣のスタブが、現在の docstring から作ったものと同じ(古ければ作り直しが必要)。"""
        fresh = self.generator._stub_files(self.dest)
        current = self.generator._stub_files(self.generator.SOURCE)
        stale = sorted(str(path) for path in set(fresh) | set(current)
                       if fresh.get(path) != current.get(path)
                       and (path in fresh or current[path].startswith(self.generator.HEADER_MARK)))
        self.assertEqual(stale, [], "run: python tools/generate_mlib_stubs.py")

    def test_docstring_types_are_all_usable(self):
        """docstring の型をすべて注釈にできる(省いたものは --report で場所と理由が分かる)。"""
        self.assertEqual(["%s: %s: %r (%s)" % item for item in self.unresolved], [])

    def test_return_types_of_main_entries(self):
        """引数で戻り値が変わる入口は、オーバーロードで型を分ける。"""
        ls = self.stub("cmds/ls.pyi")
        self.assertIn('type: Literal["joint"]', ls)
        self.assertIn("-> Joints: ...", ls)
        self.assertIn('type: Literal["transform"]', ls)
        self.assertIn("-> list[Transform]: ...", ls)
        self.assertIn("-> list[Vertex]: ...", ls)
        self.assertIn('Literal["transform"]', self.stub("cmds/createNode.pyi"))
        self.assertIn("-> Node:", self.stub("cmds/getNode.pyi"))
        node = self.stub("nodes/node.pyi")
        self.assertIn("-> list[Node]: ...", node)
        self.assertIn("-> list[Plug]: ...", node)

    def test_collections_iterate_their_element_type(self):
        """複数形のコレクションは、要素の型で for と [] の型を返す。"""
        self.assertIn("def __iter__(self) -> Iterator[Joint]: ...", self.stub("nodes/joint.pyi"))
        self.assertIn("def __getitem__(self, index: int) -> Vertex: ...", self.stub("components/vertex.pyi"))


if __name__ == "__main__":
    unittest.main()
