"""10.1.0 で足したスキンのウェイト編集向けの照会・編集の契約を固定する。

- GeometryFilter: デフォーマーのウェイトの読み書き・既定値1・Undo 1回・fast は Undo なし・skinCluster は TypeError。
- SkinCluster: ロック、行での読み書き、深い順の一括解除、位置付きの書き出し/読み込み、設定の名前。
- Joint: ロック、ボーンの線分。
- Mesh: シェル・三角形・左右の対応・最も近い頂点。Vertices.grow/shrink、Edges.getLoop/getRing は cmds と突き合わせる。
- Selection.getSoftSelection、mlib.bakeDeformer。
"""

import math
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common import Selection
from mlib.nodes import GeometryFilter, Joint, SkinCluster
from support.specCase import NamespaceCase


def _distance(first, second):
    """2点の距離(Python 3.7 には math.dist が無いため)。"""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


class _SkinCase(NamespaceCase):
    """root→mid→tip の chain と、それにバインドした円柱を作る。"""

    def chain(self):
        cmds.select(clear=True)
        self.root = cmds.joint(name=self.name("root"), position=(0, -2, 0))
        self.mid = cmds.joint(name=self.name("mid"), position=(0, 0, 0))
        self.tip = cmds.joint(name=self.name("tip"), position=(0, 2, 0))
        cmds.select(clear=True)
        return [self.root, self.mid, self.tip]

    def skinned(self, max_influences=3):
        joints = self.chain()
        self.mesh = cmds.polyCylinder(name=self.name("geo"), height=4, subdivisionsHeight=8)[0]
        self.skin = SkinCluster(cmds.skinCluster(joints, self.mesh, toSelectedBones=True,
                                                 maximumInfluences=max_influences)[0])
        cmds.select(clear=True)
        return self.skin

    def raw(self, skin=None):
        skin = skin or self.skin
        return [round(value, 6) for value in skin.getWeights([self.root, self.mid, self.tip])]


class GeometryFilterTest(_SkinCase):

    def test_classes_derive_from_geometry_filter(self):
        """SkinCluster・Cluster・BlendShape と生成クラス(deltaMush)は GeometryFilter の派生。"""
        skin = self.skinned()
        cube = cmds.polyCube(name=self.name("cube"))[0]
        cluster = mlib.getNode(cmds.cluster(cube, name=self.name("cl"))[0])
        mush = mlib.getNode(cmds.deltaMush(self.mesh, name=self.name("mush"))[0])
        for node in (skin, cluster, mush):
            with self.subTest(node=node.getType()):
                self.assertIsInstance(node, GeometryFilter)
        self.assertIs(type(cluster), mlib.Cluster)

    def test_deformer_weights_default_and_write(self):
        """値の無い頂点は1、書いた値を読み戻し、通常は Undo 1 回で戻る。"""
        cube = cmds.polyCube(name=self.name("cube"))[0]
        cluster = mlib.getNode(cmds.cluster(cube, name=self.name("cl"))[0])
        self.assertEqual(cluster.getDeformerWeights(), [1.0] * 8)
        cmds.flushUndo()
        self.assertIs(cluster.setDeformerWeights([0.25, 0.5], vertices=[2, 3]), cluster)
        values = cluster.getDeformerWeights()
        self.assertEqual(values[2:4], [0.25, 0.5])
        self.assertEqual(values[0], 1.0)
        cluster.setDeformerWeights([0.1] * 8)
        self.assertTrue(all(abs(value - 0.1) < 1e-6 for value in cluster.getDeformerWeights()))
        cmds.undo()
        cmds.undo()
        self.assertEqual(cluster.getDeformerWeights(), [1.0] * 8)

    def test_deformer_weights_fast(self):
        """fast=True は同じ値を Undo なしで書く。"""
        cube = cmds.polyCube(name=self.name("cube"))[0]
        cluster = mlib.getNode(cmds.cluster(cube, name=self.name("cl"))[0])
        cmds.flushUndo()
        cluster.setDeformerWeights([0.0, 0.75], vertices=[0, 7], fast=True)
        self.assertEqual(cluster.getDeformerWeights()[0], 0.0)
        self.assertAlmostEqual(cluster.getDeformerWeights()[7], 0.75, places=6)
        self.assertFalse(cmds.undoInfo(query=True, undoName=True))

    def test_deformer_weights_errors(self):
        """不正な入力は変更前に型どおりの例外。"""
        skin = self.skinned()
        cube = cmds.polyCube(name=self.name("cube"))[0]
        cluster = mlib.getNode(cmds.cluster(cube, name=self.name("cl"))[0])
        cases = (
            (TypeError, lambda: skin.getDeformerWeights()),
            (TypeError, lambda: cluster.getDeformerWeights(geometryIndex=True)),
            (IndexError, lambda: cluster.getDeformerWeights(geometryIndex=5)),
            (ValueError, lambda: cluster.setDeformerWeights([1.0])),
            (ValueError, lambda: cluster.setDeformerWeights([1.0, 1.0], vertices=[1, 1])),
            (ValueError, lambda: cluster.setDeformerWeights([math.nan], vertices=[0])),
            (IndexError, lambda: cluster.setDeformerWeights([1.0], vertices=[8])),
            (TypeError, lambda: cluster.setDeformerWeights(["a"], vertices=[0])),
            (TypeError, lambda: cluster.setDeformerWeights([1.0], vertices=[0], fast=1)),
        )
        for error, call in cases:
            with self.subTest(error=error.__name__):
                self.assertRaises(error, call)
        self.assertEqual(cluster.getDeformerWeights(), [1.0] * 8)


