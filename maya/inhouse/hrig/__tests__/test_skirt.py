"""スカートの方向補間・保存・評価切替を隔離Mayaで検証する。"""

import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from maya import cmds

import hlib
from hrig.setups import RadialWeights
from hrig import build_skirt
from hrig.skirtRig import SkirtRig


class SkirtTest(unittest.TestCase):
    """標準constraintだけで姿勢と所有関係を維持する。"""

    def setUp(self):
        """新規シーンで外部プラグインのロードを禁止する。"""
        cmds.file(new=True, force=True)
        patcher = mock.patch.object(cmds, "loadPlugin", side_effect=AssertionError("Plugin load"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def assertMatrix(self, a, b):
        """行列全要素を比較する。"""
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=4)

    def test_rest_and_vector_ratios(self):
        """4/8方向・境界・非対称方向で基準姿勢と正規化を維持する。"""
        for count in (4, 8):
            rig = build_skirt("skirt" + str(count), count, chain_count=19)
            initial = [
                cmds.xform(j, query=True, worldSpace=True, matrix=True) for j in rig.getJoints()
            ]
            self.assertEqual(len(rig.driver_chains()), count)
            self.assertEqual(len(rig.getJoints()), 57)
            for falloff in (0.1, 1, 4, 8):
                rig.root.getPlug("falloff").set(falloff)
                for index, graph in enumerate(rig._members("graphs")):
                    _, expected = RadialWeights.weights(math.tau * index / 19, count, falloff)
                    self.assertAlmostEqual(graph.getPlug("weightA").get(), expected[0], places=5)
                    self.assertAlmostEqual(graph.getPlug("weightB").get(), expected[1], places=5)
                for joint, matrix in zip(rig.getJoints(), initial):
                    self.assertMatrix(
                        cmds.xform(joint, query=True, worldSpace=True, matrix=True), matrix
                    )
            rig.delete()

    def test_pose_blend_and_lod(self):
        """非対称ポーズ、Blendの基準復帰、Enabled/LODとUndoを確認する。"""
        rig = build_skirt()
        rest = [cmds.xform(j, query=True, worldSpace=True, matrix=True) for j in rig.getJoints()]
        drivers = rig.driver_chains()
        drivers[0][0].getPlug("rotateX").set(math.radians(50))
        drivers[0][1].getPlug("rotateZ").set(math.radians(15))
        drivers[1][0].getPlug("rotateZ").set(math.radians(-30))
        followers = rig.chains()
        self.assertAlmostEqual(followers[0][0].getPlug("rotateX").get(), math.radians(50), places=4)
        self.assertAlmostEqual(followers[0][1].getPlug("rotateZ").get(), math.radians(15), places=4)
        pose = [cmds.xform(j, query=True, worldSpace=True, matrix=True) for j in rig.getJoints()]
        rig.root.getPlug("blend").set(0)
        for joint, matrix in zip(rig.getJoints(), rest):
            self.assertMatrix(cmds.xform(joint, query=True, worldSpace=True, matrix=True), matrix)
        rig.root.getPlug("blend").set(1)
        rig.set_layer_enabled("radial", False)
        for joint in rig._members("followers"):
            self.assertIsNone(joint.getPlug("rotateX").getSourceWithConversion())
            self.assertEqual(joint.getPlug("rotateX").get(), 0)
        cmds.undo()
        self.assertTrue(rig.layer_enabled())
        for j, matrix in zip(rig.getJoints(), pose):
            self.assertMatrix(cmds.xform(j, query=True, worldSpace=True, matrix=True), matrix)
        cmds.redo()
        self.assertFalse(rig.layer_enabled())
        rig.set_layer_enabled("radial", True)
        rig.set_lod(0)
        self.assertIsNone(followers[0][0].getPlug("rotateX").getSourceWithConversion())
        rig.set_lod(1)
        self.assertAlmostEqual(followers[0][0].getPlug("rotateX").get(), math.radians(50), places=4)

    def test_parent_save_rename_delete(self):
        """親空間の移動・回転・一様scaleと保存後の参照を確認する。"""
        rig = build_skirt(driver_count=8, chain_count=8)
        rig.driver_chains()[0][0].getPlug("rotateZ").set(math.radians(35))
        rotations = [cmds.getAttr(j + ".rotate")[0] for j in rig.getJoints()]
        rig.root.getPlug("translate").set((12, 5, -9))
        rig.root.getPlug("rotate").set((15, 37, -18))
        rig.root.getPlug("scale").set((2, 2, 2))
        for j, expected in zip(rig.getJoints(), rotations):
            for a, b in zip(cmds.getAttr(j + ".rotate")[0], expected):
                self.assertAlmostEqual(a, b, places=4)
        rig.root.rename("renamedSkirt")
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "skirt.ma")
            cmds.file(rename=path)
            cmds.file(save=True, type="mayaAscii")
            cmds.file(path, open=True, force=True, executeScriptNodes=False)
        rig = SkirtRig("renamedSkirt")
        self.assertEqual(len(rig.chains()), 8)
        rig.set_lod(0)
        rig.set_lod(1)
        self.assertAlmostEqual(rig.chains()[0][0].getPlug("rotateZ").get(), math.radians(35), places=4)
        rig.delete()
        self.assertFalse(cmds.ls("skirt01*"))
        self.assertFalse(cmds.objExists("renamedSkirt"))

    def test_validation_and_skin_protection(self):
        """無効な指定は生成前に拒否し、バインド済み削除を防ぐ。"""
        for kwargs in (
            {"driver_count": 5},
            {"chain_count": 2},
            {"radius": 0},
            {"joints_per_chain": 1},
            {"length": float("nan")},
        ):
            with self.assertRaises(ValueError):
                build_skirt(**kwargs)
            self.assertFalse(cmds.objExists("skirt01"))
        rig = build_skirt(chain_count=4)
        mesh = cmds.polyPlane()[0]
        cmds.skinCluster(rig.getJoints(), mesh, toSelectedBones=True)
        with self.assertRaises(ValueError):
            rig.delete()
        self.assertTrue(cmds.objExists("skirt01"))

    def test_units_and_parallel_evaluation(self):
        """ラジアン・メートルでも配置を維持し、評価モード間で姿勢を比較する。"""
        try:
            cmds.currentUnit(angle="rad", linear="m")
            rig = build_skirt(driver_count=8, chain_count=8, radius=2, length=4)
            driver = rig.driver_chains()[2][0]
            follower = rig.chains()[2][0]
            position = cmds.xform(
                follower.getFullName(), query=True, worldSpace=True, translation=True
            )
            for value, expected in zip(position, (0, 0, 2)):
                self.assertAlmostEqual(value, expected, places=4)
            driver.getPlug("rotateX").set(0.5)
            self.assertAlmostEqual(cmds.getAttr(follower.getFullName() + ".rotateX"), 0.5, places=4)
            matrices = []
            for mode in ("off", "serial", "parallel"):
                cmds.evaluationManager(mode=mode)
                cmds.currentTime(cmds.currentTime(query=True) + 1)
                matrices.append(
                    cmds.xform(follower.getFullName(), query=True, worldSpace=True, matrix=True)
                )
            self.assertMatrix(matrices[0], matrices[1])
            self.assertMatrix(matrices[0], matrices[2])
        finally:
            cmds.currentUnit(angle="deg", linear="cm")
            cmds.evaluationManager(mode="off")
