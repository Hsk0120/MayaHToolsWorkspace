"""ポーズクリップのウェイトと記録先の分離を調べる。"""

import unittest

import maya.cmds as cmds

from animBar.core import poseClip


class PoseClipTest(unittest.TestCase):
    def test_partial_weight(self):
        """半量では各回転軸を線形補間し、ロックと別の名前空間を保つ。"""
        cmds.file(new=True, force=True)
        for namespace in ("actorA", "actorB"):
            cmds.namespace(add=namespace)
            cmds.createNode("transform", name=namespace + ":ctrl")
        ctrl = "actorA:ctrl"
        cmds.setAttr(ctrl + ".ry", -55)
        cmds.setAttr(ctrl + ".tx", 1.25)
        cmds.setAttr(ctrl + ".visibility", False)
        cmds.select(ctrl)
        clip = poseClip.captureSelected()
        cmds.setAttr(ctrl + ".ry", 0)
        cmds.setAttr(ctrl + ".tx", 0)
        cmds.setAttr(ctrl + ".visibility", True)
        cmds.setAttr(ctrl + ".tz", 7)
        cmds.setAttr(ctrl + ".tz", lock=True)
        cmds.select(clip)
        cmds.setAttr(clip + ".animBarPoseWeight", 0.25)
        poseClip.restoreSelected()
        self.assertTrue(cmds.getAttr(ctrl + ".visibility"))
        cmds.undo()
        cmds.setAttr(clip + ".animBarPoseWeight", 0.5)
        poseClip.restoreSelected()
        self.assertAlmostEqual(cmds.getAttr(ctrl + ".ry"), -27.5)
        self.assertAlmostEqual(cmds.getAttr(ctrl + ".tx"), 0.625)
        self.assertFalse(cmds.getAttr(ctrl + ".visibility"))
        self.assertEqual(cmds.getAttr(ctrl + ".tz"), 7)
        self.assertEqual(cmds.getAttr("actorB:ctrl.ry"), 0)
        cmds.undo()
        self.assertEqual(cmds.getAttr(ctrl + ".ry"), 0)
        self.assertTrue(cmds.getAttr(ctrl + ".visibility"))

    def test_restore_shortcut_subset(self):
        """記録した側の選択対象だけに全量適用し、1回でUndoできる。"""
        from animBar.core import commands
        cmds.file(new=True, force=True)
        for namespace in ("actorA", "actorB"):
            cmds.namespace(add=namespace)
            for name in ("hand", "foot"):
                cmds.createNode("transform", name=namespace + ":" + name)
        cmds.select("actorA:hand", "actorA:foot")
        clip = poseClip.captureSelected()
        for ctrl in ("actorA:hand", "actorA:foot", "actorB:hand"):
            cmds.setAttr(ctrl + ".tx", 5)
        cmds.setAttr(clip + ".animBarPoseWeight", 0)
        cmds.select(clip, "actorA:foot", "actorB:hand")
        commands.register()
        cmds.AnimBarRestorePoseClip()
        self.assertEqual([cmds.getAttr(n + ".tx") for n in ("actorA:hand", "actorA:foot", "actorB:hand")], [5, 0, 5])
        cmds.undo()
        self.assertEqual(cmds.getAttr("actorA:foot.tx"), 5)
        cmds.redo()
        self.assertEqual(cmds.getAttr("actorA:foot.tx"), 0)
