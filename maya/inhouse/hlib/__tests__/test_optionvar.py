"""hlib.utils.optionvar の OptionVar ラッパーを検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.utils.optionvar import OptionVar


class OptionVarTest(unittest.TestCase):
    """接頭辞・デフォルト値・型別の保存/復元を検証する。"""

    prefix = "hlibOptionVarTest_"

    def _cleanup(self):
        for key in cmds.optionVar(list=True) or []:
            if key.startswith(self.prefix):
                cmds.optionVar(remove=key)

    def setUp(self):
        self._cleanup()
        self.option_var = OptionVar(prefix=self.prefix)

    def tearDown(self):
        self._cleanup()

    def test_scalar_round_trip_for_supported_types(self):
        self.option_var["s"] = "hello"
        self.option_var["i"] = 42
        self.option_var["f"] = 3.5
        self.option_var["n"] = None
        self.option_var["t"] = True
        self.option_var["b"] = False

        self.assertEqual(self.option_var["s"], "hello")
        self.assertEqual(self.option_var["i"], 42)
        self.assertEqual(self.option_var["f"], 3.5)
        self.assertIsNone(self.option_var["n"])
        self.assertIs(self.option_var["t"], True)
        self.assertIs(self.option_var["b"], False)

    def test_sequence_round_trip_including_empty(self):
        self.option_var["ints"] = [1, 2, 3]
        self.option_var["floats"] = [1.5, 2.5]
        self.option_var["strings"] = ["a", "b", "c"]
        self.option_var["empty"] = []

        self.assertEqual(self.option_var["ints"], [1, 2, 3])
        self.assertEqual(self.option_var["floats"], [1.5, 2.5])
        self.assertEqual(self.option_var["strings"], ["a", "b", "c"])
        self.assertEqual(self.option_var["empty"], [])

    def test_mixed_type_sequence_raises_type_error(self):
        with self.assertRaises(TypeError):
            self.option_var["mixed"] = [1, "two"]

    def test_unsupported_type_raises_type_error(self):
        with self.assertRaises(TypeError):
            self.option_var["obj"] = object()

    def test_missing_key_raises_key_error_without_default(self):
        with self.assertRaises(KeyError):
            self.option_var["missing"]

    def test_get_returns_fallback_when_missing(self):
        self.assertIsNone(self.option_var.get("missing"))
        self.assertEqual(self.option_var.get("missing", "fallback"), "fallback")

    def test_default_value_is_used_when_not_stored(self):
        self.option_var.set_default("threshold", 10)
        self.assertEqual(self.option_var["threshold"], 10)
        self.assertIn("threshold", self.option_var)

    def test_storing_value_equal_to_default_does_not_persist(self):
        self.option_var.set_default("threshold", 10)
        self.option_var["threshold"] = 10
        self.assertFalse(cmds.optionVar(exists=self.prefix + "threshold"))
        self.assertEqual(self.option_var["threshold"], 10)

        self.option_var["threshold"] = 20
        self.assertTrue(cmds.optionVar(exists=self.prefix + "threshold"))
        self.assertEqual(self.option_var["threshold"], 20)

    def test_set_default_removes_matching_stored_value(self):
        self.option_var["threshold"] = 10
        self.option_var.set_default("threshold", 10)
        self.assertFalse(cmds.optionVar(exists=self.prefix + "threshold"))

    def test_delitem_removes_stored_value_but_keeps_default(self):
        self.option_var.set_default("threshold", 10)
        self.option_var["threshold"] = 20
        del self.option_var["threshold"]
        self.assertFalse(cmds.optionVar(exists=self.prefix + "threshold"))
        self.assertEqual(self.option_var["threshold"], 10)

    def test_delitem_without_stored_or_default_raises_key_error(self):
        with self.assertRaises(KeyError):
            del self.option_var["missing"]

    def test_pop_returns_and_removes_value(self):
        self.option_var["key"] = "value"
        self.assertEqual(self.option_var.pop("key"), "value")
        self.assertNotIn("key", self.option_var)

        self.assertEqual(self.option_var.pop("missing", "fallback"), "fallback")
        with self.assertRaises(KeyError):
            self.option_var.pop("missing")

    def test_keys_values_items_combine_stored_and_default(self):
        self.option_var.set_default("a", 1)
        self.option_var["b"] = 2
        self.option_var["a"] = 5

        self.assertEqual(set(self.option_var.keys()), {"a", "b"})
        self.assertEqual(dict(self.option_var.items()), {"a": 5, "b": 2})
        self.assertEqual(sorted(self.option_var.values()), [2, 5])
        self.assertEqual(len(self.option_var), 2)
        self.assertEqual(sorted(list(self.option_var)), ["a", "b"])

    def test_clear_removes_stored_values_but_keeps_defaults(self):
        self.option_var.set_default("a", 1)
        self.option_var["a"] = 9
        self.option_var["b"] = 2
        self.option_var.clear()
        self.assertEqual(self.option_var["a"], 1)
        self.assertNotIn("b", self.option_var)

    def test_prefix_scopes_keys_independently(self):
        other = OptionVar(prefix="hlibOptionVarOtherScope_")
        try:
            self.option_var["shared"] = "mine"
            other["shared"] = "theirs"
            self.assertEqual(self.option_var["shared"], "mine")
            self.assertEqual(other["shared"], "theirs")
        finally:
            del other["shared"]

    def test_set_defaults_bulk_registers_multiple_keys(self):
        self.option_var.set_defaults({"x": 1, "y": "two"})
        self.assertEqual(self.option_var["x"], 1)
        self.assertEqual(self.option_var["y"], "two")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
