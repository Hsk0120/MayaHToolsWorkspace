"""hlib.utils.optionvar.OptionVar(JSON文字列で optionVar に保存するストア)のMaya内テスト。

テストごとに一意な接頭辞を使い、その接頭辞で始まる optionVar を tearDown で
``cmds.optionVar`` から直接すべて削除する(テスト対象のクラスには頼らない)。
"""

import json
import sys
import unittest
import uuid

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.utils.optionvar import OptionVar


class OptionVarTestBase(unittest.TestCase):
    """一意な接頭辞の用意と、その接頭辞で始まる optionVar の後始末を行う。"""

    def setUp(self):
        self.base = "hlibOptionVarTest" + uuid.uuid4().hex[:12]
        self.store = OptionVar(self.base)

    def tearDown(self):
        for name in cmds.optionVar(list=True) or []:
            if name.startswith(self.base):
                cmds.optionVar(remove=name)
        leftovers = [name for name in cmds.optionVar(list=True) or [] if name.startswith(self.base)]
        self.assertEqual(leftovers, [])

    def raw(self, key):
        """テスト対象を通さずに optionVar の生の値を読む。"""
        return cmds.optionVar(query=self.base + "." + key)

    def exists(self, key):
        """テスト対象を通さずに optionVar の有無を調べる。"""
        return bool(cmds.optionVar(exists=self.base + "." + key))


class StorageFormatTest(OptionVarTestBase):
    """JSON テキストとしての保存形式と、値の往復を確認する。"""

    def test_json_values_round_trip_with_their_types(self):
        samples = {
            "none": None,
            "yes": True,
            "no": False,
            "zero": 0,
            "negative": -7,
            "real": 3.25,
            "empty_text": "",
            "tricky_text": 'quote " backslash \\ newline \n tab \t semicolon ;',
            "unicode": "日本語 é",
            "empty_list": [],
            "mixed_list": [1, "a", None, [True, 2.5]],
            "empty_dict": {},
            "nested": {"list": [1.5, False], "child": {"name": "x"}},
        }
        for key, value in samples.items():
            self.store[key] = value
        for key, value in samples.items():
            with self.subTest(key=key):
                restored = self.store[key]
                self.assertEqual(restored, value)
                self.assertIs(type(restored), type(value))
        self.assertIs(self.store["yes"], True)
        self.assertIs(self.store["no"], False)

    def test_each_key_is_one_ascii_json_string_optionvar(self):
        self.store.set("data", {"name": "日本", "items": [1, 2]})
        raw = self.raw("data")
        self.assertIsInstance(raw, str)
        self.assertTrue(all(ord(char) < 128 for char in raw), raw)
        self.assertEqual(json.loads(raw), {"name": "日本", "items": [1, 2]})
        self.assertEqual(self.store.full_name("data"), self.base + ".data")

    def test_value_is_overwritten_even_when_previous_optionvar_was_array(self):
        name = self.store.full_name("list")
        cmds.optionVar(intValueAppend=(name, 1))
        cmds.optionVar(intValueAppend=(name, 2))
        self.store["list"] = {"now": "dict"}
        self.assertEqual(self.store["list"], {"now": "dict"})

    def test_tuple_is_read_back_as_list(self):
        self.store["pair"] = (1, (2, 3))
        self.assertEqual(self.store["pair"], [1, [2, 3]])

    def test_unsupported_values_raise_without_writing(self):
        cyclic = []
        cyclic.append(cyclic)
        invalid = [
            (TypeError, object()),
            (TypeError, {1, 2}),
            (TypeError, {1: "int key"}),
            (TypeError, {"outer": [{None: "none key"}]}),
            (ValueError, float("nan")),
            (ValueError, [float("inf")]),
            (ValueError, cyclic),
        ]
        for error, value in invalid:
            with self.subTest(value=repr(value)):
                with self.assertRaises(error):
                    self.store["bad"] = value
                self.assertFalse(self.exists("bad"))

    def test_too_deeply_nested_value_raises_value_error_without_writing(self):
        # json.dumps が RecursionError を送出する深さ。repr できないので subTest に載せない。
        deep = []
        for _ in range(100000):
            deep = [deep]
        with self.assertRaises(ValueError):
            self.store["deep"] = deep
        with self.assertRaises(ValueError):
            self.store.update({"fine": 1, "deep": deep})
        with self.assertRaises(ValueError):
            OptionVar(self.base, defaults={"deep": deep})
        self.assertFalse(self.exists("deep"))
        self.assertFalse(self.exists("fine"))

    def test_values_are_shared_between_instances_with_same_prefix(self):
        self.store["shared"] = [1, 2]
        other = OptionVar(self.base)
        self.assertEqual(other["shared"], [1, 2])


