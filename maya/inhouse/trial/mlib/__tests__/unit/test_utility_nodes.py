"""行列・距離ノードの自動登録、評価、接続、Undo/Redoを検証する。"""

import sys
import unittest
import uuid
import maya.cmds as cmds
import mlib

mlib.reload()


class UtilityNodesTest(unittest.TestCase):
    def setUp(self):
        self.namespace = "mlibUtility_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)

    def tearDown(self):
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def create(self, kind, name):
        return mlib.createNode(kind, name=self.namespace + ":" + name)

    def test_registration_and_matrix_product(self):
        a, b = self.create("transform", "a"), self.create("transform", "b")
        cmds.setAttr(a.getFullName() + ".translate", 2, 3, 4)
        cmds.setAttr(b.getFullName() + ".rotateY", 40)
        mult = self.create("multMatrix", "mult")
        self.assertIsInstance(mult, mlib.nodes.MultMatrix)
        mult.setInput(0, a.getMatrix()).setInput(3, b.getMatrix())
        expected = a.getMatrix() * b.getMatrix()
        for x, y in zip(mult.getResult(), expected):
            self.assertAlmostEqual(x, y)
        cmds.undo()
        for x, y in zip(mult.getResult(), a.getMatrix()):
            self.assertAlmostEqual(x, y)
        cmds.redo()
        for x, y in zip(mult.getResult(), expected):
            self.assertAlmostEqual(x, y)
        with self.assertRaises(ValueError):
            mult.setInput(-1, expected)

    def test_live_matrix_connections_and_decomposition(self):
        source = self.create("transform", "source")
        mult = self.create("multMatrix", "mult")
        decompose = self.create("decomposeMatrix", "decompose")
        self.assertIsInstance(decompose, mlib.nodes.DecomposeMatrix)
        self.assertFalse(hasattr(type(decompose), "getOutputPlugs"))
        mult.connectInput(0, source.getPlug("matrix"))
        decompose.connectInput(mult.getOutputPlug())
        cmds.setAttr(source.getFullName() + ".translate", 5, 6, 7)
        self.assertEqual(tuple(decompose.getPlug("outputTranslate").get()), (5, 6, 7))
        decompose.setRotateOrder("zyx")
        self.assertEqual(decompose.getPlug("inputRotateOrder").get(), 5)
        cmds.undo()
        self.assertEqual(decompose.getPlug("inputRotateOrder").get(), 0)
        cmds.redo()
        self.assertEqual(decompose.getPlug("inputRotateOrder").get(), 5)
        with self.assertRaises(ValueError):
            decompose.setRotateOrder("bad")
        other = self.create("multMatrix", "other")
        decompose.connectInput(other.getOutputPlug(), force=True)
        self.assertTrue(other.getOutputPlug().isConnectedTo(decompose.getPlug("inputMatrix")))
        cmds.undo()
        self.assertTrue(mult.getOutputPlug().isConnectedTo(decompose.getPlug("inputMatrix")))
        cmds.redo()
        self.assertTrue(other.getOutputPlug().isConnectedTo(decompose.getPlug("inputMatrix")))

    def test_decompose_constant_and_undo(self):
        source = self.create("transform", "source")
        cmds.setAttr(source.getFullName() + ".translate", 3, 4, 5)
        node = self.create("decomposeMatrix", "decompose")
        node.setInput(source.getMatrix())
        self.assertEqual(tuple(node.getPlug("outputTranslate").get()), (3, 4, 5))
        cmds.undo()
        self.assertEqual(tuple(node.getPlug("outputTranslate").get()), (0, 0, 0))
        cmds.redo()
        self.assertEqual(tuple(node.getPlug("outputTranslate").get()), (3, 4, 5))

    def test_distance_points_units_and_undo(self):
        node = self.create("distanceBetween", "distance")
        self.assertIsInstance(node, mlib.nodes.DistanceBetween)
        self.assertFalse(hasattr(type(node), "getOutputPlug"))
        previous = cmds.currentUnit(query=True, linear=True)
        try:
            cmds.currentUnit(linear="m")
            node.setPoints((0, 0, 0), (3, 4, 0))
            self.assertAlmostEqual(node.getDistance(), 5)
            cmds.undo()
            self.assertAlmostEqual(node.getDistance(), 0)
            cmds.redo()
            self.assertAlmostEqual(node.getDistance(), 5)
            with self.assertRaises(ValueError):
                node.setPoints((0, 0, 0), (float("nan"), 1, 2))
            self.assertAlmostEqual(node.getDistance(), 5)
        finally:
            cmds.currentUnit(linear=previous)

    def test_vector_normalization_preserves_values_and_undo(self):
        """標準Plugへ委譲した正規化も検証・Vector返却・Undo/fastを保つ。"""
        node = self.create("vectorProduct", "vector")
        self.assertFalse(hasattr(type(node), "getNormalizeOutputPlug"))
        self.assertFalse(hasattr(type(node), "getOutputPlug"))
        node.setInput(1, (2, 0, 0)).setInput(2, (0, 3, 0)).setOperation("cross")
        self.assertIsInstance(node.getResult(), mlib.maths.Vector)
        self.assertEqual(tuple(node.getResult()), (0, 0, 6))
        with self.assertRaises(TypeError):
            node.setNormalizeOutput(1)
        self.assertFalse(node.getNormalizeOutput())
        self.assertIs(node.setNormalizeOutput(True), node)
        self.assertEqual(tuple(node.getResult()), (0, 0, 1))
        cmds.undo()
        self.assertFalse(node.getNormalizeOutput())
        self.assertEqual(tuple(node.getResult()), (0, 0, 6))
        self.assertIs(node.setNormalizeOutput(True, fast=True), node)
        self.assertTrue(node.getNormalizeOutput())
        driver = self.create("network", "normalizationDriver")
        source = driver.addAttr("normalize", "bool")
        self.assertIs(node.connectNormalizeOutput(source), node)
        self.assertEqual(node.getPlug("normalizeOutput").getSource(skipConversionNodes=False), source)
        self.assertFalse(node.getNormalizeOutput())
        cmds.undo()
        self.assertTrue(node.getNormalizeOutput())

    def test_angle_uses_standard_output_plug_and_radians(self):
        """標準出力参照と値getterがUI角度単位に依存しない。"""
        import math

        node = self.create("angleBetween", "angle")
        self.assertFalse(hasattr(type(node), "getOutputPlug"))
        previous = cmds.currentUnit(query=True, angle=True)
        try:
            cmds.currentUnit(angle="deg")
            node.setInput(1, (1, 0, 0)).setInput(2, (0, 1, 0))
            self.assertAlmostEqual(node.getPlug("angle").get(), math.pi / 2)
            self.assertAlmostEqual(node.getResult(), math.pi / 2)
        finally:
            cmds.currentUnit(angle=previous)

    def test_distance_live_transforms_and_undo(self):
        a, b = self.create("transform", "a"), self.create("transform", "b")
        cmds.setAttr(b.getFullName() + ".translate", 3, 4, 0)
        node = self.create("distanceBetween", "distance")
        node.connectTransforms(a, b.getFullName())
        self.assertAlmostEqual(node.getDistance(), 5)
        cmds.undo()
        self.assertFalse(node.getPlug("inMatrix1").isDestination())
        self.assertFalse(node.getPlug("inMatrix2").isDestination())
        cmds.redo()
        self.assertAlmostEqual(node.getDistance(), 5)
        cmds.setAttr(b.getFullName() + ".translateY", 0)
        self.assertAlmostEqual(node.getDistance(), 3)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
