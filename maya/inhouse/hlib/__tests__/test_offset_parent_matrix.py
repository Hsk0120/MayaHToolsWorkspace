"""別TransformのMatrixをoffsetParentMatrixへ設定する経路を検証する。"""
from maya.api.OpenMaya import MSpace
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
        cmds.delete(self.root.fullName())

    def test_matrix_type_copy_undo_and_fast(self):
        self.source.setTranslation((2, 3, 4))
        self.source.setRotation((.2, .3, .4))
        self.source.setScale((2, 3, 4))
        value = self.source.getMatrix()
        plug = self.target.plug("offsetParentMatrix")
        self.assertIsInstance(value, Matrix)
        self.assertIsInstance(plug, MatrixPlug)
        self.assertIs(plug.set(value), plug)
        self.assertIsInstance(plug.get(), Matrix)
        self.assertTrue(plug.get().isEquivalent(value, 1e-9))
        self.assertTrue(self.target.getMatrix().isEquivalent(Matrix(), 1e-9))
        self.assertTrue(self.target.getMatrix(space=MSpace.kWorld).isEquivalent(value, 1e-9))
        cmds.undo()
        self.assertTrue(plug.get().isEquivalent(Matrix(), 1e-9))
        cmds.redo()
        self.assertTrue(plug.get().isEquivalent(value, 1e-9))
        plug.set(Matrix(), fast=True)
        self.assertTrue(plug.get().isEquivalent(Matrix(), 1e-9))
        plug.set(value, fast=True)
        self.assertTrue(plug.get().isEquivalent(value, 1e-9))

    def test_world_alignment_preserves_channels(self):
        self.root.setTranslation((10, 20, 30))
        self.root.setRotation((.1, .2, .3))
        self.root.setScale((2, 3, 4))
        self.source.setTranslation((4, 5, 6))
        self.target.setTranslation((1, 2, 3))
        self.target.setRotation((.4, .5, .6))
        local = self.target.getMatrix()
        world = self.source.getMatrix(space=MSpace.kWorld)
        offset = local.inverse() * world * self.root.getMatrix(space=MSpace.kWorld).inverse()
        self.target.plug("offsetParentMatrix").set(offset)
        self.assertTrue(self.target.getMatrix().isEquivalent(local, 1e-9))
        self.assertTrue(self.target.getMatrix(space=MSpace.kWorld).isEquivalent(world, 1e-8))

    def test_transform_methods_and_collection(self):
        from hlib.nodes import Transforms
        nodes = Transforms([self.source, self.target])
        value = Matrix(translate=(4, 5, 6))
        self.assertIs(self.target.setOffsetParentMatrix(value), self.target)
        self.assertTrue(self.target.getOffsetParentMatrix().isEquivalent(value))
        cmds.undo()
        self.assertTrue(self.target.getOffsetParentMatrix().isEquivalent(Matrix()))
        nodes.setOffsetParentMatrix(value)
        self.assertTrue(all(matrix.isEquivalent(value) for matrix in nodes.getOffsetParentMatrix()))
        cmds.undo()
        self.assertTrue(all(matrix.isEquivalent(Matrix()) for matrix in nodes.getOffsetParentMatrix()))
        self.target.setOffsetParentMatrix(value, fast=True)
        self.assertTrue(self.target.getOffsetParentMatrix().isEquivalent(value))
        cmds.setAttr(self.target.fullName() + ".offsetParentMatrix", lock=True)
        with self.assertRaises(RuntimeError):
            self.target.setOffsetParentMatrix(Matrix())

    def test_transform_methods_and_collection(self):
        from hlib.nodes import Transforms
        nodes = Transforms([self.source, self.target])
        value = Matrix(translate=(4, 5, 6))
        self.assertIs(self.target.setOffsetParentMatrix(value), self.target)
        self.assertTrue(self.target.getOffsetParentMatrix().isEquivalent(value))
        cmds.undo()
        self.assertTrue(self.target.getOffsetParentMatrix().isEquivalent(Matrix()))
        nodes.setOffsetParentMatrix(value)
        self.assertTrue(all(matrix.isEquivalent(value) for matrix in nodes.getOffsetParentMatrix()))
        cmds.undo()
        self.assertTrue(all(matrix.isEquivalent(Matrix()) for matrix in nodes.getOffsetParentMatrix()))
        self.target.setOffsetParentMatrix(value, fast=True)
        self.assertTrue(self.target.getOffsetParentMatrix().isEquivalent(value))
        cmds.setAttr(self.target.fullName() + ".offsetParentMatrix", lock=True)
        with self.assertRaises(RuntimeError):
            self.target.setOffsetParentMatrix(Matrix())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
