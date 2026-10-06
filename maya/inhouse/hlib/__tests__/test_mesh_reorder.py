"""UVからの頂点番号合わせと形状維持・Undoを実Mayaで検証する。"""

import sys
import unittest
from unittest import mock

import hlib
import maya.api.OpenMaya as om2
import maya.cmds as cmds


class MeshReorderTest(unittest.TestCase):
    def setUp(self):
        self.before = set(cmds.ls(long=True))
        cmds.undoInfo(state=True)
        self.reference = hlib.getNode(cmds.polyCube(ch=False)[0]).getShape()
        source = self.reference.meshFn()
        self.permutation = [3, 6, 0, 7, 1, 5, 2, 4]
        points = source.getPoints()
        target_points = om2.MPointArray(points)
        for old, new in enumerate(self.permutation):
            point = points[old]
            target_points[new] = om2.MPoint(point.x * 2, point.y + old * 0.2, point.z)
        counts, connects = source.getVertices()
        fn = om2.MFnMesh()
        transform = fn.create(target_points, counts, [self.permutation[v] for v in connects])
        self.target = hlib.getNode(om2.MFnDagNode(transform).fullPathName()).getShape()
        fn = self.target.meshFn()
        fn.setUVs(*source.getUVs("map1"), uvSet="map1")
        fn.assignUVs(*source.getAssignedUVs("map1"), uvSet="map1")

    def tearDown(self):
        for name in sorted(set(cmds.ls(long=True)) - self.before, key=len, reverse=True):
            if cmds.objExists(name):
                cmds.delete(name)

    def snapshot(self):
        fn = self.target.meshFn()
        return ([tuple(p) for p in fn.getPoints()], tuple(fn.getVertices()[1]),
                tuple(fn.getUVs()[0]), tuple(fn.getAssignedUVs()[1]))

    def set_matching_positions(self, offset=0):
        points = self.reference.meshFn().getPoints()
        for source, target in enumerate(self.permutation):
            p = self.target.meshFn().getPoint(target)
            points[source] = om2.MPoint(p.x - offset, p.y, p.z)
        self.reference.meshFn().setPoints(points)

    def test_position_preserves_different_uvs_and_undo(self):
        self.set_matching_positions()
        fn = self.target.meshFn()
        u, v = fn.getUVs()
        fn.setUVs([x * 2 + 1 for x in u], [y * 3 - 1 for y in v])
        before = self.snapshot()
        self.assertIs(self.target.reorderVertices(self.reference, match="position", uv_set=None), self.target)
        after = self.snapshot()
        self.assertEqual(after[0], [before[0][i] for i in self.permutation])
        self.assertEqual(after[2:], before[2:])
        cmds.undo()
        self.assertEqual(self.snapshot(), before)
        cmds.redo()
        self.assertEqual(self.snapshot(), after)

    def test_position_world_space_and_alias(self):
        self.set_matching_positions(offset=-5)
        transform = cmds.listRelatives(self.target.getFullName(), parent=True, fullPath=True)[0]
        cmds.setAttr(transform + ".translateX", 5)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.target.reorderVertices(self.reference, match="position")
        previous = cmds.undoInfo(q=True, undoName=True)
        self.target.reorderVertices(self.reference, match="position", ws=True, fast=True)
        self.assertEqual(self.snapshot()[0], [before[0][i] for i in self.permutation])
        self.assertEqual(self.snapshot()[2:], before[2:])
        self.assertEqual(cmds.undoInfo(q=True, undoName=True), previous)
        self.assertEqual(cmds.getAttr(transform + ".translateX"), 5)

    def test_position_tolerance_and_ambiguity(self):
        self.set_matching_positions(offset=0.125)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.target.reorderVertices(self.reference, match="position", tolerance=0.1)
        self.assertEqual(self.snapshot(), before)
        self.target.reorderVertices(self.reference, match="position", tolerance=0.13)
        self.assertEqual(self.snapshot()[0], [before[0][i] for i in self.permutation])
        for mesh in (self.reference, self.target):
            mesh.meshFn().setPoints([om2.MPoint(0, 0, 0)] * 8)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.target.reorderVertices(self.reference, match="position", tolerance=0)
        self.assertEqual(self.snapshot(), before)

    def test_match_flags_validation(self):
        before = self.snapshot()
        for kwargs in ({"match": "nearest"}, {"match": True}, {"worldSpace": 1},
                       {"ws": True, "worldSpace": True}):
            with self.assertRaises((ValueError, TypeError)):
                self.target.reorderVertices(self.reference, **kwargs)
        self.assertEqual(self.snapshot(), before)

    def test_reorder_preserves_geometry_uv_undo_redo(self):
        before = self.snapshot()
        expected = [before[0][i] for i in self.permutation]
        self.assertIs(self.target.reorderVertices(self.reference), self.target)
        after = self.snapshot()
        self.assertEqual(after[0], expected)
        self.assertEqual(after[1], tuple(self.reference.meshFn().getVertices()[1]))
        self.assertEqual(after[2:], before[2:])
        cmds.undo()
        self.assertEqual(self.snapshot(), before)
        cmds.redo()
        self.assertEqual(self.snapshot(), after)

    def test_fast_and_idempotent(self):
        previous = cmds.undoInfo(q=True, undoName=True)
        with mock.patch.object(cmds, "connectAttr", side_effect=AssertionError), mock.patch.object(cmds, "createNode", side_effect=AssertionError):
            self.target.reorderVertices(self.reference, fast=True)
        self.assertEqual(cmds.undoInfo(q=True, undoName=True), previous)
        before = self.snapshot()
        self.target.reorderVertices(self.reference)
        self.assertEqual(self.snapshot(), before)

    def test_failure_rolls_back_without_temporary_nodes(self):
        before = self.snapshot()
        nodes = set(cmds.ls(long=True))
        with mock.patch.object(cmds, "connectAttr", side_effect=RuntimeError("injected failure")):
            with self.assertRaises(RuntimeError):
                self.target.reorderVertices(self.reference)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(set(cmds.ls(long=True)), nodes)

    def test_named_uv_set(self):
        for mesh in (self.reference, self.target):
            cmds.polyUVSet(mesh.getFullName(), rename=True, uvSet="map1", newUVSet="matchUV")
        self.target.reorderVertices(self.reference, uv_set="matchUV")
        self.assertEqual(self.target.meshFn().getUVSetNames(), ("matchUV",))

    def test_validation_before_changes(self):
        before = self.snapshot()
        for tolerance in (-1, True, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.target.reorderVertices(self.reference, tolerance=tolerance)
        with self.assertRaises(ValueError):
            self.target.reorderVertices(self.reference, uv_set="missing")
        self.assertEqual(self.snapshot(), before)
        fn = self.target.meshFn()
        u, v = fn.getUVs()
        fn.setUVs([0] * len(u), [0] * len(v))
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.target.reorderVertices(self.reference)
        self.assertEqual(self.snapshot(), before)

    def test_history_rejected(self):
        source = hlib.getNode(cmds.polyCube(ch=True)[0]).getShape()
        with self.assertRaises(NotImplementedError):
            source.reorderVertices(self.target)

    def test_tolerance_and_face_topology(self):
        fn = self.target.meshFn()
        u, v = fn.getUVs()
        fn.setUVs([value + 0.00001 for value in u], v)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.target.reorderVertices(self.reference, tolerance=0)
        self.assertEqual(self.snapshot(), before)
        self.target.reorderVertices(self.reference, tolerance=0.0001)
        self.assertEqual(self.snapshot()[0], [before[0][i] for i in self.permutation])

    def test_locked_and_instanced_rejected(self):
        before = self.snapshot()
        cmds.setAttr(self.target.getFullName() + ".outMesh", lock=True)
        with self.assertRaises(RuntimeError):
            self.target.reorderVertices(self.reference)
        cmds.setAttr(self.target.getFullName() + ".outMesh", lock=False)
        self.assertEqual(self.snapshot(), before)
        cmds.instance(cmds.listRelatives(self.target.getFullName(), parent=True, fullPath=True)[0])
        with self.assertRaises(NotImplementedError):
            self.target.reorderVertices(self.reference)

    def test_materials_normals_multiple_uvs(self):
        name = self.target.getFullName()
        cmds.sets(name + ".f[0:2]", e=True, forceElement="initialShadingGroup")
        cmds.polyUVSet(name, copy=True, uvSet="map1", newUVSet="secondUV")
        cmds.polyUVSet(name, currentUVSet=True, uvSet="secondUV")
        fn = self.target.meshFn()
        vertex = fn.getPolygonVertices(0)[0]
        fn.setFaceVertexNormal(om2.MVector(1, 0, 0), 0, vertex)
        fn.lockFaceVertexNormals([0], [vertex])
        before = self.snapshot()
        uv = (tuple(fn.getUVs("secondUV")[0]), tuple(fn.getAssignedUVs("secondUV")[1]))
        materials = self.target.getFaceShadingEngines()
        normals = [tuple(n) for i in range(fn.numPolygons) for n in fn.getFaceVertexNormals(i)]
        self.target.reorderVertices(self.reference)
        fn = self.target.meshFn()
        self.assertEqual(self.snapshot()[0], [before[0][i] for i in self.permutation])
        self.assertEqual(self.target.getFaceShadingEngines(), materials)
        self.assertEqual((tuple(fn.getUVs("secondUV")[0]), tuple(fn.getAssignedUVs("secondUV")[1])), uv)
        self.assertEqual(fn.currentUVSetName(), "secondUV")
        after_normals = [tuple(n) for i in range(fn.numPolygons) for n in fn.getFaceVertexNormals(i)]
        for a, b in zip(normals, after_normals):
            for x, y in zip(a, b):
                self.assertAlmostEqual(x, y, places=6)
        cmds.undo()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.target.getFaceShadingEngines(), materials)
        cmds.redo()
        self.assertEqual(self.target.getFaceShadingEngines(), materials)
        self.assertEqual(self.target.meshFn().currentUVSetName(), "secondUV")

    def test_fast_with_tweaks_materials_and_uvs(self):
        name = self.target.getFullName()
        cmds.sets(name + ".f[0:2]", e=True, forceElement="initialShadingGroup")
        cmds.polyUVSet(name, copy=True, uvSet="map1", newUVSet="secondUV")
        cmds.polyUVSet(name, currentUVSet=True, uvSet="secondUV")
        cmds.move(0.3, 0, 0, name + ".vtx[0]", r=True)
        before = self.snapshot()
        materials = self.target.getFaceShadingEngines()
        with self.assertRaises(NotImplementedError):
            self.target.reorderVertices(self.reference)
        self.assertEqual(self.snapshot(), before)
        self.target.reorderVertices(self.reference, fast=True)
        self.assertEqual(self.snapshot()[0], [before[0][i] for i in self.permutation])
        self.assertEqual(self.target.getFaceShadingEngines(), materials)
        self.assertEqual(self.target.meshFn().getUVSetNames(), ("map1", "secondUV"))
        self.assertEqual(self.target.meshFn().currentUVSetName(), "secondUV")

    def test_ambiguous_uv_rejected(self):
        for mesh in (self.reference, self.target):
            fn = mesh.meshFn()
            u, v = fn.getUVs()
            fn.setUVs([0] * len(u), [0] * len(v))
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.target.reorderVertices(self.reference)
        self.assertEqual(self.snapshot(), before)

    def test_downstream_and_color_data_rejected(self):
        destination = cmds.createNode("mesh")
        cmds.connectAttr(self.target.getFullName() + ".outMesh", destination + ".inMesh")
        before = self.snapshot()
        with self.assertRaises(NotImplementedError):
            self.target.reorderVertices(self.reference)
        self.assertEqual(self.snapshot(), before)
        cmds.disconnectAttr(self.target.getFullName() + ".outMesh", destination + ".inMesh")
        cmds.polyColorSet(self.target.getFullName(), create=True, colorSet="colors")
        with self.assertRaises(NotImplementedError):
            self.target.reorderVertices(self.reference)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
