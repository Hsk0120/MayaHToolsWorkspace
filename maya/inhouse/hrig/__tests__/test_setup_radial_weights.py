"""放射状ウェイトの方向比率とDGを検証する。"""

import math
import unittest

from maya import cmds

from hrig.setups import RadialWeights


class RadialWeightsTest(unittest.TestCase):
    """隣接方向・シーム・調整値を検証する。"""

    def setUp(self):
        """新規の隔離シーンを用意する。"""
        cmds.file(new=True, force=True)

    def test_vector_and_seam(self):
        """ブレンドされた方向が元の方向と平行になり、シームが連続する。"""
        for count in (4, 8):
            for angle in (-0.01, 0, 0.12, math.pi / 4, 1.7, math.tau - 0.01):
                indices, weights = RadialWeights.weights(angle, count)
                x = sum(w * math.cos(math.tau * i / count) for i, w in zip(indices, weights))
                y = sum(w * math.sin(math.tau * i / count) for i, w in zip(indices, weights))
                self.assertAlmostEqual(x * math.sin(angle) - y * math.cos(angle), 0)
                self.assertAlmostEqual(sum(weights), 1)
                self.assertTrue(all(w >= 0 for w in weights))
            self.assertEqual(RadialWeights.directions(-0.01, count)[0], (count - 1, 0))

    def test_dg_blend(self):
        """DGのFalloff/Blendが数値計算と一致する。"""
        graph = RadialWeights.create(0.3, 4).container
        for falloff in (0.1, 1, 3, 8):
            graph.getPlug("falloff").set(falloff)
            _, weights = RadialWeights.weights(0.3, 4, falloff)
            for blend in (0, 0.25, 1):
                graph.getPlug("blend").set(blend)
                self.assertAlmostEqual(graph.getPlug("weightA").get(), weights[0] * blend, places=5)
                self.assertAlmostEqual(graph.getPlug("weightB").get(), weights[1] * blend, places=5)
                self.assertAlmostEqual(graph.getPlug("restWeight").get(), 1 - blend, places=5)
