"""形状ラッパーと標準コンストレイントを Maya 内で検証する。"""
from maya.api.OpenMaya import MSpace

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

    def getTransform(self):
        return hlib_cmds.createNode('transform')

    def test_delete_constraints_direct_and_undo(self):
        source, driven, other = self.getTransform(), self.getTransform(), self.getTransform()
        constraint = driven.addConstraint(source)
        untouched = other.addConstraint(driven)
        name, untouched_name = constraint.getFullName(), untouched.getFullName()
        self.assertEqual(driven.deleteConstraints(), [name])
        self.assertFalse(cmds.objExists(name))
        self.assertTrue(cmds.objExists(untouched_name))
        self.assertTrue(source.isValid())
        cmds.undo()
        self.assertTrue(cmds.objExists(name))
        cmds.redo()
        self.assertFalse(cmds.objExists(name))
        self.assertEqual(driven.deleteConstraints(), [])

    def test_delete_constraints_pair_blend_preserves_animation(self):
        source, driven = self.getTransform(), self.getTransform()
        cmds.setKeyframe(driven.getFullName(), attribute='translateX', time=1, value=2)
        animation = cmds.listConnections(driven.getFullName(), source=True, destination=False, type='animCurve')[0]
        constraint = driven.addConstraint(source, type='point')
        name = constraint.getFullName()
        blends = cmds.listConnections(driven.getFullName(), source=True, destination=False, type='pairBlend')
        self.assertTrue(blends)
        deleted = driven.deleteConstraints()
        self.assertIn(name, deleted)
        for blend in blends:
            self.assertIn(blend, deleted)
            self.assertFalse(cmds.objExists(blend))
        self.assertTrue(cmds.objExists(animation))
        cmds.undo()
        self.assertTrue(cmds.objExists(name))
        self.assertTrue(cmds.objExists(blends[0]))

    def test_delete_constraints_shared_output_rejected(self):
        source, driven, other = self.getTransform(), self.getTransform(), self.getTransform()
        constraint = driven.addConstraint(source, type='point')
        cmds.connectAttr(constraint.getFullName() + '.constraintTranslateX', other.getFullName() + '.translateX')
        with self.assertRaises(RuntimeError):
            driven.deleteConstraints()
        self.assertTrue(constraint.isValid())

    def test_delete_constraints_keeps_unrelated_pair_blend(self):
        driven = self.getTransform()
        blend = cmds.createNode('pairBlend')
        cmds.connectAttr(blend + '.outTranslate', driven.getFullName() + '.translate')
        self.assertEqual(driven.deleteConstraints(), [])
        self.assertTrue(cmds.objExists(blend))

    def test_camera_shape_wrapper_and_focal_length(self):
        _camera_transform, camera_shape_name = cmds.camera()
        camera = hlib.nodes.Node(camera_shape_name)
        self.assertIsInstance(camera, hlib.nodes.Camera)

        cmds.setAttr(camera_shape_name + '.focalLength', 50.0)
        self.assertAlmostEqual(camera.getFocalLength(), 50.0)

        import maya.api.OpenMaya as om2
        self.assertIsInstance(camera.cameraFn(), om2.MFnCamera)

    def test_mesh_and_curve_geometry(self):
        cube = hlib.nodes.Node(cmds.polyCube(constructionHistory=False)[0])
        mesh = cube.getShape()
        self.assertIsInstance(mesh, hlib.nodes.Mesh)
        self.assertEqual((mesh.getNumVertices(), mesh.getNumEdges(), mesh.getNumPolygons()), (8, 12, 6))
        local_x = mesh.getPoints()[0].x
        cmds.setAttr(cube.getFullName() + '.translateX', 5)
        self.assertAlmostEqual(mesh.getPoints(ws=True)[0].x, local_x + 5)

        curve = hlib.nodes.Node(cmds.curve(degree=1, point=[(0, 0, 0), (3, 0, 0), (3, 4, 0)]))
        shape = curve.getShape()
        self.assertIsInstance(shape, hlib.nodes.NurbsCurve)
        self.assertEqual((shape.getNumCVs(), shape.getNumSpans(), shape.getDegree()), (3, 2, 1))
        self.assertAlmostEqual(shape.getLength(), 7)
        cmds.setAttr(curve.getFullName() + '.scaleX', 2)
        self.assertAlmostEqual(shape.getLength(), 7)
        cmds.setAttr(curve.getFullName() + '.translateY', 2)
        self.assertAlmostEqual(shape.getCvPositions(ws=True)[0].y, 2)
        self.assertAlmostEqual(shape.getCvPositions()[0].y, 0)
        with self.assertRaises(ValueError):
            shape.getLength(0)

    def test_mesh_normals_object_and_world_space(self):
        cube = hlib.nodes.Node(cmds.polyCube(constructionHistory=False)[0])
        mesh = cube.getShape()

        local_normals = mesh.getVertexNormals()
        self.assertEqual(len(local_normals), mesh.getNumVertices())
        for normal in local_normals:
            self.assertAlmostEqual(sum(c * c for c in (normal.x, normal.y, normal.z)) ** 0.5, 1.0, places=5)

        cmds.setAttr(cube.getFullName() + '.rotateY', 90)
        world_normals = mesh.getVertexNormals(ws=True)
        self.assertEqual(len(world_normals), mesh.getNumVertices())
        self.assertFalse(
            all(
                abs(a.x - b.x) < 1e-5 and abs(a.y - b.y) < 1e-5 and abs(a.z - b.z) < 1e-5
                for a, b in zip(local_normals, world_normals)
            )
        )

        weighted = mesh.getVertexNormals(angle_weighted=True)
        self.assertEqual(len(weighted), mesh.getNumVertices())

    def test_basic_constraints_targets_weights_and_registration(self):
        for kind in ('parent', 'point', 'orient', 'scale', 'aim'):
            with self.subTest(kind=kind):
                source, second, driven = self.getTransform(), self.getTransform(), self.getTransform()
                cmds.setAttr(source.getFullName() + '.translateX', 3)
                result = driven.addConstraint([source, second], kind, maintainOffset=True)
                expected = getattr(hlib.nodes, kind.title() + 'Constraint')
                self.assertIsInstance(result, expected)
                self.assertIsInstance(hlib.nodes.Node(result.getFullName()), expected)
                self.assertEqual([node.getUuid() for node in result.getTargets()], [source.getUuid(), second.getUuid()])
                self.assertEqual(result.getWeights(), [1.0, 1.0])
                self.assertEqual(len(result.getWeightAliases()), 2)
                result.getWeightPlugs()[0].set(0.25)
                self.assertEqual(result.getWeights(), [0.25, 1.0])

    def test_constraint_set_weight(self):
        source, second, driven = self.getTransform(), self.getTransform(), self.getTransform()
        result = driven.addConstraint([source, second], 'point', maintainOffset=True)
        self.assertEqual(result.getWeights(), [1.0, 1.0])

        returned = result.setWeight(0.5)
        self.assertIs(returned, result)
        self.assertEqual(result.getWeights(), [0.5, 0.5])

        result.setWeight(0.25, source)
        self.assertEqual(result.getWeights(), [0.25, 0.5])

        result.setWeight(0.75, source, second)
        self.assertEqual(result.getWeights(), [0.75, 0.75])

        unrelated = self.getTransform()
        with self.assertRaises(ValueError):
            result.setWeight(1.0, unrelated)

    def test_top_level_constraint_command(self):
        self.assertTrue(callable(hlib_cmds.addConstraint))
        self.assertIs(hlib.addConstraint, hlib_cmds.addConstraint)
        source = self.getTransform()
        target = self.getTransform()
        result = hlib_cmds.addConstraint(source, target, type='point')
        self.assertIsInstance(result, hlib.nodes.PointConstraint)
        self.assertEqual([node.getUuid() for node in result.getTargets()], [source.getUuid()])

        source_name = self.getTransform()
        target_name = self.getTransform()
        result = hlib_cmds.addConstraint(source_name.getFullName(), target_name.getFullName(), type='point')
        self.assertEqual([node.getUuid() for node in result.getTargets()], [source_name.getUuid()])

    def test_specialized_constraints(self):
        mesh = hlib.nodes.Node(cmds.polyPlane(constructionHistory=False)[0])
        for kind, expected in [('geometry', hlib.nodes.GeometryConstraint), ('normal', hlib.nodes.NormalConstraint),
                               ('pointOnPoly', hlib.nodes.PointOnPolyConstraint)]:
            with self.subTest(kind=kind):
                result = self.getTransform().addConstraint(mesh, kind)
                self.assertIsInstance(result, expected)
                self.assertEqual(len(result.getTargets()), 1)
                self.assertEqual(result.getWeights(), [1.0])
        curve = hlib.nodes.Node(cmds.curve(degree=1, point=[(0, 0, 0), (3, 0, 0)]))
        result = self.getTransform().addConstraint(curve, 'tangent')
        self.assertIsInstance(result, hlib.nodes.TangentConstraint)
        self.assertEqual(len(result.getTargets()), 1)
        self.assertEqual(result.getWeights(), [1.0])

        cmds.select(clear=True)
        start = cmds.joint(position=(0, 0, 0))
        cmds.joint(position=(2, 1, 0))
        end = cmds.joint(position=(4, 0, 0))
        handle = hlib.nodes.Node(cmds.ikHandle(startJoint=start, endEffector=end, solver='ikRPsolver')[0])
        self.assertIsInstance(handle, hlib.nodes.IkHandle)
        result = handle.addConstraint(self.getTransform(), 'poleVector')
        self.assertIsInstance(result, hlib.nodes.PoleVectorConstraint)
        self.assertEqual(len(result.getTargets()), 1)
        self.assertEqual(result.getWeights(), [1.0])

    def test_joint_chain_from_here_and_ik_handle_queries(self):
        cmds.select(clear=True)
        j1 = hlib.nodes.Joint(cmds.joint(position=(0, 0, 0)))
        j2 = hlib.nodes.Joint(cmds.joint(position=(2, 0, 0)))
        j3 = hlib.nodes.Joint(cmds.joint(position=(4, 0, 0)))
        branch = hlib.nodes.Joint(cmds.joint(position=(4, 2, 0)))
        j3.setParent(j2)
        branch.setParent(j2)

        chain = j1.getChainFromHere()
        self.assertEqual([joint.getFullName() for joint in chain], [j1.getFullName(), j2.getFullName()])

        chain_to_j3 = j1.getChainFromHere(j3)
        self.assertEqual(
            [joint.getFullName() for joint in chain_to_j3],
            [j1.getFullName(), j2.getFullName(), j3.getFullName()],
        )

        cmds.select(clear=True)
        unrelated = hlib.nodes.Joint(cmds.joint(position=(0, 5, 0)))
        with self.assertRaises(ValueError):
            j1.getChainFromHere(unrelated)

        self.assertEqual(j1.getIkHandles(), [])
        handle = hlib.nodes.Node(
            cmds.ikHandle(startJoint=j1.getFullName(), endEffector=j3.getFullName(), solver='ikRPsolver')[0]
        )
        self.assertIsInstance(handle, hlib.nodes.IkHandle)

        found_handles = j1.getIkHandles()
        self.assertEqual(len(found_handles), 1)
        self.assertEqual(found_handles[0].getFullName(), handle.getFullName())
        self.assertEqual(j2.getIkHandles(), [])

        self.assertEqual(handle.getEndJoint().getFullName(), j3.getFullName())
        joint_list = handle.getJoints()
        self.assertEqual([joint.getFullName() for joint in joint_list], [j1.getFullName(), j2.getFullName()])
        joint_list_with_tip = handle.getJoints(include_tip=True)
        self.assertEqual(
            [joint.getFullName() for joint in joint_list_with_tip],
            [j1.getFullName(), j2.getFullName(), j3.getFullName()],
        )

    def test_creation_undo_and_redo(self):
        if not cmds.undoInfo(query=True, state=True):
            self.skipTest('Undo is disabled in this Maya session')
        source, driven = self.getTransform(), self.getTransform()
        result = driven.addConstraint(source, 'pointConstraint')
        name = result.getFullName()
        cmds.undo()
        self.assertFalse(cmds.objExists(name))
        cmds.redo()
        self.assertIsInstance(hlib.nodes.Node(name), hlib.nodes.PointConstraint)

    def test_point_evaluation_and_parent_offset(self):
        source, driven = self.getTransform(), self.getTransform()
        cmds.setAttr(source.getFullName() + '.translateX', 4)
        driven.addConstraint(source.getFullName(), 'point')
        self.assertAlmostEqual(cmds.getAttr(driven.getFullName() + '.translateX'), 4)
        cmds.setAttr(source.getFullName() + '.translateX', 7)
        self.assertAlmostEqual(cmds.getAttr(driven.getFullName() + '.translateX'), 7)

        offset_driven = self.getTransform()
        cmds.setAttr(offset_driven.getFullName() + '.translateX', 10)
        offset_driven.addConstraint(source, maintainOffset=True)
        self.assertAlmostEqual(cmds.getAttr(offset_driven.getFullName() + '.translateX'), 10)
        cmds.setAttr(source.getFullName() + '.translateX', 9)
        self.assertAlmostEqual(cmds.getAttr(offset_driven.getFullName() + '.translateX'), 12)

    def test_invalid_requests_do_not_create_nodes(self):
        source, driven = self.getTransform(), self.getTransform()
        before = set(cmds.ls(long=True))
        invalid_requests = [
            ([], 'point', ValueError),
            (source, 'unknown', ValueError),
            ([object()], 'point', TypeError),
        ]
        for sources, kind, error in invalid_requests:
            with self.assertRaises(error):
                driven.addConstraint(sources, kind)
        self.assertEqual(before, set(cmds.ls(long=True)))

    def mirror_shapes(self):
        """非対称カーブと履歴付きメッシュを変換済みの親の下へ作成する。"""
        cube = hlib.nodes.Node(cmds.polyCube()[0])
        curve = hlib.nodes.Node(cmds.curve(degree=1, point=[(1, 2, 3), (4, 1, -2), (2, 5, 1)]))
        parent = self.getTransform()
        cmds.setAttr(parent.getFullName() + '.translate', 4, -2, 3)
        cmds.setAttr(parent.getFullName() + '.rotate', 23, 41, -17)
        cmds.setAttr(parent.getFullName() + '.scale', 2, 0.7, 1.3)
        cmds.parent(cube.getFullName(), curve.getFullName(), parent.getFullName(), relative=True)
        return [cube.getShape(), curve.getShape()]

    def positions(self, shape, ws=False):
        """API の内部距離単位で形状の全位置を返す。"""
        points = shape.getPoints(ws) if isinstance(shape, hlib.nodes.Mesh) else shape.getCvPositions(ws)
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
                    with self.subTest(shape=shape.getType(), ws=ws, axes=axes):
                        before = self.positions(shape, ws)
                        parent = shape.getParent()
                        matrix = cmds.xform(parent.getFullName(), query=True, matrix=True, worldSpace=True)
                        selected = {'xyz'.index(a) for a in axes.lower()}
                        expected = [tuple(-v if i in selected else v for i, v in enumerate(p)) for p in before]
                        self.assertIs(shape.mirror(axes, ws=ws), shape)
                        self.assert_positions(self.positions(shape, ws), expected)
                        self.assertEqual(cmds.xform(parent.getFullName(), query=True, matrix=True, worldSpace=True), matrix)

    def test_transform_mirror_all_shapes(self):
        parent = self.getTransform()
        cube = hlib.nodes.Node(cmds.polyCube(constructionHistory=False)[0])
        curve = hlib.nodes.Node(cmds.curve(degree=1, point=[(1, 2, 3), (4, 1, -2), (2, 5, 1)]))
        cmds.parent(cube.getShape().getFullName(), curve.getShape().getFullName(), parent.getFullName(), shape=True, relative=True)
        shapes = parent.getShapes()
        before = {shape.getFullName(): self.positions(shape, True) for shape in shapes}
        matrix = cmds.xform(parent.getFullName(), query=True, matrix=True, worldSpace=True)

        self.assertIs(parent.mirrorGeometry(axis='x', ws=True), parent)

        mirrored_shapes = parent.getShapes()
        self.assertEqual({shape.getFullName() for shape in mirrored_shapes}, set(before))
        for shape in mirrored_shapes:
            positions = before[shape.getFullName()]
            expected = [(-point[0], point[1], point[2]) for point in positions]
            self.assert_positions(self.positions(shape, True), expected)
        self.assertEqual(cmds.xform(parent.getFullName(), query=True, matrix=True, worldSpace=True), matrix)

    def test_mirror_custom_pivot_subset_and_distance_units(self):
        import maya.api.OpenMaya as om2
        previous = cmds.currentUnit(query=True, linear=True)
        try:
            cmds.currentUnit(linear='m')
            for ws in (False, True):
                for shape in self.mirror_shapes():
                    before = self.positions(shape, ws)
                    pivot = (1, 2, 3)
                    internal = pivot
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
            cmds.setAttr(shape.getParent().getFullName() + '.scaleX', 0)
            with self.assertRaises(ValueError):
                shape.mirror(ws=True)

    def test_mirror_periodic_curve(self):
        curve = hlib.nodes.Node(cmds.circle(constructionHistory=False)[0])
        shape = curve.getShape()
        before = self.positions(shape)
        form, degree, count = shape.getForm(), shape.getDegree(), shape.getNumCVs()
        shape.mirror('x')
        self.assert_positions(self.positions(shape), [(-x, y, z) for x, y, z in before])
        self.assertEqual((shape.getForm(), shape.getDegree(), shape.getNumCVs()), (form, degree, count))

    def test_nurbs_curve_get_collocated_cv_groups(self):
        curve = hlib.nodes.Node(
            cmds.curve(degree=1, point=[(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)])
        )
        shape = curve.getShape()
        self.assertEqual(shape.getCollocatedCVGroups(), [])

        cmds.move(1, 0, 0, shape.getFullName() + '.cv[2]', absolute=True)
        self.assertEqual(shape.getCollocatedCVGroups(), [[1, 2]])

        cmds.move(1, 0, 0, shape.getFullName() + '.cv[3]', absolute=True)
        self.assertEqual(shape.getCollocatedCVGroups(), [[1, 2, 3]])

        with self.assertRaises(ValueError):
            shape.getCollocatedCVGroups(tolerance=0)

    def test_component_collections_and_live_positions(self):
        for shape in self.mirror_shapes():
            is_mesh = isinstance(shape, hlib.nodes.Mesh)
            component_type = hlib.components.Vertex if is_mesh else hlib.components.CV
            collection_type = hlib.components.Vertices if is_mesh else hlib.components.CVs
            collection = shape.getVertices([2, 0, 2]) if is_mesh else shape.cvs([2, 0, 2])
            self.assertIsInstance(collection, collection_type)
            self.assertEqual(collection.indices, (2, 0))
            self.assertEqual(len(collection), 2)
            self.assertEqual([item.index for item in collection], [2, 0])
            self.assertIsInstance(collection[0], component_type)
            self.assertEqual(collection[-1].index, 0)
            self.assertIsInstance(collection[:1], collection_type)
            self.assertEqual(collection[:1].indices, (2,))
            self.assertEqual(collection[0].getPosition(), collection.getPosition()[0])
            single = shape.vertex(2) if is_mesh else shape.cv(2)
            before = single.getPosition()
            self.assertIs(collection.mirror('z'), collection)
            self.assert_positions([single.getPosition()], [(before[0], before[1], -before[2])])
            old_name = single.getFullName()
            shape.rename('renamedMirrorShape')
            self.assertNotEqual(single.getFullName(), old_name)
            self.assertTrue(cmds.objExists(single.getFullName()))
            other_type = hlib.components.CVs if is_mesh else hlib.components.Vertices
            with self.assertRaises(TypeError):
                other_type(shape, [])
            cmds.delete(shape.getFullName())
            with self.assertRaises(RuntimeError):
                single.getPosition()

    def test_xyz_and_mesh_components(self):
        mesh, curve = self.mirror_shapes()
        for item in (mesh.vertex(0), curve.cv(0)):
            before = item.getPosition()
            for axis in 'xyz':
                getattr(item, "setPosition" + axis.upper())(2.75)
                self.assertAlmostEqual(getattr(item, "getPosition" + axis.upper())(), 2.75)
                cmds.undo()
                self.assert_positions([item.getPosition()], [before])
            item.setPosition((3, 4, 5), ws=True)
            self.assert_positions([item.getPosition(ws=True)], [(3, 4, 5)])
            cmds.undo()
            with self.assertRaises(ValueError):
                item.setPosition((1, float('nan'), 3))
            self.assert_positions([item.getPosition()], [before])
        self.assertEqual(len(mesh.edges()), mesh.getNumEdges())
        self.assertEqual(len(mesh.faces()), mesh.getNumPolygons())
        self.assertEqual(len(mesh.edge(0).getVertices()), 2)
        self.assertEqual(len(mesh.face(0).getVertices()), 4)
        self.assertEqual(len(mesh.edges().getVertices()), mesh.getNumVertices())
        self.assertEqual(len(mesh.faces().getVertices()), mesh.getNumVertices())
        self.assertEqual(len(mesh.uvs()), mesh.getNumUVs())
        uv = mesh.uv(0)
        before = uv.getPosition()
        uv.setU(0.125)
        self.assertAlmostEqual(uv.getU(), 0.125)
        self.assertAlmostEqual(uv.getV(), before[1])
        cmds.undo()
        self.assertEqual(uv.getPosition(), before)
        uv.setV(0.375)
        self.assertAlmostEqual(uv.getV(), 0.375)
        cmds.undo()
        self.assertEqual(mesh.uvs([0]).getPosition(), [before])
        for collection in (hlib.components.Edges, hlib.components.Faces, hlib.components.UVs):
            with self.assertRaises(TypeError):
                collection(curve)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
