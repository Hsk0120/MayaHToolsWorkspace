"""描画のオーバーライド色とアウトライナーの文字色のメソッドを確かめる。"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import DagNode, Nodes
from support.specCase import NamespaceCase


class DisplayColorTest(NamespaceCase):
    """ロケーターとグループで、単数・複数形の読み書きを確かめる。"""

    PREFIX = "mlibSpecDisplayColor_"
    ENABLE_UNDO = True

    def setUp(self):
        super().setUp()
        self.a = mlib.getNode(cmds.spaceLocator(name=self.name("a"))[0])
        self.b = mlib.getNode(cmds.createNode("transform", name=self.name("b")))

    def assertRgb(self, actual, expected):
        """RGB の 3 成分が近いことを確かめる。"""
        self.assertEqual(len(actual), 3)
        for value, wanted in zip(actual, expected):
            self.assertAlmostEqual(value, wanted, places=5)

    def test_old_names_are_gone(self):
        self.assertFalse(hasattr(DagNode, "getColor"))
        self.assertFalse(hasattr(DagNode, "setColor"))
        self.assertFalse(hasattr(Nodes, "setColor"))

    def test_outliner_rgb_stays_on_transform(self):
        """既定は None。RGB は Transform 自身に設定し、Shape には書かない。"""
        self.assertIsNone(self.a.getOutlinerColor())
        self.assertIs(self.a.setOutlinerColor((0.25, 0.5, 1.0)), self.a)
        name = self.a.getFullName()
        self.assertTrue(cmds.getAttr(name + ".useOutlinerColor"))
        self.assertRgb(cmds.getAttr(name + ".outlinerColor")[0], (0.25, 0.5, 1.0))
        self.assertRgb(self.a.getOutlinerColor(), (0.25, 0.5, 1.0))
        self.assertFalse(cmds.getAttr(self.a.getShape().getFullName() + ".useOutlinerColor"))

    def test_outliner_index_becomes_rgb(self):
        """番号は標準パレットの RGB へ変換する(mayapy は GUI なし)。"""
        self.a.setOutlinerColor(13)
        self.assertRgb(self.a.getOutlinerColor(), (1.0, 0.0, 0.0))
        self.a.setOutlinerColor(0)
        self.assertRgb(self.a.getOutlinerColor(), (0.47, 0.47, 0.47))

    def test_override_stays_on_node_itself(self):
        """Transform も Joint も自身へ設定し、Shape には書かない。"""
        self.a.setOverrideColor(13)
        self.assertEqual(cmds.getAttr(self.a.getFullName() + ".overrideColor"), 13)
        self.assertFalse(cmds.getAttr(self.a.getShape().getFullName() + ".overrideEnabled"))
        joint = mlib.getNode(cmds.createNode("joint", name=self.name("joint")))
        curve = cmds.circle(constructionHistory=False, name=self.name("curve"))[0]
        cmds.parent(cmds.listRelatives(curve, shapes=True, fullPath=True)[0], joint.getFullName(), shape=True, relative=True)
        cmds.delete(curve)
        joint.setOverrideColor(6)
        self.assertEqual(cmds.getAttr(joint.getFullName() + ".overrideColor"), 6)
        self.assertFalse(cmds.getAttr(joint.getShapes()[0].getFullName() + ".overrideEnabled"))

    def curve_joint(self):
        """カーブの Shape を 2 つ持つ Joint を返す。"""
        joint = mlib.getNode(cmds.createNode("joint", name=self.name("ctrl")))
        for label in ("c1", "c2"):
            curve = cmds.circle(constructionHistory=False, name=self.name(label))[0]
            cmds.parent(cmds.listRelatives(curve, shapes=True, fullPath=True)[0], joint.getFullName(), shape=True, relative=True)
            cmds.delete(curve)
        return joint

    def test_shape_flag_writes_every_shape_only(self):
        joint = self.curve_joint()
        shapes = [shape.getFullName() for shape in joint.getShapes()]
        self.assertEqual(len(shapes), 2)
        self.assertIs(joint.setOverrideColor(13, shape=True), joint)
        self.assertEqual([cmds.getAttr(name + ".overrideColor") for name in shapes], [13, 13])
        self.assertFalse(cmds.getAttr(joint.getFullName() + ".overrideEnabled"))
        self.assertEqual(joint.getOverrideColor(shape=True), 13)
        self.assertIsNone(joint.getOverrideColor())
        joint.setOutlinerColor((1, 0, 0), shape=True)
        self.assertTrue(all(cmds.getAttr(name + ".useOutlinerColor") for name in shapes))
        self.assertFalse(cmds.getAttr(joint.getFullName() + ".useOutlinerColor"))
        self.assertRgb(joint.getOutlinerColor(shape=True), (1, 0, 0))
        self.assertIsNone(joint.getOutlinerColor())
        joint.setOverrideColor(None, shape=True)
        self.assertIsNone(joint.getOverrideColor(shape=True))

    def test_shape_flag_without_shape_uses_node(self):
        self.b.setOverrideColor(6, shape=True)
        self.assertEqual(cmds.getAttr(self.b.getFullName() + ".overrideColor"), 6)
        self.assertEqual(self.b.getOverrideColor(shape=True), 6)
        shape = self.a.getShape()
        shape.setOverrideColor(4, shape=True)
        self.assertEqual(shape.getOverrideColor(shape=True), 4)

    def test_shape_flag_undo_and_fast(self):
        joint = self.curve_joint()
        cmds.flushUndo()
        joint.setOverrideColor(13, shape=True)
        cmds.undo()
        self.assertIsNone(joint.getOverrideColor(shape=True))
        cmds.flushUndo()
        joint.setOverrideColor((0, 1, 0), shape=True, fast=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertRgb(joint.getOverrideColor(shape=True), (0, 1, 0))

    def test_shape_flag_locked_shape_changes_nothing(self):
        joint = self.curve_joint()
        names = [shape.getFullName() for shape in joint.getShapes()]
        cmds.setAttr(names[1] + ".overrideColor", lock=True)
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaises(RuntimeError):
                    joint.setOverrideColor(9, shape=True, fast=fast)
                self.assertFalse(cmds.getAttr(names[0] + ".overrideEnabled"))

    def test_shape_flag_on_nodes(self):
        first, second = self.curve_joint(), self.a
        nodes = Nodes([first, second])
        nodes.setOverrideColor(17, shape=True)
        self.assertEqual(nodes.getOverrideColor(shape=True), [17, 17])
        self.assertEqual(nodes.getOverrideColor(), [None, None])
        nodes.setOutlinerColors([(1, 0, 0), None], shape=True)
        self.assertRgb(nodes.getOutlinerColor(shape=True)[0], (1, 0, 0))
        self.assertIsNone(nodes.getOutlinerColor(shape=True)[1])
        nodes.setOverrideColors([13, 14], shape=True, fast=True)
        self.assertEqual(nodes.getOverrideColor(shape=True), [13, 14])

    def test_shape_flag_must_be_bool(self):
        nodes = Nodes([self.a, self.b])
        for call in (lambda: self.a.setOverrideColor(1, shape="yes"), lambda: self.a.getOverrideColor(shape=1),
                     lambda: self.a.setOutlinerColor(1, shape=None), lambda: self.a.getOutlinerColor(shape="x"),
                     lambda: nodes.setOverrideColor(1, shape="yes"), lambda: nodes.setOutlinerColors([1, 2], shape=1)):
            with self.assertRaises(TypeError):
                call()
        self.assertEqual(nodes.getOverrideColor(), [None, None])

    def test_none_disables(self):
        self.a.setOutlinerColor((1, 0, 0))
        self.a.setOutlinerColor(None)
        self.assertIsNone(self.a.getOutlinerColor())
        self.a.setOverrideColor(13)
        self.a.setOverrideColor(None)
        self.assertIsNone(self.a.getOverrideColor())
        self.assertFalse(cmds.getAttr(self.a.getFullName() + ".overrideEnabled"))

    def test_fast_matches_normal_without_undo(self):
        cmds.flushUndo()
        self.a.setOutlinerColor((0.1, 0.2, 0.3), fast=True)
        self.b.setOverrideColor(None, fast=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertRgb(self.a.getOutlinerColor(), (0.1, 0.2, 0.3))

    def test_undo_in_one_step(self):
        cmds.flushUndo()
        self.a.setOutlinerColor((0.1, 0.2, 0.3))
        cmds.undo()
        self.assertIsNone(self.a.getOutlinerColor())
        cmds.redo()
        self.assertRgb(self.a.getOutlinerColor(), (0.1, 0.2, 0.3))

    def test_invalid_inputs_change_nothing(self):
        for error, value in ((TypeError, True), (TypeError, "red"), (TypeError, 1.5), (ValueError, -1),
                             (ValueError, 32), (ValueError, (1, 0)), (ValueError, (1, 0, 2))):
            with self.subTest(value=value):
                with self.assertRaises(error):
                    self.a.setOutlinerColor(value)
        with self.assertRaises(TypeError):
            self.a.setOutlinerColor((1, 0, 0), fast="yes")
        self.assertIsNone(self.a.getOutlinerColor())

    def test_locked_attribute_is_rejected(self):
        cmds.setAttr(self.a.getFullName() + ".outlinerColor", lock=True)
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaises(RuntimeError):
                    self.a.setOutlinerColor((1, 0, 0), fast=fast)
                self.assertFalse(cmds.getAttr(self.a.getFullName() + ".useOutlinerColor"))

    def test_nodes_same_color(self):
        nodes = Nodes([self.a, self.b])
        self.assertEqual(nodes.getOutlinerColor(), [None, None])
        self.assertIs(nodes.setOutlinerColor((0, 1, 0)), nodes)
        for color in nodes.getOutlinerColor():
            self.assertRgb(color, (0, 1, 0))
        self.assertIs(nodes.setOverrideColor(17), nodes)
        self.assertEqual(nodes.getOverrideColor(), [17, 17])

    def test_nodes_one_color_each(self):
        nodes = Nodes([self.a, self.b])
        self.assertIs(nodes.setOverrideColors([13, None]), nodes)
        self.assertEqual(nodes.getOverrideColor(), [13, None])
        cmds.flushUndo()
        nodes.setOutlinerColors([(1, 0, 0), (0, 0, 1)])
        self.assertRgb(self.a.getOutlinerColor(), (1, 0, 0))
        self.assertRgb(self.b.getOutlinerColor(), (0, 0, 1))
        cmds.undo()
        self.assertEqual(nodes.getOutlinerColor(), [None, None])

    def test_nodes_each_validates_before_writing(self):
        nodes = Nodes([self.a, self.b])
        with self.assertRaises(ValueError):
            nodes.setOutlinerColors([(1, 0, 0)])
        with self.assertRaises(ValueError):
            nodes.setOutlinerColors([(1, 0, 0), 99])
        with self.assertRaises(TypeError):
            nodes.setOverrideColors([13, "red"])
        self.assertEqual(nodes.getOutlinerColor(), [None, None])
        self.assertEqual(nodes.getOverrideColor(), [None, None])

    def test_nodes_reject_non_dag(self):
        other = mlib.getNode(cmds.createNode("multiplyDivide", name=self.name("md")))
        nodes = Nodes([self.a, other])
        with self.assertRaises(TypeError):
            nodes.getOutlinerColor()
        with self.assertRaises(TypeError):
            nodes.setOverrideColors([1, 2])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