class LookupTest(OptionVarTestBase):
    """取得・存在確認とデフォルト値へのフォールバックを確認する。"""

    def test_missing_key(self):
        with self.assertRaises(KeyError):
            self.store["missing"]
        self.assertIsNone(self.store.get("missing"))
        self.assertEqual(self.store.get("missing", "fallback"), "fallback")
        self.assertNotIn("missing", self.store)
        self.assertFalse(self.store.is_stored("missing"))

    def test_default_is_used_until_a_value_is_stored(self):
        store = OptionVar(self.base, defaults={"size": 1.0})
        self.assertEqual(store["size"], 1.0)
        self.assertEqual(store.get("size", "fallback"), 1.0)
        self.assertIn("size", store)
        self.assertFalse(store.is_stored("size"))
        self.assertFalse(self.exists("size"))

        store["size"] = 4.0
        self.assertEqual(store["size"], 4.0)
        self.assertTrue(store.is_stored("size"))

    def test_value_equal_to_default_is_still_stored(self):
        store = OptionVar(self.base, defaults={"size": 1.0})
        store["size"] = 1.0
        self.assertTrue(store.is_stored("size"))
        self.assertEqual(json.loads(self.raw("size")), 1.0)

    def test_defaults_are_returned_as_independent_copies(self):
        source = {"axes": ["x"]}
        store = OptionVar(self.base, defaults=source)
        source["axes"].append("mutated-after-init")

        first = store["axes"]
        first.append("mutated-result")
        store.defaults["axes"].append("mutated-property")

        self.assertEqual(store["axes"], ["x"])
        self.assertEqual(store.defaults, {"axes": ["x"]})

    def test_stored_values_are_returned_as_independent_copies(self):
        self.store["axes"] = ["x"]
        self.store["axes"].append("mutated-result")
        self.assertEqual(self.store["axes"], ["x"])

    def test_invalid_defaults_raise_at_construction(self):
        with self.assertRaises(TypeError):
            OptionVar(self.base, defaults={"bad": object()})
        with self.assertRaises(ValueError):
            OptionVar(self.base, defaults={"bad": float("inf")})
        with self.assertRaises(ValueError):
            OptionVar(self.base, defaults={"a.b": 1})
        with self.assertRaises(TypeError):
            OptionVar(self.base, defaults={1: 1})


class ModificationTest(OptionVarTestBase):
    """保存済みの値の削除・リセット・一括保存を確認する。"""

    def test_reset_returns_to_default(self):
        store = OptionVar(self.base, defaults={"mode": "fast"})
        store["mode"] = "slow"
        self.assertTrue(store.reset("mode"))
        self.assertEqual(store["mode"], "fast")
        self.assertFalse(self.exists("mode"))
        self.assertFalse(store.reset("mode"))

    def test_reset_without_default_makes_key_missing(self):
        self.store["temp"] = 1
        self.assertTrue(self.store.reset("temp"))
        self.assertNotIn("temp", self.store)

    def test_delitem_requires_a_stored_value(self):
        store = OptionVar(self.base, defaults={"mode": "fast"})
        store["mode"] = "slow"
        del store["mode"]
        self.assertEqual(store["mode"], "fast")
        with self.assertRaises(KeyError):
            del store["mode"]
        with self.assertRaises(KeyError):
            del store["never"]

    def test_update_writes_all_or_nothing(self):
        with self.assertRaises(TypeError):
            self.store.update({"first": 1, "second": object()})
        self.assertFalse(self.exists("first"))
        self.assertFalse(self.exists("second"))

        with self.assertRaises(ValueError):
            self.store.update({"first": 1, "bad.key": 2})
        self.assertFalse(self.exists("first"))

        self.store.update({"first": 1, "second": [2]})
        self.assertEqual(self.store.to_dict(), {"first": 1, "second": [2]})

    def test_reset_all_removes_only_direct_members(self):
        child = OptionVar(self.base + ".child")
        sibling = OptionVar(self.base + "Sibling")
        store = OptionVar(self.base, defaults={"a": 0})
        store.update({"a": 1, "b": 2})
        child["a"] = "child"
        sibling["a"] = "sibling"

        self.assertEqual(store.reset_all(), ["a", "b"])
        self.assertEqual(store.stored_keys(), [])
        self.assertEqual(store["a"], 0)
        self.assertEqual(child["a"], "child")
        self.assertEqual(sibling["a"], "sibling")


