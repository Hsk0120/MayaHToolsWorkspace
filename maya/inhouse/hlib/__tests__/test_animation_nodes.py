"""全8型と重み付き加算の登録・編集・Undoを検証する。"""
import sys
import unittest
import uuid
from unittest.mock import patch
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

    def test_infinity_api_reads_and_fast_updates_all_types(self):
        """全8型で照会・fast更新がcmds非依存で、通常更新と同じ外挿になる。"""
        for suffix in ("TA", "TL", "TT", "TU", "UA", "UL", "UT", "UU"):
            curve = self.create("animCurve" + suffix).setKey(0, 0).setKey(1, 2)
            for mode in ("constant", "linear", "cycle", "cycleRelative", "oscillate"):
                curve.setInfinity(pre=mode, post=mode)
                expected = [curve.evaluate(t) for t in (-.5, 1.5)]
                cmds.undo()
                before = cmds.undoInfo(query=True, undoName=True)
                with patch.object(cmds, "getAttr", side_effect=AssertionError("getAttr")), \
                        patch.object(cmds, "setAttr", side_effect=AssertionError("setAttr")), \
                        patch.object(cmds, "undoInfo", side_effect=AssertionError("undoInfo")):
                    self.assertIs(curve.setInfinity(pre=mode, post=mode, fast=True), curve)
                    self.assertEqual(curve.getInfinity(), dict(pre=mode, post=mode))
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), before)
                for actual, value in zip([curve.evaluate(t) for t in (-.5, 1.5)], expected):
                    self.assertAlmostEqual(actual, value)

    def test_infinity_fast_preflight_and_partial_flags(self):
        """両側を事前検証し、片側省略・不正値・ロック・接続を扱う。"""
        curve = self.create("animCurveUU")
        original = curve.getInfinity()
        cmds.setAttr(curve.fullName() + ".postInfinity", lock=True)
        with self.assertRaises(RuntimeError):
            curve.setInfinity(pre="cycle", post="linear", fast=True)
        self.assertEqual(curve.getInfinity(), original)
        curve.setInfinity(pre="oscillate", fast=True)
        self.assertEqual(curve.getInfinity(), dict(pre="oscillate", post="constant"))
        cmds.setAttr(curve.fullName() + ".postInfinity", lock=False)
        source = self.create("animCurveUU")
        cmds.connectAttr(source.fullName() + ".preInfinity", curve.fullName() + ".postInfinity")
        with self.assertRaises(RuntimeError):
            curve.setInfinity(pre="linear", post="linear", fast=True)
        self.assertEqual(curve.getInfinity()["pre"], "oscillate")
        with self.assertRaises(ValueError):
            curve.setInfinity(pre="linear", post="invalid", fast=True)
        with self.assertRaises(TypeError):
            curve.setInfinity(pre="linear", fast=1)
        self.assertEqual(curve.getInfinity()["pre"], "oscillate")
        self.assertIs(curve.setInfinity(fast=True), curve)

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
