"""WaveChainの各関節の正弦波の回転を、Pythonの式とOpenMayaで求めた期待値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import WaveChain

_AXES = {"x": 0, "y": 1, "z": 2}


def _local(node):
    """matrix * offsetParentMatrix。"""
    return om.MMatrix(cmds.getAttr(node + ".matrix")) * om.MMatrix(cmds.getAttr(node + ".offsetParentMatrix"))


class WaveChainTest(unittest.TestCase):
    """標準ノードの数値評価・生成時の姿勢・波の進行・重み・引数検査を確認する。"""

    def setUp(self):
        """回転した親の下に、jointOrientを持つ5関節の尻尾を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.root = cmds.createNode("transform", name="hip")
        cmds.setAttr(self.root + ".rotate", 0, 30, 10)
        self.joints = []
        parent = self.root
        for index in range(5):
            joint = cmds.createNode("joint", name="tail{}".format(index), parent=parent)
            cmds.setAttr(joint + ".translate", 3 if index else 0, 0, 0)
            cmds.setAttr(joint + ".jointOrient", 0, 5 * index, -8)
            cmds.setAttr(joint + ".rotate", 2, 0, index)
            self.joints.append(joint)
            parent = joint

    def build(self, **kwargs):
        """セットアップと、出力をoffsetParentMatrixで受ける同じ親子の結果transformを作る。"""
        owner = WaveChain.create(self.joints, **kwargs).container
        results = []
        parent = self.root
        for index in range(len(self.joints)):
            result = cmds.createNode("transform", name="result{}".format(index), parent=parent)
            cmds.connectAttr("{}.matrix{}".format(owner, index), result + ".offsetParentMatrix")
            results.append(result)
            parent = result
        return owner, results

    def check(self, owner, results, axis="z", **parameters):
        """各関節の角度出力と、出力行列(ローカルの軸まわりの回転 * 入力のローカル行列)を確認する。"""
        expected = WaveChain.waveAngles(len(self.joints), **parameters)
        for index, (joint, result) in enumerate(zip(self.joints, results)):
            self.assertAlmostEqual(cmds.getAttr("{}.angle{}".format(owner, index)), expected[index], places=4)
            values = [0.0, 0.0, 0.0]
            values[_AXES[axis]] = math.radians(expected[index])
            wave = om.MEulerRotation(*values).asMatrix()
            actual = om.MMatrix(cmds.getAttr(result + ".offsetParentMatrix"))
            self.assertTrue(actual.isEquivalent(wave * _local(joint), 1e-5), index)
        return expected

    def test_rest_pose_does_not_jump(self):
        """既定の振幅0では、生成直後の出力の各関節が入力と同じワールド行列になる。"""
        owner, results = self.build()
        for joint, result in zip(self.joints, results):
            world = om.MMatrix(cmds.getAttr(result + ".worldMatrix[0]"))
            self.assertTrue(world.isEquivalent(om.MMatrix(cmds.getAttr(joint + ".worldMatrix[0]")), 1e-5))

    def test_wave_progresses_with_phase(self):
        """phaseを進めると、各関節の角度が式どおりに変わる。"""
        owner, results = self.build(amplitude=20, wavelength=4, rootWeight=0.3, tipWeight=1.0)
        parameters = {"amplitude": 20, "wavelength": 4, "rootWeight": 0.3, "tipWeight": 1.0}
        for phase in (0, 45, 90, 200, 360, 725, -30):
            cmds.setAttr(str(owner) + ".phase", phase)
            self.check(owner, results, phase=phase, **parameters)
        # 位相を360度進めると、全関節が元の角度へ戻る(周期性)。
        cmds.setAttr(str(owner) + ".phase", 90)
        first = [cmds.getAttr("{}.angle{}".format(owner, i)) for i in range(5)]
        cmds.setAttr(str(owner) + ".phase", 450)
        for index in range(5):
            self.assertAlmostEqual(cmds.getAttr("{}.angle{}".format(owner, index)), first[index], places=4)

    def test_tip_reaches_amplitude(self):
        """先端の関節は、正弦が1になる位相で振幅×tipWeightに達する。"""
        owner, results = self.build(amplitude=30, wavelength=8, rootWeight=0.0, tipWeight=0.5)
        cmds.setAttr(str(owner) + ".phase", 90 + 360.0 * 4 / 8)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".angle4"), 15.0, places=4)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".angle0"), 0.0, places=6)

    def test_axis_and_attributes(self):
        """揺らす軸の指定と、生成後のアトリビュート変更に追従する。"""
        owner, results = self.build(name="yWave", axis="y", amplitude=10)
        parameters = {"amplitude": -25, "wavelength": 2.5, "rootWeight": 0.8, "tipWeight": 0.2}
        for attr, value in parameters.items():
            cmds.setAttr(str(owner) + "." + attr, value)
        cmds.setAttr(str(owner) + ".phase", 137)
        self.check(owner, results, axis="y", phase=137, **parameters)

    def test_radian_ui_unit(self):
        """UIの角度単位がradianでも、角度の出力は度のまま一致する。"""
        owner, results = self.build(amplitude=20)
        cmds.setAttr(str(owner) + ".phase", 60)
        expected = [cmds.getAttr("{}.angle{}".format(owner, i)) for i in range(5)]
        cmds.currentUnit(angle="rad")
        try:
            for index in range(5):
                self.assertAlmostEqual(cmds.getAttr("{}.angle{}".format(owner, index)), expected[index], places=5)
            self.check(owner, results, phase=60, amplitude=20, wavelength=4, rootWeight=0.3, tipWeight=1.0)
        finally:
            cmds.currentUnit(angle="deg")

    def test_invalid_arguments(self):
        """範囲外の値・軸・親子でない並び・既存の名前を拒否する。"""
        for kwargs in ({"axis": "w"}, {"amplitude": 200}, {"wavelength": 0}, {"rootWeight": 1.5},
                       {"tipWeight": float("nan")}):
            with self.assertRaises(ValueError):
                WaveChain.create(self.joints, **kwargs)
        with self.assertRaises(ValueError):
            WaveChain.create(self.joints[:1])
        with self.assertRaises(ValueError):
            WaveChain.create([self.joints[0], self.joints[2]])
        WaveChain.create(self.joints, name="taken")
        with self.assertRaises(ValueError):
            WaveChain.create(self.joints, name="taken")

    def test_undo_removes_graph(self):
        """生成を1回のUndoで取り消せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        WaveChain.create(self.joints, name="undoWave", amplitude=10)
        self.assertTrue(cmds.objExists("undoWave"))
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main()
