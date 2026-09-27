"""Bifrostなしでも利用できるC++バックエンドの実機テスト。"""

import math
import unittest
from maya import cmds
from hrig import build_limb
from hrig.soft_ik import softened_distance


class NativeTest(unittest.TestCase):
    """ビルド済み専用ノードと最小リグを検証する。"""

    def setUp(self):
        """空シーンへC++リグを構築する。"""
        cmds.file(new=True,force=True)
        self.rig=build_limb(backend='cpp')

    def test_numeric_and_lod(self):
        """目標距離とsoftnessの組合せを参照実装と比較する。"""
        self.rig.set_mode('ik')
        target=self.rig.controls()['target']
        for softness in (0,0.1,1,5,10):
            cmds.setAttr(target+'.softness',softness)
            for distance in (0,2,8,9.5,10,12):
                cmds.setAttr(target+'.tx',distance-8)
                output=cmds.xform(self.rig.joints()[2],q=True,ws=True,t=True)
                self.assertAlmostEqual(math.dist(output,(0,0,0)),
                                       softened_distance(distance,10,softness),delta=0.002)
        self.rig.set_mode('fk')
        self.assertEqual(cmds.getAttr(self.rig._member('softGraph')+'.nodeState'),2)

    def test_layer_settings_and_channel_requests(self):
        """GUIと共通の適用処理・有効状態・Undoを検証する。"""
        from hrig.channel_controls import apply
        rig = self.rig
        module = rig._member('channelModule')
        cmds.setAttr(module+'.matchOnSwitch',False)
        cmds.setAttr(module+'.mode',1)
        apply(rig)
        self.assertEqual(rig.mode(),'ik')
        soft = rig._member('channel_soft')
        cmds.setAttr(soft+'.enabled',False)
        apply(rig)
        self.assertFalse(rig.layer_enabled('soft'))
        self.assertFalse(cmds.getAttr(soft+'.active'))
        self.assertEqual(cmds.getAttr(rig._member('softGraph')+'.nodeState'),2)
        rig.set_layer_enabled('soft',True)
        self.assertTrue(cmds.getAttr(soft+'.enabled'))
        rig.set_lod(0)
        self.assertTrue(cmds.getAttr(soft+'.enabled'))
        self.assertFalse(cmds.getAttr(soft+'.active'))
        cmds.undo()
        self.assertEqual(rig.lod(),1)
        self.assertTrue(cmds.getAttr(soft+'.active'))

    def test_match_redo_preserves_pose(self):
        """親階層を持つFK合わせをRedoしてもローカル位置を二重変換しない。"""
        from hlib.decorators.undo import undo_chunk
        rig = self.rig
        rig.set_mode('ik')
        expected = [cmds.xform(j,q=True,ws=True,matrix=True) for j in rig.joints()[:3]]
        with undo_chunk('match_and_switch'):
            rig.match_fk()
            rig.set_mode('fk')
        cmds.undo()
        self.assertEqual(rig.mode(),'ik')
        cmds.redo()
        self.assertEqual(rig.mode(),'fk')
        for joint, matrix in zip(rig.joints(),expected):
            for actual,value in zip(cmds.xform(joint,q=True,ws=True,matrix=True),matrix):
                self.assertAlmostEqual(actual,value,delta=0.003)


if __name__=='__main__':
    unittest.main()
