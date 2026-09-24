"""hlib.utils.naming の文字列サニタイズを検証するMaya内テスト。"""

import sys
import unittest

import hlib
hlib.reload()
from hlib.utils.naming import legalize_name


class LegalizeNameTest(unittest.TestCase):
    """legalize_name が Maya のノード名として有効な文字列を返すことを検証する。"""

    def test_returns_unchanged_for_already_legal_names(self):
        self.assertEqual(legalize_name("hlibValidName"), "hlibValidName")
        self.assertEqual(legalize_name("hlib_valid_name_2"), "hlib_valid_name_2")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(legalize_name("  hlibName  "), "hlibName")

    def test_prefixes_underscore_when_name_starts_with_a_digit(self):
        self.assertEqual(legalize_name("123abc"), "_123abc")

    def test_collapses_illegal_character_runs_into_a_single_underscore(self):
        self.assertEqual(legalize_name("hlib name!!  test"), "hlib_name_test")
        self.assertEqual(legalize_name("a---b"), "a_b")

    def test_preserves_namespace_colon_separators(self):
        self.assertEqual(legalize_name("hlibNamespace:hlibName"), "hlibNamespace:hlibName")

    def test_empty_or_whitespace_only_input_becomes_underscore(self):
        self.assertEqual(legalize_name(""), "_")
        self.assertEqual(legalize_name("   "), "_")

    def test_all_illegal_characters_becomes_underscore(self):
        self.assertEqual(legalize_name("!!!"), "_")

    def test_non_string_input_raises_type_error(self):
        with self.assertRaises(TypeError):
            legalize_name(None)
        with self.assertRaises(TypeError):
            legalize_name(123)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
