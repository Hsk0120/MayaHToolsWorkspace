"""コントローラー階層へ移譲した複合操作を検証する。"""

import unittest

from maya import cmds
import mlib
from mlrig.setups import ControlHierarchy


class ControlHierarchyTests(unittest.TestCase):
    """通常Undoと高速更新のオフセット階層・チャンネル操作を確認する。"""

    def setUp(self):
        """テスト専用シーンを作る。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def tearDown(self):
        """検証シーンを破棄する。"""
        cmds.file(new=True, force=True)

    def test_offset_groups_preserve_world_and_order(self):
        """外側から内側への順序と対象のワールド姿勢を保つ。"""
        for fast in (False, True):
            parent = mlib.createNode("transform")
            parent.setTranslate((5, 1, 2))
            target = mlib.createNode("transform", parent=parent)
            target.setTranslate((1, 2, 3)).setRotate((0.2, 0.3, 0.4))
            before = target.getMatrix(worldSpace=True)
            cmds.flushUndo()
            groups = ControlHierarchy.createOffsetGroups(target, "zero", "offset", fast=fast)
            self.assertEqual(groups[0].getParent(), parent)
            self.assertEqual(groups[1].getParent(), groups[0])
            self.assertEqual(target.getParent(), groups[1])
            self.assertTrue(target.getMatrix(worldSpace=True).isEquivalent(before, 1e-8))
            self.assertTrue(groups[0].getMatrix(worldSpace=True).isEquivalent(before, 1e-8))
            self.assertTrue(groups[1].getMatrix(worldSpace=True).isEquivalent(before, 1e-8))
            if fast:
                self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
            else:
                cmds.undo()
                self.assertEqual(target.getParent(), parent)
                self.assertFalse(groups[0].isValid())

    def test_channel_release_and_undo(self):
        """親子Plugのロック解除と入出力切断を通常・高速で確認する。"""
        for fast in (False, True):
            source = mlib.createNode("transform")
            target = mlib.createNode("transform")
            source.getPlug("translateX").connectTo(target.getPlug("translateX"))
            target.getPlug("translate").setFlags(locked=True)
            target.getPlug("rotateY").setFlags(locked=True)
            cmds.flushUndo()
            result = ControlHierarchy.unlockAndDisconnectTransformChannels(target, fast=fast)
            self.assertIs(result, target)
            self.assertFalse(target.getPlug("translate").isLocked())
            self.assertFalse(target.getPlug("rotateY").isLocked())
            self.assertIsNone(target.getPlug("translateX").getSource())
            if fast:
                self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
            else:
                cmds.undo()
                self.assertTrue(target.getPlug("translate").isLocked())
                self.assertTrue(target.getPlug("rotateY").isLocked())
                self.assertIsNotNone(target.getPlug("translateX").getSource())


if __name__ == "__main__":
    unittest.main()
