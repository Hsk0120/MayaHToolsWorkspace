"""コンポーネント一括座標編集の保持順・入力検証・Undo。"""
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
        self.mesh = hlib.node(cmds.listRelatives(self.mesh_transform, shapes=True, fullPath=True)[0])
        curve = cmds.curve(name=self.ns + ":curve", degree=1, point=[(0, 0, 0), (1, 2, 3), (4, 5, 6)])
        self.curve = hlib.node(cmds.listRelatives(curve, shapes=True, fullPath=True)[0])

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def assert_points(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for a, b in zip(actual, expected):
            for x, y in zip(a, b):
                self.assertAlmostEqual(x, y, places=5)

    def test_vertex_cv_positions_order_and_undo(self):
        for items in (self.mesh.vertices([2, 0]), self.curve.cvs([2, 0])):
            before = items.get_positions()
            result = [(9, 8, 7), (-1, -2, -3)]
            self.assertIs(items.set_positions(iter(result)), items)
            self.assert_points(items.get_position(), result)
            self.assert_points(items.get_position(), result)
            self.assert_points([items[0].get_position()], [result[0]])
            cmds.undo()
            self.assert_points(items.get_positions(), before)
            cmds.redo()
            self.assert_points(items.get_positions(), result)
            items.set_x([20, 30])
            self.assertEqual(items.get_x(), [20, 30])
            self.assertEqual(items.get_y(), [8, -2])
            cmds.undo()
            self.assert_points(items.get_positions(), result)
            items.set_y(5)
            self.assertEqual(items.get_y(), [5, 5])
            items.set_z(6)
            self.assertEqual(items.get_z(), [6, 6])
            items.set_position((1, 2, 3))
            self.assert_points(items.get_positions(), [(1, 2, 3)] * 2)
            self.assertEqual(items.full_names(), [item.full_name() for item in items])

    def test_world_space_and_invalid_input_is_not_partial(self):
        cmds.setAttr(self.mesh_transform + ".translateX", 10)
        items = self.mesh.vertices([0, 1])
        items.set_positions([(1, 2, 3), (4, 5, 6)], ws=True)
        self.assert_points(items.get_positions(ws=True), [(1, 2, 3), (4, 5, 6)])
        before = items.get_positions()
        for values in ([(0, 0, 0)], [(0, 0, 0), (float("nan"), 0, 0)]):
            with self.assertRaises(ValueError):
                items.set_positions(values)
            self.assert_points(items.get_positions(), before)
        with self.assertRaises(ValueError):
            items.set_x([1])
        self.assert_points(items.get_positions(), before)
        empty = self.mesh.vertices([])
        self.assertIs(empty.set_positions([]), empty)
        self.assertEqual(empty.get_position(), [])
        with self.assertRaises(ValueError):
            empty.set_positions([], ws=1)

    def test_uv_bulk_axes_and_undo(self):
        items = self.mesh.uvs([2, 0])
        before = items.get_positions()
        result = [(0.2, 0.4), (0.6, 0.8)]
        items.set_positions(result)
        self.assert_points(items.get_position(), result)
        cmds.undo()
        self.assert_points(items.get_positions(), before)
        cmds.redo()
        self.assert_points(items.get_positions(), result)
        items.set_u([2, 3])
        self.assert_points(items.get_positions(), [(2, 0.4), (3, 0.8)])
        items.set_v(5)
        self.assertEqual(items.get_v(), [5, 5])
        items.set_position((0, 0))
        self.assert_points(items.get_positions(), [(0, 0), (0, 0)])
        with self.assertRaises(ValueError):
            items.set_positions([(1, 2), (3, float("inf"))])
        self.assert_points(items.get_positions(), [(0, 0), (0, 0)])

    def test_edges_and_faces_keep_vertex_collection_operations(self):
        for items in (self.mesh.edges([0, 1]), self.mesh.faces([0, 1])):
            vertices = items.vertices()
            self.assertEqual(len(vertices.indices), len(set(vertices.indices)))
            before = vertices.get_positions()
            vertices.set_z(10)
            self.assertEqual(vertices.get_z(), [10] * len(vertices))
            cmds.undo()
            self.assert_points(vertices.get_positions(), before)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
