"""ツイスト補助骨の等間隔配置、回転分配、LODとスキン保護を検証する。"""

import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from maya import cmds
from maya.api import OpenMaya as om

import hlib
from hrig import build_limb
from hrig.limb import LimbRig


class TwistTest(unittest.TestCase):
    """標準ノードだけで生成したリグを実評価する。"""

    def setUp(self):
        """空シーンを用意してプラグインロードを禁止する。"""
        cmds.file(new=True, force=True)
        patcher = mock.patch.object(cmds, "loadPlugin", side_effect=AssertionError("Plugin load"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rig = build_limb()
        self.start, self.end = self.rig.getJoints()[:2]

    def relative(self, node, parent):
        """親空間の実評価行列を取得する。

        Args:
            node (str): 評価対象。
            parent (str): 基準transform。

        Returns:
            MMatrix: 親空間の行列。
        """
        return om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]")) * om.MMatrix(
            cmds.getAttr(parent + ".worldInverseMatrix[0]")
        )

    def angle(self, matrix, axis="x"):
        """Quaternionの軸成分から最短ツイスト角を取得する。

        Args:
            matrix (MMatrix): 評価行列。
            axis (str): x/y/z。

        Returns:
            float: -180から180の角度。
        """
        quaternion = om.MTransformationMatrix(matrix).rotation(asQuaternion=True)
        angle = math.degrees(2 * math.atan2(getattr(quaternion, axis), quaternion.w))
        return (angle + 180) % 360 - 180

    def test_equal_positions_and_twist(self):
        """3本を25/50/75%へ配置し、正負のツイストを均等に配る。"""
        joints = self.rig.add_twist("upper", self.start, self.end, 3)
        for angle in (-150, -90, 0, 60, 150):
            cmds.setAttr(self.rig.controls()["fk1"] + ".rx", angle)
            for index, joint in enumerate(joints):
                fraction = (index + 1) / 4
                matrix = self.relative(joint, self.start)
                self.assertAlmostEqual(matrix[12], 5 * fraction, places=5)
                self.assertAlmostEqual(self.angle(matrix), angle * fraction, delta=0.002)
        self.assertEqual(len(self.rig.getJoints()), 7)

    def test_swing_is_not_distributed_as_twist(self):
        """複合回転から軸成分だけを抽出し、曲げを補助骨へ混ぜない。"""
        joints = self.rig.add_twist("upper", self.start, self.end, 2)
        cmds.setAttr(self.rig.controls()["fk1"] + ".rotate", 60, 40, 25)
        expected = self.angle(self.relative(self.end, self.start))
        for index, joint in enumerate(joints):
            matrix = self.relative(joint, self.start)
            self.assertAlmostEqual(self.angle(matrix), expected * (index + 1) / 3, delta=0.002)
            self.assertAlmostEqual(matrix[0], 1, places=5)
            self.assertAlmostEqual(matrix[1], 0, places=5)
            self.assertAlmostEqual(matrix[2], 0, places=5)
        cmds.setAttr(self.rig.controls()["fk1"] + ".rotate", 0, 180, 0)
        for joint in joints:
            self.assertTrue(all(math.isfinite(v) for v in self.relative(joint, self.start)))
            self.assertAlmostEqual(self.angle(self.relative(joint, self.start)), 0, places=4)

    def test_resize_undo_and_persistence(self):
        """本数変更・削除・Undoと保存再取得を確認する。"""
        self.rig.add_twist("upper", self.start, self.end, 1)
        self.rig.set_twist_count("upper", 5)
        self.assertEqual(len(self.rig.twist_joints("upper")), 5)
        cmds.undo()
        self.assertEqual(len(self.rig.twist_joints("upper")), 1)
        cmds.redo()
        self.assertEqual(len(self.rig.twist_joints("upper")), 5)
        with tempfile.TemporaryDirectory() as directory:
            file = str(Path(directory) / "twist.ma")
            cmds.file(rename=file)
            cmds.file(save=True, type="mayaAscii")
            cmds.file(file, open=True, force=True)
        rig = LimbRig("limb")
        cmds.rename(rig.getJoints()[1], "renamedEnd")
        rig.set_twist_count("upper", 2)
        self.assertEqual(len(rig.twist_joints()), 2)
        rig.set_twist_count("upper", 0)
        self.assertEqual(rig.twist_joints(), ())
        self.assertFalse(cmds.ls("*twist_layer_upper*"))

    def test_lod_and_enabled(self):
        """無効時は出力を切断し、再有効化で現在のツイストを復元する。"""
        from hrig.channel_controls import apply

        joints = self.rig.add_twist("upper", self.start, self.end, 3)
        cmds.setAttr(self.rig.controls()["fk1"] + ".rx", 80)
        self.rig.set_lod(0)
        for joint in joints:
            self.assertFalse(cmds.connectionInfo(joint + ".offsetParentMatrix", isDestination=True))
            self.assertAlmostEqual(self.angle(self.relative(joint, self.start)), 0, places=5)
        self.rig.set_lod(1)
        self.assertAlmostEqual(self.angle(self.relative(joints[0], self.start)), 20, places=4)
        channel = self.rig._member("channel_twist")
        cmds.setAttr(channel + ".enabled", False)
        apply(self.rig)
        self.assertFalse(cmds.getAttr(channel + ".active"))
        self.rig.set_layer_enabled("twist", True)
        self.assertTrue(cmds.getAttr(channel + ".active"))

    def test_demo_skin_and_protected_resize(self):
        """高詳細は全補助骨、proxyは基本3骨でバインドし、使用中の削除を拒否する。"""
        from hrig.examples.limb_demo import build_demo

        cmds.file(new=True, force=True)
        demo = build_demo(twist_count=4)
        rig = demo["rig"]
        self.assertEqual(len(rig.twist_joints()), 8)
        self.assertEqual(len(cmds.skinCluster(demo["high_skin"], query=True, influence=True)), 15)
        self.assertEqual(len(cmds.skinCluster(demo["proxy_skin"], query=True, influence=True)), 3)
        before = set(cmds.ls())
        with self.assertRaises(ValueError):
            rig.set_twist_count("lower", 2)
        self.assertEqual(set(cmds.ls()), before)
        rig.delete()
        self.assertFalse(cmds.ls("*twist_layer*"))

    def test_y_z_axes_and_parent_transform(self):
        """Y/Z軸にも同じ分配ができ、親の移動・回転・一様スケールを継承する。"""
        for axis in ("y", "z"):
            start = cmds.createNode("joint", name=axis + "Start")
            end = cmds.createNode("joint", name=axis + "End", parent=start)
            cmds.setAttr(end + ".t" + axis, 6)
            cmds.setAttr(end + ".segmentScaleCompensate", False)
            joints = self.rig.add_twist(axis, start, end, 2, axis)
            cmds.setAttr(end + ".r" + axis, 120)
            cmds.setAttr(start + ".translate", 2, 3, 4)
            cmds.setAttr(start + ".rotate", 10, 20, 30)
            cmds.setAttr(start + ".scale", 2, 2, 2)
            for index, joint in enumerate(joints):
                matrix = self.relative(joint, start)
                self.assertAlmostEqual(matrix[12 + "xyz".index(axis)], 2 * (index + 1), places=4)
                self.assertAlmostEqual(self.angle(matrix, axis), 40 * (index + 1), delta=0.002)

    def test_invalid_count_and_duplicate(self):
        """不正本数と重複区間を変更なしで拒否する。"""
        for count in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                self.rig.add_twist("bad", self.start, self.end, count)
        self.rig.add_twist("upper", self.start, self.end)
        before = set(cmds.ls())
        with self.assertRaises(ValueError):
            self.rig.add_twist("upper", self.start, self.end)
        self.assertEqual(before, set(cmds.ls()))
