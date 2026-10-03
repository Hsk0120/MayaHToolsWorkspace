"""参照空間レイヤーの姿勢保持・追従・永続化を隔離Mayaで検証する。"""

import tempfile
import unittest
from pathlib import Path

from maya import cmds
from maya.api import OpenMaya as om

import hlib
from hrig.examples.limb_demo import build_demo
from hrig.limb import LimbRig


class SpaceTest(unittest.TestCase):
    """標準ノードの実評価を使って空間切替を検証する。"""

    def setUp(self):
        """空シーンに標準デモを構築する。"""
        cmds.file(new=True, force=True)
        self.rig = build_demo()["rig"]

    def matrix(self, node):
        """ワールド行列を取得する。

        Args:
            node (str): ノード名。

        Returns:
            MMatrix: ワールド行列。
        """
        return om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))

    def assertMatrix(self, actual, expected):
        """行列を数値誤差付きで比較する。

        Args:
            actual (MMatrix): 実際値。
            expected (MMatrix): 期待値。
        """
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, delta=0.0001)

    def test_no_pop_and_world_follow(self):
        """移動・回転済みリグで切替直後の姿勢とワールド固定を確認する。"""
        rig = self.rig
        cmds.setAttr("rig.translate", 1, 2, 3)
        cmds.setAttr("rig.rotate", 10, 20, 30)
        target, pole = rig.controls()["target"], rig.controls()["pole"]
        cmds.setAttr(target + ".translate", -1, 1, 0)
        before = {node: self.matrix(node) for node in (target, pole) + rig.joints()[:3]}
        channels = cmds.getAttr(target + ".translate")
        for role in ("ik", "pole"):
            rig.set_space(role, "world")
        for node, expected in before.items():
            self.assertMatrix(self.matrix(node), expected)
        self.assertEqual(cmds.getAttr(target + ".translate"), channels)
        cmds.setAttr("rig.translate", 2, 3, 4)
        cmds.setAttr("rig.rotate", 15, 25, 35)
        self.assertMatrix(self.matrix(target), before[target])
        self.assertMatrix(self.matrix(pole), before[pole])
        # 再びLocalへ切り替えてから親を移動すると同じ変換が加わる。
        rig.set_space("ik", "local")
        old = self.matrix(target)
        old_root = self.matrix("rig")
        cmds.setAttr("rig.tx", 3)
        self.assertMatrix(self.matrix(target), old * old_root.inverse() * self.matrix("rig"))

    def test_foot_and_custom_space(self):
        """Poleは足の移動・回転に追従し、任意ノードの改名後も追従する。"""
        rig = self.rig
        target, pole = rig.controls()["target"], rig.controls()["pole"]
        before = self.matrix(pole)
        rig.set_space("pole", "foot")
        self.assertMatrix(self.matrix(pole), before)
        target_before = self.matrix(target)
        cmds.setAttr(target + ".ty", 2)
        cmds.setAttr(target + ".rz", 25)
        self.assertMatrix(self.matrix(pole), before * target_before.inverse() * self.matrix(target))
        chest = hlib.createNode("transform", name="chest", skipSelect=True)
        chest.setTranslation((2, 3, 4))
        rig.add_space("ik", "chest", chest)
        before = self.matrix(target)
        reference = self.matrix("chest")
        rig.set_space("ik", "chest")
        self.assertMatrix(self.matrix(target), before)
        cmds.rename("chest", "renamedChest")
        cmds.setAttr("renamedChest.ry", 35)
        self.assertMatrix(
            self.matrix(target), before * reference.inverse() * self.matrix("renamedChest")
        )
        rig.delete()
        self.assertTrue(cmds.objExists("renamedChest"))
        self.assertFalse(cmds.ls("*_space_grp*_multMatrix"))

    def test_channel_undo_save_and_match(self):
        """チャンネル要求とUndo/Redo・保存後の再取得・IK合わせを確認する。"""
        from hrig.channel_controls import apply

        rig = self.rig
        target = rig.controls()["target"]
        before = self.matrix(target)
        cmds.setAttr(target + ".space", 1)
        apply(rig)
        self.assertEqual(rig.space_switch("ik").current(), "world")
        self.assertMatrix(self.matrix(target), before)
        rig.set_space("pole", "foot")
        cmds.undo()
        self.assertEqual(rig.space_switch("pole").current(), "local")
        cmds.redo()
        self.assertEqual(rig.space_switch("pole").current(), "foot")
        # 動いたルートの下でもtargetMatrixへ空間分が伝わり、往復マッチが成立する。
        cmds.setAttr("rig.tx", 1)
        expected = [self.matrix(j) for j in rig.joints()[:3]]
        rig.match_fk()
        rig.set_mode("fk")
        cmds.setAttr(rig.controls()["fk0"] + ".rz", 15)
        expected = [self.matrix(j) for j in rig.joints()[:3]]
        rig.match_ik()
        rig.set_mode("ik")
        for joint, matrix in zip(rig.joints(), expected):
            self.assertMatrix(self.matrix(joint), matrix)
        with tempfile.TemporaryDirectory() as directory:
            file = str(Path(directory) / "spaces.ma")
            cmds.file(rename=file)
            cmds.file(save=True, type="mayaAscii")
            cmds.file(file, open=True, force=True)
        rig = LimbRig("rig")
        self.assertEqual(rig.space_switch("ik").current(), "world")
        rig.set_space("ik", "local")
        self.assertEqual(rig.space_switch("ik").current(), "local")

    def test_reject_cycles_and_invalid_labels(self):
        """子孫・IKの結果骨・相互依存・重複名はシーンを変えず拒否する。"""
        rig = self.rig
        for target in (rig.controls()["target"], rig.joints()[1], rig.controls()["pole"]):
            before = set(cmds.ls())
            with self.assertRaises(ValueError, msg=target):
                rig.add_space("ik", "bad", target)
            self.assertEqual(set(cmds.ls()), before)
        for label in ("world", "bad:name"):
            with self.assertRaises(ValueError):
                rig.add_space("pole", label, "rig")

    def test_spaces_survive_low_lod_and_fk(self):
        """空間はLODとFK/IKから独立し、構成切替で姿勢を飛ばさない。"""
        rig = self.rig
        rig.set_space("ik", "world")
        rig.set_space("pole", "foot")
        target = rig.controls()["target"]
        before = self.matrix(target)
        rig.set_lod(0)
        rig.set_mode("fk")
        self.assertMatrix(self.matrix(target), before)
        self.assertEqual(rig.space_switch("pole").current(), "foot")
        self.assertTrue(cmds.getAttr(rig._member("channel_space") + ".active"))
