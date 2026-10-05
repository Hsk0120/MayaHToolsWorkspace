"""Splineおよび腕脚の伸縮・体積補正レイヤーを検証する。"""

import math
import os
import tempfile
import unittest
from unittest.mock import patch
from maya import cmds

import hlib
from hrig import build_spline, build_limb
from hrig.splineRig import SplineRig
from hrig.limb import LimbRig


class StretchTest(unittest.TestCase):
    """数値・評価切断・他レイヤーとの合成・所有を検証する。"""

    def setUp(self):
        """隔離シーンを用意する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg")
        mock = patch.object(cmds, "loadPlugin", side_effect=AssertionError("Plugin load"))
        mock.start()
        self.addCleanup(mock.stop)

    def position(self, node):
        """ワールド位置を取得する。"""
        return cmds.xform(str(node), query=True, worldSpace=True, translation=True)

    def same(self, a, b):
        """数列を誤差付きで比較する。"""
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=4)

    def matrix(self, node):
        """ワールド行列を取得する。"""
        return cmds.xform(str(node), query=True, worldSpace=True, matrix=True)

    def test_spline_stretch_squash_volume(self):
        """直線の伸縮・断面の非累積・上下限・固定長復帰を確認する。"""
        rig = build_spline()
        group = rig.add_stretch()
        rig.controls()[-1].plug("ty").set(10)
        self.same(self.position(rig.joints()[-1]), (0, 20, 0))
        for joint in rig.members("deform"):
            self.assertAlmostEqual(joint.plug("scaleY").get(), 1 / math.sqrt(2), places=5)
            self.assertAlmostEqual(
                sum(v * v for v in self.matrix(joint)[8:11]) ** 0.5, 1 / math.sqrt(2), places=5
            )
        group.plug("maxStretch").set(1.5)
        self.same(self.position(rig.joints()[-1]), (0, 15, 0))
        for i, control in enumerate(rig.controls()):
            control.plug("ty").set(-10 * i / (len(rig.controls()) - 1) * 0.5)
        self.same(self.position(rig.joints()[-1]), (0, 5, 0))
        group.plug("volume").set(0)
        self.assertAlmostEqual(rig.members("deform")[2].plug("scaleY").get(), 1)
        rig.set_layer_enabled("stretch", False)
        self.assertAlmostEqual(rig.members("ik")[1].plug("tx").get(), 10 / 6)
        self.assertIsNone(group.plug("measurement").sourceWithConversion().node().plug("inputCurve").sourceWithConversion())

    def test_spline_match_lod_units(self):
        """伸縮済み姿勢のFK合わせと単位・親scale・保存復元を確認する。"""
        cmds.currentUnit(linear="m")
        rig = build_spline(length=2, axis="z")
        group = rig.add_stretch()
        rig.controls()[-1].plug("tz").set(100)
        self.same(self.position(rig.joints()[-1]), (0, 0, 3))
        rig.controls()[1].plug("ty").set(20)
        before = [self.matrix(j) for j in rig.joints()]
        rig.match_fk()
        rig.set_mode("fk")
        for joint, matrix in zip(rig.joints(), before):
            self.same(self.matrix(joint), matrix)
        rig.set_mode("ik")
        for axis in "XYZ":
            rig.root.plug("scale" + axis).set(2)
        self.assertAlmostEqual(
            group.plug("graph").sourceWithConversion().node().plug("lengthScale").get(), 1.5, delta=0.03
        )
        rig.set_lod(0)
        self.assertIsNone(rig.members("ik")[1].plug("tx").sourceWithConversion())
        rig.set_lod(1)
        path = os.path.join(tempfile.gettempdir(), "hrig_stretch_spline.ma")
        cmds.file(rename=path)
        cmds.file(save=True, type="mayaAscii", force=True)
        cmds.file(path, open=True, force=True, executeScriptNodes=False)
        rig = SplineRig("spine01")
        self.assertIsNotNone(rig.members("ik")[1].plug("tx").sourceWithConversion())
        rig.delete()
        self.assertFalse(cmds.ls("spine01*"))

    def test_limb_stretch_soft_and_volume(self):
        """腕脚の目標到達、Soft IK合成、断面補正を確認する。"""
        rig = build_limb()
        group = rig.add_stretch()
        rig.set_mode("ik")
        rig.set_layer_enabled("soft", False)
        hlib.getPlug(rig.controls()["target"] + ".tx").set(7)
        self.same(self.position(rig.joints()[2]), (15, 0, 0))
        self.assertAlmostEqual(hlib.getPlug(rig._member("ik1") + ".tx").get(), 7.5)
        for i in range(3):
            self.same(self.position(rig.joints()[i]), self.position(rig._member("ik" + str(i))))
            self.assertAlmostEqual(
                sum(v * v for v in self.matrix(rig.joints()[i])[8:11]) ** 0.5,
                (1.5) ** -0.5,
                places=4,
            )
        rig.set_layer_enabled("soft", True)
        self.assertTrue(14 < self.position(rig.joints()[2])[0] < 15)
        before = [self.matrix(j) for j in rig.joints()[:3]]
        rig.match_fk()
        rig.set_mode("fk")
        rig.match_ik()
        rig.set_mode("ik")
        for joint, matrix in zip(rig.joints()[:3], before):
            self.same(self.matrix(joint), matrix)
        rig.set_layer_enabled("soft", False)
        group.plug("maxStretch").set(1.2)
        self.assertAlmostEqual(self.position(rig.joints()[2])[0], 12, places=4)
        rig.set_layer_enabled("stretch", False)
        self.assertAlmostEqual(hlib.getPlug(rig._member("ik1") + ".tx").get(), 5)
        cmds.undo()
        self.assertTrue(rig.layer_enabled("stretch"))

    def test_limb_squash_match_save(self):
        """圧縮、曲げ姿勢の体積補正、FK復帰、保存・削除を確認する。"""
        rig = build_limb()
        group = rig.add_stretch()
        rig.set_mode("ik")
        rig.set_layer_enabled("soft", False)
        # 初期目標距離8ではsquash=0なので通常の肘曲げを維持する。
        self.assertAlmostEqual(hlib.getPlug(rig._member("ik1") + ".tx").get(), 5)
        group.plug("squash").set(0.5)
        self.assertAlmostEqual(hlib.getPlug(rig._member("ik1") + ".tx").get(), 4.5)
        before = [self.matrix(j) for j in rig.joints()[:3]]
        rig.match_fk()
        rig.set_mode("fk")
        for joint, matrix in zip(rig.joints()[:3], before):
            self.same(self.matrix(joint), matrix)
        rig.set_mode("ik")
        rig.set_lod(0)
        self.assertIsNone(hlib.getPlug(rig._member("ik1") + ".tx").sourceWithConversion())
        rig.set_lod(1)
        path = os.path.join(tempfile.gettempdir(), "hrig_stretch_limb.ma")
        root = rig.root.name()
        cmds.file(rename=path)
        cmds.file(save=True, type="mayaAscii", force=True)
        cmds.file(path, open=True, force=True, executeScriptNodes=False)
        rig = LimbRig(root)
        self.assertIsNotNone(hlib.getPlug(rig._member("ik1") + ".tx").sourceWithConversion())
        rig.delete()
        self.assertFalse(cmds.objExists(root + "_stretchGraph"))

    def test_add_undo(self):
        """追加全体のUndo/Redoとスキン済みSplineの追加拒否を確認する。"""
        rig = build_spline()
        rig.add_stretch()
        cmds.undo()
        self.assertFalse(rig.root.hasAttr("stretchGroup"))
        cmds.redo()
        self.assertTrue(rig.root.hasAttr("stretchGroup"))
        other = build_spline("bound")
        mesh = cmds.polyCube()[0]
        cmds.skinCluster(other.joints(), mesh, toSelectedBones=True)
        with self.assertRaises(ValueError):
            other.add_stretch()

    def test_leg_foot_and_animated_evaluation(self):
        """脚のリバースフット、親scale、キー再評価との合成を確認する。"""
        from hrig.definition import limb_definition
        from hrig.reverse_foot import add_reverse_foot

        rig = build_limb(limb_definition("leg"))
        add_reverse_foot(rig)
        group = rig.add_stretch()
        rig.set_mode("ik")
        rig.set_layer_enabled("soft", False)
        target = rig.controls()["target"]
        for time, value in ((1, 0), (10, 7), (20, 3)):
            cmds.setKeyframe(target, attribute="tx", time=time, value=value)
        hlib.getPlug(target + ".heelRoll").set(15)
        expected = {}
        for time in (1, 10, 20):
            cmds.currentTime(time)
            expected[time] = self.matrix(rig.joints()[2])
        for mode in ("off", "serial", "parallel"):
            cmds.evaluationManager(mode=mode)
            for time in (20, 1, 10, 1):
                cmds.currentTime(time)
                self.same(self.matrix(rig.joints()[2]), expected[time])
        cmds.evaluationManager(mode="off")
        before = self.position(rig.joints()[2])
        ratio = group.plug("graph").sourceWithConversion().node().plug("lengthScale").get()
        for axis in "XYZ":
            rig.root.plug("scale" + axis).set(2)
        self.same(self.position(rig.joints()[2]), [v * 2 for v in before])
        self.assertAlmostEqual(group.plug("graph").sourceWithConversion().node().plug("lengthScale").get(), ratio)
