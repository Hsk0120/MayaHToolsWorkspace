"""10.2.0 で足した DAG・Transform・アニメーションカーブ・DG の照会と編集の契約を固定する。

- mlib.cmds.bakeResults.bakeResults: 焼き込んだカーブを返す・時刻を戻す・Undo 1 回・不正入力。
- AnimCurve.eulerFilter / Transform.eulerFilter: cmds.filterCurve と同じ結果・Undo 1 回・型の拒否。
- DagNode.deleteHistory: デフォーマーを残す/残さない・Undo 1 回。
- DagNode.setDisplayType / getDisplayType、setShadingOverride / isShadingOverridden: 通常・fast・不正入力。
- Node.findCycles: cycleCheck の循環を Plug の並びに分ける。
- Transform.getOffsetParentMatrix / setOffsetParentMatrix / freezeToOffsetParent: ワールドを保つ・Joint の扱い。
"""

import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.cmds.bakeResults import bakeResults
from mlib.maths import Matrix
from mlib.nodes import AnimCurve
from support.specCase import NamespaceCase


def _world(name):
    """cmds で読むワールドマトリクス。"""
    return cmds.xform(name, query=True, worldSpace=True, matrix=True)


class BakeResultsTest(NamespaceCase):

    def setUp(self):
        super().setUp()
        self.range = cmds.playbackOptions(query=True, minTime=True), cmds.playbackOptions(query=True, maxTime=True)
        self.time = cmds.currentTime(query=True)
        cmds.playbackOptions(minTime=1, maxTime=5)
        self.driver = self.make(text="driver")
        self.target = self.make(text="target")
        cmds.setKeyframe(self.driver, attribute="translateX", time=1, value=0)
        cmds.setKeyframe(self.driver, attribute="translateX", time=10, value=10)
        cmds.parentConstraint(self.driver, self.target, name=self.name("pc"))

    def tearDown(self):
        cmds.playbackOptions(minTime=self.range[0], maxTime=self.range[1])
        cmds.currentTime(self.time)
        super().tearDown()

    def test_bake_returns_curves_and_restores_time(self):
        """既定は再生範囲、焼き込んだカーブを AnimCurve で返し、現在時刻を戻す。"""
        cmds.currentTime(3)
        self.flushUndo()
        curves = bakeResults(self.target, simulation=True)
        self.assertTrue(curves)
        self.assertTrue(all(isinstance(curve, AnimCurve) for curve in curves))
        self.assertEqual(cmds.currentTime(query=True), 3)
        tx = cmds.listConnections(self.target + ".translateX", source=True, destination=False, type="animCurve")
        self.assertIn(mlib.getNode(tx[0]), curves)
        self.assertEqual(cmds.keyframe(self.target + ".translateX", query=True, timeChange=True),
                         [1.0, 2.0, 3.0, 4.0, 5.0])
        cmds.undo()
        self.assertFalse(cmds.listConnections(self.target + ".translateX", source=True, destination=False,
                                              type="animCurve"))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_attributes_time_and_sample(self):
        """attributes・time・sampleBy を cmds.bakeResults へ渡し、指定したアトリビュートのカーブだけを返す。"""
        curves = bakeResults([self.target], attributes=["tx", "rotate"], time=(2, 6), sampleBy=2,
                             simulation=True)
        driven = {plug.getLongName() for curve in curves for plug in curve.getDrivenPlugs()}
        self.assertEqual(driven, {"translateX", "rotateX", "rotateY", "rotateZ"})
        self.assertEqual(cmds.keyframe(self.target + ".translateX", query=True, timeChange=True), [2.0, 4.0, 6.0])
        self.assertFalse(cmds.listConnections(self.target + ".translateY", source=True, destination=False,
                                              type="animCurve"))

    def test_errors(self):
        """引数で受けるフラグ・query・不正な time/sampleBy/attributes/nodes は例外。"""
        for kwargs, error in (({"time": (1, 2), "t": (1, 2)}, TypeError), ({"attributes": "tx", "at": "tx"}, TypeError),
                              ({"attribute": "tx"}, TypeError), ({"query": True}, TypeError),
                              ({"time": (5, 1)}, ValueError), ({"time": (1,)}, ValueError),
                              ({"time": "1:5"}, TypeError), ({"sampleBy": 0}, ValueError),
                              ({"sampleBy": "1"}, TypeError), ({"attributes": 1}, TypeError),
                              ({"attributes": []}, ValueError)):
            with self.subTest(kwargs=kwargs):
                self.assertRaises(error, bakeResults, self.target, **kwargs)
        self.assertRaises(ValueError, bakeResults, [])
        self.assertRaises(RuntimeError, bakeResults, self.name("missing"))


