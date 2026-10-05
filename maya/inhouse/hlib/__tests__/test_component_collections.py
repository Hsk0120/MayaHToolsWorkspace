"""コンポーネント一括座標編集の保持順・入力検証・Undo。"""
from maya.api.OpenMaya import MSpace
import sys
import unittest
import uuid
import maya.cmds as cmds
import hlib

hlib.reload()


class ComponentCollectionsTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibPoints_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.mesh_transform = cmds.polyCube(name=self.ns + ":mesh")[0]
        self.mesh = hlib.getNode(cmds.listRelatives(self.mesh_transform, shapes=True, fullPath=True)[0])
        curve = cmds.curve(name=self.ns + ":curve", degree=1, point=[(0, 0, 0), (1, 2, 3), (4, 5, 6)])
        self.curve = hlib.getNode(cmds.listRelatives(curve, shapes=True, fullPath=True)[0])

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def assert_points(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for a, b in zip(actual, expected):
            for x, y in zip(a, b):
                self.assertAlmostEqual(x, y, places=5)

    def test_vertex_cv_positions_order_and_undo(self):
        for items in (self.mesh.vertices([2, 0]), self.curve.cvs([2, 0])):
            before = items.getPosition()
            result = [(9, 8, 7), (-1, -2, -3)]
            self.assertIs(items.setPositions(iter(result)), items)
            self.assert_points(items.getPosition(), result)
            self.assert_points(items.getPosition(), result)
            self.assert_points([items[0].getPosition()], [result[0]])
            cmds.undo()
            self.assert_points(items.getPosition(), before)
            cmds.redo()
            self.assert_points(items.getPosition(), result)
            items.setX([20, 30])
            self.assertEqual(items.getX(), [20, 30])
            self.assertEqual(items.getY(), [8, -2])
            cmds.undo()
            self.assert_points(items.getPosition(), result)
            items.setY(5)
            self.assertEqual(items.getY(), [5, 5])
            items.setZ(6)
            self.assertEqual(items.getZ(), [6, 6])
            items.setPosition((1, 2, 3))
            self.assert_points(items.getPosition(), [(1, 2, 3)] * 2)
            self.assertEqual(items.fullNames(), [item.fullName() for item in items])

    def test_world_space_and_invalid_input_is_not_partial(self):
        cmds.setAttr(self.mesh_transform + ".translateX", 10)
        items = self.mesh.vertices([0, 1])
        items.setPositions([(1, 2, 3), (4, 5, 6)], ws=True)
        self.assert_points(items.getPosition(ws=True), [(1, 2, 3), (4, 5, 6)])
        before = items.getPosition()
        for values in ([(0, 0, 0)], [(0, 0, 0), (float("nan"), 0, 0)]):
            with self.assertRaises(ValueError):
                items.setPositions(values)
            self.assert_points(items.getPosition(), before)
        with self.assertRaises(ValueError):
            items.setX([1])
        self.assert_points(items.getPosition(), before)
        empty = self.mesh.vertices([])
        self.assertIs(empty.setPositions([]), empty)
        self.assertEqual(empty.getPosition(), [])
        with self.assertRaises(ValueError):
            empty.setPositions([], ws=1)

    def test_uv_bulk_axes_and_undo(self):
        items = self.mesh.uvs([2, 0])
        before = items.getPosition()
        result = [(0.2, 0.4), (0.6, 0.8)]
        items.setPositions(result)
        self.assert_points(items.getPosition(), result)
        cmds.undo()
        self.assert_points(items.getPosition(), before)
        cmds.redo()
        self.assert_points(items.getPosition(), result)
        items.setU([2, 3])
        self.assert_points(items.getPosition(), [(2, 0.4), (3, 0.8)])
        items.setV(5)
        self.assertEqual(items.getV(), [5, 5])
        items.setPosition((0, 0))
        self.assert_points(items.getPosition(), [(0, 0), (0, 0)])
        with self.assertRaises(ValueError):
            items.setPositions([(1, 2), (3, float("inf"))])
        self.assert_points(items.getPosition(), [(0, 0), (0, 0)])

    def test_edges_and_faces_keep_vertex_collection_operations(self):
        for items in (self.mesh.edges([0, 1]), self.mesh.faces([0, 1])):
            vertices = items.vertices()
            self.assertEqual(len(vertices.indices), len(set(vertices.indices)))
            before = vertices.getPosition()
            vertices.setZ(10)
            self.assertEqual(vertices.getZ(), [10] * len(vertices))
            cmds.undo()
            self.assert_points(vertices.getPosition(), before)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
