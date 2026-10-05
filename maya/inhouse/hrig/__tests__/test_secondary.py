"""スカートの揺れ・ポーズ補正・所有権を検証する。"""

import json
from pathlib import Path
import tempfile
import math
import unittest
from unittest import mock

from maya import cmds

import hlib
from hrig import build_skirt
from hrig.skirtRig import SkirtRig
from hrig.secondaryLayer import SecondaryLayer
from hrig.sampleBuilder import SampleBuilder


class SecondaryTest(unittest.TestCase):
    """元アニメーションの保持と標準ノード再生を確認する。"""

    def setUp(self):
        """空シーンにスカートと手付けキーを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", time="film")
        patcher = mock.patch.object(cmds, "loadPlugin", side_effect=AssertionError("Plugin load"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rig = build_skirt(chain_count=4)
        self.source = self.rig.driver_chains()[0][0]
        for time, value in ((1, 0), (8, 60), (24, 60)):
            cmds.setKeyframe(self.source.fullName(), attribute="rx", time=time, value=value)

    def matrix(self, node):
        """現在ワールド行列を取得する。"""
        return cmds.xform(node.fullName(), query=True, worldSpace=True, matrix=True)

    def same(self, a, b):
        """行列を誤差付きで比較する。"""
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=4)

    def test_bake_lod_and_reproducibility(self):
        """元キー保持、ベイク再現性、逆順評価、停止を確認する。"""
        before = cmds.keyframe(
            self.source.fullName(), attribute="rx", query=True, valueChange=True
        )
        cmds.currentTime(5)
        group = self.rig.bake_spring(start=1, end=24)
        self.assertEqual(cmds.currentTime(query=True), 5)
        layer = SecondaryLayer(self.rig)
        target = layer._members(group, "targets")[0]
        cmds.currentTime(8)
        self.assertNotAlmostEqual(target.plug("rx").get(), 60, places=2)
        self.same(self.matrix(target), self.matrix(self.rig.chains()[0][0]))
        poses = {}
        for time in (3, 8, 15, 24):
            cmds.currentTime(time)
            poses[time] = self.matrix(target)
        for mode in ("off", "serial", "parallel"):
            cmds.evaluationManager(mode=mode)
            for time in (24, 8, 3, 15, 8):
                cmds.currentTime(time)
                self.same(self.matrix(target), poses[time])
        self.rig.set_layer_enabled("spring", False)
        self.same(self.matrix(self.source), self.matrix(self.rig.chains()[0][0]))
        cmds.undo()
        self.same(self.matrix(target), self.matrix(self.rig.chains()[0][0]))
        self.rig.bake_spring(start=1, end=24)
        cmds.currentTime(8)
        self.same(self.matrix(target), poses[8])
        self.assertEqual(
            before,
            cmds.keyframe(self.source.fullName(), attribute="rx", query=True, valueChange=True),
        )
        self.rig.set_lod(0)
        self.assertIsNone(layer._members(group, "blends")[0].plug("inRotateX2").sourceWithConversion())
        self.rig.set_lod(1)
        self.same(self.matrix(target), self.matrix(self.rig.chains()[0][0]))
        cmds.evaluationManager(mode="off")

    def test_pose_combination_save_delete(self):
        """揺れと複数入力補正を同時使用し、保存と削除を確認する。"""
        self.rig.bake_spring(start=1, end=24)
        SampleBuilder.layer(self.rig, "pose")
        layer = SecondaryLayer(self.rig)
        group = layer.groups()[0]
        graph = group.plug("poseGraph").sourceWithConversion().node()
        cmds.currentTime(24)
        self.assertAlmostEqual(graph.plug("outputs[2]").get(), 20, places=4)
        self.source.plug("rz").set(math.radians(60))
        self.assertAlmostEqual(graph.plug("outputs[0]").get(), -20, places=4)
        self.assertAlmostEqual(graph.plug("outputs[2]").get(), 25, places=4)
        target = layer._members(group, "targets")[0]
        corrected = self.matrix(target)
        self.same(corrected, self.matrix(self.rig.chains()[0][0]))
        self.rig.set_layer_enabled("pose", False)
        self.assertNotEqual(corrected, self.matrix(target))
        self.rig.set_layer_enabled("pose", True)
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "secondary.ma")
            cmds.file(rename=path)
            cmds.file(save=True, type="mayaAscii")
            cmds.file(path, open=True, force=True, executeScriptNodes=False)
        rig = SkirtRig("skirt01")
        cmds.currentTime(24)
        self.same(corrected, self.matrix(rig.chains()[0][0]))
        rig.set_layer_enabled("spring", False)
        rig.set_layer_enabled("pose", False)
        self.same(self.matrix(rig.driver_chains()[0][0]), self.matrix(rig.chains()[0][0]))
        rig.delete()
        self.assertFalse(cmds.ls("skirt01*"))

    def test_validation_and_undo(self):
        """範囲・循環入力拒否とベイクUndoを確認する。"""
        with self.assertRaises(ValueError):
            self.rig.bake_spring(start=3, end=1)
        self.assertFalse(SecondaryLayer(self.rig).groups())
        self.rig.bake_spring(start=1, end=24)
        cmds.undo()
        self.assertFalse(SecondaryLayer(self.rig).groups())
        cmds.redo()
        self.assertTrue(SecondaryLayer(self.rig).groups())
        target = SecondaryLayer(self.rig)._members(SecondaryLayer(self.rig).groups()[0], "targets")[
            0
        ]
        with self.assertRaises(ValueError):
            self.rig.add_pose_correction(
                0, [target.plug("rx")], [[0], [60]], [[0] * 9, [1] * 9], [60]
            )
