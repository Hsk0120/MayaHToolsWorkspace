"""責務委譲後の副作用・参照・通常/fastの境界を検証する。"""
import sys
import unittest
from unittest.mock import patch
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace
import hlib
hlib.reload()


class ResponsibilityTest(unittest.TestCase):
    """独立シーンで共有された操作の公開契約を検証する。"""

    def setUp(self):
        """ユーザー環境を使わずテスト用のシーンを初期化する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear='cm', angle='deg')

    def test_disconnect_input_preserves_outputs_and_undo(self):
        """入力だけ解除し、未接続・Undo/Redo・変換ノードを維持する。"""
        a, b, c = [hlib.createNode('transform') for _ in range(3)]
        a.getPlug('tx').connectTo(b.getPlug('rx'))
        b.getPlug('rx').connectTo(c.getPlug('rx'))
        source = b.getPlug('rx').getSourceWithConversion()
        self.assertIs(b.getPlug('rx').disconnectInput().getNode(), b)
        self.assertIsNone(b.getPlug('rx').getSourceWithConversion())
        self.assertTrue(b.getPlug('rx').isConnectedTo(c.getPlug('rx')))
        self.assertTrue(source.getNode().isValid())
        cmds.undo()
        self.assertEqual(b.getPlug('rx').getSourceWithConversion(), source)
        cmds.redo()
        before = cmds.undoInfo(query=True, undoName=True)
        b.getPlug('rx').disconnectInput()
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), before)

    def test_disconnect_compound_input_keeps_outputs(self):
        """親の複合接続は親で解除し、子の出力を保持する。"""
        a, b, c = [hlib.createNode('transform') for _ in range(3)]
        a.getPlug('translate').connectTo(b.getPlug('translate'))
        b.getPlug('tx').connectTo(c.getPlug('tx'))
        b.getPlug('translate').disconnectInput()
        self.assertIsNone(b.getPlug('translate').getSourceWithConversion())
        self.assertTrue(b.getPlug('tx').isConnectedTo(c.getPlug('tx')))
        cmds.undo()
        self.assertEqual(b.getPlug('translate').getSourceWithConversion(), a.getPlug('translate'))

    def test_array_failed_edit_does_not_create_elements(self):
        """不正値・入力元・ロックの失敗前に配列の穴を実体化しない。"""
        matrix = hlib.createNode('multMatrix')
        inputs = matrix.getPlug('matrixIn')
        with self.assertRaises((TypeError, ValueError)):
            matrix.setInput(7, [1, 2])
        with self.assertRaises((AttributeError, RuntimeError)):
            matrix.connectInput(7, 'missingNode.missingPlug')
        inputs.setFlags(locked=True)
        for fast in (False, True):
            with self.assertRaises(RuntimeError):
                matrix.setInput(7, hlib.maths.Matrix(), fast=fast)
        self.assertEqual(list(inputs.mplug().getExistingArrayAttributeIndices()), [])
        for index in (True, 1.5):
            with self.assertRaises(TypeError):
                inputs.getElement(index, create=True)
        for index in (-1, 2147483648):
            with self.assertRaises(IndexError):
                inputs.getElement(index, create=True)
        self.assertEqual(list(inputs.mplug().getExistingArrayAttributeIndices()), [])

    def test_numeric_compound_locked_child_preflight(self):
        """数値複合型の子ロックを変更前に検出し、RGBの型を維持する。"""
        node = hlib.createNode('blendColors')
        node.setColor(1, (.2, .3, .4))
        before = node.getColor(1)
        cmds.setAttr(node.getFullName() + '.color1G', lock=True)
        for fast in (False, True):
            with self.assertRaises(RuntimeError):
                node.setColor(1, (.8, .7, .6), fast=fast)
            self.assertEqual(node.getColor(1), before)
        cmds.setAttr(node.getFullName() + '.color1G', lock=False)
        node.setColor(1, (.8, .7, .6))
        cmds.undo()
        self.assertEqual(node.getColor(1), before)
        self.assertEqual(cmds.getAttr(node.getFullName() + '.color1', type=True), 'float3')

    def test_multi_shape_generator_inputs(self):
        """複数Shapeで倍率・pivotのgeneratorを再消費しない。"""
        a, b = [cmds.polyCube(constructionHistory=False)[0] for _ in range(2)]
        cmds.parent(cmds.listRelatives(b, shapes=True)[0], a, shape=True, relative=True)
        node = hlib.getNode(a)
        originals = [shape.getVertices().getPosition() for shape in node.getShapes()]
        node.scaleGeometry((v for v in (2, 3, 4)), pivot=(v for v in (0, 0, 0)))
        for shape, points in zip(node.getShapes(), originals):
            for actual, old in zip(shape.getVertices().getPosition(), points):
                self.assertEqual(tuple(actual), tuple(old[i] * (2, 3, 4)[i] for i in range(3)))
        cmds.undo()
        self.assertEqual([shape.getVertices().getPosition() for shape in node.getShapes()], originals)

    def test_geometry_batch_preserves_order_and_single_undo(self):
        """配列書込みは単数編集を反復せず保持順とcm契約を維持する。"""
        from hlib.components.pointComponent import PointComponent
        shape = hlib.getNode(cmds.polyCube(constructionHistory=False)[0]).getShapes()[0]
        points = shape.getVertices([5, 1, 3])
        original = points.getPosition()
        cmds.currentUnit(linear='m')
        rows = [(1, 2, 3), (4, 5, 6), (7, 8, 9)]
        try:
            with patch.object(PointComponent, 'setPosition', side_effect=AssertionError('single edit')):
                points.setPositions(iter(rows), ws=False)
            self.assertEqual(points.getPosition(), rows)
            cmds.undo()
            self.assertEqual(points.getPosition(), original)
        finally:
            cmds.currentUnit(linear='cm')

    def test_snapshot_signature_does_not_change_node_path(self):
        """保存用トポロジー照会が保持DAGパスをシェイプへ書き換えない。"""
        from hlib.json.snapshots import _signature
        node = hlib.getNode(cmds.polyCube()[0])
        before = node.getFullName()
        self.assertEqual(_signature(node)['vertices'], 8)
        self.assertEqual(node.getFullName(), before)
        self.assertEqual(node.mpath().node(), node.mnode())


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
