"""Mayaを起動せず、クラス内依存を保つレイアウト整形を検証する。"""

import ast
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


if __name__ == "__main__":
    unittest.main()
