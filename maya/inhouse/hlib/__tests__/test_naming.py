"""hlib.utils.naming の文字列サニタイズを検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.utils.naming import legalizeName


class LegalizeNameTest(unittest.TestCase):
    """legalizeName が Maya のノード名として有効な文字列を返すことを検証する。"""

    def test_returns_unchanged_for_already_legal_names(self):
        self.assertEqual(legalizeName("hlibValidName"), "hlibValidName")
        self.assertEqual(legalizeName("hlib_valid_name_2"), "hlib_valid_name_2")
        self.assertEqual(legalizeName("_hlibLeadingUnderscore"), "_hlibLeadingUnderscore")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(legalizeName("  hlibName  "), "hlibName")
        self.assertEqual(legalizeName("\thlibName\n"), "hlibName")

    def test_prefixes_underscore_when_name_starts_with_a_digit(self):
        self.assertEqual(legalizeName("123abc"), "_123abc")

    def test_collapses_illegal_character_runs_into_a_single_underscore(self):
        self.assertEqual(legalizeName("hlib name!!  test"), "hlib_name_test")
        self.assertEqual(legalizeName("a---b"), "a_b")

    def test_keeps_underscores_that_were_already_in_the_input(self):
        self.assertEqual(legalizeName("hlib__double"), "hlib__double")
        self.assertEqual(legalizeName("hlib_-name"), "hlib__name")

    def test_replaces_dag_separator_dot_and_non_ascii_characters(self):
        self.assertEqual(legalizeName("grp|node"), "grp_node")
        self.assertEqual(legalizeName("arm.L"), "arm_L")
        self.assertEqual(legalizeName("héllo"), "h_llo")
        self.assertEqual(legalizeName("腕L"), "_L")

    def test_does_not_treat_non_ascii_digits_as_digits(self):
        # 上付きの「2」は数字扱いせず、使えない文字として置き換える。
        self.assertEqual(legalizeName("²abc"), "_abc")

    def test_preserves_namespace_colon_separators(self):
        self.assertEqual(legalizeName("hlibNamespace:hlibName"), "hlibNamespace:hlibName")

    def test_applies_digit_rule_to_every_namespace_segment(self):
        self.assertEqual(legalizeName("ns:1abc"), "ns:_1abc")
        self.assertEqual(legalizeName("1ns:2sub:leaf"), "_1ns:_2sub:leaf")

    def test_strips_whitespace_around_namespace_separators(self):
        self.assertEqual(legalizeName("ns : hlib name"), "ns:hlib_name")

    def test_drops_empty_namespace_segments(self):
        self.assertEqual(legalizeName("a::b"), "a:b")
        self.assertEqual(legalizeName("ns:"), "ns")
        self.assertEqual(legalizeName("ns:   "), "ns")

    def test_keeps_a_single_leading_colon_for_root_namespace(self):
        self.assertEqual(legalizeName(":hlibRootName"), ":hlibRootName")
        self.assertEqual(legalizeName("  ::ns:leaf"), ":ns:leaf")

    def test_empty_or_whitespace_only_input_becomes_underscore(self):
        self.assertEqual(legalizeName(""), "_")
        self.assertEqual(legalizeName("   "), "_")
        self.assertEqual(legalizeName(":"), "_")
        self.assertEqual(legalizeName(" : : "), "_")

    def test_all_illegal_characters_becomes_underscore(self):
        self.assertEqual(legalizeName("!!!"), "_")

    def test_non_string_input_raises_type_error(self):
        with self.assertRaises(TypeError):
            legalizeName(None)
        with self.assertRaises(TypeError):
            legalizeName(123)
        with self.assertRaises(TypeError):
            legalizeName(b"hlibBytes")


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
                legal = legalizeName(self.NAMESPACE + ":" + raw)
                created = cmds.createNode("transform", name=legal)
                self.assertEqual(created, legal)

    def test_maya_accepts_leading_colon_as_root_namespace(self):
        legal = legalizeName(":" + self.NAMESPACE + ":5 leaf")
        self.assertEqual(legal, ":" + self.NAMESPACE + ":_5_leaf")
        created = cmds.createNode("transform", name=legal)
        self.assertEqual(created, legal[1:])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
