"""Shape 系(Mesh・NurbsCurve・Camera)とデフォーマー(Cluster・BlendShape)の照会の約束を固定する(担当C)。

対象: Mesh.getVertexAdjacency(ローカル/ワールド・孤立頂点)・getNumUVs、NurbsCurve.getNumSpans・getForm、
Shape.isIntermediateObject、Camera.getFocalLength・cameraFn、Cluster.getWeightedNode・getGeometry、
BlendShape.getGeometry。値は cmds・OpenMaya で独立に求めた値と比べる。
"""

import math
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import Camera, Cluster, Mesh, Node, NurbsCurve


class _NamespaceCase(unittest.TestCase):
    """専用の一時名前空間でノードを作り、Undo の設定・UI 単位・選択を元に戻す。"""

    def setUp(self):
        self.ns = "mlibSpecCGeo_" + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.ns)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        self.linear = cmds.currentUnit(query=True, linear=True)
        self.selection = cmds.ls(selection=True, long=True)

    def tearDown(self):
        cmds.currentUnit(linear=self.linear)
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_state)
        cmds.select(self.selection, replace=True) if self.selection else cmds.select(clear=True)

    def name(self, text):
        return self.ns + ":" + text


class VertexAdjacencyTest(_NamespaceCase):
    """getVertexAdjacency は頂点ごとの (隣接頂点, cm の距離) をエッジ順に返す。"""

    def setUp(self):
        super().setUp()
        self.plane = cmds.polyPlane(name=self.name("plane"), subdivisionsX=1, subdivisionsY=1,
                                    width=2, height=2, constructionHistory=False)[0]
        cmds.setAttr(self.plane + ".scale", 3, 3, 3)
        self.mesh = Node(self.plane).getShape()

    def expected(self, world):
        """MFnMesh のエッジと頂点座標から独立に求める。"""
        space = om2.MSpace.kWorld if world else om2.MSpace.kObject
        fn = om2.MFnMesh(om2.MSelectionList().add(self.plane).getDagPath(0))
        points = fn.getPoints(space)
        result = [[] for _ in points]
        for edge in range(fn.numEdges):
            first, second = fn.getEdgeVertices(edge)
            length = points[first].distanceTo(points[second])
            result[first].append((second, length))
            result[second].append((first, length))
        return result

    def assertAdjacency(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for actual_row, expected_row in zip(actual, expected):
            self.assertEqual([index for index, _ in actual_row], [index for index, _ in expected_row])
            for (_, a), (_, e) in zip(actual_row, expected_row):
                self.assertAlmostEqual(a, e, places=9)

    def test_local_and_world(self):
        """ローカルは object 空間の長さ、ws=True はワールド空間の長さ。"""
        self.assertIsInstance(self.mesh, Mesh)
        local = self.mesh.getVertexAdjacency()
        self.assertAdjacency(local, self.expected(False))
        self.assertAlmostEqual(local[0][0][1], 2.0)
        world = self.mesh.getVertexAdjacency(ws=True)
        self.assertAdjacency(world, self.expected(True))
        self.assertAlmostEqual(world[0][0][1], 6.0)
        self.assertAdjacency(self.mesh.getVertexAdjacency(worldSpace=True), world)

    def test_units_are_cm(self):
        """UI の距離単位を mm にしても cm の値を返す。"""
        cmds.currentUnit(linear="mm")
        self.assertAlmostEqual(self.mesh.getVertexAdjacency()[0][0][1], 2.0)

    def test_isolated_vertex_is_empty(self):
        """どのエッジにも使われない頂点は空リスト。並びはエッジ番号順。"""
        fn = om2.MFnMesh()
        points = [om2.MPoint(0, 0, 0), om2.MPoint(1, 0, 0), om2.MPoint(1, 0, 1), om2.MPoint(0, 0, 1),
                  om2.MPoint(9, 9, 9)]
        created = fn.create(points, [4], [0, 1, 2, 3])
        transform = cmds.rename(om2.MFnDagNode(created).fullPathName(), self.name("isolated"))
        adjacency = Node(transform).getShape().getVertexAdjacency()
        self.assertEqual(len(adjacency), 5)
        self.assertEqual(adjacency[4], [])
        self.assertEqual(adjacency[3], [(2, 1.0), (0, 1.0)])

    def test_argument_errors(self):
        """長短名の同時指定は TypeError、bool 以外は ValueError。"""
        with self.assertRaisesRegex(TypeError, "Specify only one of 'worldSpace' and 'ws'"):
            self.mesh.getVertexAdjacency(True, ws=True)
        with self.assertRaises(ValueError):
            self.mesh.getVertexAdjacency(ws=1)

    def test_num_uvs_is_current_set(self):
        """getNumUVs は現在の UV セットの数。空のセットへ切り替えると0。"""
        self.assertEqual(self.mesh.getNumUVs(), cmds.polyEvaluate(self.plane, uvcoord=True))
        cmds.polyUVSet(self.plane, create=True, uvSet="mlibEmpty")
        cmds.polyUVSet(self.plane, currentUVSet=True, uvSet="mlibEmpty")
        self.assertEqual(self.mesh.getNumUVs(), 0)


class CurveTest(_NamespaceCase):
    """NurbsCurve の数の照会。"""

    def test_spans_and_form(self):
        """getNumSpans は MFnNurbsCurve.numSpans、getForm は kOpen・kPeriodic の番号。"""
        curve = cmds.curve(degree=3, point=[(0, 0, 0), (1, 1, 0), (2, 0, 0), (3, 1, 0), (4, 0, 0)],
                           name=self.name("open"))
        shape = Node(curve).getShape()
        self.assertIsInstance(shape, NurbsCurve)
        self.assertEqual(shape.getNumSpans(), 2)
        self.assertEqual(shape.getNumSpans(), cmds.getAttr(shape.getFullName() + ".spans"))
        self.assertEqual(shape.getForm(), om2.MFnNurbsCurve.kOpen)
        circle = Node(cmds.circle(name=self.name("circle"), sections=8, constructionHistory=False)[0]).getShape()
        self.assertEqual(circle.getNumSpans(), 8)
        self.assertEqual(circle.getForm(), om2.MFnNurbsCurve.kPeriodic)


class IntermediateCameraTest(_NamespaceCase):
    """Shape.isIntermediateObject と Camera。"""

    def test_intermediate(self):
        """デフォーマーで作られる Orig は中間オブジェクト、表示 Shape は違う。"""
        cube = cmds.polyCube(name=self.name("cube"))[0]
        cmds.cluster(cube)
        shapes = Node(cube).getShapes(intermediates=True)
        flags = [shape.isIntermediateObject() for shape in shapes]
        self.assertEqual(flags, [cmds.getAttr(shape.getFullName() + ".intermediateObject") for shape in shapes])
        self.assertEqual(sorted(flags), [False, True])

    def test_camera(self):
        """getFocalLength は mm の焦点距離で、UI の距離単位に左右されない。"""
        transform, shape = cmds.camera(name=self.name("cam"), focalLength=50)
        camera = Node(shape)
        self.assertIsInstance(camera, Camera)
        self.assertIsInstance(camera.cameraFn(), om2.MFnCamera)
        self.assertEqual(camera.getFocalLength(), 50.0)
        cmds.currentUnit(linear="mm")
        self.assertEqual(camera.getFocalLength(), 50.0)
        self.assertEqual(camera.getFocalLength(), cmds.getAttr(shape + ".focalLength"))
        self.assertIsNot(type(Node(transform)), Camera)


class DeformerTest(_NamespaceCase):
    """Cluster と BlendShape の照会。"""

    def test_cluster(self):
        """getWeightedNode は matrix の入力元のハンドル、切断すると None。getGeometry は出力 Shape。"""
        cube = cmds.polyCube(name=self.name("clusterCube"))[0]
        handle = cmds.cluster(cube)[1]
        cluster = cmds.listConnections(handle + ".worldMatrix[0]", type="cluster")[0]
        node = Node(cluster)
        self.assertIsInstance(node, Cluster)
        self.assertEqual(node.getWeightedNode(), Node(handle))
        self.assertEqual(node.getGeometry(), [Node(cube).getShape()])
        cmds.disconnectAttr(handle + ".worldMatrix[0]", cluster + ".matrix")
        self.assertIsNone(node.getWeightedNode())

    def test_blend_shape_geometry(self):
        """getGeometry は出力のベース Shape。出力の無い blendShape は空リスト。"""
        target = cmds.polyCube(name=self.name("target"))[0]
        base = cmds.polyCube(name=self.name("base"))[0]
        blend = cmds.blendShape(target, base, name=self.name("blend"))[0]
        self.assertEqual(Node(blend).getGeometry(), [Node(base).getShape()])
        empty = cmds.createNode("blendShape", name=self.name("emptyBlend"), skipSelect=True)
        self.assertEqual(Node(empty).getGeometry(), [])


if __name__ == "__main__":
    unittest.main()
