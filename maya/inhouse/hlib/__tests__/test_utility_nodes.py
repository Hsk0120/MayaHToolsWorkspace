"""行列・距離ノードの自動登録、評価、接続、Undo/Redoを検証する。"""

import sys
import unittest
import uuid
import maya.cmds as cmds
import hlib

hlib.reload()


class UtilityNodesTest(unittest.TestCase):
    def setUp(self):
        self.namespace = "hlibUtility_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)

    def tearDown(self):
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def create(self, kind, name):
        return hlib.createNode(kind, name=self.namespace + ":" + name)

    def test_registration_and_matrix_product(self):
        a, b = self.create("transform", "a"), self.create("transform", "b")
        cmds.setAttr(a.getFullName() + ".translate", 2, 3, 4)
        cmds.setAttr(b.getFullName() + ".rotateY", 40)
        mult = self.create("multMatrix", "mult")
        self.assertIsInstance(mult, hlib.nodes.MultMatrix)
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
        self.assertIsInstance(decompose, hlib.nodes.DecomposeMatrix)
        mult.connectInput(0, source.getPlug("matrix"))
        decompose.connectInput(mult.getOutputPlug())
        cmds.setAttr(source.getFullName() + ".translate", 5, 6, 7)
        self.assertEqual(tuple(decompose.outputPlugs()["translate"].get()), (5, 6, 7))
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
        self.assertEqual(tuple(node.outputPlugs()["translate"].get()), (3, 4, 5))
        cmds.undo()
        self.assertEqual(tuple(node.outputPlugs()["translate"].get()), (0, 0, 0))
        cmds.redo()
        self.assertEqual(tuple(node.outputPlugs()["translate"].get()), (3, 4, 5))

    def test_distance_points_units_and_undo(self):
        node = self.create("distanceBetween", "distance")
        self.assertIsInstance(node, hlib.nodes.DistanceBetween)
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
