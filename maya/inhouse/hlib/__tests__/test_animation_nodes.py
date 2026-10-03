"""全8型と重み付き加算の登録・編集・Undoを検証する。"""
import sys
import unittest
import uuid
import maya.cmds as cmds
import hlib

hlib.reload()


class AnimationNodesTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibAnim_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def create(self, kind):
        return hlib.createNode(kind, name=self.ns + ":" + kind)

    def test_all_types(self):
        for suffix in ("TA", "TL", "TT", "TU", "UA", "UL", "UT", "UU"):
            with self.subTest(suffix=suffix):
                curve = self.create("animCurve" + suffix)
                self.assertIsInstance(curve, getattr(hlib.nodes, "AnimCurve" + suffix))
                self.assertIsInstance(curve, hlib.nodes.AnimCurve)
                curve.setKey(0, 0).setKey(10, 20)
                self.assertEqual(curve.keyInputs(), [0, 10])
                self.assertAlmostEqual(curve.keyValues()[1], 20)
                self.assertAlmostEqual(curve.evaluate(5), 10)
                self.assertEqual(curve.keyCount(), 2)
                cmds.undo()
                self.assertEqual(curve.keyCount(), 1)
                cmds.redo()
                self.assertEqual(curve.keyCount(), 2)
                curve.removeKey(1)
                self.assertEqual(curve.keyCount(), 1)
                cmds.undo()
                self.assertEqual(curve.keyCount(), 2)

    def test_tangents_infinity_and_invalid_input(self):
        curve = self.create("animCurveUU").setKey(0, 0).setKey(1, 1)
        curve.setTangent(0, outTangentType="flat")
        self.assertEqual(curve.getTangent(0)["outTangentType"], "flat")
        cmds.undo()
        self.assertEqual(curve.getTangent(0)["outTangentType"], "linear")
        curve.setInfinity(pre="cycle", post="linear")
        self.assertEqual(curve.getInfinity(), {"pre": "cycle", "post": "linear"})
        cmds.undo()
        self.assertEqual(curve.getInfinity()["pre"], "constant")
        with self.assertRaises(ValueError):
            curve.setKey(float("nan"), 1)
        with self.assertRaises(IndexError):
            curve.removeKey(5)

    def test_blend_sparse_inputs_and_connections(self):
        blend = self.create("blendWeighted")
        self.assertIsInstance(blend, hlib.nodes.BlendWeighted)
        blend.setInput(0, 3).setInput(5, 10).setWeight(5, 0.5)
        self.assertEqual(blend.inputIndices(), [0, 5])
        self.assertAlmostEqual(blend.result(), 8)
        self.assertEqual(blend.getWeights(), {0: 1, 5: 0.5})
        cmds.undo()
        self.assertAlmostEqual(blend.result(), 13)
        cmds.redo()
        self.assertAlmostEqual(blend.result(), 8)
        curve = self.create("animCurveUU").setKey(0, 7)
        blend.connectInput(0, curve.outputPlug())
        self.assertAlmostEqual(blend.result(), 12)
        self.assertEqual(curve.drivenPlugs()[0].node.fullName(), blend.fullName())
        cmds.undo()
        self.assertAlmostEqual(blend.result(), 8)
        cmds.redo()
        self.assertAlmostEqual(blend.result(), 12)
        with self.assertRaises(ValueError):
            blend.setWeight(-1, 1)

    def test_mirror_and_shift_ignore_other_selected_keys(self):
        for kind in ("animCurveTL", "animCurveUU"):
            curve = self.create(kind).setKey(-2, 3).setKey(4, 9)
            other = self.create("animCurveTU").setKey(1, 10)
            cmds.selectKey(other.fullName(), index=(0, 0))
            curve.mirror(input=True, value=True)
            self.assertEqual(curve.keyInputs(), [-4, 2])
            self.assertAlmostEqual(curve.evaluate(-1), -6)
            self.assertEqual(other.keyValues(), [10])
            cmds.undo()
            self.assertEqual(curve.keyInputs(), [-2, 4])
            cmds.redo()
            self.assertEqual(curve.keyInputs(), [-4, 2])
            curve.shiftKeys(1, 2)
            self.assertEqual(curve.keyInputs(), [-3, 3])
            self.assertAlmostEqual(curve.evaluate(0), -4)
            cmds.selectKey(clear=True)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