class EulerFilterTest(NamespaceCase):

    def keyed(self):
        node = self.make(text="rot")
        for frame, values in ((1, (0, 0, 0)), (2, (350, 10, -340)), (3, (20, 380, 0))):
            for axis, value in zip("XYZ", values):
                cmds.setKeyframe(node, attribute="rotate" + axis, time=frame, value=value)
        return node

    def values(self, node):
        return [cmds.keyframe(node + ".rotate" + axis, query=True, valueChange=True) for axis in "XYZ"]

    def test_transform_matches_filter_curve(self):
        """Transform.eulerFilter は3本を filterCurve に渡したのと同じ結果で、Undo 1回で戻る。"""
        node, reference = self.keyed(), self.keyed()
        before = self.values(node)
        cmds.filterCurve([cmds.listConnections(reference + ".rotate" + axis)[0] for axis in "XYZ"], filter="euler")
        self.flushUndo()
        transform = mlib.getNode(node)
        self.assertIs(transform.eulerFilter(), transform)
        self.assertNotEqual(self.values(node), before)
        for actual, expected in zip(self.values(node), self.values(reference)):
            self.assertSequenceAlmostEqual(actual, expected)
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.values(node), before), lambda: None)

    def test_transform_without_keys(self):
        """キーが無ければ何もしないで自身を返す。"""
        transform = mlib.getNode(self.make())
        self.flushUndo()
        self.assertIs(transform.eulerFilter(), transform)
        self.assertUndoEmpty()

    def test_anim_curve(self):
        """AnimCurve.eulerFilter は animCurveTA だけを受け、Undo 1回で戻る。"""
        node = self.keyed()
        curve = mlib.getNode(cmds.listConnections(node + ".rotateX")[0])
        before = self.values(node)[0]
        self.flushUndo()
        self.assertIs(curve.eulerFilter(), curve)
        self.assertNotEqual(self.values(node)[0], before)
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.values(node)[0], before), lambda: None)
        cmds.setKeyframe(node, attribute="translateX", time=1, value=1)
        linear = mlib.getNode(cmds.listConnections(node + ".translateX")[0])
        self.assertRaises(TypeError, linear.eulerFilter)


class DeleteHistoryTest(NamespaceCase):

    def cube(self):
        cube = cmds.polyCube(name=self.name("cube"))[0]
        cmds.polySmooth(cube)
        cmds.cluster(cube, name=self.name("cl"))
        return cube

    def history_types(self, cube):
        return {cmds.nodeType(node) for node in cmds.listHistory(cube) or []}

    def test_keep_deformers(self):
        """True はデフォーマーを残してほかの履歴を消し、Undo 1回で戻る。"""
        cube = self.cube()
        self.flushUndo()
        node = mlib.getNode(cube)
        self.assertIs(node.deleteHistory(), node)
        self.assertIn("cluster", self.history_types(cube))
        self.assertNotIn("polySmoothFace", self.history_types(cube))
        self.assertUndoesInOneStep(lambda: self.assertIn("polySmoothFace", self.history_types(cube)), lambda: None)

    def test_delete_all(self):
        """False は Shape に呼んでもデフォーマーを含めて消す。"""
        cube = self.cube()
        shape = mlib.getNode(cmds.listRelatives(cube, shapes=True, noIntermediate=True)[0])
        self.flushUndo()
        self.assertIs(shape.deleteHistory(keepDeformers=False), shape)
        self.assertFalse({"cluster", "polySmoothFace"} & self.history_types(cube))
        self.assertUndoesInOneStep(lambda: self.assertIn("cluster", self.history_types(cube)), lambda: None)

    def test_group_and_errors(self):
        """Shape の無い Transform は何もしない。keepDeformers が bool 以外は TypeError。"""
        group = mlib.getNode(self.make())
        self.assertIs(group.deleteHistory(), group)
        self.assertIs(group.deleteHistory(keepDeformers=False), group)
        self.assertRaises(TypeError, group.deleteHistory, 1)


