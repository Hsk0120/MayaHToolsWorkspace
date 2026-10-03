"""古いMayaで見つかった親変更とタイムラインUndoの回帰テスト。"""
import sys
import unittest
import uuid
import maya.cmds as cmds
import hlib

hlib.reload()


class VersionCompatibilityTest(unittest.TestCase):
    def test_same_parent_and_world_are_noops(self):
        prefix = "hlibCompat_" + uuid.uuid4().hex
        parent = cmds.createNode("transform", name=prefix)
        joint = cmds.createNode("joint", name=prefix + "Joint", parent=parent)
        try:
            node = hlib.getNode(joint)
            cmds.setAttr(joint + ".tx", 3)
            before = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
            for target in (parent, hlib.getNode(parent)):
                self.assertIs(node.setParent(target), node)
                self.assertEqual(cmds.xform(node.fullName(), query=True, worldSpace=True, matrix=True), before)
            node.setParent(None)
            self.assertIsNone(node.parentPath())
            node.setParent(None)
            cmds.undo()
            self.assertEqual(node.parentPath().fullPathName(), hlib.getNode(parent).fullName())
            cmds.redo()
            self.assertIsNone(node.parentPath())
            with self.assertRaises(RuntimeError):
                node.setParent(prefix + "missing")
            cmds.delete(node.fullName())
            with self.assertRaises(RuntimeError):
                node.setParent(None)
        finally:
            if cmds.objExists(joint):
                cmds.delete(joint)
            cmds.delete(parent)

    def test_range_reload_undo_and_redo(self):
        slider = hlib.getTimeSlider()
        playback, animation = slider.getPlaybackRange(), slider.getAnimationRange()
        try:
            if str(cmds.about(version=True)).startswith("2022"):
                before = cmds.undoInfo(query=True, undoName=True)
                slider.setPlaybackRange(-12, 103)
                hlib.reload()
                self.assertEqual(slider.getPlaybackRange(), (-12, 103))
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), before)
                slider.setAnimationRange(-24, 206)
                self.assertEqual(slider.getAnimationRange(), (-24, 206))
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), before)
                return  # Maya 2022では履歴を作らない。直前の別操作をUndoしない。
            slider.setPlaybackRange(-12, 103)
            hlib.reload()
            cmds.undo()
            self.assertEqual(slider.getPlaybackRange(), playback)
            self.assertEqual(slider.getAnimationRange(), animation)
            cmds.redo()
            self.assertEqual(slider.getPlaybackRange(), (-12, 103))
            before_animation_edit = slider.getAnimationRange()
            slider.setAnimationRange(-24, 206)
            cmds.undo()
            self.assertEqual(slider.getAnimationRange(), before_animation_edit)
            cmds.redo()
            self.assertEqual(slider.getAnimationRange(), (-24, 206))
        finally:
            slider.setAnimationRange(*animation)
            slider.setPlaybackRange(*playback)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
