"""hlib.utils.naming の文字列サニタイズを検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.utils.naming import legalize_name


class LegalizeNameTest(unittest.TestCase):
    """legalize_name が Maya のノード名として有効な文字列を返すことを検証する。"""

    def test_returns_unchanged_for_already_legal_names(self):
        self.assertEqual(legalize_name("hlibValidName"), "hlibValidName")
        self.assertEqual(legalize_name("hlib_valid_name_2"), "hlib_valid_name_2")
        self.assertEqual(legalize_name("_hlibLeadingUnderscore"), "_hlibLeadingUnderscore")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(legalize_name("  hlibName  "), "hlibName")
        self.assertEqual(legalize_name("\thlibName\n"), "hlibName")

    def test_prefixes_underscore_when_name_starts_with_a_digit(self):
        self.assertEqual(legalize_name("123abc"), "_123abc")

    def test_collapses_illegal_character_runs_into_a_single_underscore(self):
        self.assertEqual(legalize_name("hlib name!!  test"), "hlib_name_test")
        self.assertEqual(legalize_name("a---b"), "a_b")

    def test_keeps_underscores_that_were_already_in_the_input(self):
        self.assertEqual(legalize_name("hlib__double"), "hlib__double")
        self.assertEqual(legalize_name("hlib_-name"), "hlib__name")

    def test_replaces_dag_separator_dot_and_non_ascii_characters(self):
        self.assertEqual(legalize_name("grp|node"), "grp_node")
        self.assertEqual(legalize_name("arm.L"), "arm_L")
        self.assertEqual(legalize_name("héllo"), "h_llo")
        self.assertEqual(legalize_name("腕L"), "_L")

    def test_does_not_treat_non_ascii_digits_as_digits(self):
        # 上付きの「2」は数字扱いせず、使えない文字として置き換える。
        self.assertEqual(legalize_name("²abc"), "_abc")

    def test_preserves_namespace_colon_separators(self):
        self.assertEqual(legalize_name("hlibNamespace:hlibName"), "hlibNamespace:hlibName")

    def test_applies_digit_rule_to_every_namespace_segment(self):
        self.assertEqual(legalize_name("ns:1abc"), "ns:_1abc")
        self.assertEqual(legalize_name("1ns:2sub:leaf"), "_1ns:_2sub:leaf")

    def test_strips_whitespace_around_namespace_separators(self):
        self.assertEqual(legalize_name("ns : hlib name"), "ns:hlib_name")

    def test_drops_empty_namespace_segments(self):
        self.assertEqual(legalize_name("a::b"), "a:b")
        self.assertEqual(legalize_name("ns:"), "ns")
        self.assertEqual(legalize_name("ns:   "), "ns")

    def test_keeps_a_single_leading_colon_for_root_namespace(self):
        self.assertEqual(legalize_name(":hlibRootName"), ":hlibRootName")
        self.assertEqual(legalize_name("  ::ns:leaf"), ":ns:leaf")

    def test_empty_or_whitespace_only_input_becomes_underscore(self):
        self.assertEqual(legalize_name(""), "_")
        self.assertEqual(legalize_name("   "), "_")
        self.assertEqual(legalize_name(":"), "_")
        self.assertEqual(legalize_name(" : : "), "_")

    def test_all_illegal_characters_becomes_underscore(self):
        self.assertEqual(legalize_name("!!!"), "_")

    def test_non_string_input_raises_type_error(self):
        with self.assertRaises(TypeError):
            legalize_name(None)
        with self.assertRaises(TypeError):
            legalize_name(123)
        with self.assertRaises(TypeError):
            legalize_name(b"hlibBytes")


class LegalizeNameMayaAcceptanceTest(unittest.TestCase):
    """変換結果を Maya が書き換えずにノード名として受け付けることを検証する。"""

    NAMESPACE = "hlibNamingTestNS"

    def setUp(self):
        self._remove_namespace()
        cmds.namespace(add=self.NAMESPACE)

    def tearDown(self):
        self._remove_namespace()

    def _remove_namespace(self):
        if cmds.namespace(exists=self.NAMESPACE):
            cmds.namespace(removeNamespace=self.NAMESPACE, deleteNamespaceContent=True)

    def test_maya_keeps_legalized_names_unchanged(self):
        raw_names = [
            "1st hlib node",
            "hlib|dag.path",
            "hlib-é-name",
            "  hlib\tTab  ",
            "!!!",
        ]
        for raw in raw_names:
            with self.subTest(raw=raw):
                legal = legalize_name(self.NAMESPACE + ":" + raw)
                created = cmds.createNode("transform", name=legal)
                self.assertEqual(created, legal)

    def test_maya_accepts_leading_colon_as_root_namespace(self):
        legal = legalize_name(":" + self.NAMESPACE + ":5 leaf")
        self.assertEqual(legal, ":" + self.NAMESPACE + ":_5_leaf")
        created = cmds.createNode("transform", name=legal)
        self.assertEqual(created, legal[1:])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