class SkinLockTest(_SkinCase):

    def test_lock_roundtrip(self):
        """SkinCluster と Joint のどちらからもロックを読み書きでき、cmds の値と一致する。"""
        skin = self.skinned()
        self.assertEqual(skin.getLockedInfluences(), [])
        self.assertIs(skin.setInfluencesLocked([self.root, self.tip]), skin)
        self.assertEqual([node.getName() for node in skin.getLockedInfluences()],
                         [mlib.getNode(self.root).getName(), mlib.getNode(self.tip).getName()])
        self.assertTrue(cmds.getAttr(self.root + ".liw"))
        mid = Joint(self.mid)
        self.assertFalse(mid.isInfluenceLocked())
        self.assertIs(mid.setInfluenceLocked(), mid)
        self.assertTrue(cmds.getAttr(self.mid + ".liw"))
        skin.setInfluencesLocked([self.root, self.mid, self.tip], state=False)
        self.assertEqual(skin.getLockedInfluences(), [])

    def test_lock_errors_and_undo(self):
        """未登録・bool 以外は例外。バインドしていない joint は isInfluenceLocked が False で set は RuntimeError。"""
        skin = self.skinned()
        cmds.select(clear=True)
        loose = Joint(cmds.joint(name=self.name("loose")))
        self.assertFalse(loose.isInfluenceLocked())
        self.assertRaises(RuntimeError, loose.setInfluenceLocked)
        self.assertRaises(ValueError, skin.setInfluencesLocked, [loose])
        self.assertRaises(TypeError, skin.setInfluencesLocked, [self.root], state=1)
        cmds.flushUndo()
        skin.setInfluencesLocked([self.root, self.mid])
        cmds.undo()
        self.assertFalse(cmds.getAttr(self.root + ".liw") or cmds.getAttr(self.mid + ".liw"))


class SkinRowsTest(_SkinCase):

    def test_rows_match_flat(self):
        """rows=True は平坦な値を頂点ごとに分けたもの。指定頂点も同じ。"""
        skin = self.skinned()
        joints = [self.root, self.mid, self.tip]
        flat = list(skin.getWeights(joints))
        rows = skin.getWeights(joints, rows=True)
        self.assertEqual(len(rows), cmds.polyEvaluate(self.mesh, vertex=True))
        self.assertEqual([value for row in rows for value in row], flat)
        part = skin.getWeights(joints, vertices=[5, 2], rows=True)
        self.assertEqual(part, [rows[5], rows[2]])

    def test_set_rows(self):
        """rows=True で書いた行を読み戻す。行の長さ違い・broadcast 併用は ValueError。"""
        skin = self.skinned()
        joints = [self.root, self.mid, self.tip]
        for fast in (False, True):
            with self.subTest(fast=fast):
                skin.setWeights(joints, [[0.5, 0.5, 0.0], [0.0, 0.25, 0.75]], vertices=[0, 1], rows=True, fast=fast)
                self.assertEqual(skin.getWeights(joints, vertices=[0, 1], rows=True),
                                 [[0.5, 0.5, 0.0], [0.0, 0.25, 0.75]])
        self.assertRaises(ValueError, skin.setWeights, joints, [[1.0, 0.0]], vertices=[0], rows=True)
        self.assertRaises(ValueError, skin.setWeights, joints, [[1.0, 0.0, 0.0]], vertices=[0], rows=True,
                          broadcast=True)
        self.assertRaises(TypeError, skin.setWeights, joints, [1.0, 0.0, 0.0], vertices=[0], rows=True)
        self.assertRaises(TypeError, skin.getWeights, joints, rows=1)