class ListingTest(OptionVarTestBase):
    """キー一覧と、接頭辞によるスコープの区切りを確認する。"""

    def test_listing_merges_stored_values_and_defaults(self):
        store = OptionVar(self.base, defaults={"c": 3, "a": 1})
        store["b"] = 2
        store["a"] = 5

        self.assertEqual(store.stored_keys(), ["a", "b"])
        self.assertEqual(store.keys(), ["a", "b", "c"])
        self.assertEqual(store.values(), [5, 2, 3])
        self.assertEqual(store.items(), [("a", 5), ("b", 2), ("c", 3)])
        self.assertEqual(store.to_dict(), {"a": 5, "b": 2, "c": 3})
        self.assertEqual(list(store), ["a", "b", "c"])
        self.assertEqual(len(store), 3)

    def test_prefix_scope_is_exact(self):
        child = OptionVar(self.base + ".child")
        sibling = OptionVar(self.base + "Sibling")
        self.store["k"] = "parent"
        child["k"] = "child"
        sibling["k"] = "sibling"

        self.assertEqual(self.store.keys(), ["k"])
        self.assertEqual(child.keys(), ["k"])
        self.assertEqual(sibling.keys(), ["k"])
        self.assertEqual(self.store["k"], "parent")
        self.assertEqual(child["k"], "child")
        self.assertEqual(sibling["k"], "sibling")
        self.assertEqual(child.full_name("k"), self.base + ".child.k")


class LegacyValueTest(OptionVarTestBase):
    """JSON として読めない optionVar(旧形式の値など)の扱いを確認する。"""

    def setUp(self):
        super().setUp()
        self.store = OptionVar(self.base, defaults={"count": 10})
        cmds.optionVar(intValue=(self.store.full_name("count"), 99))
        cmds.optionVar(stringValue=(self.store.full_name("text"), "plain text"))
        cmds.optionVar(stringValue=(self.store.full_name("nan"), "NaN"))
        cmds.optionVar(floatValue=(self.store.full_name("real"), 1.5))
        cmds.optionVar(stringValueAppend=(self.store.full_name("array"), "a"))
        # float の範囲を超える数値は json.loads だけだと無限大になってしまう。
        cmds.optionVar(stringValue=(self.store.full_name("huge"), "1e400"))
        cmds.optionVar(stringValue=(self.store.full_name("nested_huge"), '{"a":[-1E400]}'))

    def test_unreadable_values_are_treated_as_not_stored(self):
        self.assertEqual(self.store["count"], 10)
        self.assertFalse(self.store.is_stored("count"))
        for key in ("text", "nan", "real", "array", "huge", "nested_huge"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.store)
                self.assertFalse(self.store.is_stored(key))
                self.assertEqual(self.store.get(key, "fallback"), "fallback")
                with self.assertRaises(KeyError):
                    del self.store[key]
        self.assertEqual(self.store.stored_keys(), [])
        self.assertEqual(self.store.keys(), ["count"])
        self.assertEqual(self.store.to_dict(), {"count": 10})

    def test_unreadable_values_can_be_overwritten_and_removed(self):
        self.store["array"] = ["now", "json"]
        self.assertEqual(self.store["array"], ["now", "json"])

        self.assertTrue(self.store.reset("text"))
        self.assertFalse(self.exists("text"))

        self.assertEqual(
            self.store.reset_all(), ["array", "count", "huge", "nan", "nested_huge", "real"]
        )
        self.assertEqual(self.store["count"], 10)

    def test_too_deeply_nested_json_text_is_treated_as_not_stored(self):
        # json.loads が RecursionError を送出する深さの配列を、クラスを通さずに書き込む。
        depth = 100000
        cmds.optionVar(stringValue=(self.store.full_name("deep"), "[" * depth + "]" * depth))
        self.assertFalse(self.store.is_stored("deep"))
        self.assertNotIn("deep", self.store)
        self.assertEqual(self.store.get("deep", "fallback"), "fallback")
        self.assertEqual(self.store.stored_keys(), [])
        self.assertEqual(self.store.to_dict(), {"count": 10})
        self.assertTrue(self.store.reset("deep"))
        self.assertFalse(self.exists("deep"))

    def test_json_strings_written_by_other_means_are_decoded(self):
        raw_texts = {
            "number": ("123", 123),
            "real": ("1e-3", 0.001),
            "flag": ("true", True),
            "nothing": ("null", None),
            "quoted": ('"text"', "text"),
        }
        for key, (text, _) in raw_texts.items():
            cmds.optionVar(stringValue=(self.store.full_name(key), text))
        for key, (_, expected) in raw_texts.items():
            with self.subTest(key=key):
                self.assertTrue(self.store.is_stored(key))
                restored = self.store[key]
                self.assertEqual(restored, expected)
                self.assertIs(type(restored), type(expected))

    def test_names_breaking_key_rules_are_ignored(self):
        # 名前の規則に合わない optionVar は一覧にも reset_all にも含めない
        # (後始末は tearDown が接頭辞で直接行う)。
        for suffix in ("bad-key", "space key"):
            cmds.optionVar(stringValue=(self.base + "." + suffix, "1"))
        self.assertEqual(self.store.stored_keys(), [])
        self.assertEqual(
            self.store.reset_all(), ["array", "count", "huge", "nan", "nested_huge", "real", "text"]
        )
        self.assertTrue(cmds.optionVar(exists=self.base + ".bad-key"))


