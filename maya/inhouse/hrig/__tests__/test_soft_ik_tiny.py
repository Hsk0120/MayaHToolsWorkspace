"""標準Soft IKの微小距離・減衰範囲・単位・所有とUndoを実Mayaで検証する。"""

import math
import unittest
from unittest import mock

from maya import cmds

import hlib
from hrig.setups.softIK import SoftIK


class SoftIKTinyTest(unittest.TestCase):
    """非ゼロの微小分母をゼロ扱いして目標を増幅する不具合の回帰検査。"""

    def setUp(self):
        """空シーン・通常Undo・固定単位・DG評価へ揃える。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.evaluationManager(mode="off")
        cmds.undoInfo(state=True, infinity=True)

    def tearDown(self):
        """後続テストへ表示単位の変更を残さない。"""
        cmds.currentUnit(linear="cm", angle="deg", time="film")

    def assertRatios(self, node, distances, softness_values):
        """実プラグへの入力を参照距離・有限性・倍率の上限と照合する。

        Args:
            node (Node): length=10の標準Soft IK。
            distances (Sequence[float]): 検査距離。
            softness_values (Sequence[float]): 減衰範囲。クランプ対象を含めてよい。
        """
        for softness in softness_values:
            node.getPlug("softness").set(softness)
            clamped_softness = min(max(softness, 0.0), 10.0)
            for distance in distances:
                node.getPlug("distance").set(distance)
                ratio = node.getPlug("ratio").get()
                clamped_distance = max(distance, 0.0)
                # 極微小な1-expの丸めで参照距離が入力を僅かに上回る場合も、
                # DGが以前から持つ到達距離の上限制約を参照値へ適用する。
                expected = (
                    min(1.0, SoftIK.distance(clamped_distance, 10, clamped_softness) / clamped_distance)
                    if clamped_distance else 0.0
                )
                with self.subTest(distance=distance, softness=softness):
                    self.assertTrue(math.isfinite(ratio))
                    self.assertGreaterEqual(ratio, 0.0)
                    self.assertLessEqual(ratio, 1.0 + 1e-7)
                    self.assertAlmostEqual(ratio, expected, delta=2e-6)

    def test_nonzero_tiny_distances_and_full_softness(self):
        """微小な到達距離を100000倍せず、全長減衰の指数も保持する。"""
        node = hlib.getNode(SoftIK.create("tinySoft", 10))
        self.assertRatios(node, (0, 1e-12, 1e-8, 1e-6, 1e-5, 1.0001e-5, 1e-4, 0.01),
                          (0, 1e-8, 1e-6, 1, 10))

    def test_thresholds_ordinary_range_and_clamping(self):
        """閾値前後・遠い目標・既存の負値と減衰範囲クランプを維持する。"""
        node = hlib.getNode(SoftIK.create("ordinarySoft", 10))
        self.assertRatios(node, (-1, 0, 2, 8, 9, 9.5, 9.999999, 10, 10.000001, 12, 100),
                          (-1, 0, 1e-8, 1e-6, 0.001, 0.1, 1, 5, 10, 20))

    def test_display_units_and_generated_conversion_ownership(self):
        """Maya版の距離型差を吸収し、cm/m/mmで同じ内部スカラーを評価する。"""
        for build_unit in ("cm", "m", "mm"):
            with self.subTest(build_unit=build_unit):
                cmds.currentUnit(linear=build_unit)
                node = hlib.getNode(SoftIK.create("unitSoft", 10))
                self.assertEqual(cmds.currentUnit(query=True, linear=True), build_unit)
                members = {member.getFullName() for member in node.getMembers()}
                conversions = set(cmds.ls(type="unitConversion") or [])
                self.assertLessEqual(conversions, members)
                for conversion in conversions:
                    self.assertEqual(cmds.getAttr(conversion + ".conversionFactor"), 1.0)
                for evaluation_unit in ("cm", "m", "mm"):
                    cmds.currentUnit(linear=evaluation_unit)
                    self.assertRatios(node, (0, 1e-8, 1e-6, 8, 10, 12), (0, 1e-8, 1e-6, 1, 10))
                    self.assertEqual(cmds.currentUnit(query=True, linear=True), evaluation_unit)
                hlib.delete(node)
                self.assertFalse(any(cmds.objExists(member) for member in members))
                self.assertFalse(cmds.ls(type="unitConversion"))

    def test_creation_and_value_edit_undo_redo(self):
        """演算と変換の作成を一回でUndoし、Redo後の微小値編集も元へ戻す。"""
        node_name = SoftIK.create("undoSoft", 10)
        members = [member.getFullName() for member in hlib.getNode(node_name).getMembers()]
        cmds.undo()
        self.assertFalse(cmds.objExists(node_name))
        self.assertFalse(any(cmds.objExists(member) for member in members))
        cmds.redo()
        self.assertTrue(cmds.objExists(node_name))
        node = hlib.getNode(node_name)
        node.getPlug("softness").set(1)
        node.getPlug("distance").set(12)
        expected = SoftIK.distance(12, 10, 1) / 12
        node.getPlug("distance").set(1e-6)
        self.assertAlmostEqual(node.getPlug("ratio").get(), 1, delta=1e-7)
        cmds.undo()
        self.assertAlmostEqual(node.getPlug("distance").get(), 12)
        self.assertAlmostEqual(node.getPlug("ratio").get(), expected, delta=1e-7)
        cmds.redo()
        self.assertAlmostEqual(node.getPlug("distance").get(), 1e-6)
        self.assertAlmostEqual(node.getPlug("ratio").get(), 1, delta=1e-7)

    def test_standard_creation_does_not_load_plugins(self):
        """修正後も外部・独自プラグインをロードせず、公開入出力はdoubleを維持する。"""
        with mock.patch.object(cmds, "loadPlugin", side_effect=AssertionError("Plugin load")):
            node = hlib.getNode(SoftIK.create("noPluginSoft", 10))
            self.assertRatios(node, (0, 1e-8, 1e-6, 9.5, 12), (0, 1, 10))
        self.assertEqual(cmds.nodeType(node.getFullName()), "container")
        for attr in ("distance", "softness", "ratio"):
            self.assertEqual(cmds.getAttr(node.getFullName() + "." + attr, type=True), "double")


if __name__ == "__main__":
    unittest.main()
