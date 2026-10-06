"""伸縮率と体積近似の標準ノード評価を検証する。"""

import math
import unittest
from maya import cmds
from hrig.setups import LengthCompensation


class LengthCompensationTest(unittest.TestCase):
    """境界・方向別の影響量・Undoを検証する。"""

    def setUp(self):
        """隔離シーンを初期化する。"""
        cmds.file(new=True, force=True)

    def test_ratios(self):
        """伸長、圧縮、上下限、体積近似を確認する。"""
        graph = LengthCompensation.create(10).container
        for distance, expected in ((10, 1), (15, 1.5), (5, 0.5), (100, 2), (0, 0.1)):
            graph.getPlug("inputLength").set(distance)
            self.assertAlmostEqual(graph.getPlug("lengthScale").get(), expected, places=5)
            self.assertAlmostEqual(graph.getPlug("volumeScale").get(), expected**-0.5, places=5)
        graph.getPlug("inputLength").set(5)
        graph.getPlug("squash").set(0)
        self.assertAlmostEqual(graph.getPlug("lengthScale").get(), 1)
        graph.getPlug("inputLength").set(15)
        graph.getPlug("stretch").set(0.5)
        self.assertAlmostEqual(graph.getPlug("lengthScale").get(), 1.25)
        graph.getPlug("volume").set(0)
        self.assertAlmostEqual(graph.getPlug("volumeScale").get(), 1)

    def test_validation_and_undo(self):
        """不正基準長拒否と生成Undoを確認する。"""
        for value in (0, -1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                LengthCompensation.create(value)
        graph = LengthCompensation.create(10)
        name = graph.container.getName()
        cmds.undo()
        self.assertFalse(cmds.objExists(name))