class SkinRemoveInfluencesTest(_SkinCase):

    def test_parent_and_child_move_to_remaining_ancestor(self):
        """mid と tip を同時に外すと、両方のウェイトが root へ集まる(Undo 1回で戻る)。"""
        skin = self.skinned()
        before = skin.getWeights([self.root, self.mid, self.tip], rows=True)
        cmds.flushUndo()
        self.assertIs(skin.removeInfluences([self.mid, self.tip]), skin)
        self.assertEqual([node.getName() for node in skin.getInfluences()], [mlib.getNode(self.root).getName()])
        for value in skin.getWeights([self.root]):
            self.assertAlmostEqual(value, 1.0, places=6)
        cmds.undo()
        self.assertEqual(len(skin.getInfluences()), 3)
        after = skin.getWeights([self.root, self.mid, self.tip], rows=True)
        for row, original in zip(after, before):
            for value, expected in zip(row, original):
                self.assertAlmostEqual(value, expected, places=6)

    def test_errors_before_change(self):
        """残る祖先が無い・全部・未登録・重複は変更前に ValueError。"""
        skin = self.skinned()
        before = self.raw()
        cases = (
            lambda: skin.removeInfluences([self.root]),
            lambda: skin.removeInfluences([self.root, self.mid, self.tip], transferToParent=False),
            lambda: skin.removeInfluences([self.name("missing_joint")]),
            lambda: skin.removeInfluences([self.mid, self.mid]),
        )
        for index, call in enumerate(cases):
            with self.subTest(case=index):
                self.assertRaises((ValueError, RuntimeError), call)
        self.assertEqual(len(skin.getInfluences()), 3)
        self.assertEqual(self.raw(), before)
        self.assertRaises(TypeError, skin.removeInfluences, [self.tip], transferToParent=1)

    def test_without_transfer_root_allowed(self):
        """transferToParent=False なら root も外せる。"""
        skin = self.skinned()
        skin.removeInfluences([self.root], transferToParent=False)
        self.assertEqual(len(skin.getInfluences()), 2)


class SkinSettingsTest(_SkinCase):

    def test_settings_by_name(self):
        """名前で読み書きし、cmds の値と一致する。不正な名前は ValueError、型違いは TypeError。"""
        skin = self.skinned()
        self.assertEqual(skin.getSkinningMethod(), "classicLinear")
        self.assertIs(skin.setSkinningMethod("dualQuaternion"), skin)
        self.assertEqual(cmds.getAttr(skin.getFullName() + ".skinningMethod"), 1)
        self.assertEqual(skin.getNormalizeMode(), "interactive")
        skin.setNormalizeMode("post")
        self.assertEqual(cmds.getAttr(skin.getFullName() + ".normalizeWeights"), 2)
        self.assertEqual(skin.isMaintainingMaxInfluences(),
                         bool(cmds.getAttr(skin.getFullName() + ".maintainMaxInfluences")))
        self.assertRaises(ValueError, skin.setSkinningMethod, "linear")
        self.assertRaises(TypeError, skin.setNormalizeMode, 1)
        cmds.flushUndo()
        skin.setSkinningMethod("weightBlended")
        cmds.undo()
        self.assertEqual(skin.getSkinningMethod(), "dualQuaternion")


