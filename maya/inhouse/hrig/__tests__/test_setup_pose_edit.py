"""RBF登録編集とカーブ近似の共通API検証。"""

import math
import unittest
from maya import cmds
import hlib
from hrig.setups import PoseRbf
from hlib.utils import CurveFit


class PoseEditTest(unittest.TestCase):
    """安定した外部接続と登録点の再現を検証する。"""

    def setUp(self):
        """隔離シーンを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg")
        cmds.undoInfo(state=True, infinity=True)

    def test_edit_capture_undo(self):
        """追加・削除・編集・capture・Undoと外部出力接続を確認する。"""
        driver = hlib.createNode("transform", name="input")
        graph = PoseRbf.create([driver.plug("rx")], [[0], [60]], [[0], [30]], [60])
        target = hlib.createNode("network", name="target")
        target.addAttribute(longName="value", attributeType="double")
        graph.container.plug("outputs[0]").connect(target.plug("value"))
        uuid = graph.container.uuid()
        graph.set_data([[0], [30], [60]], [[0], [10], [40]], [40])
        driver.plug("rx").set(math.radians(30))
        self.assertAlmostEqual(graph.capture()[0], 30, places=5)
        self.assertAlmostEqual(target.plug("value").get(), 10, places=4)
        graph.set_data([[0], [60]], [[0], [20]], [50])
        cmds.undo()
        self.assertEqual(len(graph.data()["poses"]), 3)
        self.assertAlmostEqual(target.plug("value").get(), 10, places=4)
        self.assertEqual(graph.container.uuid(), uuid)
        before = graph.data()
        with self.assertRaises(ValueError):
            graph.set_data([[0], [0]], [[0], [2]], [20])
        self.assertEqual(graph.data(), before)

    def test_units(self):
        """m/radian環境でも登録角を度として解釈する。"""
        import math

        cmds.currentUnit(linear="m", angle="rad")
        driver = hlib.createNode("transform", name="input")
        graph = PoseRbf.create([driver.plug("rx")], [[0], [60]], [[0], [30]], [60])
        driver.plug("rx").set(math.pi / 3)
        self.assertAlmostEqual(graph.capture()[0], 60, places=4)
        self.assertAlmostEqual(graph.container.plug("outputs[0]").get(), 30, places=4)

    def test_fit(self):
        """基底の和、端点、直線の復元とゼロ長の拒否を確認する。"""
        for count in (4, 6, 10):
            for u in (0, 0.1, 0.5, 0.9, 1):
                self.assertAlmostEqual(sum(CurveFit.basis(count, u)), 1)
            cvs = CurveFit.fit([[i, 0, 0] for i in range(7)], count)
            for i in range(7):
                position = sum(w * p[0] for w, p in zip(CurveFit.basis(count, i / 6), cvs))
                self.assertAlmostEqual(position, i, places=4)
        with self.assertRaises(ValueError):
            CurveFit.fit([[0, 0, 0], [0, 0, 0]], 4)
