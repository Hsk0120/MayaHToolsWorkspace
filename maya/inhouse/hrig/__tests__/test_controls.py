"""指・Aim・Tweak・Splineフィットの統合検証。隔離シーン専用。"""

import os
import tempfile
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
        layer.plug("curl").set(30)
        layer.plug("curl1").set(10)
        layer.plug("curlWeight1_2").set(0.5)
        layer.plug("spread").set(20)
        targets = rig.members("targets")
        self.assertAlmostEqual(targets[0].plug("rz").get(), 40, places=4)
        self.assertAlmostEqual(targets[1].plug("rz").get(), 20, places=4)
        self.assertAlmostEqual(targets[0].plug("ry").get(), -20, places=4)
        self.assertAlmostEqual(targets[-2].plug("ry").get(), 20, places=4)
        control = rig.members("controls")[0]
        control.plug("rz").set(15)
        node_count = len(cmds.ls())
        for i in range(3):
            rig.set_layer_enabled("finger", False)
            self.assertAlmostEqual(targets[0].plug("rz").get(), 0)
            self.assertAlmostEqual(control.plug("rz").get(), 15)
            rig.set_layer_enabled("finger", True)
            self.assertAlmostEqual(targets[0].plug("rz").get(), 40, places=4)
        self.assertEqual(len(cmds.ls()), node_count)
        rig.set_lod(0)
        self.assertIsNone(targets[0].plug("rx").source())
        cmds.undo()
        self.assertEqual(rig.lod(), 1)
        self.assertIsNotNone(targets[0].plug("rx").source())
        self.assertIsInstance(ModuleRegistry.get(rig.root), FingerRig)

    def test_aim(self):
        """首と左右眼の目標追従、Up、FK復帰、移動親空間を確認する。"""
        rig = AimRig.create()
        controls = rig.members("controls")
        controls[1].plug("tx").set(3)
        self.assertGreater(abs(rig.members("targets")[0].plug("ry").get()), 20)
        controls[4].plug("tx").set(2)
        self.assertGreater(abs(rig.members("targets")[1].plug("ry").get()), 1)
        before = [list(n.get_matrix()) for n in rig.members("deform")]
        rig.root.plug("tx").set(100)
        for matrix, node in zip(before, rig.members("deform")):
            self.assertLess(max(abs(a - b) for a, b in zip(matrix, node.get_matrix())), 1e-5)
        rig.set_layer_enabled("aim", False)
        self.assertAlmostEqual(rig.members("targets")[0].plug("ry").get(), 0)
        rig.set_layer_enabled("aim", True)
        self.assertGreater(abs(rig.members("targets")[0].plug("ry").get()), 20)

    def test_tweak_modules(self):
        """全モジュールで手付け、LOD、独立使用状態、スキン一覧を確認する。"""
        rigs = [build_limb(), build_spline(), build_skirt(), FingerRig.create(), AimRig.create()]
        for rig in rigs:
            layer = TweakLayer(rig)
            control = layer.add("local1", rig.joints()[0])
            control.plug("ty").set(2)
            joint = hlib.getNode(layer.joints()[0])
            self.assertIn(joint.full_name(), rig.joints())
            self.assertAlmostEqual(joint.plug("offsetParentMatrix").get()[13], 2)
            rig.set_lod(0)
            self.assertIsNone(joint.plug("offsetParentMatrix").source())
            rig.set_lod(1)
            self.assertIsNotNone(joint.plug("offsetParentMatrix").source())
            layer.groups()["local1"].plug("enabled").set(False)
            layer.update()
            self.assertIsNone(joint.plug("offsetParentMatrix").source())
            self.assertAlmostEqual(control.plug("ty").get(), 2)

    def test_spline_match(self):
        """直線・曲げのフィット、誤差、許容値拒否、モード維持を確認する。"""
        for axis in "xyz":
            rig = build_spline("fit" + axis, axis=axis)
            rig.set_mode("fk")
            self.assertLess(rig.match_ik(), 1e-4)
            rig.members("fk")[1].plug("rz").set(15)
            rig.members("fk")[3].plug("rz").set(-10)
            error = rig.match_ik()
            self.assertLess(error, 0.6)
            self.assertEqual(rig.mode(), "fk")
            before = [list(n.get_matrix()) for n in rig.controls()]
            with self.assertRaises(ValueError):
                rig.match_ik(tolerance=1e-10)
            for matrix, node in zip(before, rig.controls()):
                self.assertLess(max(abs(a - b) for a, b in zip(matrix, node.get_matrix())), 1e-5)

    def test_save_reopen(self):
        """保存・読込・改名後もmessageから復元する。"""
        rig = FingerRig.create()
        TweakLayer(rig).add("tip", rig.joints()[-1])
        root = rig.root.name()
        path = os.path.join(tempfile.gettempdir(), "hrig-controls-test.ma")
        cmds.file(rename=path)
        cmds.file(save=True, type="mayaAscii", force=True)
        cmds.file(path, open=True, force=True, executeScriptNodes=False)
        rig = ModuleRegistry.get(root)
        rig.root.rename("renamedHand")
        rig.group("layer").plug("curl").set(30)
        self.assertAlmostEqual(rig.members("targets")[0].plug("rz").get(), 30, places=4)
        self.assertEqual(len(TweakLayer(rig).joints()), 1)
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
                rig.group("layer").plug("curl").set(math.pi / 4)
                self.assertAlmostEqual(
                    cmds.getAttr(rig.members("targets")[0].full_name() + ".rz"),
                    math.pi / 4,
                    places=5,
                )
                cmds.currentUnit(angle="deg")
                self.assertAlmostEqual(rig.members("targets")[0].plug("rz").get(), 45, places=4)
            rig.delete()
            self.assertEqual(set(cmds.ls()), before)

    def test_spline_stretch_parent_units(self):
        """伸縮した直線と一様拡大した親空間をm単位で合わせる。"""
        cmds.currentUnit(linear="m")
        rig = build_spline(length=0.1)
        rig.add_stretch()
        for axis in "XYZ":
            rig.root.plug("scale" + axis).set(2)
        rig.root.plug("tx").set(0.7)
        rig.root.plug("rz").set(25)
        rig.controls()[-1].plug("ty").set(0.05)
        rig.match_fk()
        rig.set_mode("fk")
        error = rig.match_ik()
        self.assertLess(error, 1e-4)
        for node in rig.controls():
            self.assertAlmostEqual(node.plug("sx").get(), 1, places=5)