class JointSegmentTest(_SkinCase):

    def test_bone_segments(self):
        """子までの線分。子が無ければ同じ点の1組。ローカル空間は親側の空間。"""
        self.chain()
        segments = Joint(self.mid).getBoneSegments()
        self.assertEqual(len(segments), 1)
        start, end = segments[0]
        self.assertAlmostEqual(start.y, 0.0)
        self.assertAlmostEqual(end.y, 2.0)
        tip_start, tip_end = Joint(self.tip).getBoneSegments()[0]
        self.assertAlmostEqual((tip_end - tip_start).length(), 0.0)
        local = Joint(self.mid).getBoneSegments(worldSpace=False)[0]
        self.assertAlmostEqual(local[0].y, 2.0)
        self.assertAlmostEqual(local[1].y, 4.0)


class MeshQueryTest(_SkinCase):

    def test_shells_and_triangles(self):
        """シェルの数は polyEvaluate(shell)、三角形の数は polyEvaluate(triangle) と一致する。"""
        first = cmds.polyCube(name=self.name("a"))[0]
        second = cmds.polyCube(name=self.name("b"))[0]
        cmds.move(3, 0, 0, second)
        combined = cmds.polyUnite(first, second, name=self.name("c"), constructionHistory=False)[0]
        mesh = mlib.getNode(combined).getShape()
        shells = mesh.getShells()
        self.assertEqual(len(shells), cmds.polyEvaluate(combined, shell=True))
        self.assertEqual(sorted(index for shell in shells for index in shell.indices), list(range(16)))
        triangles = mesh.getTriangles()
        self.assertEqual(len(triangles), cmds.polyEvaluate(combined, triangle=True))
        self.assertTrue(all(len(set(triangle)) == 3 for triangle in triangles))

    def test_mirror_map(self):
        """対称な形では全頂点が対応し、対応は互いに逆。軸の書き方は x / YZ / 0 が同じ。"""
        plane = cmds.polyPlane(name=self.name("p"), subdivisionsX=4, subdivisionsY=2)[0]
        mesh = mlib.getNode(plane).getShape()
        mapping = mesh.getMirrorVertexMap()
        self.assertEqual(len(mapping), mesh.getNumVertices())
        for index, other in mapping.items():
            self.assertEqual(mapping[other], index)
        self.assertEqual(mesh.getMirrorVertexMap("YZ"), mapping)
        self.assertEqual(mesh.getMirrorVertexMap(0), mapping)
        cmds.move(0.3, 0, 0, plane)
        self.assertEqual(mesh.getMirrorVertexMap(), mapping)
        self.assertNotEqual(mesh.getMirrorVertexMap(worldSpace=True), mapping)
        self.assertRaises(ValueError, mesh.getMirrorVertexMap, tolerance=0)
        self.assertRaises(ValueError, mesh.getMirrorVertexMap, axis="w")

    def test_closest_vertex_matches_brute_force(self):
        """格子探索の結果は全頂点との距離の比較と一致する。"""
        sphere = cmds.polySphere(name=self.name("s"), subdivisionsX=12, subdivisionsY=8)[0]
        mesh = mlib.getNode(sphere).getShape()
        points = [(point.x, point.y, point.z) for point in mesh.getPoints()]
        queries = [(0.3, 0.9, -0.2), (5.0, 0.0, 0.0), (-0.1, -0.7, 0.6), (0.0, 0.0, 0.0)]
        found = mesh.getClosestVertices(queries)
        for query, index in zip(queries, found):
            best = min(_distance(point, query) for point in points)
            self.assertAlmostEqual(_distance(points[index], query), best)
        self.assertEqual(mesh.getClosestVertex(queries[0]).index, found[0])
        self.assertRaises(ValueError, mesh.getClosestVertices, [(math.inf, 0, 0)])


