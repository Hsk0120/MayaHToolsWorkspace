"""標準Spline IKの骨長・階層・切替・保存を隔離シーンで検証する。"""

import os
import tempfile
import unittest
from unittest.mock import patch

from maya import cmds

from hrig import build_spline
from hrig.splineRig import SplineRig
from hrig.moduleRegistry import ModuleRegistry


class SplineTest(unittest.TestCase):
    """追加プラグインなしの生成と評価を検証する。"""

    def setUp(self):
        """隔離シーンと単位を初期化する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg")
        mock = patch.object(cmds, "loadPlugin", side_effect=AssertionError("Plugin load"))
        mock.start()
        self.addCleanup(mock.stop)

    def position(self, node):
        """ワールド座標を取得する。"""
        return cmds.xform(str(node), query=True, worldSpace=True, translation=True)

    def same(self, a, b):
        """誤差付きで数列を比較する。"""
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=4)

    def test_axes_and_counts(self):
        """XYZ配置・複数CV数で初期骨位置と参照を確認する。"""
        for axis in "xyz":
            for count in (4, 6):
                rig = build_spline("test" + axis + str(count), 9, count, 12, axis)
                self.assertEqual(len(rig.joints()), 9)
                self.assertEqual(len(rig.controls()), count)
                for i, joint in enumerate(rig.joints()):
                    self.same(self.position(joint), [i * 1.5 if a == axis else 0 for a in "xyz"])
                self.assertIsInstance(ModuleRegistry.get(rig.root), SplineRig)
                self.assertIn(
                    rig.root.full_name().lstrip("|"),
                    [n.lstrip("|") for n in ModuleRegistry.roots()],
                )

    def test_bending_length_and_twist(self):
        """曲げ、両端ひねり、固定骨長、評価順を確認する。"""
        rig = build_spline()
        rig.controls()[1].plug("tx").set(3)
        rig.controls()[2].plug("tz").set(2)
        positions = [self.position(n) for n in rig.joints()]
        self.assertGreater(max(abs(p[0]) for p in positions), 0.2)
        for a, b in zip(positions, positions[1:]):
            self.assertAlmostEqual(sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5, 10 / 6, places=4)
        last = rig.joints()[-2]
        before = cmds.xform(last, query=True, worldSpace=True, matrix=True)
        rig.controls()[-1].plug("ry").set(45)
        after = cmds.xform(last, query=True, worldSpace=True, matrix=True)
        self.assertGreater(max(abs(a - b) for a, b in zip(before, after)), 0.05)
        for mode in ("off", "serial", "parallel"):
            cmds.evaluationManager(mode=mode)
            for time in (10, 1, 5, 10):
                cmds.currentTime(time)
                self.same(cmds.xform(last, query=True, worldSpace=True, matrix=True), after)
        cmds.evaluationManager(mode="off")

    def test_modes_lod_undo(self):
        """FKへの接続切替と実際のIK入力切断を確認する。"""
        rig = build_spline()
        rig.controls()[1].plug("tx").set(2)
        before = self.position(rig.joints()[3])
        rig.set_mode("fk")
        handle = rig.graph().member("handle")
        self.assertIsNone(handle.plug("inCurve").source())
        self.assertEqual(handle.plug("nodeState").get(), 2)
        rig.members("fk")[1].plug("rz").set(25)
        self.same(self.position(rig.joints()[3]), self.position(rig.members("fk")[3]))
        rig.set_mode("ik")
        self.same(self.position(rig.joints()[3]), before)
        cmds.undo()
        self.assertEqual(rig.mode(), "fk")
        cmds.redo()
        self.assertEqual(rig.mode(), "ik")
        rig.set_lod(0)
        self.assertIsNone(handle.plug("inCurve").source())
        rig.set_lod(1)
        self.same(self.position(rig.joints()[3]), before)
        rig.set_layer_enabled("spline", False)
        self.assertIsNone(handle.plug("inCurve").source())

    def test_transform_units(self):
        """ルートの移動回転・均等scale・単位差を確認する。"""
        cmds.currentUnit(linear="m", angle="rad")
        rig = build_spline(length=2, axis="z")
        rig.controls()[1].plug("tx").set(0.3)
        local = [self.position(j) for j in rig.joints()]
        rig.root.plug("translate").set((1, 2, 3))
        for axis in "XYZ":
            rig.root.plug("scale" + axis).set(2)
        for p, joint in zip(local, rig.joints()):
            self.same(self.position(joint), [v * 2 + d for v, d in zip(p, (1, 2, 3))])
        rig.root.plug("rotateY").set(0.5)
        for joint, ik in zip(rig.joints(), rig.members("ik")):
            self.same(self.position(joint), self.position(ik))
        cmds.currentUnit(linear="cm", angle="deg")

    def test_animation_and_fk_match(self):
        """キー付きカーブのフレーム再評価とIKからFKへの姿勢保持を確認する。"""
        rig = build_spline()
        for time, value in ((1, 0), (10, 3), (20, -2)):
            cmds.setKeyframe(rig.controls()[1].full_name(), attribute="tx", time=time, value=value)
        expected = {}
        for time in (1, 10, 20):
            cmds.currentTime(time)
            expected[time] = [self.position(j) for j in rig.joints()]
        self.assertGreater(abs(expected[10][3][0] - expected[20][3][0]), 0.5)
        for mode in ("off", "serial", "parallel"):
            cmds.evaluationManager(mode=mode)
            for time in (20, 1, 10, 1):
                cmds.currentTime(time)
                for joint, position in zip(rig.joints(), expected[time]):
                    self.same(self.position(joint), position)
        cmds.currentTime(10)
        before = [cmds.xform(j, query=True, worldSpace=True, matrix=True) for j in rig.joints()]
        rig.match_fk()
        rig.set_mode("fk")
        for joint, matrix in zip(rig.joints(), before):
            self.same(cmds.xform(joint, query=True, worldSpace=True, matrix=True), matrix)
        cmds.evaluationManager(mode="off")

    def test_save_delete_skin(self):
        """保存復元・名前変更・所有削除・スキン使用拒否を確認する。"""
        rig = build_spline()
        rig.controls()[1].plug("tx").set(3)
        before = self.position(rig.joints()[4])
        path = os.path.join(tempfile.gettempdir(), "hrig_spline_test.ma")
        cmds.file(rename=path)
        cmds.file(save=True, type="mayaAscii", force=True)
        cmds.file(path, open=True, force=True, executeScriptNodes=False)
        rig = SplineRig("spine01")
        self.same(self.position(rig.joints()[4]), before)
        rig.root.rename("renamedSpline")
        rig.set_mode("fk")
        mesh = cmds.polyCube()[0]
        skin = cmds.skinCluster(list(rig.joints()), mesh, toSelectedBones=True)[0]
        with self.assertRaises(ValueError):
            rig.delete()
        cmds.delete(skin)
        rig.delete()
        self.assertFalse(cmds.objExists("renamedSpline"))
        self.assertFalse(cmds.ls("spine01_*"))

    def test_validation_creation_undo(self):
        """不正指定は生成せず、生成全体をUndoできる。"""
        for kwargs in ({"joint_count": 2}, {"control_count": 3}, {"length": 0}, {"axis": "bad"}):
            with self.assertRaises(ValueError):
                build_spline(**kwargs)
            self.assertFalse(cmds.objExists("spine01"))
        build_spline()
        cmds.undo()
        self.assertFalse(cmds.ls("spine01*"))
        cmds.redo()
        self.assertEqual(len(SplineRig("spine01").joints()), 7)
