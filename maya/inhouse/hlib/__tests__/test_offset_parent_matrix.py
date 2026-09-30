"""別TransformのMatrixをoffsetParentMatrixへ設定する経路を検証する。"""
import sys
import unittest
import maya.cmds as cmds
import hlib
hlib.reload()
from hlib.maths import Matrix
from hlib.plugs.matrixPlug import MatrixPlug


class OffsetParentMatrixTest(unittest.TestCase):
    """テスト用階層だけを作成・破棄する。"""

    def setUp(self):
        self.root = hlib.createNode("transform")
        self.source = hlib.createNode("transform", parent=self.root)
        self.target = hlib.createNode("transform", parent=self.root)

    def tearDown(self):
        cmds.delete(self.root.full_name())

    def test_matrix_type_copy_undo_and_fast(self):
        self.source.set_translate((2, 3, 4))
        self.source.set_rotate((.2, .3, .4))
        self.source.set_scale((2, 3, 4))
        value = self.source.get_matrix()
        plug = self.target.plug("offsetParentMatrix")
        self.assertIsInstance(value, Matrix)
        self.assertIsInstance(plug, MatrixPlug)
        self.assertIs(plug.set(value), plug)
        self.assertIsInstance(plug.get(), Matrix)
        self.assertTrue(plug.get().isEquivalent(value, 1e-9))
        self.assertTrue(self.target.get_matrix().isEquivalent(Matrix(), 1e-9))
        self.assertTrue(self.target.get_matrix(ws=True).isEquivalent(value, 1e-9))
        cmds.undo()
        self.assertTrue(plug.get().isEquivalent(Matrix(), 1e-9))
        cmds.redo()
        self.assertTrue(plug.get().isEquivalent(value, 1e-9))
        plug.set(Matrix(), fast=True)
        self.assertTrue(plug.get().isEquivalent(Matrix(), 1e-9))
        plug.set(value, fast=True)
        self.assertTrue(plug.get().isEquivalent(value, 1e-9))

    def test_world_alignment_preserves_channels(self):
        self.root.set_translate((10, 20, 30))
        self.root.set_rotate((.1, .2, .3))
        self.root.set_scale((2, 3, 4))
        self.source.set_translate((4, 5, 6))
        self.target.set_translate((1, 2, 3))
        self.target.set_rotate((.4, .5, .6))
        local = self.target.get_matrix()
        world = self.source.get_matrix(ws=True)
        offset = local.inverse() * world * self.root.get_matrix(ws=True).inverse()
        self.target.plug("offsetParentMatrix").set(offset)
        self.assertTrue(self.target.get_matrix().isEquivalent(local, 1e-9))
        self.assertTrue(self.target.get_matrix(ws=True).isEquivalent(world, 1e-8))

    def test_transform_methods_and_collection(self):
        from hlib.nodes import Transforms
        nodes = Transforms([self.source, self.target])
        value = Matrix(translate=(4, 5, 6))
        self.assertIs(self.target.set_offset_parent_matrix(value), self.target)
        self.assertTrue(self.target.get_offset_parent_matrix().isEquivalent(value))
        cmds.undo()
        self.assertTrue(self.target.get_offset_parent_matrix().isEquivalent(Matrix()))
        nodes.set_offset_parent_matrix(value)
        self.assertTrue(all(matrix.isEquivalent(value) for matrix in nodes.get_offset_parent_matrix()))
        cmds.undo()
        self.assertTrue(all(matrix.isEquivalent(Matrix()) for matrix in nodes.get_offset_parent_matrix()))
        self.target.set_offset_parent_matrix(value, fast=True)
        self.assertTrue(self.target.get_offset_parent_matrix().isEquivalent(value))
        cmds.setAttr(self.target.full_name() + ".offsetParentMatrix", lock=True)
        with self.assertRaises(RuntimeError):
            self.target.set_offset_parent_matrix(Matrix())

    def test_transform_methods_and_collection(self):
        from hlib.nodes import Transforms
        nodes = Transforms([self.source, self.target])
        value = Matrix(translate=(4, 5, 6))
        self.assertIs(self.target.set_offset_parent_matrix(value), self.target)
        self.assertTrue(self.target.get_offset_parent_matrix().isEquivalent(value))
        cmds.undo()
        self.assertTrue(self.target.get_offset_parent_matrix().isEquivalent(Matrix()))
        nodes.set_offset_parent_matrix(value)
        self.assertTrue(all(matrix.isEquivalent(value) for matrix in nodes.get_offset_parent_matrix()))
        cmds.undo()
        self.assertTrue(all(matrix.isEquivalent(Matrix()) for matrix in nodes.get_offset_parent_matrix()))
        self.target.set_offset_parent_matrix(value, fast=True)
        self.assertTrue(self.target.get_offset_parent_matrix().isEquivalent(value))
        cmds.setAttr(self.target.full_name() + ".offsetParentMatrix", lock=True)
        with self.assertRaises(RuntimeError):
            self.target.set_offset_parent_matrix(Matrix())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
