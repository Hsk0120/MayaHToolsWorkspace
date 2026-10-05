"""ゼロウェイト追加・ノード色の設定とUndo/Redoを実Mayaで確認する。"""
import sys
import unittest
import uuid
import maya.cmds as cmds
import hlib

hlib.reload()


class InfluencesColorsTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibIC_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def node(self, kind):
        return hlib.createNode(kind, name=self.ns + ":" + kind)

    def test_add_zero_influences_and_undo(self):
        joints = [self.node("joint") for _ in range(4)]
        mesh = cmds.polyCube(name=self.ns + ":mesh")[0]
        name = cmds.skinCluster([j.fullName() for j in joints[:2]], mesh, name=self.ns + ":skin")[0]
        skin = hlib.getNode(name)
        pose = skin.bindPose()
        if pose:
            cmds.rename(pose.fullName(), self.ns + ":pose")
        vertices = cmds.ls(mesh + ".vtx[*]", flatten=True)
        for v in vertices:
            cmds.skinPercent(name, v, transformValue=[(joints[0].fullName(), 0.25), (joints[1].fullName(), 0.75)])
        # 合計1でない保存ウェイトも再正規化されないことを確認する。
        cmds.setAttr(name + ".normalizeWeights", 0)
        cmds.skinPercent(name, vertices[0], normalize=False,
                         transformValue=[(joints[0].fullName(), 0.2), (joints[1].fullName(), 0.3)])
        joints[0].plug("lockInfluenceWeights").set(True)
        for normalization in (0, 1, 2):
            for obey in (False, True):
                with self.subTest(normalization=normalization, obey=obey):
                    cmds.setAttr(name + ".normalizeWeights", normalization)
                    cmds.setAttr(name + ".maintainMaxInfluences", obey)
                    cmds.setAttr(name + ".maxInfluences", 2)
                    before = [[cmds.skinPercent(name, v, query=True, transform=j.fullName()) for j in joints[:2]] for v in vertices]
                    indices = [skin.fn.indexForInfluenceObject(j.mpath()) for j in joints[:2]]
                    raw = [[cmds.getAttr(f"{name}.weightList[{v}].weights[{i}]") for i in indices] for v in range(len(vertices))]
                    skin.addInfluences([joints[2], joints[3], joints[2], joints[0]])
                    for i, v in enumerate(vertices):
                        after = [cmds.skinPercent(name, v, query=True, transform=j.fullName()) for j in joints]
                        self.assertEqual(after[:2], before[i])
                        self.assertEqual(after[2:], [0, 0])
                        self.assertEqual([cmds.getAttr(f"{name}.weightList[{i}].weights[{k}]") for k in indices], raw[i])
                    self.assertTrue(joints[0].plug("lockInfluenceWeights").get())
                    cmds.undo()
                    self.assertEqual(len(skin.influences()), 2)
                    cmds.redo()
                    self.assertEqual(len(skin.influences()), 4)
                    cmds.undo()
        other = self.node("transform")
        with self.assertRaises(ValueError):
            skin.addInfluences([joints[2], other])
        self.assertEqual(len(skin.influences()), 2)
        skin.addInfluences([])
        skin.addInfluences(joints[0])
        self.assertEqual(len(skin.influences()), 2)

    def test_colors_and_undo(self):
        transform = self.node("transform")
        shape_name = cmds.createNode("nurbsCurve", name=self.ns + ":curveShape", parent=transform.fullName())
        shape = hlib.getNode(shape_name)
        self.assertIsNone(transform.getOutlinerColor().rgb)
        transform.setOutlinerColor((1, 0.5, 0))
        self.assertEqual(transform.getOutlinerColor().rgb, (1, 0.5, 0))
        cmds.undo()
        self.assertIsNone(transform.getOutlinerColor().rgb)
        cmds.redo()
        self.assertEqual(transform.getOutlinerColor().rgb, (1, 0.5, 0))
        transform.setOutlinerColor(None)
        self.assertIsNone(transform.getOutlinerColor().rgb)
        shape.setOverrideColor(13)
        self.assertEqual(shape.getOverrideColor().index, 13)
        shape.setOverrideColor((0, 0.5, 1))
        self.assertEqual(shape.getOverrideColor().rgb, (0, 0.5, 1))
        cmds.undo()
        self.assertEqual(shape.getOverrideColor().index, 13)
        cmds.redo()
        self.assertEqual(shape.getOverrideColor().rgb, (0, 0.5, 1))
        shape.setOverrideColor(None)
        self.assertEqual(shape.getOverrideColor().mode, "disabled")
        cmds.undo()
        self.assertEqual(shape.getOverrideColor().rgb, (0, 0.5, 1))
        for value in (-1, 32, True, (1, 0), (1, float("nan"), 0)):
            with self.assertRaises(ValueError):
                shape.setOverrideColor(value)
        self.assertEqual(shape.getOverrideColor().rgb, (0, 0.5, 1))
        with self.assertRaises(AttributeError):
            self.node("network").setOverrideColor(13)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
