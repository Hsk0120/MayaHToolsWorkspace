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
        cmds.setAttr(a.full_name + ".translate", 2, 3, 4)
        cmds.setAttr(b.full_name + ".rotateY", 40)
        mult = self.create("multMatrix", "mult")
        self.assertIsInstance(mult, hlib.nodes.MultMatrix)
        mult.set_input(0, a.get_matrix()).set_input(3, b.get_matrix())
        expected = a.get_matrix() * b.get_matrix()
        for x, y in zip(mult.result(), expected):
            self.assertAlmostEqual(x, y)
        cmds.undo()
        for x, y in zip(mult.result(), a.get_matrix()):
            self.assertAlmostEqual(x, y)
        cmds.redo()
        for x, y in zip(mult.result(), expected):
            self.assertAlmostEqual(x, y)
        with self.assertRaises(ValueError):
            mult.set_input(-1, expected)

    def test_live_matrix_connections_and_decomposition(self):
        source = self.create("transform", "source")
        mult = self.create("multMatrix", "mult")
        decompose = self.create("decomposeMatrix", "decompose")
        self.assertIsInstance(decompose, hlib.nodes.DecomposeMatrix)
        mult.connect_input(0, source.attr("matrix"))
        decompose.connect_input(mult.output())
        cmds.setAttr(source.full_name + ".translate", 5, 6, 7)
        self.assertEqual(tuple(decompose.output_plugs()["translate"].get()), (5, 6, 7))
        decompose.set_rotate_order("zyx")
        self.assertEqual(decompose.attr("inputRotateOrder").get(), 5)
        cmds.undo()
        self.assertEqual(decompose.attr("inputRotateOrder").get(), 0)
        cmds.redo()
        self.assertEqual(decompose.attr("inputRotateOrder").get(), 5)
        with self.assertRaises(ValueError):
            decompose.set_rotate_order("bad")
        other = self.create("multMatrix", "other")
        decompose.connect_input(other.output(), force=True)
        self.assertTrue(other.output().is_connected_to(decompose.attr("inputMatrix")))
        cmds.undo()
        self.assertTrue(mult.output().is_connected_to(decompose.attr("inputMatrix")))
        cmds.redo()
        self.assertTrue(other.output().is_connected_to(decompose.attr("inputMatrix")))

    def test_decompose_constant_and_undo(self):
        source = self.create("transform", "source")
        cmds.setAttr(source.full_name + ".translate", 3, 4, 5)
        node = self.create("decomposeMatrix", "decompose")
        node.set_input(source.get_matrix())
        self.assertEqual(tuple(node.output_plugs()["translate"].get()), (3, 4, 5))
        cmds.undo()
        self.assertEqual(tuple(node.output_plugs()["translate"].get()), (0, 0, 0))
        cmds.redo()
        self.assertEqual(tuple(node.output_plugs()["translate"].get()), (3, 4, 5))

    def test_distance_points_units_and_undo(self):
        node = self.create("distanceBetween", "distance")
        self.assertIsInstance(node, hlib.nodes.DistanceBetween)
        previous = cmds.currentUnit(query=True, linear=True)
        try:
            cmds.currentUnit(linear="m")
            node.set_points((0, 0, 0), (3, 4, 0))
            self.assertAlmostEqual(node.distance(), 5)
            cmds.undo()
            self.assertAlmostEqual(node.distance(), 0)
            cmds.redo()
            self.assertAlmostEqual(node.distance(), 5)
            with self.assertRaises(ValueError):
                node.set_points((0, 0, 0), (float("nan"), 1, 2))
            self.assertAlmostEqual(node.distance(), 5)
        finally:
            cmds.currentUnit(linear=previous)

    def test_distance_live_transforms_and_undo(self):
        a, b = self.create("transform", "a"), self.create("transform", "b")
        cmds.setAttr(b.full_name + ".translate", 3, 4, 0)
        node = self.create("distanceBetween", "distance")
        node.connect_transforms(a, b.full_name)
        self.assertAlmostEqual(node.distance(), 5)
        cmds.undo()
        self.assertFalse(node.attr("inMatrix1").is_destination)
        self.assertFalse(node.attr("inMatrix2").is_destination)
        cmds.redo()
        self.assertAlmostEqual(node.distance(), 5)
        cmds.setAttr(b.full_name + ".translateY", 0)
        self.assertAlmostEqual(node.distance(), 3)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
