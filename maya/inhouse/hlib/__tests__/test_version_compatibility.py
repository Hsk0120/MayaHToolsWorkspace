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
            node = hlib.node(joint)
            cmds.setAttr(joint + ".tx", 3)
            before = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
            for target in (parent, hlib.node(parent)):
                self.assertIs(node.set_parent(target), node)
                self.assertEqual(cmds.xform(node.full_name(), query=True, worldSpace=True, matrix=True), before)
            node.set_parent(None)
            self.assertIsNone(node.parent_path())
            node.set_parent(None)
            cmds.undo()
            self.assertEqual(node.parent_path().fullPathName(), hlib.node(parent).full_name())
            cmds.redo()
            self.assertIsNone(node.parent_path())
            with self.assertRaises(RuntimeError):
                node.set_parent(prefix + "missing")
            cmds.delete(node.full_name())
            with self.assertRaises(RuntimeError):
                node.set_parent(None)
        finally:
            if cmds.objExists(joint):
                cmds.delete(joint)
            cmds.delete(parent)

    def test_range_reload_undo_and_redo(self):
        slider = hlib.timeSlider()
        playback, animation = slider.playback_range(), slider.animation_range()
        try:
            if str(cmds.about(version=True)).startswith("2022"):
                before = cmds.undoInfo(query=True, undoName=True)
                slider.set_playback_range(-12, 103)
                hlib.reload()
                self.assertEqual(slider.playback_range(), (-12, 103))
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), before)
                slider.set_animation_range(-24, 206)
                self.assertEqual(slider.animation_range(), (-24, 206))
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), before)
                return  # Maya 2022では履歴を作らない。直前の別操作をUndoしない。
            slider.set_playback_range(-12, 103)
            hlib.reload()
            cmds.undo()
            self.assertEqual(slider.playback_range(), playback)
            self.assertEqual(slider.animation_range(), animation)
            cmds.redo()
            self.assertEqual(slider.playback_range(), (-12, 103))
            before_animation_edit = slider.animation_range()
            slider.set_animation_range(-24, 206)
            cmds.undo()
            self.assertEqual(slider.animation_range(), before_animation_edit)
            cmds.redo()
            self.assertEqual(slider.animation_range(), (-24, 206))
        finally:
            slider.set_animation_range(*animation)
            slider.set_playback_range(*playback)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
