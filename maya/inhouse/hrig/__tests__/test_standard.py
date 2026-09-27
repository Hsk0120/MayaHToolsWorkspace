"""プラグインをロードせず標準ノードだけで生成するリグの実機テスト。"""

import math
from unittest import mock

from maya import cmds

from hrig.__tests__ import test_limb
from hrig.soft_ik import softened_distance


class StandardTest(test_limb.LimbTest):
    """共通のリグ操作に加え、標準演算の境界値と所有関係を検証する。"""

    backend = "standard"

    def setUp(self):
        """プラグインロードを禁止し、空シーンへ標準リグを作る。"""
        patcher = mock.patch.object(cmds, "loadPlugin", side_effect=AssertionError("Plugin load"))
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()

    def test_numeric_boundaries(self):
        """ゼロ距離、softnessゼロ・全長、閾値前後を参照実装と比較する。"""
        self.rig.set_mode("ik")
        target = self.rig.controls()["target"]
        graph = self.rig._member("softGraph")
        self.assertEqual(cmds.nodeType(graph), "container")
        members = cmds.container(graph, query=True, nodeList=True)
        self.assertTrue(members)
        self.assertLessEqual(set(cmds.nodeType(n) for n in members),
                             {"condition", "multiplyDivide", "plusMinusAverage"})
        for softness in (0, 0.001, 0.1, 1, 5, 10):
            cmds.setAttr(target + ".softness", softness)
            for distance in (0, 0.001, 2, 8, 9, 9.5, 10, 12, 100):
                cmds.setAttr(target + ".tx", distance - 8)
                ratio = cmds.getAttr(graph + ".ratio")
                self.assertTrue(math.isfinite(ratio))
                self.assertAlmostEqual(distance * ratio,
                                       softened_distance(distance, 10, softness), delta=0.0001)
                self.assertAlmostEqual(math.dist(self.position(), (0, 0, 0)),
                                       softened_distance(distance, 10, softness), delta=0.002)

    def test_backend_exchange(self):
        """同一実装の再指定はノードを増やさず、削除時は内部演算も除去する。"""
        before = set(cmds.ls())
        self.rig.set_backend("standard")
        self.assertEqual(before, set(cmds.ls()))
        graph = self.rig._member("softGraph")
        members = cmds.container(graph, query=True, nodeList=True)
        self.rig.delete()
        self.assertFalse(cmds.objExists(graph))
        self.assertFalse(any(cmds.objExists(node) for node in members))

    def test_default_demo_is_standard(self):
        """引数なしデモに専用ノードを生成せず、全演算をシーン保存できる。"""
        from hrig.examples.limb_demo import build_demo

        cmds.file(new=True, force=True)
        demo = build_demo()
        rig = demo["rig"]
        self.assertEqual(cmds.getAttr(rig.root.full_name() + ".hrigBackend"), "standard")
        self.assertEqual(cmds.nodeType(rig._member("softGraph")), "container")
        self.assertNotIn("bifrostGraphShape", set(cmds.nodeType(n) for n in cmds.ls()))
        self.assertNotIn("hrigSoftIK", set(cmds.nodeType(n) for n in cmds.ls()))

    def test_match_redo_and_layer_controls(self):
        """標準演算でも既存のUndo/Redoとチャンネル要求が同じ結果になる。"""
        from hrig.__tests__ import test_native

        test_native.NativeTest.test_match_redo_preserves_pose(self)
        test_native.NativeTest.test_layer_settings_and_channel_requests(self)

    def test_startup_does_not_schedule_bifrost(self):
        """標準起動がBifrostロードを予約しないことを確認する。"""
        import runpy
        import sys
        from pathlib import Path

        channel = mock.Mock()
        bifrost = mock.Mock()
        startup = Path(__file__).resolve().parents[1] / "startup" / "userSetup.py"
        with mock.patch.dict(sys.modules, {"hrig_channel_startup": channel,
                                           "hrig_bifrost_startup": bifrost}):
            runpy.run_path(str(startup))
        channel.initialize.assert_called_once_with()
        bifrost.initialize.assert_not_called()
