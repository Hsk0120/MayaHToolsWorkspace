"""SkinCluster.copyWeightsTo・deforms と SkinClusters の同名メソッドの約束を固定する(担当C)。

copyWeightsTo は最近傍の点と name/closestJoint でウェイトを写し、1回の Undo で戻る。
deforms は形状の履歴に自身が含まれるかを返す。
"""

import unittest
import uuid

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import Node, SkinCluster, SkinClusters


class SkinCopyTest(unittest.TestCase):
    """2本の joint にバインドした円柱どうしでウェイトを写す。"""

    def setUp(self):
        self.ns = "mlibSpecCSkin_" + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.ns)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        self.selection = cmds.ls(selection=True, long=True)
        cmds.select(clear=True)
        self.root = cmds.joint(name=self.name("root"), position=(0, 0, 0))
        self.tip = cmds.joint(name=self.name("tip"), position=(0, 2, 0))
        cmds.select(clear=True)
        # 元: 側面は20分割・高さ4段。上端の輪(80〜99)と上の蓋の中心(101)だけを tip に割り当てる。
        self.source = cmds.polyCylinder(name=self.name("source"), height=2, subdivisionsHeight=4)[0]
        cmds.move(0, 1, 0, self.source)
        self.target = cmds.polyCylinder(name=self.name("target"), height=2, subdivisionsHeight=4,
                                        subdivisionsAxis=10)[0]
        cmds.move(0, 1, 0, self.target)
        self.source_skin = cmds.skinCluster(self.root, self.tip, self.source, toSelectedBones=True)[0]
        cmds.skinPercent(self.source_skin, self.source + ".vtx[*]", transformValue=[(self.root, 1.0)])
        cmds.skinPercent(self.source_skin, [self.source + ".vtx[80:99]", self.source + ".vtx[101]"],
                         transformValue=[(self.tip, 1.0)])
        self.target_skin = cmds.skinCluster(self.root, self.tip, self.target, toSelectedBones=True)[0]
        cmds.select(clear=True)

    def tearDown(self):
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_state)
        cmds.select(self.selection, replace=True) if self.selection else cmds.select(clear=True)

    def name(self, text):
        return self.ns + ":" + text

    def weights(self, index):
        return cmds.skinPercent(self.target_skin, "{}.vtx[{}]".format(self.target, index), query=True, value=True)

    def test_copy_and_undo_once(self):
        """最近傍のウェイトを写して None を返し、1回の Undo で元に戻る。"""
        before = [self.weights(index) for index in (0, 45)]
        cmds.flushUndo()
        self.assertIsNone(SkinCluster(self.source_skin).copyWeightsTo(SkinCluster(self.target_skin)))
        # 下端の輪(0〜9)は root、上端の輪(40〜49)は tip だけになる。
        for index in (0, 5):
            self.assertEqual([round(value, 6) for value in self.weights(index)], [1.0, 0.0])
        for index in (40, 45):
            self.assertEqual([round(value, 6) for value in self.weights(index)], [0.0, 1.0])
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibSkinClusterCopyWeightsTo")
        cmds.undo()
        for index, expected in zip((0, 45), before):
            for value, old in zip(self.weights(index), expected):
                self.assertAlmostEqual(value, old, places=6)

    def test_target_by_name(self):
        """転送先は名前でも指定できる。"""
        SkinCluster(self.source_skin).copyWeightsTo(self.target_skin)
        self.assertEqual([round(value, 6) for value in self.weights(45)], [0.0, 1.0])

    def test_errors(self):
        """自身は ValueError、存在しない名前は RuntimeError、skinCluster 以外は TypeError。"""
        skin = SkinCluster(self.source_skin)
        with self.assertRaisesRegex(ValueError, "must differ"):
            skin.copyWeightsTo(self.source_skin)
        with self.assertRaises(RuntimeError):
            skin.copyWeightsTo(self.name("missing"))
        with self.assertRaisesRegex(TypeError, "SkinCluster requires a compatible node"):
            skin.copyWeightsTo(self.root)

    def test_deforms(self):
        """Transform・Shape のどちらでも履歴を調べ、他の形状・joint は False。"""
        skin = SkinCluster(self.source_skin)
        self.assertTrue(skin.deforms(self.source))
        self.assertTrue(skin.deforms(Node(self.source).getShape()))
        self.assertFalse(skin.deforms(self.target))
        self.assertFalse(skin.deforms(self.root))
        with self.assertRaises(RuntimeError):
            skin.deforms(self.name("missing"))

    def test_bulk(self):
        """deforms はリスト、copyWeightsTo は自身。自身を含むと番号付きで止まる。"""
        skins = SkinClusters([self.source_skin, self.target_skin])
        self.assertEqual(skins.deforms(self.target), [False, True])
        single = SkinClusters([self.source_skin])
        self.assertIs(single.copyWeightsTo(self.target_skin), single)
        with self.assertRaisesRegex(RuntimeError, r"SkinClusters\.copyWeightsTo failed at item 1: .*must differ"):
            skins.copyWeightsTo(self.target_skin)


if __name__ == "__main__":
    unittest.main()
