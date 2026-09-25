"""形状ラッパーと標準コンストレイントを Maya 内で検証する。"""

import sys
import unittest
import uuid

import maya.cmds as cmds
import hlib

hlib.reload()
import importlib
hlib_cmds = importlib.import_module("hlib.cmds")


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
        return hlib_cmds.createNode('transform')

    def test_delete_constraints_direct_and_undo(self):
        source, driven, other = self.transform(), self.transform(), self.transform()
        constraint = driven.add_constraint(source)
        untouched = other.add_constraint(driven)
        name, untouched_name = constraint.full_name(), untouched.full_name()
        self.assertEqual(driven.delete_constraints(), [name])
        self.assertFalse(cmds.objExists(name))
        self.assertTrue(cmds.objExists(untouched_name))
        self.assertTrue(source.is_valid())
        cmds.undo()
        self.assertTrue(cmds.objExists(name))
        cmds.redo()
        self.assertFalse(cmds.objExists(name))
        self.assertEqual(driven.delete_constraints(), [])

    def test_delete_constraints_pair_blend_preserves_animation(self):
        source, driven = self.transform(), self.transform()
        cmds.setKeyframe(driven.full_name(), attribute='translateX', time=1, value=2)
        animation = cmds.listConnections(driven.full_name(), source=True, destination=False, type='animCurve')[0]
        constraint = driven.add_constraint(source, type='point')
        name = constraint.full_name()
        blends = cmds.listConnections(driven.full_name(), source=True, destination=False, type='pairBlend')
        self.assertTrue(blends)
        deleted = driven.delete_constraints()
        self.assertIn(name, deleted)
        for blend in blends:
            self.assertIn(blend, deleted)
            self.assertFalse(cmds.objExists(blend))
        self.assertTrue(cmds.objExists(animation))
        cmds.undo()
        self.assertTrue(cmds.objExists(name))
        self.assertTrue(cmds.objExists(blends[0]))

    def test_delete_constraints_shared_output_rejected(self):
        source, driven, other = self.transform(), self.transform(), self.transform()
        constraint = driven.add_constraint(source, type='point')
        cmds.connectAttr(constraint.full_name() + '.constraintTranslateX', other.full_name() + '.translateX')
        with self.assertRaises(RuntimeError):
            driven.delete_constraints()
        self.assertTrue(constraint.is_valid())

    def test_delete_constraints_keeps_unrelated_pair_blend(self):
        driven = self.transform()
        blend = cmds.createNode('pairBlend')
        cmds.connectAttr(blend + '.outTranslate', driven.full_name() + '.translate')
        self.assertEqual(driven.delete_constraints(), [])
        self.assertTrue(cmds.objExists(blend))

    def test_camera_shape_wrapper_and_focal_length(self):
        _camera_transform, camera_shape_name = cmds.camera()
        camera = hlib.nodes.Node(camera_shape_name)
        self.assertIsInstance(camera, hlib.nodes.Camera)

        cmds.setAttr(camera_shape_name + '.focalLength', 50.0)
        self.assertAlmostEqual(camera.focal_length(), 50.0)

        import maya.api.OpenMaya as om2
        self.assertIsInstance(camera.camera_fn(), om2.MFnCamera)

    def test_mesh_and_curve_geometry(self):
        cube = hlib.nodes.Node(cmds.polyCube(constructionHistory=False)[0])
        mesh = cube.shape()
        self.assertIsInstance(mesh, hlib.nodes.Mesh)
        self.assertEqual((mesh.num_vertices(), mesh.num_edges(), mesh.num_polygons()), (8, 12, 6))
        local_x = mesh.points()[0].x
        cmds.setAttr(cube.full_name() + '.translateX', 5)
        self.assertAlmostEqual(mesh.points(ws=True)[0].x, local_x + 5)

        curve = hlib.nodes.Node(cmds.curve(degree=1, point=[(0, 0, 0), (3, 0, 0), (3, 4, 0)]))
        shape = curve.shape()
        self.assertIsInstance(shape, hlib.nodes.NurbsCurve)
        self.assertEqual((shape.num_cvs(), shape.num_spans(), shape.degree()), (3, 2, 1))
        self.assertAlmostEqual(shape.length(), 7)
        cmds.setAttr(curve.full_name() + '.scaleX', 2)
        self.assertAlmostEqual(shape.length(), 7)
        cmds.setAttr(curve.full_name() + '.translateY', 2)
        self.assertAlmostEqual(shape.cv_positions(ws=True)[0].y, 2)
        self.assertAlmostEqual(shape.cv_positions()[0].y, 0)
        with self.assertRaises(ValueError):
            shape.length(0)

    def test_mesh_normals_object_and_world_space(self):
        cube = hlib.nodes.Node(cmds.polyCube(constructionHistory=False)[0])
        mesh = cube.shape()

        local_normals = mesh.normals()
        self.assertEqual(len(local_normals), mesh.num_vertices())
        for normal in local_normals:
            self.assertAlmostEqual(sum(c * c for c in (normal.x, normal.y, normal.z)) ** 0.5, 1.0, places=5)

        cmds.setAttr(cube.full_name() + '.rotateY', 90)
        world_normals = mesh.normals(ws=True)
        self.assertEqual(len(world_normals), mesh.num_vertices())
        self.assertFalse(
            all(
                abs(a.x - b.x) < 1e-5 and abs(a.y - b.y) < 1e-5 and abs(a.z - b.z) < 1e-5
                for a, b in zip(local_normals, world_normals)
            )
        )

        weighted = mesh.normals(angle_weighted=True)
        self.assertEqual(len(weighted), mesh.num_vertices())

    def test_basic_constraints_targets_weights_and_registration(self):
        for kind in ('parent', 'point', 'orient', 'scale', 'aim'):
            with self.subTest(kind=kind):
                source, second, driven = self.transform(), self.transform(), self.transform()
                cmds.setAttr(source.full_name() + '.translateX', 3)
                result = driven.add_constraint([source, second.full_name()], kind, maintainOffset=True)
                expected = getattr(hlib.nodes, kind.title() + 'Constraint')
                self.assertIsInstance(result, expected)
                self.assertIsInstance(hlib.nodes.Node(result.full_name()), expected)
                self.assertEqual([node.uuid() for node in result.targets()], [source.uuid(), second.uuid()])
                self.assertEqual(result.weights(), [1.0, 1.0])
                self.assertEqual(len(result.weight_aliases()), 2)
                result.weight_plugs()[0].set(0.25)
                self.assertEqual(result.weights(), [0.25, 1.0])

    def test_constraint_set_weight(self):
        source, second, driven = self.transform(), self.transform(), self.transform()
        result = driven.add_constraint([source, second], 'point', maintainOffset=True)
        self.assertEqual(result.weights(), [1.0, 1.0])

        returned = result.set_weight(0.5)
        self.assertIs(returned, result)
        self.assertEqual(result.weights(), [0.5, 0.5])

        result.set_weight(0.25, source)
        self.assertEqual(result.weights(), [0.25, 0.5])

        result.set_weight(0.75, source.full_name(), second)
        self.assertEqual(result.weights(), [0.75, 0.75])

        unrelated = self.transform()
        with self.assertRaises(ValueError):
            result.set_weight(1.0, unrelated)

    def test_top_level_constraint_command(self):
        self.assertTrue(callable(hlib_cmds.constraint))
        self.assertIs(hlib.constraint, hlib_cmds.constraint)
        source = self.transform()
        target = self.transform()
        result = hlib_cmds.constraint(source, target, type='point')
        self.assertIsInstance(result, hlib.nodes.PointConstraint)
        self.assertEqual([node.uuid() for node in result.targets()], [source.uuid()])

        source_name = self.transform()
        target_name = self.transform()
        result = hlib_cmds.constraint(source_name.full_name(), target_name.full_name(), type='point')
        self.assertEqual([node.uuid() for node in result.targets()], [source_name.uuid()])

    def test_specialized_constraints(self):
        mesh = hlib.nodes.Node(cmds.polyPlane(constructionHistory=False)[0])
        for kind, expected in [('geometry', hlib.nodes.GeometryConstraint), ('normal', hlib.nodes.NormalConstraint),
                               ('pointOnPoly', hlib.nodes.PointOnPolyConstraint)]:
            with self.subTest(kind=kind):
                result = self.transform().add_constraint(mesh, kind)
                self.assertIsInstance(result, expected)
                self.assertEqual(len(result.targets()), 1)
                self.assertEqual(result.weights(), [1.0])
        curve = hlib.nodes.Node(cmds.curve(degree=1, point=[(0, 0, 0), (3, 0, 0)]))
        result = self.transform().add_constraint(curve, 'tangent')
        self.assertIsInstance(result, hlib.nodes.TangentConstraint)
        self.assertEqual(len(result.targets()), 1)
        self.assertEqual(result.weights(), [1.0])

        cmds.select(clear=True)
        start = cmds.joint(position=(0, 0, 0))
        cmds.joint(position=(2, 1, 0))
        end = cmds.joint(position=(4, 0, 0))
        handle = hlib.nodes.Node(cmds.ikHandle(startJoint=start, endEffector=end, solver='ikRPsolver')[0])
        self.assertIsInstance(handle, hlib.nodes.IkHandle)
        result = handle.add_constraint(self.transform(), 'poleVector')
        self.assertIsInstance(result, hlib.nodes.PoleVectorConstraint)
        self.assertEqual(len(result.targets()), 1)
        self.assertEqual(result.weights(), [1.0])

    def test_joint_chain_from_here_and_ik_handle_queries(self):
        cmds.select(clear=True)
        j1 = hlib.nodes.Joint(cmds.joint(position=(0, 0, 0)))
        j2 = hlib.nodes.Joint(cmds.joint(position=(2, 0, 0)))
        j3 = hlib.nodes.Joint(cmds.joint(position=(4, 0, 0)))
        branch = hlib.nodes.Joint(cmds.joint(position=(4, 2, 0)))
        j3.set_parent(j2)
        branch.set_parent(j2)

        chain = j1.chain_from_here()
        self.assertEqual([joint.full_name() for joint in chain], [j1.full_name(), j2.full_name()])

        chain_to_j3 = j1.chain_from_here(j3)
        self.assertEqual(
            [joint.full_name() for joint in chain_to_j3],
            [j1.full_name(), j2.full_name(), j3.full_name()],
        )

        cmds.select(clear=True)
        unrelated = hlib.nodes.Joint(cmds.joint(position=(0, 5, 0)))
        with self.assertRaises(ValueError):
            j1.chain_from_here(unrelated)

        self.assertEqual(j1.ik_handles(), [])
        handle = hlib.nodes.Node(
            cmds.ikHandle(startJoint=j1.full_name(), endEffector=j3.full_name(), solver='ikRPsolver')[0]
        )
        self.assertIsInstance(handle, hlib.nodes.IkHandle)

        found_handles = j1.ik_handles()
        self.assertEqual(len(found_handles), 1)
        self.assertEqual(found_handles[0].full_name(), handle.full_name())
        self.assertEqual(j2.ik_handles(), [])

        self.assertEqual(handle.get_end_joint().full_name(), j3.full_name())
        joint_list = handle.get_joint_list()
        self.assertEqual([joint.full_name() for joint in joint_list], [j1.full_name(), j2.full_name()])
        joint_list_with_tip = handle.get_joint_list(include_tip=True)
        self.assertEqual(
            [joint.full_name() for joint in joint_list_with_tip],
            [j1.full_name(), j2.full_name(), j3.full_name()],
        )

    def test_creation_undo_and_redo(self):
        if not cmds.undoInfo(query=True, state=True):
            self.skipTest('Undo is disabled in this Maya session')
        source, driven = self.transform(), self.transform()
        result = driven.add_constraint(source, 'pointConstraint')
        name = result.full_name()
        cmds.undo()
        self.assertFalse(cmds.objExists(name))
        cmds.redo()
        self.assertIsInstance(hlib.nodes.Node(name), hlib.nodes.PointConstraint)

    def test_point_evaluation_and_parent_offset(self):
        source, driven = self.transform(), self.transform()
        cmds.setAttr(source.full_name() + '.translateX', 4)
        driven.add_constraint(source.full_name(), 'point')
        self.assertAlmostEqual(cmds.getAttr(driven.full_name() + '.translateX'), 4)
        cmds.setAttr(source.full_name() + '.translateX', 7)
        self.assertAlmostEqual(cmds.getAttr(driven.full_name() + '.translateX'), 7)

        offset_driven = self.transform()
        cmds.setAttr(offset_driven.full_name() + '.translateX', 10)
        offset_driven.add_constraint(source, maintainOffset=True)
        self.assertAlmostEqual(cmds.getAttr(offset_driven.full_name() + '.translateX'), 10)
        cmds.setAttr(source.full_name() + '.translateX', 9)
        self.assertAlmostEqual(cmds.getAttr(offset_driven.full_name() + '.translateX'), 12)

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
        cube = hlib.nodes.Node(cmds.polyCube()[0])
        curve = hlib.nodes.Node(cmds.curve(degree=1, point=[(1, 2, 3), (4, 1, -2), (2, 5, 1)]))
        parent = self.transform()
        cmds.setAttr(parent.full_name() + '.translate', 4, -2, 3)
        cmds.setAttr(parent.full_name() + '.rotate', 23, 41, -17)
        cmds.setAttr(parent.full_name() + '.scale', 2, 0.7, 1.3)
        cmds.parent(cube.full_name(), curve.full_name(), parent.full_name(), relative=True)
        return [cube.shape(), curve.shape()]

    def positions(self, shape, ws=False):
        """API の内部距離単位で形状の全位置を返す。"""
        points = shape.points(ws) if isinstance(shape, hlib.nodes.Mesh) else shape.cv_positions(ws)
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
                        matrix = cmds.xform(parent.full_name(), query=True, matrix=True, worldSpace=True)
                        selected = {'xyz'.index(a) for a in axes.lower()}
                        expected = [tuple(-v if i in selected else v for i, v in enumerate(p)) for p in before]
                        self.assertIs(shape.mirror(axes, ws=ws), shape)
                        self.assert_positions(self.positions(shape, ws), expected)
                        self.assertEqual(cmds.xform(parent.full_name(), query=True, matrix=True, worldSpace=True), matrix)

    def test_transform_mirror_all_shapes(self):
        parent = self.transform()
        cube = hlib.nodes.Node(cmds.polyCube(constructionHistory=False)[0])
        curve = hlib.nodes.Node(cmds.curve(degree=1, point=[(1, 2, 3), (4, 1, -2), (2, 5, 1)]))
        cmds.parent(cube.shape().full_name(), curve.shape().full_name(), parent.full_name(), shape=True, relative=True)
        shapes = parent.shapes()
        before = {shape.full_name(): self.positions(shape, True) for shape in shapes}
        matrix = cmds.xform(parent.full_name(), query=True, matrix=True, worldSpace=True)

        self.assertIs(parent.mirror(axis='x', ws=True), parent)

        mirrored_shapes = parent.shapes()
        self.assertEqual({shape.full_name() for shape in mirrored_shapes}, set(before))
        for shape in mirrored_shapes:
            positions = before[shape.full_name()]
            expected = [(-point[0], point[1], point[2]) for point in positions]
            self.assert_positions(self.positions(shape, True), expected)
        self.assertEqual(cmds.xform(parent.full_name(), query=True, matrix=True, worldSpace=True), matrix)

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
            cmds.setAttr(shape.parent_transform().full_name() + '.scaleX', 0)
            with self.assertRaises(ValueError):
                shape.mirror(ws=True)

    def test_mirror_periodic_curve(self):
        curve = hlib.nodes.Node(cmds.circle(constructionHistory=False)[0])
        shape = curve.shape()
        before = self.positions(shape)
        form, degree, count = shape.form(), shape.degree(), shape.num_cvs()
        shape.mirror('x')
        self.assert_positions(self.positions(shape), [(-x, y, z) for x, y, z in before])
        self.assertEqual((shape.form(), shape.degree(), shape.num_cvs()), (form, degree, count))

    def test_nurbs_curve_get_collocated_cv_groups(self):
        curve = hlib.nodes.Node(
            cmds.curve(degree=1, point=[(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)])
        )
        shape = curve.shape()
        self.assertEqual(shape.get_collocated_cv_groups(), [])

        cmds.move(1, 0, 0, shape.full_name() + '.cv[2]', absolute=True)
        self.assertEqual(shape.get_collocated_cv_groups(), [[1, 2]])

        cmds.move(1, 0, 0, shape.full_name() + '.cv[3]', absolute=True)
        self.assertEqual(shape.get_collocated_cv_groups(), [[1, 2, 3]])

        with self.assertRaises(ValueError):
            shape.get_collocated_cv_groups(tolerance=0)

    def test_component_collections_and_live_positions(self):
        for shape in self.mirror_shapes():
            is_mesh = isinstance(shape, hlib.nodes.Mesh)
            component_type = hlib.components.Vertex if is_mesh else hlib.components.CV
            collection_type = hlib.components.Vertices if is_mesh else hlib.components.CVs
            collection = shape.vertices([2, 0, 2]) if is_mesh else shape.cvs([2, 0, 2])
            self.assertIsInstance(collection, collection_type)
            self.assertEqual(collection.indices, (2, 0))
            self.assertEqual(len(collection), 2)
            self.assertEqual([item.index for item in collection], [2, 0])
            self.assertIsInstance(collection[0], component_type)
            self.assertEqual(collection[-1].index, 0)
            self.assertIsInstance(collection[:1], collection_type)
            self.assertEqual(collection[:1].indices, (2,))
            self.assertEqual(collection[0].get_position(), collection.get_positions()[0])
            single = shape.vertex(2) if is_mesh else shape.cv(2)
            before = single.get_position()
            self.assertIs(collection.mirror('z'), collection)
            self.assert_positions([single.get_position()], [(before[0], before[1], -before[2])])
            old_name = single.full_name()
            shape.rename('renamedMirrorShape')
            self.assertNotEqual(single.full_name(), old_name)
            self.assertTrue(cmds.objExists(single.full_name()))
            other_type = hlib.components.CVs if is_mesh else hlib.components.Vertices
            with self.assertRaises(TypeError):
                other_type(shape, [])
            cmds.delete(shape.full_name())
            with self.assertRaises(RuntimeError):
                single.get_position()

    def test_xyz_and_mesh_components(self):
        mesh, curve = self.mirror_shapes()
        for item in (mesh.vertex(0), curve.cv(0)):
            before = item.get_position()
            for axis in 'xyz':
                getattr(item, "set_" + axis)(2.75)
                self.assertAlmostEqual(getattr(item, "get_" + axis)(), 2.75)
                cmds.undo()
                self.assert_positions([item.get_position()], [before])
            item.set_position((3, 4, 5), ws=True)
            self.assert_positions([item.get_position(ws=True)], [(3, 4, 5)])
            cmds.undo()
            with self.assertRaises(ValueError):
                item.set_position((1, float('nan'), 3))
            self.assert_positions([item.get_position()], [before])
        self.assertEqual(len(mesh.edges()), mesh.num_edges())
        self.assertEqual(len(mesh.faces()), mesh.num_polygons())
        self.assertEqual(len(mesh.edge(0).vertices()), 2)
        self.assertEqual(len(mesh.face(0).vertices()), 4)
        self.assertEqual(len(mesh.edges().vertices()), mesh.num_vertices())
        self.assertEqual(len(mesh.faces().vertices()), mesh.num_vertices())
        self.assertEqual(len(mesh.uvs()), mesh.num_uvs())
        uv = mesh.uv(0)
        before = uv.get_position()
        uv.set_u(0.125)
        self.assertAlmostEqual(uv.get_u(), 0.125)
        self.assertAlmostEqual(uv.get_v(), before[1])
        cmds.undo()
        self.assertEqual(uv.get_position(), before)
        uv.set_v(0.375)
        self.assertAlmostEqual(uv.get_v(), 0.375)
        cmds.undo()
        self.assertEqual(mesh.uvs([0]).get_positions(), [before])
        for collection in (hlib.components.Edges, hlib.components.Faces, hlib.components.UVs):
            with self.assertRaises(TypeError):
                collection(curve)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
