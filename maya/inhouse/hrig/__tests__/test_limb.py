"""最小リグの数値・切替・永続化を隔離Maya standaloneで検証する。"""

import math
import tempfile
import unittest
from pathlib import Path
from maya import cmds
from hrig import build_limb
from hrig.limb import LimbRig
from hrig.soft_ik import softened_distance
from hrig.skin import bind_mesh, create_skin_lod, set_mesh_lod


class LimbTest(unittest.TestCase):
    """実際のDG出力を検証する。新規シーンを使う専用テスト。"""

    backend = "bifrost"

    @classmethod
    def setUpClass(cls):
        """プラグイン初期化はテスト対象のUndoから分離する。"""
        if cls.backend == "bifrost":
            from hlib_bifrost import ensure_available
            ensure_available()

    def setUp(self):
        """部位を空シーンに生成する。"""
        cmds.file(new=True,force=True)
        self.rig=build_limb(backend=self.backend)

    def position(self):
        """終端のワールド座標を評価する。"""
        return cmds.xform(self.rig.joints()[2],query=True,worldSpace=True,translation=True)

    def test_fk_and_soft_ik(self):
        """FK、LOD0のIK、Soft IKの数値を検証する。"""
        self.assertEqual(self.position(),[10,0,0])
        self.rig.set_mode('ik')
        for distance in (2,8,9,9.5,10,12):
            cmds.setAttr(self.rig.controls()['target']+'.translateX',distance-8)
            self.rig.set_lod(0)
            self.assertAlmostEqual(math.dist(self.position(),(0,0,0)),min(distance,10),delta=0.002)
            self.rig.set_lod(1)
            self.assertAlmostEqual(math.dist(self.position(),(0,0,0)),softened_distance(distance,10,1),delta=0.002)

    def test_matching(self):
        """曲がった姿勢のFK/IK往復で終端と中間関節を保持する。"""
        self.rig.set_mode('ik')
        cmds.setAttr(self.rig.controls()['target']+'.translate',0,2,1)
        expected=[cmds.xform(j,q=True,ws=True,matrix=True) for j in self.rig.joints()[:3]]
        self.rig.match_fk();self.rig.set_mode('fk')
        self.rig.match_ik();self.rig.set_mode('ik')
        for joint,matrix in zip(self.rig.joints(),expected):
            actual=cmds.xform(joint,q=True,ws=True,matrix=True)
            for a,b in zip(actual,matrix):
                self.assertAlmostEqual(a,b,delta=0.003)

    def test_modes_and_parent_transform(self):
        """部位の親変換と明示的な評価ブロックを検証する。"""
        cmds.setAttr(self.rig.root.full_name()+'.translate',3,4,5)
        cmds.setAttr(self.rig.root.full_name()+'.rotateZ',90)
        for value,expected in zip(self.position(),(3,14,5)):
            self.assertAlmostEqual(value,expected,places=5)
        self.assertEqual(cmds.getAttr(self.rig._member('handle')+'.nodeState'),2)
        self.assertEqual(cmds.getAttr(self.rig._member('softGraph')+'.nodeState'),2)
        self.rig.set_mode('ik');self.rig.set_lod(0)
        self.assertEqual(cmds.getAttr(self.rig._member('softGraph')+'.nodeState'),2)
        self.assertFalse(cmds.connectionInfo(self.rig._member('helper')+'.rotate',isDestination=True))

    def test_save_reload_rename_delete(self):
        """メッセージ参照を保存し、改名後も切替・削除できる。"""
        with tempfile.TemporaryDirectory() as directory:
            cmds.file(rename=str(Path(directory)/'limb.ma'))
            cmds.file(save=True,type='mayaAscii')
            cmds.file(new=True,force=True)
            cmds.file(str(Path(directory)/'limb.ma'),open=True,force=True)
        cmds.rename('limb','renamedLimb')
        rig=LimbRig('renamedLimb')
        rig.set_mode('ik')
        self.assertEqual(len(rig.joints()),4)
        rig.delete()
        self.assertFalse(cmds.objExists('renamedLimb'))
        self.assertFalse(cmds.objExists('limb_soft_ik_multiplyDivide'))

    def test_skin_lod(self):
        """proxy側に補助骨を含めず、非選択スキンをブロックする。"""
        high=cmds.polyCube(name='high',width=10,height=1,depth=1,subdivisionsX=8)[0]
        low=cmds.polyCube(name='proxy',width=10,height=1,depth=1,subdivisionsX=2)[0]
        for node in (high,low):
            cmds.setAttr(node+'.translateX',5)
            cmds.makeIdentity(node,apply=True,translate=True)
        skin=bind_mesh(self.rig,high)
        proxy_skin=create_skin_lod(self.rig,high,low,skin)
        self.assertEqual(len(cmds.skinCluster(proxy_skin,query=True,influence=True)),3)
        set_mesh_lod(high,skin,low,proxy_skin,proxy=True)
        self.assertEqual(cmds.getAttr(skin+'.nodeState'),1)
        self.assertEqual(cmds.getAttr(proxy_skin+'.envelope'),1)
        self.assertFalse(cmds.getAttr(high+'.visibility'))

    def test_backend_exchange(self):
        """骨とコントローラーを保持したままC++とBifrostを交換する。"""
        self.rig.set_mode('ik')
        cmds.setAttr(self.rig.controls()['target']+'.translateX',1.5)
        expected=self.position()
        joints=self.rig.joints()
        for backend in ('standard','cpp','standard','bifrost','standard'):
            self.rig.set_backend(backend)
            self.assertEqual(self.rig.joints(),joints)
            for actual,value in zip(self.position(),expected):
                self.assertAlmostEqual(actual,value,delta=0.002)

    def test_bake_external_fk(self):
        """外部の同一骨長チェーンをコントローラーのキーへ変換する。"""
        from hrig.animation import bake_source
        a=cmds.createNode('joint',name='sourceRoot')
        b=cmds.createNode('joint',name='sourceMid',parent=a)
        c=cmds.createNode('joint',name='sourceTip',parent=b)
        cmds.setAttr(b+'.tx',5);cmds.setAttr(c+'.tx',5)
        cmds.setKeyframe(a,attribute='rz',time=1,value=0)
        cmds.setKeyframe(a,attribute='rz',time=3,value=30)
        cmds.setKeyframe(b,attribute='rz',time=1,value=-30)
        cmds.setKeyframe(b,attribute='rz',time=3,value=-60)
        self.rig.set_lod(0)
        for mode in ('fk','ik'):
            self.assertEqual(bake_source(self.rig,[a,b,c],1,3,mode=mode),(1,2,3))
            for frame in (1,2,3):
                cmds.currentTime(frame)
                expected=cmds.xform(c,q=True,ws=True,t=True)
                for actual,value in zip(self.position(),expected):
                    self.assertAlmostEqual(actual,value,delta=0.003)

    def test_reverse_foot_layer(self):
        """足ロールを後付けし、LOD0で計算経路から外す。"""
        from hrig.reverse_foot import add_reverse_foot
        add_reverse_foot(self.rig)
        self.rig.set_mode('ik')
        target=self.rig.controls()['target']
        before=self.position()
        cmds.setAttr(target+'.ballRoll',30)
        self.assertGreater(math.dist(before,self.position()),0.1)
        with self.assertRaises(ValueError):
            self.rig.match_ik()
        self.rig.set_lod(0)
        for actual,value in zip(self.position(),(8,0,0)):
            self.assertAlmostEqual(actual,value,delta=0.002)
        with self.assertRaises(ValueError):
            add_reverse_foot(self.rig)

    def test_demo_naming_and_offsets(self):
        """参照の階層・用途サフィックスとゼロ姿勢をデモで検証する。"""
        from hrig.examples.limb_demo import build_demo
        cmds.file(new=True, force=True)
        demo = build_demo()
        rig = demo['rig']
        self.assertEqual(rig.root.full_name(), '|rig')
        for group in ('geo_grp', 'jnt_grp', 'ctrl_grp', 'setup_grp'):
            self.assertTrue(cmds.objExists('|rig|' + group))
        self.assertTrue(cmds.objExists('|rig|jnt_grp|limb_jnt_grp|root_jnt|mid_jnt|tip_jnt'))
        self.assertTrue(cmds.objExists(
            '|rig|ctrl_grp|limb_ctrl_grp|limb_fk_ctrl_grp|root_ctrl_ofs|root_ctrl|mid_ctrl_ofs|mid_ctrl|tip_ctrl_ofs|tip_ctrl'))
        for control in rig.controls().values():
            short = control.rsplit('|', 1)[-1]
            self.assertTrue(short.endswith('_ctrl'))
            self.assertEqual(cmds.listRelatives(control, parent=True)[0], short + '_ofs')
            self.assertEqual(cmds.getAttr(control + '.translate')[0], (0, 0, 0))
            self.assertEqual(cmds.getAttr(control + '.rotate')[0], (0, 0, 0))
            self.assertEqual(cmds.listRelatives(control, shapes=True), [short + 'Shape'])
        for role, name in (('high_mesh', 'body_geo'), ('proxy_mesh', 'body_proxy_geo')):
            self.assertEqual(cmds.ls(demo[role], long=True), ['|rig|geo_grp|limb_geo_grp|' + name])
        for role in ('fkSet','ikSet','softSet','helperSet','footSet'):
            self.assertTrue(cmds.sets(rig._member(role), isMember=rig._member('moduleSet')))
        self.assertTrue(cmds.sets(rig._member('softGraph'), isMember=rig._member('softSet')))
        self.assertTrue(cmds.sets(rig._member('helper'), isMember=rig._member('helperSet')))
        self.assertFalse(cmds.getAttr(rig._member('setupGroup') + '.visibility'))
        rig.set_lod(0)
        cmds.setAttr(rig.root.full_name() + '.translate', 3, 4, 5)
        cmds.setAttr(rig.root.full_name() + '.rotateZ', 90)
        for actual, expected in zip(cmds.xform(rig.joints()[2], q=True, ws=True, t=True), (3, 12, 5)):
            self.assertAlmostEqual(actual, expected, delta=0.002)
        rig.match_fk(); rig.set_mode('fk')
        rig.match_ik(); rig.set_mode('ik')
        for actual, expected in zip(cmds.xform(rig.joints()[2], q=True, ws=True, t=True), (3, 12, 5)):
            self.assertAlmostEqual(actual, expected, delta=0.002)
        # 2体目は明示名を接頭辞にし、自動採番に依存しない。
        second = build_demo('other')
        self.assertTrue(cmds.objExists('|other|other_jnt_grp|other_limb_jnt_grp|other_root_jnt'))
        self.assertNotEqual(second['rig'].joints(), rig.joints())
        before = set(cmds.ls(long=True))
        with self.assertRaises(ValueError):
            build_demo()
        self.assertEqual(set(cmds.ls(long=True)), before)


if __name__=='__main__':
    unittest.main()
