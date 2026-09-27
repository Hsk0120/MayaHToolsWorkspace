"""揺れの数値計算と標準DGポーズ補間を検証する。"""

import math
import unittest

from maya import cmds

from hlib.utils import DampedSpring
from hrig.setups import PoseRbf


class SecondaryMathTest(unittest.TestCase):
    """再現性・登録値・不正入力を検証する。"""

    def setUp(self):
        """隔離シーンを初期化する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg")

    def test_spring(self):
        """静止、遅れ、収束、角度制限、繰返し再現性を検証する。"""
        self.assertEqual(DampedSpring.solve([[5]] * 20, 1 / 24), [(5.0,)] * 20)
        samples = [[0]] * 5 + [[60]] * 120
        result = DampedSpring.solve(samples, 1 / 24, frequency=2, damping=0.4, limit=20)
        self.assertTrue(40 <= result[5][0] < 60)
        self.assertAlmostEqual(result[-1][0], 60, places=5)
        self.assertEqual(result, DampedSpring.solve(samples, 1 / 24, 2, 0.4, 20))
        self.assertTrue(all(abs(v[0] - goal[0]) <= 20.00001 for v, goal in zip(result, samples)))
        for kwargs in ({"frequency": 0}, {"damping": -1}, {"limit": 0}):
            with self.assertRaises(ValueError):
                DampedSpring.solve(samples, 1 / 24, **kwargs)

    def test_rbf_registration_and_edit(self):
        """多入力多出力の登録値、編集、度単位を検証する。"""
        source = cmds.createNode("transform")
        poses = [[0, 0], [60, 0], [0, 60], [60, 60]]
        values = [[0, 0], [20, 0], [0, 15], [30, -10]]
        graph = PoseRbf.create([source + ".rx", source + ".rz"], poses, values, [60, 60]).container
        for pose, value in zip(poses, values):
            cmds.setAttr(source + ".rx", pose[0])
            cmds.setAttr(source + ".rz", pose[1])
            for index, expected in enumerate(value):
                self.assertAlmostEqual(
                    graph.plug("outputs[{}]".format(index)).get(), expected, places=4
                )
        updated = [[v * 2 for v in row] for row in values]
        PoseRbf(graph).set_values(updated)
        self.assertAlmostEqual(graph.plug("outputs[0]").get(), 60, places=4)
        cmds.undo()
        self.assertAlmostEqual(graph.plug("outputs[0]").get(), 30, places=4)
        cmds.currentUnit(angle="rad")
        self.assertAlmostEqual(graph.plug("outputs[0]").get(), 30, places=4)
        cmds.currentUnit(angle="deg")
        cmds.setAttr(source + ".rx", 1000)
        self.assertAlmostEqual(graph.plug("outputs[0]").get(), 0, places=4)

    def test_rejection(self):
        """重複ポーズと不正データを拒否する。"""
        for poses, values, scales in (
            ([[0], [0]], [[0], [1]], [1]),
            ([[0], [1]], [[0], [1]], [0]),
            ([[0], [math.nan]], [[0], [1]], [1]),
        ):
            with self.assertRaises(ValueError):
                PoseRbf.coefficients(poses, values, scales)
