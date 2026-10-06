"""指・Aim・Tweak・Splineフィットの統合検証。隔離シーン専用。"""

import os
import tempfile
import math
import unittest
from maya import cmds
import hlib
from hrig import build_limb, build_skirt, build_spline
from hrig.fingerRig import FingerRig
from hrig.aimRig import AimRig
from hrig.tweakLayer import TweakLayer
from hrig.moduleRegistry import ModuleRegistry


class ControlsTest(unittest.TestCase):
    """標準ノード・ローカル評価・所有参照・Undoを確認する。"""

    def setUp(self):
        """隔離シーンを初期化する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg")
        cmds.undoInfo(state=True, infinity=True)

    def test_finger(self):
        """Curl、個別加算、重み、Spread、手付けFKと停止を確認する。"""
        rig = FingerRig.create(finger_count=3, joint_count=2)
        layer = rig.group("layer")
        layer.getPlug("curl").set(math.radians(30))
        layer.getPlug("curl1").set(math.radians(10))
        layer.getPlug("curlWeight1_2").set(0.5)
        layer.getPlug("spread").set(math.radians(20))
        targets = rig.getMembers("targets")
        self.assertAlmostEqual(targets[0].getPlug("rz").get(), math.radians(40), places=4)
        self.assertAlmostEqual(targets[1].getPlug("rz").get(), math.radians(20), places=4)
        self.assertAlmostEqual(targets[0].getPlug("ry").get(), math.radians(-20), places=4)
        self.assertAlmostEqual(targets[-2].getPlug("ry").get(), math.radians(20), places=4)
        control = rig.getMembers("controls")[0]
        control.getPlug("rz").set(math.radians(15))
        node_count = len(cmds.ls())
        for i in range(3):
            rig.set_layer_enabled("finger", False)
            self.assertAlmostEqual(targets[0].getPlug("rz").get(), math.radians(0))
            self.assertAlmostEqual(control.getPlug("rz").get(), math.radians(15))
            rig.set_layer_enabled("finger", True)
            self.assertAlmostEqual(targets[0].getPlug("rz").get(), math.radians(40), places=4)
        self.assertEqual(len(cmds.ls()), node_count)
        rig.set_lod(0)
        self.assertIsNone(targets[0].getPlug("rx").getSourceWithConversion())
        cmds.undo()
        self.assertEqual(rig.lod(), 1)
        self.assertIsNotNone(targets[0].getPlug("rx").getSourceWithConversion())
        self.assertIsInstance(ModuleRegistry.get(rig.root), FingerRig)

    def test_aim(self):
        """首と左右眼の目標追従、Up、FK復帰、移動親空間を確認する。"""
        rig = AimRig.create()
        controls = rig.getMembers("controls")
        controls[1].getPlug("tx").set(3)
        self.assertGreater(abs(rig.getMembers("targets")[0].getPlug("ry").get()), math.radians(20))
        controls[4].getPlug("tx").set(2)
        self.assertGreater(abs(rig.getMembers("targets")[1].getPlug("ry").get()), math.radians(1))
        before = [list(n.getMatrix()) for n in rig.getMembers("deform")]
        rig.root.getPlug("tx").set(100)
        for matrix, node in zip(before, rig.getMembers("deform")):
            self.assertLess(max(abs(a - b) for a, b in zip(matrix, node.getMatrix())), 1e-5)
        rig.set_layer_enabled("aim", False)
        self.assertAlmostEqual(rig.getMembers("targets")[0].getPlug("ry").get(), math.radians(0))
        rig.set_layer_enabled("aim", True)
        self.assertGreater(abs(rig.getMembers("targets")[0].getPlug("ry").get()), math.radians(20))

    def test_tweak_modules(self):
        """全モジュールで手付け、LOD、独立使用状態、スキン一覧を確認する。"""
        rigs = [build_limb(), build_spline(), build_skirt(), FingerRig.create(), AimRig.create()]
        for rig in rigs:
            layer = TweakLayer(rig)
            control = layer.add("local1", rig.getJoints()[0])
            control.getPlug("ty").set(2)
            joint = hlib.getNode(layer.getJoints()[0])
            self.assertIn(joint.getFullName(), rig.getJoints())
            self.assertAlmostEqual(joint.getPlug("offsetParentMatrix").get()[13], 2)
            rig.set_lod(0)
            self.assertIsNone(joint.getPlug("offsetParentMatrix").getSourceWithConversion())
            rig.set_lod(1)
            self.assertIsNotNone(joint.getPlug("offsetParentMatrix").getSourceWithConversion())
            layer.groups()["local1"].getPlug("enabled").set(False)
            layer.update()
            self.assertIsNone(joint.getPlug("offsetParentMatrix").getSourceWithConversion())
            self.assertAlmostEqual(control.getPlug("ty").get(), 2)

    def test_spline_match(self):
        """直線・曲げのフィット、誤差、許容値拒否、モード維持を確認する。"""
        for axis in "xyz":
            rig = build_spline("fit" + axis, axis=axis)
            rig.set_mode("fk")
            self.assertLess(rig.match_ik(), 1e-4)
            rig.getMembers("fk")[1].getPlug("rz").set(math.radians(15))
            rig.getMembers("fk")[3].getPlug("rz").set(math.radians(-10))
            error = rig.match_ik()
            self.assertLess(error, 0.6)
            self.assertEqual(rig.mode(), "fk")
            before = [list(n.getMatrix()) for n in rig.controls()]
            with self.assertRaises(ValueError):
                rig.match_ik(tolerance=1e-10)
            for matrix, node in zip(before, rig.controls()):
                self.assertLess(max(abs(a - b) for a, b in zip(matrix, node.getMatrix())), 1e-5)

    def test_save_reopen(self):
        """保存・読込・改名後もmessageから復元する。"""
        rig = FingerRig.create()
        TweakLayer(rig).add("tip", rig.getJoints()[-1])
        root = rig.root.getName()
        path = os.path.join(tempfile.gettempdir(), "hrig-controls-test.ma")
        cmds.file(rename=path)
        cmds.file(save=True, type="mayaAscii", force=True)
        cmds.file(path, open=True, force=True, executeScriptNodes=False)
        rig = ModuleRegistry.get(root)
        rig.root.rename("renamedHand")
        rig.group("layer").getPlug("curl").set(math.radians(30))
        self.assertAlmostEqual(rig.getMembers("targets")[0].getPlug("rz").get(), math.radians(30), places=4)
        self.assertEqual(len(TweakLayer(rig).getJoints()), 1)
        rig.delete()
        self.assertFalse(cmds.objExists("renamedHand"))

    def test_units_ownership(self):
        """角度単位変更と全所有物の削除を確認する。"""
        import math

        for kind in (FingerRig, AimRig):
            cmds.file(new=True, force=True)
            cmds.currentUnit(linear="m", angle="rad")
            before = set(cmds.ls())
            rig = kind.create()
            if kind is FingerRig:
                rig.group("layer").getPlug("curl").set(math.pi / 4)
                self.assertAlmostEqual(
                    cmds.getAttr(rig.getMembers("targets")[0].getFullName() + ".rz"),
                    math.pi / 4,
                    places=5,
                )
                cmds.currentUnit(angle="deg")
                self.assertAlmostEqual(rig.getMembers("targets")[0].getPlug("rz").get(), math.radians(45), places=4)
            rig.delete()
            self.assertEqual(set(cmds.ls()), before)

    def test_spline_stretch_parent_units(self):
        """伸縮した直線と一様拡大した親空間をm単位で合わせる。"""
        cmds.currentUnit(linear="m")
        rig = build_spline(length=0.1)
        rig.add_stretch()
        for axis in "XYZ":
            rig.root.getPlug("scale" + axis).set(2)
        rig.root.getPlug("tx").set(70)
        rig.root.getPlug("rz").set(math.radians(25))
        rig.controls()[-1].getPlug("ty").set(5)
        rig.match_fk()
        rig.set_mode("fk")
        error = rig.match_ik()
        self.assertLess(error, 1e-4)
        for node in rig.controls():
            self.assertAlmostEqual(node.getPlug("sx").get(), 1, places=5)