class ComponentTopologyTest(_SkinCase):

    def test_grow_shrink(self):
        """grow は cmds の頂点→エッジ→頂点の変換と同じ。shrink は縁を外す。選択は変えない。"""
        plane = cmds.polyPlane(name=self.name("p"), subdivisionsX=4, subdivisionsY=4)[0]
        mesh = mlib.getNode(plane).getShape()
        cmds.select(clear=True)
        vertices = mesh.getVertices([12])
        grown = vertices.grow()
        edges = cmds.polyListComponentConversion(plane + ".vtx[12]", fromVertex=True, toEdge=True)
        expected = cmds.ls(cmds.polyListComponentConversion(edges, fromEdge=True, toVertex=True), flatten=True)
        self.assertEqual(sorted(grown.indices), sorted(int(name.split("[")[-1][:-1]) for name in expected))
        self.assertEqual(grown.indices[0], 12)
        self.assertEqual(grown.shrink().indices, (12,))
        self.assertEqual(vertices.shrink().indices, ())
        self.assertEqual(cmds.ls(selection=True), [])

    def test_loop_ring_match_cmds(self):
        """内部・縁のエッジのループとリングは cmds.polySelect と同じ集合(縁のエッジのループは自身だけ)。"""
        plane = cmds.polyPlane(name=self.name("p"), subdivisionsX=5, subdivisionsY=4)[0]
        cylinder = cmds.polyCylinder(name=self.name("c"), subdivisionsAxis=8, subdivisionsHeight=3)[0]
        for name in (plane, cylinder):
            mesh = mlib.getNode(name).getShape()
            for edge in range(0, mesh.getNumEdges(), 3):
                with self.subTest(mesh=name, edge=edge):
                    loop = cmds.polySelect(name, edgeLoop=edge, noSelection=True) or []
                    ring = cmds.polySelect(name, edgeRing=edge, noSelection=True) or []
                    self.assertEqual(sorted(mesh.getEdge(edge).getLoop().indices), sorted(set(loop)))
                    self.assertEqual(sorted(mesh.getEdges([edge]).getRing().indices), sorted(set(ring)))


class SoftSelectionTest(_SkinCase):

    def tearDown(self):
        cmds.softSelect(softSelectEnabled=self.soft_state)
        super().tearDown()

    def setUp(self):
        super().setUp()
        self.soft_state = cmds.softSelect(query=True, softSelectEnabled=True)

    def test_without_soft_select(self):
        """ソフト選択が無効なら、選んだ頂点を重み1で返す。"""
        cmds.softSelect(softSelectEnabled=False)
        plane = cmds.polyPlane(name=self.name("p"))[0]
        cmds.select(plane + ".vtx[3]", plane + ".vtx[5]")
        result = Selection.getSoftSelection()
        self.assertEqual(list(result.values()), [{3: 1.0, 5: 1.0}])
        self.assertEqual(list(result)[0], mlib.getNode(plane).getShape())
        cmds.select(clear=True)
        self.assertEqual(Selection.getSoftSelection(), {})

    def test_with_soft_select(self):
        """ソフト選択が有効なら、選んだ頂点は1、周りの頂点は0〜1の重みになる。"""
        cmds.softSelect(softSelectEnabled=True, softSelectDistance=0.5, softSelectFalloff=0)
        plane = cmds.polyPlane(name=self.name("p"), subdivisionsX=10, subdivisionsY=10)[0]
        cmds.select(plane + ".vtx[60]")
        weights = list(Selection.getSoftSelection().values())[0]
        self.assertAlmostEqual(weights[60], 1.0)
        self.assertGreater(len(weights), 1)
        self.assertTrue(all(0.0 < value <= 1.0 for value in weights.values()))


class BakeDeformerTest(_SkinCase):

    def test_bake_to_duplicate_and_undo(self):
        """delta mush の変形を複製へ焼き込み、skinCluster を返す。Undo 1 回で消える。"""
        self.skinned()
        target = cmds.duplicate(self.mesh, name=self.name("bake"))[0]
        cmds.deltaMush(self.mesh, name=self.name("mush"))
        cmds.flushUndo()
        skin = mlib.bakeDeformer(self.mesh, self.root, target, maxInfluences=2)
        self.assertIsInstance(skin, SkinCluster)
        self.assertTrue(skin.deforms(target))
        cmds.undo()
        self.assertEqual(cmds.ls(cmds.listHistory(target), type="skinCluster"), [])

    def test_errors(self):
        """引数で受けるフラグ・query・maxInfluences の不正は例外。"""
        self.skinned()
        self.assertRaises(TypeError, mlib.bakeDeformer, self.mesh, self.root, mi=3)
        self.assertRaises(TypeError, mlib.bakeDeformer, self.mesh, self.root, query=True)
        self.assertRaises(ValueError, mlib.bakeDeformer, self.mesh, self.root, maxInfluences=0)


if __name__ == "__main__":
    unittest.main()
