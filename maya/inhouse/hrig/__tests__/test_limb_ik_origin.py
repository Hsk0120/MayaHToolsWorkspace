"""原点近傍でSoft IKの増幅とRPソルバーの残差を分離して検証する。"""

import math
import unittest

from maya import cmds

from hrig import build_limb


class LimbIKOriginTest(unittest.TestCase):
    """最小Mayaチェーンとの一致、骨長、通常姿勢への復帰を確認する。"""

    def setUp(self):
        """同じ骨長・preferredAngle・ポール位置の独立RPチェーンを作る。"""
        self.previous_mode = cmds.evaluationManager(query=True, mode=True)[0]
        self.previous_units = {
            key: cmds.currentUnit(query=True, **{key: True})
            for key in ("linear", "angle", "time")
        }
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        self.reference_root = cmds.createNode("joint", name="referenceRoot")
        self.reference_middle = cmds.createNode("joint", name="referenceMiddle", parent=self.reference_root)
        self.reference_tip = cmds.createNode("joint", name="referenceTip", parent=self.reference_middle)
        for node in (self.reference_middle, self.reference_tip):
            cmds.setAttr(node + ".translateX", 5)
        cmds.setAttr(self.reference_middle + ".preferredAngleZ", -10)
        self.reference_handle, _ = cmds.ikHandle(
            startJoint=self.reference_root, endEffector=self.reference_tip, solver="ikRPsolver"
        )
        pole = cmds.createNode("transform", name="referencePole")
        cmds.setAttr(pole + ".translate", 5, 10, 0)
        cmds.poleVectorConstraint(pole, self.reference_handle)
        solver = cmds.listConnections(self.reference_handle + ".ikSolver", source=True, destination=False)[0]
        self.solver_state = (solver, cmds.getAttr(solver + ".tolerance"), cmds.getAttr(solver + ".maxIterations"))
        self.rig = build_limb(backend="standard")
        self.rig.set_mode("ik")
        self.target = self.rig.controls()["target"]
        self.handle = self.rig._member("handle")
        self.graph = self.rig._member("softGraph")
        cmds.setAttr(self.target + ".softness", 0)

    def tearDown(self):
        """テスト前の評価モード・単位へ戻す。"""
        cmds.file(new=True, force=True)
        cmds.evaluationManager(mode=self.previous_mode)
        cmds.currentUnit(**self.previous_units)

    @staticmethod
    def position(node):
        """worldMatrixを要求し、評価後のワールド位置をcmで取得する。

        Args:
            node (str): 照会するTransformまたはJointの名前。

        Returns:
            tuple[float, float, float]: 評価後のワールド位置（cm）。
        """
        return tuple(cmds.getAttr(node + ".worldMatrix[0]")[12:15])

    def test_native_solver_equivalence_without_soft_amplification(self):
        """微小目標でも倍率が増幅せず、残差は最小RP構成と同じになる。"""
        # 目標の理想位置へ完全追従する保証ではない。完全折畳み付近の
        # RPソルバー残差と、Soft IKの計算・出力複製による誤差を分離する。
        for mode in ("off", "serial", "parallel"):
            cmds.evaluationManager(mode=mode)
            for lod in (0, 1):
                self.rig.set_lod(lod)
                for distance in (8.0, 0.01, 1e-4, 1e-6, 1e-8, 0.0, 0.01, 8.0):
                    with self.subTest(mode=mode, lod=lod, distance=distance):
                        cmds.setAttr(self.target + ".translate", distance - 8.0, 0, 0)
                        handle_position = self.position(self.handle)
                        self.assertLessEqual(math.dist(handle_position, (distance, 0, 0)), 2e-8)
                        if lod == 1:
                            ratio = cmds.getAttr(self.graph + ".ratio")
                            self.assertTrue(math.isfinite(ratio))
                            self.assertGreaterEqual(ratio, 0)
                            self.assertLessEqual(ratio, 1 + 1e-7)
                            if distance > 0:
                                self.assertAlmostEqual(ratio, 1, delta=1e-7)
                        # 入力複合のfloat丸めをソルバー誤差に混ぜないよう、
                        # 実際に受け渡された同じ座標で最小RPチェーンを評価する。
                        cmds.setAttr(self.reference_handle + ".translate", *handle_position)
                        reference = self.position(self.reference_tip)
                        ik_tip = self.position(self.rig._member("ik2"))
                        output_tip = self.position(self.rig.getJoints()[2])
                        self.assertLessEqual(math.dist(ik_tip, reference), 1e-9)
                        self.assertLessEqual(math.dist(output_tip, ik_tip), 1e-9)

    def test_solver_settings_bone_lengths_and_normal_pose_are_preserved(self):
        """共有solver設定と骨長を維持し、折畳み後に通常姿勢へ復帰する。"""
        self.rig.set_lod(0)
        for distance in (8.0, 0.0, 1e-8, 8.0):
            cmds.setAttr(self.target + ".translateX", distance - 8.0)
            joints = [self.position(self.rig._member("ik" + str(i))) for i in range(3)]
            for start, end in zip(joints, joints[1:]):
                self.assertAlmostEqual(math.dist(start, end), 5.0, delta=1e-9)
        self.assertLessEqual(math.dist(joints[2], (8, 0, 0)), 1e-5)
        solver, tolerance, iterations = self.solver_state
        self.assertEqual(cmds.getAttr(solver + ".tolerance"), tolerance)
        self.assertEqual(cmds.getAttr(solver + ".maxIterations"), iterations)


if __name__ == "__main__":
    unittest.main()
