"""コマ打ちの範囲・秒換算・時間ドライバーからの分離を調べる。"""

import unittest

import maya.cmds as cmds

from animBar.core import animCopy, timeDriver, timing


class SteppedClipTest(unittest.TestCase):
    def setUp(self):
        cmds.file(new=True, force=True)
        cmds.currentUnit(time="film")
        self.source = cmds.createNode("transform", name="source")
        for frame in (0, 6, 12):
            cmds.setKeyframe(self.source, attribute="tx", time=frame, value=frame,
                             inTangentType="linear", outTangentType="linear")
        cmds.playbackOptions(minTime=2, maxTime=10)
        cmds.select(self.source)

    def test_bake_and_paste_timing(self):
        """2コマをベイクして、通常コピーのフレーム維持と秒コピーを区別する。"""
        curve, rows = timing.previewSteppedBake(2)
        timing.applySteppedBake(curve, rows)
        self.assertAlmostEqual(cmds.getAttr(self.source + ".tx", time=3.99), 2)
        self.assertAlmostEqual(cmds.getAttr(self.source + ".tx", time=4), 4)
        self.assertEqual(animCopy.copySteppedRange(), 1)
        cmds.currentUnit(time="ntsc")
        target = cmds.createNode("transform", name="dest")
        cmds.select(target)
        animCopy.pasteAnimation()
        self.assertEqual(cmds.keyframe(target + ".tx", q=True, tc=True), [2.5, 5, 7.5, 10, 12.5])
        cmds.currentUnit(time="film")
        cmds.select(self.source)
        animCopy.copyAnimation(timeRange=(2, 10))
        cmds.currentUnit(time="ntsc")
        target = cmds.createNode("transform", name="frames")
        cmds.select(target)
        animCopy.pasteAnimation()
        self.assertEqual(cmds.keyframe(target + ".tx", q=True, tc=True), [2, 4, 6, 8, 10])

    def test_reject_time_warp_and_layer(self):
        """時間ドライバーとレイヤーは通常ベイクの書込前に拒否する。"""
        curve, = cmds.keyframe(self.source + ".tx", q=True, name=True)
        cmds.select(curve)
        driver = timeDriver.attachSelected()
        cmds.select(self.source)
        with self.assertRaises(ValueError):
            timing.previewSteppedBake(2)
        cmds.select(driver)
        timeDriver.detachSelected()
        layer = cmds.animLayer("Layer")
        cmds.animLayer(layer, edit=True, attribute=self.source + ".tx")
        cmds.select(self.source)
        with self.assertRaises(ValueError):
            timing.previewSteppedBake(3)
        self.assertEqual(cmds.keyframe(curve, q=True, tc=True), [0, 6, 12])