class DrawingOverrideTest(NamespaceCase):

    def test_display_type(self):
        """setDisplayType は自身の overrideEnabled・overrideDisplayType を設定し、Undo 1回で戻る。"""
        name = self.make()
        node = mlib.getNode(name)
        self.assertEqual(node.getDisplayType(), "normal")
        for kind, index in (("template", 1), ("reference", 2)):
            with self.subTest(kind=kind):
                cmds.setAttr(name + ".overrideEnabled", False)
                cmds.setAttr(name + ".overrideDisplayType", 0)
                self.flushUndo()
                self.assertIs(node.setDisplayType(kind), node)
                self.assertEqual(node.getDisplayType(), kind)
                self.assertEqual((cmds.getAttr(name + ".overrideEnabled"),
                                  cmds.getAttr(name + ".overrideDisplayType")), (True, index))
                self.assertUndoesInOneStep(lambda: self.assertEqual(node.getDisplayType(), "normal"), lambda: None)
        node.setDisplayType("template")
        node.setDisplayType("normal")
        self.assertEqual(node.getDisplayType(), "normal")
        self.assertTrue(cmds.getAttr(name + ".overrideEnabled"))

    def test_display_type_fast_and_errors(self):
        """fast は Undo に積まない。不正な kind・fast は例外、ロックは RuntimeError。"""
        name = self.make()
        node = mlib.getNode(name)
        self.flushUndo()
        node.setDisplayType("reference", fast=True)
        self.assertEqual(node.getDisplayType(), "reference")
        self.assertUndoEmpty()
        self.assertRaises(TypeError, node.setDisplayType, 1)
        self.assertRaises(ValueError, node.setDisplayType, "wire")
        self.assertRaises(TypeError, node.setDisplayType, "normal", fast=1)
        cmds.setAttr(name + ".overrideDisplayType", lock=True)
        for fast in (False, True):
            with self.subTest(fast=fast):
                self.assertRaises(RuntimeError, node.setDisplayType, "template", fast=fast)
                self.assertEqual(node.getDisplayType(), "reference")

    def test_shading_override(self):
        """True は overrideShading=False(ワイヤー表示)、False は戻す。通常は Undo 1回、fast は Undo なし。"""
        name = self.make()
        node = mlib.getNode(name)
        self.assertFalse(node.isShadingOverridden())
        self.flushUndo()
        self.assertIs(node.setShadingOverride(True), node)
        self.assertTrue(node.isShadingOverridden())
        self.assertEqual((cmds.getAttr(name + ".overrideEnabled"), cmds.getAttr(name + ".overrideShading")),
                         (True, False))
        self.assertUndoesInOneStep(lambda: self.assertFalse(node.isShadingOverridden()), lambda: None)
        node.setShadingOverride(True, fast=True)
        self.assertUndoEmpty()
        node.setShadingOverride(False)
        self.assertFalse(node.isShadingOverridden())
        self.assertTrue(cmds.getAttr(name + ".overrideShading"))
        self.assertRaises(TypeError, node.setShadingOverride, 1)


class FindCyclesTest(NamespaceCase):

    def test_two_cycles(self):
        """同じノードを通る2つの循環を分け、各循環を自身の入力から流れの順で返す。"""
        a = self.make("plusMinusAverage", "a")
        b = self.make("plusMinusAverage", "b")
        c = self.make("plusMinusAverage", "c")
        cmds.connectAttr(a + ".output1D", b + ".input1D[0]")
        cmds.connectAttr(b + ".output1D", a + ".input1D[0]")
        cmds.connectAttr(a + ".output1D", c + ".input1D[0]")
        cmds.connectAttr(c + ".output1D", a + ".input1D[1]")
        cycles = mlib.getNode(a).findCycles()
        names = sorted([str(plug).rsplit(":", 1)[-1] for plug in cycle] for cycle in cycles)
        self.assertEqual(names, [["a.input1D[0]", "a.output1D", "b.input1D[0]", "b.output1D"],
                                 ["a.input1D[1]", "a.output1D", "c.input1D[0]", "c.output1D"]])
        listed = {str(plug) for cycle in cycles for plug in cycle}
        expected = {cmds.ls(name)[0] for name in cmds.cycleCheck(a, list=True)}
        self.assertEqual(listed, expected)
        self.assertEqual(mlib.getNode(c).findCycles()[0][0].getLongName(), "input1D")
        self.assertEqual(len(mlib.getNode(c).findCycles()), 1)

    def test_no_cycle(self):
        """循環が無ければ空リスト。"""
        self.assertEqual(mlib.getNode(self.make()).findCycles(), [])


