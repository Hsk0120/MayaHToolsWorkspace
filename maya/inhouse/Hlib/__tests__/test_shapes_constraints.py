"""形状ラッパーと標準コンストレイントを Maya 内で検証する。"""

import sys
import unittest
import uuid

import maya.cmds as cmds
import Hlib

Hlib.reload()
import importlib
hlib_cmds = importlib.import_module("Hlib.cmds")


class ShapesConstraintsTest(unittest.TestCase):
    """専用名前空間に作成したノードだけで動作を確認する。"""

    def setUp(self):
        self.selection = cmds.ls(selection=True, long=True) or []
        self.previous_namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.namespace = ':hlibShapesConstraints_' + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        cmds.namespace(set=self.previous_namespace)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        if self.selection:
            cmds.select(self.selection, replace=True)
        else:
            cmds.select(clear=True)

    def transform(self):
        return hlib_cmds.create_node('transform')

    def test_mesh_and_curve_geometry(self):
        cube = Hlib.Node(cmds.polyCube(constructionHistory=False)[0])
        mesh = cube.shape()
        self.assertIsInstance(mesh, Hlib.Mesh)
        self.assertEqual((mesh.num_vertices, mesh.num_edges, mesh.num_polygons), (8, 12, 6))
        local = mesh.points()[0]
        cmds.setAttr(cube.full_name + '.translateX', 5)
        self.assertAlmostEqual(mesh.points(ws=True)[0].x, local.x + 5)

        curve = Hlib.Node(cmds.curve(degree=1, point=[(0, 0, 0), (3, 0, 0), (3, 4, 0)]))
        shape = curve.shape()
        self.assertIsInstance(shape, Hlib.NurbsCurve)
        self.assertEqual((shape.num_cvs, shape.num_spans, shape.degree), (3, 2, 1))
        self.assertAlmostEqual(shape.length(), 7)
        cmds.setAttr(curve.full_name + '.scaleX', 2)
        self.assertAlmostEqual(shape.length(), 7)
        cmds.setAttr(curve.full_name + '.translateY', 2)
        self.assertAlmostEqual(shape.cv_positions(ws=True)[0].y, 2)
        self.assertAlmostEqual(shape.cv_positions()[0].y, 0)
        with self.assertRaises(ValueError):
            shape.length(0)

    def test_basic_constraints_targets_weights_and_registration(self):
        for kind in ('parent', 'point', 'orient', 'scale', 'aim'):
            with self.subTest(kind=kind):
                source, second, driven = self.transform(), self.transform(), self.transform()
                cmds.setAttr(source.full_name + '.translateX', 3)
                result = driven.add_constraint([source, second.full_name], kind, maintainOffset=True)
                expected = getattr(Hlib, kind.title() + 'Constraint')
                self.assertIsInstance(result, expected)
                self.assertIsInstance(Hlib.Node(result.full_name), expected)
                self.assertEqual([node.uuid for node in result.targets()], [source.uuid, second.uuid])
                self.assertEqual(result.weights(), [1.0, 1.0])
                self.assertEqual(len(result.weight_aliases()), 2)
                result.weight_plugs()[0].set(0.25)
                self.assertEqual(result.weights(), [0.25, 1.0])

    def test_top_level_constraint_command(self):
        self.assertTrue(callable(hlib_cmds.constraint))
        self.assertIs(Hlib.constraint, hlib_cmds.constraint)
        source = self.transform()
        target = self.transform()
        result = hlib_cmds.constraint(source, target, type='point')
        self.assertIsInstance(result, Hlib.PointConstraint)
        self.assertEqual([node.uuid for node in result.targets()], [source.uuid])

        source_name = self.transform()
        target_name = self.transform()
        result = hlib_cmds.constraint(source_name.full_name, target_name.full_name, type='point')
        self.assertEqual([node.uuid for node in result.targets()], [source_name.uuid])

    def test_specialized_constraints(self):
        mesh = Hlib.Node(cmds.polyPlane(constructionHistory=False)[0])
        for kind, expected in [('geometry', Hlib.GeometryConstraint), ('normal', Hlib.NormalConstraint),
                               ('pointOnPoly', Hlib.PointOnPolyConstraint)]:
            with self.subTest(kind=kind):
                result = self.transform().add_constraint(mesh, kind)
                self.assertIsInstance(result, expected)
                self.assertEqual(len(result.targets()), 1)
                self.assertEqual(result.weights(), [1.0])
        curve = Hlib.Node(cmds.curve(degree=1, point=[(0, 0, 0), (3, 0, 0)]))
        result = self.transform().add_constraint(curve, 'tangent')
        self.assertIsInstance(result, Hlib.TangentConstraint)
        self.assertEqual(len(result.targets()), 1)
        self.assertEqual(result.weights(), [1.0])

        cmds.select(clear=True)
        start = cmds.joint(position=(0, 0, 0))
        cmds.joint(position=(2, 1, 0))
        end = cmds.joint(position=(4, 0, 0))
        handle = Hlib.Node(cmds.ikHandle(startJoint=start, endEffector=end, solver='ikRPsolver')[0])
        self.assertIsInstance(handle, Hlib.IkHandle)
        result = handle.add_constraint(self.transform(), 'poleVector')
        self.assertIsInstance(result, Hlib.PoleVectorConstraint)
        self.assertEqual(len(result.targets()), 1)
        self.assertEqual(result.weights(), [1.0])

    def test_creation_undo_and_redo(self):
        if not cmds.undoInfo(query=True, state=True):
            self.skipTest('Undo is disabled in this Maya session')
        source, driven = self.transform(), self.transform()
        result = driven.add_constraint(source, 'pointConstraint')
        name = result.full_name
        cmds.undo()
        self.assertFalse(cmds.objExists(name))
        cmds.redo()
        self.assertIsInstance(Hlib.Node(name), Hlib.PointConstraint)

    def test_point_evaluation_and_parent_offset(self):
        source, driven = self.transform(), self.transform()
        cmds.setAttr(source.full_name + '.translateX', 4)
        driven.add_constraint(source.full_name, 'point')
        self.assertAlmostEqual(cmds.getAttr(driven.full_name + '.translateX'), 4)
        cmds.setAttr(source.full_name + '.translateX', 7)
        self.assertAlmostEqual(cmds.getAttr(driven.full_name + '.translateX'), 7)

        offset_driven = self.transform()
        cmds.setAttr(offset_driven.full_name + '.translateX', 10)
        offset_driven.add_constraint(source, maintainOffset=True)
        self.assertAlmostEqual(cmds.getAttr(offset_driven.full_name + '.translateX'), 10)
        cmds.setAttr(source.full_name + '.translateX', 9)
        self.assertAlmostEqual(cmds.getAttr(offset_driven.full_name + '.translateX'), 12)

    def test_invalid_requests_do_not_create_nodes(self):
        source, driven = self.transform(), self.transform()
        before = set(cmds.ls(long=True))
        invalid_requests = [
            ([], 'point', ValueError),
            (source, 'unknown', ValueError),
            ([object()], 'point', TypeError),
        ]
        for sources, kind, error in invalid_requests:
            with self.assertRaises(error):
                driven.add_constraint(sources, kind)
        self.assertEqual(before, set(cmds.ls(long=True)))

    def mirror_shapes(self):
        """非対称カーブと履歴付きメッシュを変換済みの親の下へ作成する。"""
        cube = Hlib.Node(cmds.polyCube()[0])
        curve = Hlib.Node(cmds.curve(degree=1, point=[(1, 2, 3), (4, 1, -2), (2, 5, 1)]))
        parent = self.transform()
        cmds.setAttr(parent.full_name + '.translate', 4, -2, 3)
        cmds.setAttr(parent.full_name + '.rotate', 23, 41, -17)
        cmds.setAttr(parent.full_name + '.scale', 2, 0.7, 1.3)
        cmds.parent(cube.full_name, curve.full_name, parent.full_name, relative=True)
        return [cube.shape(), curve.shape()]

    def positions(self, shape, ws=False):
        """API の内部距離単位で形状の全位置を返す。"""
        points = shape.points(ws) if isinstance(shape, Hlib.Mesh) else shape.cv_positions(ws)
        return [tuple(point)[:3] for point in points]

    def assert_positions(self, actual, expected):
        """全成分を許容誤差付きで比較する。"""
        self.assertEqual(len(actual), len(expected))
        for point, reference in zip(actual, expected):
            for component, value in zip(point, reference):
                # Mesh の座標保存精度を考慮し、距離単位変更時も相対誤差で比較する。
                self.assertAlmostEqual(component, value, delta=max(1e-5, abs(value) * 1e-6))

    def test_mirror_axes_in_world_and_object_space(self):
        for ws in (False, True):
            for axes in ('x', 'Y', 'z', 'xy', 'xz', 'yz', 'xyz'):
                for shape in self.mirror_shapes():
                    with self.subTest(shape=shape.type(), ws=ws, axes=axes):
                        before = self.positions(shape, ws)
                        parent = shape.parent_transform()
                        matrix = cmds.xform(parent.full_name, query=True, matrix=True, worldSpace=True)
                        selected = {'xyz'.index(a) for a in axes.lower()}
                        expected = [tuple(-v if i in selected else v for i, v in enumerate(p)) for p in before]
                        self.assertIs(shape.mirror(axes, ws=ws), shape)
                        self.assert_positions(self.positions(shape, ws), expected)
                        self.assertEqual(cmds.xform(parent.full_name, query=True, matrix=True, worldSpace=True), matrix)

    def test_transform_mirror_all_shapes(self):
        parent = self.transform()
        cube = Hlib.Node(cmds.polyCube(constructionHistory=False)[0])
        curve = Hlib.Node(cmds.curve(degree=1, point=[(1, 2, 3), (4, 1, -2), (2, 5, 1)]))
        cmds.parent(cube.shape().full_name, curve.shape().full_name, parent.full_name, shape=True, relative=True)
        shapes = parent.shapes()
        before = {shape.full_name: self.positions(shape, True) for shape in shapes}
        matrix = cmds.xform(parent.full_name, query=True, matrix=True, worldSpace=True)

        self.assertIs(parent.mirror(axis='x', ws=True), parent)

        mirrored_shapes = parent.shapes()
        self.assertEqual({shape.full_name for shape in mirrored_shapes}, set(before))
        for shape in mirrored_shapes:
            positions = before[shape.full_name]
            expected = [(-point[0], point[1], point[2]) for point in positions]
            self.assert_positions(self.positions(shape, True), expected)
        self.assertEqual(cmds.xform(parent.full_name, query=True, matrix=True, worldSpace=True), matrix)

    def test_mirror_custom_pivot_subset_and_distance_units(self):
        import maya.api.OpenMaya as om2
        previous = cmds.currentUnit(query=True, linear=True)
        try:
            cmds.currentUnit(linear='m')
            for ws in (False, True):
                for shape in self.mirror_shapes():
                    before = self.positions(shape, ws)
                    pivot = (1, 2, 3)
                    internal = [om2.MDistance(v, om2.MDistance.uiUnit()).asCentimeters() for v in pivot]
                    expected = list(before)
                    expected[0] = (2 * internal[0] - before[0][0], before[0][1], 2 * internal[2] - before[0][2])
                    shape.mirror('xz', ws=ws, pivot=pivot, indices=[0, 0])
                    self.assert_positions(self.positions(shape, ws), expected)
        finally:
            cmds.currentUnit(linear=previous)

    def test_mirror_undo_redo(self):
        if not cmds.undoInfo(query=True, state=True):
            self.skipTest('Undo is disabled in this Maya session')
        for shape in self.mirror_shapes():
            before = self.positions(shape, True)
            shape.mirror('x', ws=True)
            after = self.positions(shape, True)
            cmds.undo()
            self.assert_positions(self.positions(shape, True), before)
            cmds.redo()
            self.assert_positions(self.positions(shape, True), after)

    def test_mirror_validation_before_mutation(self):
        for shape in self.mirror_shapes():
            before = self.positions(shape)
            for kwargs, error in [({'axis': ''}, ValueError), ({'axis': 'xx'}, ValueError),
                                  ({'axis': 'a'}, ValueError), ({'ws': 'world'}, ValueError),
                                  ({'pivot': (0, 1)}, ValueError), ({'pivot': (0, float('nan'), 0)}, ValueError),
                                  ({'indices': [0, -1]}, IndexError), ({'indices': [0, 10000]}, IndexError),
                                  ({'indices': [0, 1.2]}, TypeError)]:
                with self.assertRaises(error):
                    shape.mirror(**kwargs)
                self.assert_positions(self.positions(shape), before)
            self.assertIs(shape.mirror(indices=[]), shape)
            self.assert_positions(self.positions(shape), before)
            cmds.setAttr(shape.parent_transform().full_name + '.scaleX', 0)
            with self.assertRaises(ValueError):
                shape.mirror(ws=True)

    def test_mirror_periodic_curve(self):
        curve = Hlib.Node(cmds.circle(constructionHistory=False)[0])
        shape = curve.shape()
        before = self.positions(shape)
        form, degree, count = shape.form, shape.degree, shape.num_cvs
        shape.mirror('x')
        self.assert_positions(self.positions(shape), [(-x, y, z) for x, y, z in before])
        self.assertEqual((shape.form, shape.degree, shape.num_cvs), (form, degree, count))

    def test_component_collections_and_live_positions(self):
        for shape in self.mirror_shapes():
            is_mesh = isinstance(shape, Hlib.Mesh)
            component_type = Hlib.Vertex if is_mesh else Hlib.CV
            collection_type = Hlib.Vertices if is_mesh else Hlib.CVs
            collection = shape.vertices([2, 0, 2]) if is_mesh else shape.cvs([2, 0, 2])
            self.assertIsInstance(collection, collection_type)
            self.assertEqual(collection.indices, (2, 0))
            self.assertEqual(len(collection), 2)
            self.assertEqual([item.index for item in collection], [2, 0])
            self.assertIsInstance(collection[0], component_type)
            self.assertEqual(collection[-1].index, 0)
            self.assertIsInstance(collection[:1], collection_type)
            self.assertEqual(collection[:1].indices, (2,))
            self.assertEqual(collection[0].position(), collection.positions()[0])
            single = shape.vertex(2) if is_mesh else shape.cv(2)
            before = single.position()
            self.assertIs(collection.mirror('z'), collection)
            self.assert_positions([single.position()], [(before[0], before[1], -before[2])])
            old_name = single.full_name
            shape.rename('renamedMirrorShape')
            self.assertNotEqual(single.full_name, old_name)
            self.assertTrue(cmds.objExists(single.full_name))
            other_type = Hlib.CVs if is_mesh else Hlib.Vertices
            with self.assertRaises(TypeError):
                other_type(shape, [])
            cmds.delete(shape.full_name)
            with self.assertRaises(RuntimeError):
                single.position()

    def test_xyz_and_mesh_components(self):
        mesh, curve = self.mirror_shapes()
        for item in (mesh.vertex(0), curve.cv(0)):
            before = item.position()
            for axis in 'xyz':
                setattr(item, axis, 2.75)
                self.assertAlmostEqual(getattr(item, axis), 2.75)
                cmds.undo()
                self.assert_positions([item.position()], [before])
            item.set_position((3, 4, 5), ws=True)
            self.assert_positions([item.position(ws=True)], [(3, 4, 5)])
            cmds.undo()
            with self.assertRaises(ValueError):
                item.set_position((1, float('nan'), 3))
            self.assert_positions([item.position()], [before])
        self.assertEqual(len(mesh.edges()), mesh.num_edges)
        self.assertEqual(len(mesh.faces()), mesh.num_polygons)
        self.assertEqual(len(mesh.edge(0).vertices()), 2)
        self.assertEqual(len(mesh.face(0).vertices()), 4)
        self.assertEqual(len(mesh.edges().vertices()), mesh.num_vertices)
        self.assertEqual(len(mesh.faces().vertices()), mesh.num_vertices)
        self.assertEqual(len(mesh.uvs()), mesh.num_uvs)
        uv = mesh.uv(0)
        before = uv.position()
        uv.u = 0.125
        self.assertAlmostEqual(uv.u, 0.125)
        self.assertAlmostEqual(uv.v, before[1])
        cmds.undo()
        self.assertEqual(uv.position(), before)
        uv.v = 0.375
        self.assertAlmostEqual(uv.v, 0.375)
        cmds.undo()
        self.assertEqual(mesh.uvs([0]).positions(), [before])
        for collection in (Hlib.Edges, Hlib.Faces, Hlib.UVs):
            with self.assertRaises(TypeError):
                collection(curve)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
