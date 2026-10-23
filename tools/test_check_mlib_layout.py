"""Mayaを起動せず、クラス内依存を保つレイアウト整形を検証する。"""

import ast
import textwrap
import unittest
from pathlib import Path

import check_mlib_layout as layout


def _is_alias(predicate, *, static=False):
    """実装を呼ばず、参照された先行定義だけを記録する。"""
    def decorate(alias):
        alias.predicate = getattr(predicate, "__func__", predicate)
        alias.static = static
        return alias
    return decorate


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

    def test_alias_stays_after_its_predicate_when_categories_move(self):
        """省略入口は本体直後へ付き、constructor/特殊/内部の順序も整う。"""
        source = '''
            class Example:
                def _internal(self):
                    return "internal"

                def isReady(self):
                    return True

                def unrelated(self):
                    return "public"

                @_is_alias(isReady)
                def ready(self):
                    return self.isReady()

                def __init__(self):
                    self.value = 1

                def __repr__(self):
                    return "Example"
        '''
        before = self.source(source)
        self.assertIn("L022", [v.code for v in layout.check_source(before)])
        fixed, after = self.formatted(source)
        names = [node.name for node in after.tree.body[0].body if isinstance(node, ast.FunctionDef)]
        self.assertEqual(names, ["__init__", "__repr__", "isReady", "ready", "unrelated", "_internal"])
        namespace = {"_is_alias": _is_alias}
        exec(fixed, namespace)
        self.assertTrue(namespace["Example"]().ready())
        self.assertIs(namespace["Example"].ready.predicate, namespace["Example"].isReady)

    def test_static_predicate_class_alias_and_attached_signature_keep_dependencies(self):
        """static本体→class入口→署名/別名の依存連鎖を保持する。"""
        fixed, after = self.formatted('''
            class Example:
                @staticmethod
                def isEnabled():
                    return True

                def unrelated(self):
                    return None

                @classmethod
                @_is_alias(isEnabled, static=True)
                def enabled(cls):
                    return cls.isEnabled()

                enabled.__signature__ = "signature"
                available = enabled
        ''')
        namespace = {"_is_alias": _is_alias}
        exec(fixed, namespace)
        self.assertTrue(namespace["Example"].enabled())
        self.assertTrue(namespace["Example"].available())
        nodes = after.tree.body[0].body
        self.assertEqual([getattr(node, "name", None) for node in nodes[:2]], ["isEnabled", "enabled"])
        self.assertIsInstance(nodes[2], ast.Assign)
        self.assertIsInstance(nodes[3], ast.Assign)

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
        """既知aliasに似た依存でも、未知装飾や既定値への参照を許可しない。"""
        for decorator, default in (
            ("@unknown(isReady)", ""),
            ("@namespace._is_alias(isReady)", ""),
            ("@_is_alias(isReady)", ", callback=isReady"),
            ("@_is_alias(isReady, static=isReady())", ""),
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

    def test_alias_before_target_and_class_local_alias_decorator_are_refused(self):
        """先行していない判定や同名のクラス内デコレータは安全扱いにしない。"""
        for text in ('''
            class Example:
                @_is_alias(isReady)
                def ready(self):
                    return True

                def isReady(self):
                    return True
        ''', '''
            class Example:
                def _is_alias(self):
                    return None

                def isReady(self):
                    return True

                @_is_alias(isReady)
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
