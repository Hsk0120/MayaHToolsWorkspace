"""責務委譲後の副作用・参照・通常/fastの境界を検証する。"""
import sys
import unittest
from unittest.mock import patch
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace
import mlib
mlib.reload()


class ResponsibilityTest(unittest.TestCase):
    """独立シーンで共有された操作の公開契約を検証する。"""

    def setUp(self):
        """ユーザー環境を使わずテスト用のシーンを初期化する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear='cm', angle='deg')

    def test_disconnect_input_preserves_outputs_and_undo(self):
        """入力だけ解除し、未接続・Undo/Redo・変換ノードを維持する。"""
        a, b, c = [mlib.createNode('transform') for _ in range(3)]
        a.getPlug('tx').connectTo(b.getPlug('rx'))
        b.getPlug('rx').connectTo(c.getPlug('rx'))
        source = b.getPlug('rx').getSource(skipConversionNodes=False)
        self.assertIs(b.getPlug('rx').disconnectInput().getNode(), b)
        self.assertIsNone(b.getPlug('rx').getSource(skipConversionNodes=False))
        self.assertTrue(b.getPlug('rx').isConnectedTo(c.getPlug('rx')))
        self.assertTrue(source.getNode().isValid())
        cmds.undo()
        self.assertEqual(b.getPlug('rx').getSource(skipConversionNodes=False), source)
        cmds.redo()
        before = cmds.undoInfo(query=True, undoName=True)
        b.getPlug('rx').disconnectInput()
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), before)

    def test_disconnect_compound_input_keeps_outputs(self):
        """親の複合接続は親で解除し、子の出力を保持する。"""
        a, b, c = [mlib.createNode('transform') for _ in range(3)]
        a.getPlug('translate').connectTo(b.getPlug('translate'))
        b.getPlug('tx').connectTo(c.getPlug('tx'))
        b.getPlug('translate').disconnectInput()
        self.assertIsNone(b.getPlug('translate').getSource(skipConversionNodes=False))
        self.assertTrue(b.getPlug('tx').isConnectedTo(c.getPlug('tx')))
        cmds.undo()
        self.assertEqual(b.getPlug('translate').getSource(skipConversionNodes=False), a.getPlug('translate'))

    def test_array_failed_edit_does_not_create_elements(self):
        """不正値・入力元・ロックの失敗前に配列の穴を実体化しない。"""
        matrix = mlib.createNode('multMatrix')
        inputs = matrix.getPlug('matrixIn')
        with self.assertRaises((TypeError, ValueError, RuntimeError)):
            inputs[7].set([1, 2])
        with self.assertRaises((AttributeError, RuntimeError, ValueError)):
            inputs[7].connect('missingNode.missingPlug')
        inputs.setFlags(locked=True)
        for fast in (False, True):
            with self.assertRaises(RuntimeError):
                inputs[7].set(mlib.maths.Matrix(), fast=fast)
        self.assertEqual(list(inputs.mplug().getExistingArrayAttributeIndices()), [])
        for index in (True, 1.5):
            with self.assertRaises(TypeError):
                inputs.getElement(index)
        for index in (-1, 2147483648):
            with self.assertRaises(IndexError):
                inputs.getElement(index)
        self.assertEqual(list(inputs.mplug().getExistingArrayAttributeIndices()), [])

    def test_numeric_compound_locked_child_preflight(self):
        """数値複合型の子ロックを変更前に検出し、RGBの型を維持する。"""
        node = mlib.createNode('blendColors')
        node.getPlug("color1").set((.2, .3, .4))
        before = node.getPlug("color1").get()
        cmds.setAttr(node.getFullName() + '.color1G', lock=True)
        for fast in (False, True):
            with self.assertRaises(RuntimeError):
                node.getPlug("color1").set((.8, .7, .6), fast=fast)
            self.assertEqual(node.getPlug("color1").get(), before)
        cmds.setAttr(node.getFullName() + '.color1G', lock=False)
        node.getPlug("color1").set((.8, .7, .6))
        cmds.undo()
        self.assertEqual(node.getPlug("color1").get(), before)
        self.assertEqual(cmds.getAttr(node.getFullName() + '.color1', type=True), 'float3')

    def test_multi_shape_generator_inputs(self):
        """複数Shapeで倍率・pivotのgeneratorを再消費しない。"""
        a, b = [cmds.polyCube(constructionHistory=False)[0] for _ in range(2)]
        cmds.parent(cmds.listRelatives(b, shapes=True)[0], a, shape=True, relative=True)
        node = mlib.getNode(a)
        originals = [shape.getVertices().getPosition() for shape in node.getShapes()]
        node.scaleGeometry((v for v in (2, 3, 4)), pivot=(v for v in (0, 0, 0)))
        for shape, points in zip(node.getShapes(), originals):
            for actual, old in zip(shape.getVertices().getPosition(), points):
                self.assertEqual(tuple(actual), tuple(old[i] * (2, 3, 4)[i] for i in range(3)))
        cmds.undo()
        self.assertEqual([shape.getVertices().getPosition() for shape in node.getShapes()], originals)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
