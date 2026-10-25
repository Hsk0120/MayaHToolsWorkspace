"""Mayaを起動せず、クラス内依存を保つレイアウト整形を検証する。"""

import ast
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import check_mlib_layout as layout


class ClassDependencyLayoutTest(unittest.TestCase):
    """既知依存だけを分類し、元の文・実行順制約を保つ。"""

    def source(self, text):
        """試験用の字下げを除き、AST付きソースを返す。"""
        return layout.Source(Path("sample.py"), textwrap.dedent(text).strip() + "\n")

    def formatted(self, text):
        """内容不変・再整形不変・整形後の違反なしを共通検証する。"""
        before = self.source(text)
        fixed = layout.fix_text(before.path, "\n".join(before.lines) + "\n")
        after = layout.Source(before.path, fixed)
        self.assertEqual(layout.compare_snapshots(layout.snapshot_source(before),
                                                   layout.snapshot_source(after)), [])
        self.assertEqual(layout.fix_text(before.path, fixed), fixed)
        self.assertEqual([str(v) for v in layout.check_source(after)
                          if v.code not in layout.INFORMATIONAL], [])
        return fixed, after


    def test_method_signature_and_class_attribute_alias_stay_attached(self):
        """メソッドに付く署名代入と単純なクラス内別名は元の順序を保つ。"""
        fixed, after = self.formatted('''
            class Example:
                def _internal(self):
                    return None

                def ready(self):
                    return True

                ready.__signature__ = "signature"
                available = ready

                def __init__(self):
                    self.value = 1
        ''')
        namespace = {}
        exec(fixed, namespace)
        self.assertTrue(namespace["Example"]().available())
        nodes = after.tree.body[0].body
        index = next(i for i, node in enumerate(nodes)
                     if isinstance(node, ast.FunctionDef) and node.name == "ready")
        self.assertIsInstance(nodes[index + 1], ast.Assign)
        self.assertIsInstance(nodes[index + 2], ast.Assign)

    def test_property_setter_and_special_alias_keep_their_getters(self):
        """property setterと特殊メソッド別名を移動しても元定義へ結び付ける。"""
        fixed, after = self.formatted('''
            class Example:
                @property
                def value(self):
                    return self._value

                def other(self):
                    return None

                @value.setter
                def value(self, value):
                    self._value = value

                def __init__(self):
                    self._value = 3

                def __repr__(self):
                    return str(self._value)

                __str__ = __repr__
        ''')
        namespace = {}
        exec(fixed, namespace)
        instance = namespace["Example"]()
        instance.value = 9
        self.assertEqual(instance.value, 9)
        self.assertEqual(str(instance), "9")
        nodes = after.tree.body[0].body
        getter = next(i for i, node in enumerate(nodes)
                      if isinstance(node, ast.FunctionDef) and node.name == "value")
        self.assertEqual(nodes[getter + 1].name, "value")

    def test_type_checking_annotation_block_keeps_order_content_and_comments(self):
        """注釈専用のTYPE_CHECKINGブロックは文を保ったまま属性群へ置く。"""
        source = '''
            class Example:
                def method(self):
                    return 1

                if TYPE_CHECKING:
                    # 宣言の順序は意味付きの値と短縮名を対応させる。
                    translate: "Translate"
                    t: "Translate"
                    scale: "Scale"

                marker = "kept"
        '''
        original = self.source(source).tree.body[0].body[1]
        fixed, after = self.formatted(source)
        reordered = after.tree.body[0].body[0]
        self.assertEqual(ast.dump(original), ast.dump(reordered))
        namespace = {"TYPE_CHECKING": False}
        exec(fixed, namespace)
        self.assertEqual(namespace["Example"]().method(), 1)

    def test_qualified_type_checking_annotation_block_is_supported(self):
        """typing.TYPE_CHECKING表記でも単純な注釈だけを扱う。"""
        fixed, _ = self.formatted('''
            class Example:
                def method(self):
                    return 1

                if typing.TYPE_CHECKING:
                    value: int
        ''')
        self.assertLess(fixed.index("if typing.TYPE_CHECKING:"), fixed.index("def method"))

    def test_unknown_decorator_or_default_class_reference_is_refused(self):
        """クラス内定義に依存する未知装飾や既定値の参照を許可しない。"""
        for decorator, default in (
            ("@unknown(isReady)", ""),
            ("@namespace.decorate(isReady)", ""),
            ("@decorate(isReady)", ", callback=isReady"),
            ("@decorate(isReady, static=isReady())", ""),
        ):
            with self.subTest(decorator=decorator, default=default):
                source = self.source('''
                    class Example:
                        def isReady(self):
                            return True

                        DECORATOR
                        def ready(selfDEFAULT):
                            return True
                '''.replace("DECORATOR", decorator).replace("DEFAULT", default))
                with self.assertRaises(layout.Unsupported):
                    layout.classify_members(source.tree.body[0])
                self.assertIn("L023", [v.code for v in layout.check_source(source)])
                fixed = layout.Source(source.path, layout.fix_text(source.path, "\n".join(source.lines) + "\n"))
                self.assertEqual(ast.dump(source.tree), ast.dump(fixed.tree))

    def test_unknown_decorator_before_target_or_defined_in_class_is_refused(self):
        """参照先が後続する装飾やクラス内定義の装飾を安全扱いにしない。"""
        for text in ('''
            class Example:
                @decorate(isReady)
                def ready(self):
                    return True

                def isReady(self):
                    return True
        ''', '''
            class Example:
                def decorate(self):
                    return None

                def isReady(self):
                    return True

                @decorate(isReady)
                def ready(self):
                    return True
        '''):
            with self.subTest(text=text):
                source = self.source(text)
                with self.assertRaises(layout.Unsupported):
                    layout.classify_members(source.tree.body[0])

    def test_property_accessor_does_not_allow_other_class_dependencies(self):
        """propertyの既知依存に紛れた、別デコレータや既定値の参照も拒否する。"""
        for decorator, default in (("@unknown(isReady)", ""), ("", "=isReady")):
            with self.subTest(decorator=decorator, default=default):
                source = self.source('''
                    class Example:
                        def isReady(self):
                            return True

                        @property
                        def value(self):
                            return 1

                        @value.setter
                        DECORATOR
                        def value(self, valueDEFAULT):
                            return None
                '''.replace("DECORATOR", decorator).replace("DEFAULT", default))
                with self.assertRaises(layout.Unsupported):
                    layout.classify_members(source.tree.body[0])

    def test_type_checking_runtime_statements_or_else_are_refused(self):
        """TYPE_CHECKINGでも値代入・import・定義やelseは対応範囲へ広げない。"""
        for body in ("value: int = 1", "import typing", "value = 1", "pass"):
            with self.subTest(body=body):
                source = self.source("class Example:\n    if TYPE_CHECKING:\n        " + body)
                with self.assertRaises(layout.Unsupported):
                    layout.classify_members(source.tree.body[0])
        source = self.source('''
            class Example:
                if TYPE_CHECKING:
                    value: int
                else:
                    value = 1
        ''')
        with self.assertRaises(layout.Unsupported):
            layout.classify_members(source.tree.body[0])
        source = self.source('''
            class Example:
                if application.TYPE_CHECKING:
                    value: int
        ''')
        with self.assertRaises(layout.Unsupported):
            layout.classify_members(source.tree.body[0])


