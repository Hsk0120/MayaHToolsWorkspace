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
                curve.set_key(0, 0).set_key(10, 20)
                self.assertEqual(curve.key_inputs(), [0, 10])
                self.assertAlmostEqual(curve.values()[1], 20)
                self.assertAlmostEqual(curve.evaluate(5), 10)
                self.assertEqual(curve.key_count(), 2)
                cmds.undo()
                self.assertEqual(curve.key_count(), 1)
                cmds.redo()
                self.assertEqual(curve.key_count(), 2)
                curve.remove_key(1)
                self.assertEqual(curve.key_count(), 1)
                cmds.undo()
                self.assertEqual(curve.key_count(), 2)

    def test_tangents_infinity_and_invalid_input(self):
        curve = self.create("animCurveUU").set_key(0, 0).set_key(1, 1)
        curve.set_tangent(0, outTangentType="flat")
        self.assertEqual(curve.tangent(0)["outTangentType"], "flat")
        cmds.undo()
        self.assertEqual(curve.tangent(0)["outTangentType"], "linear")
        curve.set_infinity("cycle", "linear")
        self.assertEqual(curve.infinity(), {"pre": "cycle", "post": "linear"})
        cmds.undo()
        self.assertEqual(curve.infinity()["pre"], "constant")
        with self.assertRaises(ValueError):
            curve.set_key(float("nan"), 1)
        with self.assertRaises(IndexError):
            curve.remove_key(5)

    def test_blend_sparse_inputs_and_connections(self):
        blend = self.create("blendWeighted")
        self.assertIsInstance(blend, hlib.nodes.BlendWeighted)
        blend.set_input(0, 3).set_input(5, 10).set_weight(5, 0.5)
        self.assertEqual(blend.input_indices(), [0, 5])
        self.assertAlmostEqual(blend.result(), 8)
        self.assertEqual(blend.weights(), {0: 1, 5: 0.5})
        cmds.undo()
        self.assertAlmostEqual(blend.result(), 13)
        cmds.redo()
        self.assertAlmostEqual(blend.result(), 8)
        curve = self.create("animCurveUU").set_key(0, 7)
        blend.connect_input(0, curve.output())
        self.assertAlmostEqual(blend.result(), 12)
        self.assertEqual(curve.driven_plugs()[0].node.full_name(), blend.full_name())
        cmds.undo()
        self.assertAlmostEqual(blend.result(), 8)
        cmds.redo()
        self.assertAlmostEqual(blend.result(), 12)
        with self.assertRaises(ValueError):
            blend.set_weight(-1, 1)

    def test_mirror_and_shift_ignore_other_selected_keys(self):
        for kind in ("animCurveTL", "animCurveUU"):
            curve = self.create(kind).set_key(-2, 3).set_key(4, 9)
            other = self.create("animCurveTU").set_key(1, 10)
            cmds.selectKey(other.full_name(), index=(0, 0))
            curve.mirror(input=True, value=True)
            self.assertEqual(curve.key_inputs(), [-4, 2])
            self.assertAlmostEqual(curve.evaluate(-1), -6)
            self.assertEqual(other.values(), [10])
            cmds.undo()
            self.assertEqual(curve.key_inputs(), [-2, 4])
            cmds.redo()
            self.assertEqual(curve.key_inputs(), [-4, 2])
            curve.shift_keys(1, 2)
            self.assertEqual(curve.key_inputs(), [-3, 3])
            self.assertAlmostEqual(curve.evaluate(0), -4)
            cmds.selectKey(clear=True)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