class OffsetParentMatrixTest(NamespaceCase):

    def test_get_set(self):
        """get は offsetParentMatrix を返し、set は通常 Undo 1回、fast は Undo なし。"""
        name = self.make()
        node = mlib.getNode(name)
        self.assertEqual(node.getOffsetParentMatrix(), Matrix())
        value = Matrix(translate=(1, 2, 3))
        self.flushUndo()
        self.assertIs(node.setOffsetParentMatrix(value), node)
        self.assertSequenceAlmostEqual(cmds.getAttr(name + ".offsetParentMatrix"), list(value))
        self.assertIsInstance(node.getOffsetParentMatrix(), Matrix)
        self.assertUndoesInOneStep(lambda: self.assertEqual(node.getOffsetParentMatrix(), Matrix()), lambda: None)
        node.setOffsetParentMatrix(list(value), fast=True)
        self.assertUndoEmpty()
        self.assertEqual(node.getOffsetParentMatrix(), value)
        self.assertRaises(ValueError, node.setOffsetParentMatrix, [1, 2])
        self.assertRaises(TypeError, node.setOffsetParentMatrix, value, fast=1)

    def assertFrozen(self, name, attributes):
        for attribute, expected in attributes:
            self.assertSequenceAlmostEqual(cmds.getAttr(name + "." + attribute)[0], expected)

    def test_freeze_transform(self):
        """ピボット・rotateAxis・既存の offsetParentMatrix・親があってもワールドを保ち、Undo 1回で戻る。"""
        parent = self.make(text="parent")
        cmds.xform(parent, translation=(1, 2, 3), rotation=(10, 20, 30), scale=(2, 2, 2))
        name = self.make(text="child", parent=parent)
        cmds.xform(name, translation=(4, -1, 2), rotation=(30, 45, 60), scale=(1, 2, 3), shear=(0.1, 0, 0.2))
        cmds.setAttr(name + ".rotateAxis", 5, 10, 15)
        cmds.setAttr(name + ".rotateOrder", 3)
        cmds.setAttr(name + ".rotatePivot", 0.5, 0.2, 0.1)
        cmds.setAttr(name + ".scalePivot", -0.3, 0.4, 0.0)
        offset = om2.MTransformationMatrix()
        offset.setRotation(om2.MEulerRotation(0.1, 0, 0))
        offset.setTranslation(om2.MVector(0, 1, 0), om2.MSpace.kTransform)
        cmds.setAttr(name + ".offsetParentMatrix", *offset.asMatrix(), type="matrix")
        world = _world(name)
        self.flushUndo()
        node = mlib.getNode(name)
        self.assertIs(node.freezeToOffsetParent(), node)
        self.assertSequenceAlmostEqual(_world(name), world)
        self.assertFrozen(name, (("translate", (0, 0, 0)), ("rotate", (0, 0, 0)), ("scale", (1, 1, 1)),
                                 ("shear", (0, 0, 0)), ("rotateAxis", (5, 10, 15))))
        self.assertUndoesInOneStep(lambda: self.assertSequenceAlmostEqual(
            cmds.getAttr(name + ".translate")[0], (4, -1, 2)), lambda: None)
        self.assertSequenceAlmostEqual(_world(name), world)

    def test_freeze_joint(self):
        """Joint は jointOrient も0にし、segmentScaleCompensate の親スケールがあってもワールドを保つ。"""
        parent = self.make("joint", "parentJnt")
        cmds.setAttr(parent + ".scale", 2, 1, 1)
        name = self.make("joint", "childJnt", parent=parent)
        cmds.setAttr(name + ".translate", 3, 1, 0)
        cmds.setAttr(name + ".rotate", 10, 20, 30)
        cmds.setAttr(name + ".jointOrient", 0, 0, 45)
        world = _world(name)
        mlib.getNode(name).freezeToOffsetParent()
        self.assertSequenceAlmostEqual(_world(name), world)
        self.assertFrozen(name, (("translate", (0, 0, 0)), ("rotate", (0, 0, 0)), ("jointOrient", (0, 0, 0))))

    def test_freeze_rejects_locked_or_keyed(self):
        """ロック・キーのあるチャンネルは何も変えずに RuntimeError。"""
        name = self.make()
        cmds.setAttr(name + ".translateX", 2)
        node = mlib.getNode(name)
        cmds.setAttr(name + ".rotateY", lock=True)
        self.assertRaises(RuntimeError, node.freezeToOffsetParent)
        cmds.setAttr(name + ".rotateY", lock=False)
        cmds.setKeyframe(name, attribute="scaleZ", time=1, value=1)
        self.assertRaises(RuntimeError, node.freezeToOffsetParent)
        self.assertEqual(cmds.getAttr(name + ".translateX"), 2)
        self.assertEqual(node.getOffsetParentMatrix(), Matrix())


if __name__ == "__main__":
    unittest.main()
