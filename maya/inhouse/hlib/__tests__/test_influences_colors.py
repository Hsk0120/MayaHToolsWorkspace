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
        name = cmds.skinCluster([j.full_name for j in joints[:2]], mesh, name=self.ns + ":skin")[0]
        skin = hlib.node(name)
        pose = skin.bind_pose()
        if pose:
            cmds.rename(pose.full_name, self.ns + ":pose")
        vertices = cmds.ls(mesh + ".vtx[*]", flatten=True)
        for v in vertices:
            cmds.skinPercent(name, v, transformValue=[(joints[0].full_name, 0.25), (joints[1].full_name, 0.75)])
        # 合計1でない保存ウェイトも再正規化されないことを確認する。
        cmds.setAttr(name + ".normalizeWeights", 0)
        cmds.skinPercent(name, vertices[0], normalize=False,
                         transformValue=[(joints[0].full_name, 0.2), (joints[1].full_name, 0.3)])
        joints[0].plug("lockInfluenceWeights").set(True)
        for normalization in (0, 1, 2):
            for obey in (False, True):
                with self.subTest(normalization=normalization, obey=obey):
                    cmds.setAttr(name + ".normalizeWeights", normalization)
                    cmds.setAttr(name + ".maintainMaxInfluences", obey)
                    cmds.setAttr(name + ".maxInfluences", 2)
                    before = [[cmds.skinPercent(name, v, query=True, transform=j.full_name) for j in joints[:2]] for v in vertices]
                    indices = [skin.fn.indexForInfluenceObject(j.dag_path()) for j in joints[:2]]
                    raw = [[cmds.getAttr(f"{name}.weightList[{v}].weights[{i}]") for i in indices] for v in range(len(vertices))]
                    skin.add_influences([joints[2], joints[3].full_name, joints[2], joints[0]])
                    for i, v in enumerate(vertices):
                        after = [cmds.skinPercent(name, v, query=True, transform=j.full_name) for j in joints]
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
            skin.add_influences([joints[2], other])
        self.assertEqual(len(skin.influences()), 2)
        skin.add_influences([])
        skin.add_influences(joints[0])
        self.assertEqual(len(skin.influences()), 2)

    def test_colors_and_undo(self):
        transform = self.node("transform")
        shape_name = cmds.createNode("nurbsCurve", name=self.ns + ":curveShape", parent=transform.full_name)
        shape = hlib.node(shape_name)
        self.assertIsNone(transform.outliner_color())
        transform.set_outliner_color((1, 0.5, 0))
        self.assertEqual(transform.outliner_color(), (1, 0.5, 0))
        cmds.undo()
        self.assertIsNone(transform.outliner_color())
        cmds.redo()
        self.assertEqual(transform.outliner_color(), (1, 0.5, 0))
        transform.set_outliner_color(None)
        self.assertIsNone(transform.outliner_color())
        shape.set_override_color(13)
        self.assertEqual(shape.override_color(), 13)
        shape.set_override_color((0, 0.5, 1))
        self.assertEqual(shape.override_color(), (0, 0.5, 1))
        cmds.undo()
        self.assertEqual(shape.override_color(), 13)
        cmds.redo()
        self.assertEqual(shape.override_color(), (0, 0.5, 1))
        shape.set_override_color(None)
        self.assertIsNone(shape.override_color())
        cmds.undo()
        self.assertEqual(shape.override_color(), (0, 0.5, 1))
        for value in (-1, 32, True, (1, 0), (1, float("nan"), 0)):
            with self.assertRaises(ValueError):
                shape.set_override_color(value)
        self.assertEqual(shape.override_color(), (0, 0.5, 1))
        with self.assertRaises(RuntimeError):
            self.node("network").set_override_color(13)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