class ValidationTest(OptionVarTestBase):
    """接頭辞・キーの検査と、Maya へ問い合わせない補助 API を確認する。"""

    # userPrefs.mel の文字列リテラルを壊す、または ASCII の英数字と "_" 以外を含む名前。
    UNSAFE_NAMES = ('q"k', "back\\slash", "a b", "a-b", "tab\t", "line\n", "日本", "é")

    def test_invalid_prefix(self):
        with self.assertRaises(TypeError):
            OptionVar(None)
        invalid = ("", ".a", "a.", "a..b") + self.UNSAFE_NAMES
        invalid += tuple("studio." + name for name in self.UNSAFE_NAMES)
        for prefix in invalid:
            with self.subTest(prefix=prefix):
                with self.assertRaises(ValueError):
                    OptionVar(prefix)

    def test_invalid_keys(self):
        with self.assertRaises(TypeError):
            self.store.get(1)
        with self.assertRaises(ValueError):
            self.store.set("", 1)
        with self.assertRaises(ValueError):
            self.store["a.b"] = 1
        with self.assertRaises(ValueError):
            self.store.reset("a.b")
        self.assertNotIn(1, self.store)
        self.assertNotIn("a.b", self.store)
        self.assertNotIn("", self.store)

    def test_unsafe_characters_in_keys_are_rejected_without_writing(self):
        for key in self.UNSAFE_NAMES:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    self.store[key] = 1
                with self.assertRaises(ValueError):
                    self.store.update({"fine": 1, key: 2})
                with self.assertRaises(ValueError):
                    OptionVar(self.base, defaults={key: 1})
                with self.assertRaises(ValueError):
                    self.store.full_name(key)
                self.assertNotIn(key, self.store)
        self.assertEqual(
            [name for name in cmds.optionVar(list=True) or [] if name.startswith(self.base)], []
        )

    def test_ascii_letters_digits_and_underscore_are_accepted(self):
        store = OptionVar(self.base + "._Tool_2")
        store["2nd_Key"] = "ok"
        self.assertEqual(store["2nd_Key"], "ok")
        self.assertEqual(store.full_name("2nd_Key"), self.base + "._Tool_2.2nd_Key")
        self.assertEqual(store.stored_keys(), ["2nd_Key"])

    def test_prefix_property_and_repr(self):
        store = OptionVar("studio.tool")
        self.assertEqual(store.prefix, "studio.tool")
        self.assertEqual(repr(store), "OptionVar('studio.tool')")
        self.assertEqual(store.full_name("size"), "studio.tool.size")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