class SpacingLayoutTest(unittest.TestCase):
    """文字列や構文上必要な記号と、検査する空白・lambda代入を区別する。"""

    def violations(self, text):
        """指定したソースの追加規則による違反だけを返す。"""
        source = layout.Source(Path("sample.py"), textwrap.dedent(text).strip() + "\n")
        return [v for v in layout.check_source(source) if v.code.startswith("L03")]

    def test_assignment_and_comparison_spaces(self):
        """代入・複合代入・比較を検出し、通常の算術演算は検査を広げない。"""
        for text in ("value=10", "value =10", "value+=1", "value = left>=right",
                     "value = left is(None)", "value = left not in(items)"):
            with self.subTest(text=text):
                self.assertIn("L030", [v.code for v in self.violations(text)])
        self.assertEqual(self.violations("value = 10\nvalue += 1\nready = value >= 0\nresult = value*2"), [])

    def test_comma_and_bracket_spaces(self):
        """カンマ後・同じ行の括弧内空白を検査する。"""
        for text in ("getValue(node,index)", "value = ( 1)", "value = [1 ]",
                     "value = { 'x': 1}", "getValue( )"):
            with self.subTest(text=text):
                self.assertIn("L031", [v.code for v in self.violations(text)])
        self.assertEqual(self.violations("getValue(node, index)\nvalues = [1, 2,]\nempty = {}"), [])

    def test_multiline_brackets_and_operators(self):
        """括弧内の改行・字下げと末尾カンマを不要な空白として扱わない。"""
        self.assertEqual(self.violations('''
            value = (
                left
                == right
            )
            values = [
                1,
                2,
            ]
        '''), [])

    def test_unannotated_defaults_and_call_keywords(self):
        """位置引数・キーワード専用引数・呼出しの = は空白なしにする。"""
        for text in ("def run(fast = False): pass", "def run(*, fast= False): pass",
                     "run(fast = False)", "callback = use(lambda value = 1: value)"):
            with self.subTest(text=text):
                self.assertIn("L032", [v.code for v in self.violations(text)])
        self.assertEqual(self.violations("def run(fast=False, *, safe=True): pass\nrun(fast=False)"), [])

    def test_annotated_defaults_need_spaces(self):
        """型注釈付き引数と通常の変数代入は = の前後を空ける。"""
        self.assertEqual(self.violations("def run(fast: bool = False): pass\nvalue: int = 1"), [])
        self.assertIn("L032", [v.code for v in self.violations("def run(fast: bool=False): pass")])

    def test_positional_only_defaults(self):
        """位置専用引数の既定値も同じ規則で検査する。"""
        self.assertEqual(self.violations("def run(value=1, /, *, flag: bool = False): pass"), [])
        self.assertIn("L032", [v.code for v in self.violations("def run(value = 1, /): pass")])

    def test_unicode_ast_byte_offsets(self):
        """日本語識別子や先行文字列があってもASTとtokenizeの位置を合わせる。"""
        self.assertEqual(self.violations('def 実行(値="日本語", *, 型付き: str = "値"): pass'), [])
        self.assertIn("L032", [v.code for v in self.violations('実行("日本語", 値 = 1)')])

    def test_nested_default_and_keyword_expressions(self):
        """既定値の中の呼出し・lambda・比較も別々の構文として扱う。"""
        self.assertEqual(self.violations('''
            def run(callback=use(lambda value=1: value), *, ready=(1 == 1)):
                return use(callback, fast=False)
        '''), [])
        self.assertIn("L032", [v.code for v in self.violations("def run(value=make(key = 1)): pass")])

    def test_inline_comment_spacing(self):
        """行末コメントの前2空白以上・#後1空白を検査する。"""
        self.assertEqual(self.violations("index += 1  # 次の要素へ\nother = 1    # 説明"), [])
        for text in ("index += 1 # 次の要素へ", "index += 1  #説明", "index += 1\t# 説明"):
            with self.subTest(text=text):
                self.assertIn("L033", [v.code for v in self.violations(text)])

    def test_standalone_comments_and_literal_contents_are_excluded(self):
        """単独コメント・docstring・通常文字列中の見かけのコードを検査しない。"""
        self.assertEqual(self.violations('''
            #コメントの別ルールは追加しない
            #: Sphinxの定数説明
            """value=1,2 #comment [ ]"""
            text = "function=lambda x:x #comment ( )"
            block = """value=1
            values=[ 1,2 ] #comment
            """
        '''), [])

    def test_sphinx_attribute_comments_keep_their_directive(self):
        """Sphinxの#:を通常コメントへ壊さず、コードとの間隔だけを検査する。"""
        self.assertEqual(self.violations("value = None  #: アトリビュートの説明"), [])
        self.assertIn("L033", [v.code for v in self.violations("value = None #: 説明")])

    def test_fstring_contents_are_excluded(self):
        """f-stringの文字部分・埋込み式は検査せず、外側の代入は検査する。"""
        self.assertEqual(self.violations('text = f"value={value!r:>10} {left==right} [ ] #comment"'), [])
        self.assertEqual(self.violations('text = f"{(callback := lambda: 1)}"'), [])
        self.assertIn("L030", [v.code for v in self.violations('text=f"{value}"')])

    @unittest.skipUnless(sys.version_info >= (3, 12), "f-string内コメントはPython 3.12以降")
    def test_fstring_expression_comments_and_nested_strings_are_excluded(self):
        """分割されたf-stringトークン内のコメントや入れ子を検査しない。"""
        self.assertEqual(self.violations('text = f"""{(\n    value #comment\n)}"""'), [])
        self.assertEqual(self.violations('text = f"{f\'{left==right}\'}"'), [])

    def test_named_lambda_assignment_forms(self):
        """通常・型付き・連鎖・代入式で名前へ直接渡すlambdaを検出する。"""
        for text in ("function = lambda value: value", "function: Callable = lambda: 1",
                     "first = second = lambda: 1", "if (function := lambda: 1): pass"):
            with self.subTest(text=text):
                self.assertIn("L034", [v.code for v in self.violations(text)])

    def test_callback_lambdas_are_allowed(self):
        """引数・既定値・戻り値・コレクションのlambdaを禁止しない。"""
        self.assertEqual(self.violations('''
            result = sorted(items, key=lambda item: item.name)
            options = {"callback": lambda: 1}
            def run(callback=lambda value=1: value):
                return lambda: callback()
        '''), [])

    def test_fix_does_not_rewrite_new_check_only_rules(self):
        """新規規則は検査だけに追加し、既存--fixで式やlambdaを変えない。"""
        text = '"""Example."""\n\nvalue=1  #comment\ncallback = lambda: value\n'
        fixed = layout.fix_text(Path("sample.py"), text)
        self.assertEqual(ast.dump(ast.parse(fixed)), ast.dump(ast.parse(text)))
        self.assertIn("value=1  #comment", fixed)
        self.assertIn("L034", [v.code for v in self.violations(fixed)])

    def test_check_cli_returns_failure_for_spacing(self):
        """既存の--checkから新規違反と終了コード1を返す。"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "example.py"
            path.write_text('"""Example."""\n\nvalue=1\n', encoding="utf-8")
            result = subprocess.run([sys.executable, layout.__file__, "--check", str(path)],
                                    capture_output=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 1)
        self.assertIn("L030", result.stdout)


class ModernPracticeLayoutTest(unittest.TestCase):
    """入力検証の候補、手動レビュー、明示的なassert修正の境界を確認する。"""

    def source(self, text, filename="sample.py"):
        return layout.Source(Path(filename), textwrap.dedent(text).strip() + "\n")

    def codes(self, text, filename="sample.py"):
        return [v.code for v in layout.check_source(self.source(text, filename))
                if v.code in {"L040", "L041", "L042", "L043"}]

    def test_public_input_guards_and_constructors(self):
        """公開関数とconstructorの冒頭の引数検証を検出する。"""
        for text in ("def run(value):\n    assert value > 0",
                     'class Example:\n    def __init__(self, value):\n        assert isinstance(value, int)',
                     'def run(*, value):\n    """概要。"""\n    assert value is not None'):
            with self.subTest(text=text):
                self.assertIn("L040", self.codes(text))
        self.assertIn("L040", self.codes("def run(value):\n    assert value", "__init__.py"))

    def test_internal_invariants_and_test_assertions_are_allowed(self):
        """内部関数・selfの状態・計算後の確認・テストは入力検証にしない。"""
        for text in ("def _run(value):\n    assert value",
                     "class _Example:\n    def run(self, value):\n        assert value",
                     "class Example:\n    def run(self, value):\n        assert self.ready",
                     "def run(value):\n    result = convert(value)\n    assert result"):
            with self.subTest(text=text):
                self.assertNotIn("L040", self.codes(text))
        for filename in ("test_example.py", "tests/example.py", "pkg/__tests__/example.py", "_internal.py"):
            self.assertNotIn("L040", self.codes("def run(value):\n    assert value", filename))

    def test_selected_assert_fix_keeps_message_and_other_invariants(self):
        """選んだassertだけを変え、後続の内部確認は保持する。"""
        source = self.source('''
            def run(value):
                assert isinstance(value, int), "整数を指定してください"
                result = value + 1
                assert result != 0
                return result
        ''')
        fixed = layout.rewrite_input_asserts(source, [2], "TypeError")
        namespace = {}
        exec(compile(fixed, "sample.py", "exec", optimize=2), namespace)
        self.assertEqual(namespace["run"](2), 3)
        with self.assertRaisesRegex(TypeError, "整数を指定してください"):
            namespace["run"]("bad")
        self.assertIn("assert result != 0", fixed)
        self.assertNotIn("L040", self.codes(fixed))

    def test_assert_fix_message_is_evaluated_only_on_failure(self):
        """assertのメッセージ評価を失敗時1回のまま保つ。"""
        source = self.source("def run(value, message):\n    assert value > 0, message()\n    return value")
        fixed = layout.rewrite_input_asserts(source, [2], "ValueError")
        namespace = {}
        exec(fixed, namespace)
        calls = []
        def message():
            calls.append(1)
            return "不正な値"
        namespace["run"](1, message)
        self.assertEqual(calls, [])
        with self.assertRaisesRegex(ValueError, "不正な値"):
            namespace["run"](0, message)
        self.assertEqual(calls, [1])

    def test_assert_fix_handles_multiline_and_no_message(self):
        source = self.source("def run(value):\n    assert (\n        value > 0\n    )\n    return value")
        fixed = layout.rewrite_input_asserts(source, [2], "ValueError")
        namespace = {}
        exec(fixed, namespace)
        with self.assertRaises(ValueError) as raised:
            namespace["run"](0)
        self.assertEqual(raised.exception.args, ())

    def test_assert_fix_refuses_shared_lines_comments_and_unknown_selection(self):
        for text in ("def run(value): assert value",
                     "def run(value):\n    assert value; return value",
                     "def run(value):\n    assert value  # 説明",
                     "def run(value):\n    assert (\n        value  # 説明\n    )"):
            source = self.source(text)
            selected = layout.public_input_asserts(source)[0].lineno
            with self.subTest(text=text), self.assertRaises(ValueError):
                layout.rewrite_input_asserts(source, [selected], "ValueError")
        source = self.source("def run(value):\n    assert value")
        for lines, error in (([], "ValueError"), ([2, 99], "ValueError"), ([2], "RuntimeError")):
            with self.assertRaises(ValueError):
                layout.rewrite_input_asserts(source, lines, error)

    def test_enumerate_candidate_is_informational(self):
        text = "for index in range(len(nodes)):\n    print(index, nodes[index])"
        self.assertIn("L041", self.codes(text))
        self.assertIn("L041", layout.INFORMATIONAL)

    def test_assert_fix_refuses_shadowed_exception_names(self):
        for text in ('def run(value, TypeError):\n    assert value',
                     'TypeError = CustomError\ndef run(value):\n    assert value',
                     'from errors import TypeError\ndef run(value):\n    assert value'):
            source = self.source(text)
            selected = layout.public_input_asserts(source)[0].lineno
            with self.subTest(text=text), self.assertRaises(ValueError):
                layout.rewrite_input_asserts(source, [selected], "TypeError")

    def test_index_algorithms_and_updates_are_not_simple_enumeration(self):
        for body in ("nodes[index] = index", "print(nodes[index + 1])", "print(index)",
                     "nodes.append(nodes[index])", "del nodes[index]", "nodes[index] += 1"):
            with self.subTest(body=body):
                self.assertNotIn("L041", self.codes("for index in range(len(nodes)):\n    " + body))
        self.assertNotIn("L041", self.codes("for index in range(len(nodes) - 1):\n    print(nodes[index])"))

    def test_text_open_requires_encoding(self):
        for text in ('stream = open(path)', 'stream = open(path, "w")',
                     'stream = open(path, encoding=None)', 'import io\nstream = io.open(path)',
                     'from io import open as text_open\nstream = text_open(path)'):
            with self.subTest(text=text):
                self.assertIn("L043", self.codes(text))

    def test_binary_dynamic_modes_and_encoding_arguments_are_allowed(self):
        for text in ('stream = open(path, "rb")', 'stream = open(path, mode="wb")',
                     'stream = open(path, encoding="utf-8")', 'stream = open(path, "r", -1, "cp932")',
                     'stream = open(path, **options)', 'stream = open(*arguments)', 'stream = open(path, mode)',
                     'import tokenize\nstream = tokenize.open(path)'):
            with self.subTest(text=text):
                self.assertNotIn("L043", self.codes(text))

    def test_known_path_instances_and_annotations(self):
        for text in ('from pathlib import Path\ntext = Path("file.txt").read_text()',
                     'import pathlib as paths\npath = paths.Path("file.txt")\npath.write_text("日本語")',
                     'from pathlib import Path\ndef run(path: Path):\n    return path.read_text()',
                     'from pathlib import Path\npath = Path("folder") / "file.txt"\nstream = path.open("r")'):
            with self.subTest(text=text):
                self.assertIn("L043", self.codes(text))

    def test_path_encoding_and_binary_methods_are_allowed(self):
        for text in ('from pathlib import Path\nPath("x").read_text("utf-8")',
                     'from pathlib import Path\nPath("x").write_text("text", encoding="utf-8")',
                     'from pathlib import Path\nPath("x").open("r", -1, "utf-8")',
                     'from pathlib import Path\nPath("x").read_bytes()',
                     'from pathlib import Path\nPath("x").open("rb")'):
            with self.subTest(text=text):
                self.assertNotIn("L043", self.codes(text))

    def test_unrelated_objects_and_shadowed_names_are_not_guessed(self):
        for text in ('result = client.read_text()', 'def run(open):\n    return open(path)',
                     'from pathlib import Path\ndef run(Path):\n    return Path().read_text()',
                     'from pathlib import Path\npath = Path("x")\npath = client\npath.read_text()',
                     'from pathlib import Path\ndef first(path: Path):\n    return path.read_text("utf-8")\ndef second(path):\n    return path.read_text()'):
            with self.subTest(text=text):
                self.assertNotIn("L043", self.codes(text))

    def test_pathlib_candidates_preserve_os_specific_operations_and_maya_names(self):
        self.assertIn("L042", self.codes('import os as system\npath = system.path.join(folder, "file")'))
        self.assertIn("L042", self.codes('from os.path import dirname as parent\npath = parent(filename)'))
        self.assertIn("L042", layout.INFORMATIONAL)
        for text in ('import os\npath = os.path.normcase(os.path.realpath(value))',
                     'plug_name = node + ".translateX"', 'dag_path = "|root|shape"'):
            self.assertNotIn("L042", self.codes(text))

    def test_assert_cli_requires_explicit_selection_and_keeps_bom_crlf(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "example.py"
            original = b'\xef\xbb\xbfdef run(value):\r\n    assert value > 0, "positive"\r\n    return value\r\n'
            path.write_bytes(original)
            base = [sys.executable, layout.__file__, "--fix-asserts", "ValueError", str(path)]
            result = subprocess.run(base, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_bytes(), original)
            result = subprocess.run(base + ["--line", "2", "--line", "99"], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(path.read_bytes(), original)
            result = subprocess.run(base + ["--line", "2"], capture_output=True)
            self.assertEqual(result.returncode, 0)
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
            self.assertIn(b"raise ValueError", data)

    def test_cli_encoding_failure_and_review_only_success(self):
        """未指定の文字コードは失敗、意味の確認が必要な置換候補は情報として返す。"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "example.py"
            base = [sys.executable, layout.__file__, "--check", str(path)]
            path.write_text('stream = open("file.txt")\n', encoding="utf-8")
            result = subprocess.run(base, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"L043", result.stdout)
            original = 'import os\n\npath = os.path.join("folder", "file.txt")\n'
            path.write_text(original, encoding="utf-8")
            result = subprocess.run(base, capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn(b"L042", result.stdout)
            self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
