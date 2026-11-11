"""12.4.0 で足したデフォーマー・AnimCurve・ObjectSet のメソッドと作成関数を確かめる。

- GeometryFilter.getInputGeometry: 入力側の形状(Orig の中間形状)を返す。
- SkinCluster.getInfluenceVertices(ウェイトから求めた頂点と一致)・getBlendWeights/setBlendWeights(setAttr の値と
  突き合わせ、Undo 1回・fast)・unbind(keepHistory の有無)・recacheBindMatrices。
- AnimCurve.insertKey(形を保つ・Undo 1回)・findClosestIndex・isBreakdown/setBreakdown(cmds の照会と一致)、
  Keyframe.isBreakdown/setBreakdown。
- ObjectSet.clear・getUnion・getIntersection・getDifference・isSubSet(コンポーネントは要素単位)。
- createCluster・createLattice・createWire: 作成物の型・フラグ・短縮名・選択を変えないこと・Undo 1回・不正入力。
"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from support.specCase import NamespaceCase


class _Case(NamespaceCase):
    """形状を作る補助。"""

    PREFIX = "mlibV124Deform_"

    def cube(self, subdivisionsY=1):
        """1辺2cm の polyCube を作り、(transform 名, shape 名) を返す。"""
        transform = cmds.polyCube(name=self.name("cube#"), width=2, height=2, depth=2, subdivisionsY=subdivisionsY,
                                  constructionHistory=False)[0]
        transform = cmds.ls(transform, long=True)[0]
        return transform, cmds.listRelatives(transform, shapes=True, fullPath=True)[0]

    def skinned(self):
        """2段の cube を2本の joint へバインドし、(skin, mesh 名, joints, 未登録 joint) を返す。"""
        mesh, _ = self.cube(subdivisionsY=2)
        cmds.select(clear=True)
        j0 = cmds.joint(name=self.name("j0"), position=(0, -1, 0))
        j1 = cmds.joint(name=self.name("j1"), position=(0, 1, 0))
        cmds.select(clear=True)
        stranger = cmds.joint(name=self.name("stranger"))
        cmds.select(clear=True)
        name = cmds.skinCluster(j0, j1, mesh, toSelectedBones=True, name=self.name("skin"))[0]
        cmds.select(clear=True)
        return mlib.getNode(name), mesh, (j0, j1), stranger

    def keyed(self):
        """translateX の frame 1 に 0、frame 10 に 5 のキーを打ったカーブを返す。"""
        node = self.make("transform", "keyed#")
        cmds.setKeyframe(node, attribute="translateX", time=1, value=0.0)
        cmds.setKeyframe(node, attribute="translateX", time=10, value=5.0)
        return mlib.getNode(cmds.listConnections(node + ".tx", type="animCurve")[0])


class GeometryFilterTest(_Case):
    """GeometryFilter.getInputGeometry。"""

    def test_input_geometry_is_orig_shape(self):
        """skinCluster・cluster の入力は同じ transform の下の中間形状で、出力の形状とは別。"""
        skin, mesh, _, _ = self.skinned()
        cluster = mlib.createCluster(mesh)
        for deformer in (skin, cluster):
            with self.subTest(deformer=deformer.getType()):
                inputs = deformer.getInputGeometry()
                self.assertEqual(len(inputs), 1)
                self.assertTrue(cmds.getAttr(inputs[0].getFullName() + ".intermediateObject"))
                self.assertEqual(cmds.listRelatives(inputs[0].getFullName(), parent=True, fullPath=True)[0], mesh)
                self.assertNotEqual(inputs[0], deformer.getGeometry()[0])

    def test_deleted_raises(self):
        """削除済みのデフォーマーは RuntimeError。"""
        transform, _ = self.cube()
        cluster = mlib.createCluster(transform)
        cmds.delete(cluster.getFullName())
        with self.assertRaises(RuntimeError):
            cluster.getInputGeometry()


class SkinClusterTest(_Case):
    """SkinCluster の追加メソッド。"""

    def test_influence_vertices_match_weights(self):
        """getInfluenceVertices は閾値より大きいウェイトの頂点を昇順で返す。"""
        skin, mesh, joints, _ = self.skinned()
        rows = skin.getWeights(list(joints), rows=True)
        for column, joint in enumerate(joints):
            for threshold in (0.0, 0.5):
                with self.subTest(joint=joint, threshold=threshold):
                    expected = [index for index, row in enumerate(rows) if row[column] > threshold]
                    vertices = skin.getInfluenceVertices(joint, threshold)
                    self.assertEqual(list(vertices.indices), expected)
                    self.assertEqual(vertices.shape.getFullName(), cmds.listRelatives(mesh, shapes=True,
                                                                                      fullPath=True)[0])

    def test_influence_vertices_invalid(self):
        """閾値・influence の不正は例外。"""
        skin, _, joints, stranger = self.skinned()
        for args, error in (((joints[0], -1.0), ValueError), ((joints[0], float("nan")), ValueError),
                            ((joints[0], "a"), TypeError), ((joints[0], True), TypeError),
                            ((stranger,), ValueError), ((list(joints),), ValueError)):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    skin.getInfluenceVertices(*args)

    def test_blend_weights_match_set_attr(self):
        """getBlendWeights は blendWeights の値と一致し、setBlendWeights は Undo 1回で戻る。"""
        skin, mesh, _, _ = self.skinned()
        name = skin.getFullName()
        count = cmds.polyEvaluate(mesh, vertex=True)
        self.assertEqual(skin.getBlendWeights(), [0.0] * count)
        cmds.setAttr(name + ".blendWeights[2]", 0.75)
        self.assertEqual(skin.getBlendWeights(vertices=[5, 2]), [0.0, 0.75])
        self.flushUndo()
        self.assertIs(skin.setBlendWeights([0.25, 0.5, 1.0], vertices=[0, 1, 4]), skin)

        def values():
            return [cmds.getAttr(f"{name}.blendWeights[{index}]") for index in (0, 1, 2, 4)]
        self.assertUndoesInOneStep(lambda: self.assertSequenceAlmostEqual(values(), [0.0, 0.0, 0.75, 0.0]),
                                   lambda: self.assertSequenceAlmostEqual(values(), [0.25, 0.5, 0.75, 1.0]))

    def test_set_blend_weights_all_and_fast(self):
        """vertices=None は全頂点、fast は Undo に残らない。"""
        skin, mesh, _, _ = self.skinned()
        count = cmds.polyEvaluate(mesh, vertex=True)
        values = [index / (count - 1) for index in range(count)]
        skin.setBlendWeights(values)
        self.assertSequenceAlmostEqual(skin.getBlendWeights(), values)
        self.flushUndo()
        skin.setBlendWeights([0.5, 0.125], vertices=[3, 1], fast=True)
        self.assertUndoEmpty()
        self.assertAlmostEqual(cmds.getAttr(skin.getFullName() + ".blendWeights[3]"), 0.5)
        self.assertAlmostEqual(cmds.getAttr(skin.getFullName() + ".blendWeights[1]"), 0.125)

    def test_set_blend_weights_invalid(self):
        """件数・値・頂点の不正は例外で、値は変わらない。"""
        skin, _, _, _ = self.skinned()
        before = skin.getBlendWeights()
        for args, kwargs, error in (
                (([0.5, 0.5],), {"vertices": [0]}, ValueError), (([1.5],), {"vertices": [0]}, ValueError),
                (([-0.1],), {"vertices": [0]}, ValueError), ((["a"],), {"vertices": [0]}, TypeError),
                (("0.5",), {"vertices": [0]}, TypeError), (([0.5],), {"vertices": [999]}, IndexError),
                (([0.5],), {"vertices": [0], "fast": "yes"}, TypeError)):
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(error):
                    skin.setBlendWeights(*args, **kwargs)
                self.assertEqual(skin.getBlendWeights(), before)

    def test_unbind(self):
        """unbind は skinCluster を削除し、Undo 1回で戻る。keepHistory はノードを残して形状から外す。"""
        for keep in (False, True):
            with self.subTest(keepHistory=keep):
                skin, mesh, joints, _ = self.skinned()
                name = skin.getFullName()
                cmds.setAttr(joints[1] + ".tx", 3.0)
                bound_point = cmds.pointPosition(mesh + ".vtx[10]")
                self.flushUndo()
                self.assertIsNone(skin.unbind(keepHistory=keep))

                def check(deforming):
                    in_history = name in (cmds.ls(cmds.listHistory(mesh), type="skinCluster", long=True) or [])
                    self.assertEqual(in_history, deforming or keep)
                    self.assertEqual(skin.isValid(), deforming or keep)
                    if keep:
                        self.assertEqual(cmds.getAttr(name + ".nodeState"), 0 if deforming else 1)
                    point = cmds.pointPosition(mesh + ".vtx[10]")
                    self.assertEqual(point == bound_point, deforming)
                self.assertUndoesInOneStep(lambda: check(True), lambda: check(False))
                with self.assertRaises(TypeError):
                    skin.unbind(keepHistory="yes")
                cmds.delete(mesh, *joints)

    def test_recache_and_deleted(self):
        """recacheBindMatrices は自身を返す。削除済みでは RuntimeError。"""
        skin, mesh, joints, _ = self.skinned()
        self.assertIs(skin.recacheBindMatrices(), skin)
        cmds.delete(skin.getFullName())
        for call in (skin.recacheBindMatrices, skin.unbind, skin.getBlendWeights,
                     lambda: skin.setBlendWeights([]), lambda: skin.getInfluenceVertices(joints[0])):
            with self.subTest(call=call):
                with self.assertRaises(RuntimeError):
                    call()


class AnimCurveTest(_Case):
    """AnimCurve と Keyframe の追加メソッド。"""

    def test_insert_key_keeps_shape(self):
        """insertKey は評価値を変えずにキーを足し、Undo 1回で戻る。"""
        curve = self.keyed()
        value = curve.evaluate(4)
        self.flushUndo()
        self.assertIs(curve.insertKey(4), curve)
        self.assertUndoesInOneStep(lambda: self.assertEqual(curve.getKeyInputs(), [1.0, 10.0]),
                                   lambda: self.assertEqual(curve.getKeyInputs(), [1.0, 4.0, 10.0]))
        cmds.redo()
        self.assertAlmostEqual(curve.getKeyValues()[1], value)
        self.assertAlmostEqual(curve.evaluate(4), value)

    def test_insert_key_seconds_and_invalid(self):
        """timeUnit="sec" の入力と、不正な入力・空のカーブ。"""
        curve = self.keyed()
        fps = {"film": 24.0, "ntsc": 30.0, "pal": 25.0}[cmds.currentUnit(query=True, time=True)]
        curve.insertKey(7.0 / fps, timeUnit="sec")
        self.assertEqual([round(value, 6) for value in curve.getKeyInputs()], [1.0, 7.0, 10.0])
        for args, kwargs, error in (((float("inf"),), {}, ValueError), (("a",), {}, ValueError),
                                    ((None,), {}, TypeError), ((5,), {"timeUnit": "week"}, ValueError)):
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(error):
                    curve.insertKey(*args, **kwargs)
        empty = mlib.getNode(self.make("animCurveTL", "empty#"))
        with self.assertRaises(RuntimeError):
            empty.insertKey(3)

    def test_find_closest_index(self):
        """findClosestIndex は最も近いキーの番号。"""
        curve = self.keyed()
        for value, expected in ((-5, 0), (3, 0), (8, 1), (100, 1)):
            with self.subTest(value=value):
                self.assertEqual(curve.findClosestIndex(value), expected)
        empty = mlib.getNode(self.make("animCurveTL", "empty#"))
        with self.assertRaises(RuntimeError):
            empty.findClosestIndex(1)
        with self.assertRaises(ValueError):
            curve.findClosestIndex(float("nan"))

    def test_breakdown(self):
        """setBreakdown は keyframe -q -breakdown と一致し、Undo 1回で戻る。Keyframe からも使える。"""
        curve = self.keyed()
        curve.insertKey(5)
        name = curve.getFullName()

        def queried():
            return cmds.keyframe(name, query=True, breakdown=True) or []
        self.assertEqual([curve.isBreakdown(i) for i in range(3)], [False, False, False])
        self.flushUndo()
        self.assertIs(curve.setBreakdown(1), curve)
        self.assertUndoesInOneStep(lambda: self.assertEqual(queried(), []),
                                   lambda: self.assertEqual(queried(), [5.0]))
        key = curve.getKeyframe(1)
        self.assertIs(key.setBreakdown(), key)
        self.assertTrue(key.isBreakdown())
        self.assertEqual([curve.isBreakdown(i) for i in range(3)], [False, True, False])
        key.setBreakdown(False)
        self.assertFalse(key.isBreakdown())
        curve.setBreakdown([0, 2])
        self.assertEqual(queried(), [1.0, 10.0])
        for args, error in (((5,), IndexError), ((1, "yes"), TypeError), ((None,), TypeError)):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    curve.setBreakdown(*args)
        with self.assertRaises(IndexError):
            curve.isBreakdown(3)
        cmds.delete(name)
        with self.assertRaises(RuntimeError):
            curve.isBreakdown(0)


class ObjectSetTest(_Case):
    """ObjectSet の集合演算と clear。"""

    def flat(self, members):
        """getMembers 形式のリストを、フルパスの要素名の集合へ展開する。"""
        result = set()
        for member in members:
            if isinstance(member, str):
                result.update(cmds.ls(member, flatten=True, long=True))
            else:
                result.add(member.getFullName())
        return result

    def sets(self):
        """頂点の一部と transform を持つ2つのセットを返す。"""
        cube, _ = self.cube()
        a, b = self.make("transform", "a#"), self.make("transform", "b#")
        first = cmds.sets(cube + ".vtx[0:3]", a, name=self.name("first"))
        second = cmds.sets(cube + ".vtx[2:5]", b, name=self.name("second"))
        return mlib.getNode(first), mlib.getNode(second), cube, cmds.ls(a, long=True)[0], cmds.ls(b, long=True)[0]

    def test_set_operations(self):
        """和・積・差は要素単位で cmds の結果を集合演算したものと一致する。"""
        first, second, cube, a, b = self.sets()
        one = self.flat(cmds.sets(first.getFullName(), query=True))
        two = self.flat(cmds.sets(second.getFullName(), query=True))
        self.assertEqual(self.flat(first.getUnion(second)), one | two)
        self.assertEqual(self.flat(first.getIntersection(second)), one & two)
        self.assertEqual(self.flat(first.getDifference(second)), one - two)
        self.assertEqual(self.flat(first.getIntersection(second.getName())), one & two)
        self.assertFalse(first.isSubSet(second))
        sub = mlib.getNode(cmds.sets(cube + ".vtx[2]", b, name=self.name("sub")))
        self.assertTrue(sub.isSubSet(second))
        self.assertTrue(mlib.getNode(cmds.sets(empty=True, name=self.name("empty"))).isSubSet(first))

    def test_clear_and_invalid(self):
        """clear は Undo 1回で戻る。相手が objectSet でなければ TypeError、削除済みは RuntimeError。"""
        first, second, _, a, _ = self.sets()
        before = self.flat(first.getMembers())
        self.flushUndo()
        self.assertIs(first.clear(), first)
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.flat(first.getMembers()), before),
                                   lambda: self.assertEqual(first.getMembers(), []))
        with self.assertRaises(TypeError):
            first.getUnion(a)
        cmds.delete(second.getFullName())
        with self.assertRaises(RuntimeError):
            first.getDifference(second)
        with self.assertRaises(RuntimeError):
            second.clear()


class CreateDeformerTest(_Case):
    """createCluster・createLattice・createWire。"""

    CLEAR_SELECTION = True

    def test_create_cluster(self):
        """cluster を作り、ハンドルを取れる。relative・短縮名・選択を変えないこと・Undo 1回。"""
        cube, _ = self.cube()
        cmds.select(clear=True)
        self.flushUndo()
        cluster = mlib.createCluster(cube + ".vtx[0:3]", n=self.name("made"), rel=True)
        self.assertEqual(cluster.getType(), "cluster")
        self.assertEqual(cluster.getName(), self.name("made"))
        self.assertTrue(cmds.getAttr(cluster.getFullName() + ".relative"))
        self.assertTrue(cmds.listRelatives(cluster.getWeightedNode().getFullName(), shapes=True,
                                           type="clusterHandle"))
        self.assertEqual(cmds.ls(selection=True), [])
        name = cluster.getFullName()
        self.assertUndoesInOneStep(lambda: self.assertFalse(cmds.objExists(name)),
                                   lambda: self.assertTrue(cmds.objExists(name)))
        self.assertFalse(cmds.getAttr(mlib.createCluster(cube).getFullName() + ".relative"))

    def test_create_lattice(self):
        """ffd を作り、分割数がラティスに設定される。"""
        cube, _ = self.cube()
        cmds.select(clear=True)
        self.flushUndo()
        ffd = mlib.createLattice(cube, name=self.name("made"), dv=(3, 4, 2), ldv=(2, 3, 2))
        self.assertEqual(ffd.getType(), "ffd")
        lattice = ffd.getPlug("deformedLatticePoints").getSource().getNode().getFullName()
        self.assertEqual([cmds.getAttr(lattice + "." + axis + "Divisions") for axis in "stu"], [3, 4, 2])
        self.assertEqual([cmds.getAttr(ffd.getFullName() + ".localInfluence" + axis) for axis in "STU"],
                         [2, 3, 2])
        self.assertEqual(cmds.ls(selection=True), [])
        name = ffd.getFullName()
        self.assertUndoesInOneStep(lambda: self.assertFalse(cmds.objExists(name)),
                                   lambda: self.assertTrue(cmds.objExists(name)))

    def test_create_wire(self):
        """wire を作り、dropoffDistance を全カーブに設定する。"""
        cube, _ = self.cube()
        curves = [cmds.curve(degree=1, point=[(-2, y, 1), (2, y, 1)], name=self.name("crv#")) for y in (0.5, -0.5)]
        cmds.select(clear=True)
        self.flushUndo()
        wire = mlib.createWire(cube, curves, name=self.name("made"), dds=2.5)
        self.assertEqual(wire.getType(), "wire")
        self.assertEqual([cmds.getAttr(f"{wire.getFullName()}.dropoffDistance[{i}]") for i in (0, 1)], [2.5, 2.5])
        self.assertEqual(cmds.ls(selection=True), [])
        name = wire.getFullName()
        self.assertUndoesInOneStep(lambda: self.assertFalse(cmds.objExists(name)),
                                   lambda: self.assertTrue(cmds.objExists(name)))

    def test_invalid_arguments(self):
        """不正な引数はシーンを変えずに例外。"""
        cube, _ = self.cube()
        curve = cmds.curve(degree=1, point=[(-2, 0, 1), (2, 0, 1)], name=self.name("crv#"))
        before = set(cmds.ls())
        cases = (
            (mlib.createCluster, ([],), {}, ValueError),
            (mlib.createCluster, (cube,), {"name": "a", "n": "b"}, TypeError),
            (mlib.createCluster, (cube,), {"relative": "yes"}, TypeError),
            (mlib.createCluster, (cube,), {"name": ""}, ValueError),
            (mlib.createLattice, (cube,), {"divisions": (1, 2, 2)}, ValueError),
            (mlib.createLattice, (cube,), {"divisions": (2, 2)}, ValueError),
            (mlib.createLattice, (cube,), {"divisions": (2.0, 2, 2)}, TypeError),
            (mlib.createLattice, (cube,), {"divisions": (2, 2, 2), "dv": (2, 2, 2)}, TypeError),
            (mlib.createLattice, (cube,), {"objectCentered": 1}, TypeError),
            (mlib.createWire, (cube, []), {}, ValueError),
            (mlib.createWire, (cube, curve), {"dropoffDistance": 0}, ValueError),
            (mlib.createWire, (cube, curve), {"dropoffDistance": "1"}, TypeError),
            (mlib.createWire, (cube, curve), {"dropoffDistance": 1.0, "dds": 1.0}, TypeError),
        )
        for function, args, kwargs, error in cases:
            with self.subTest(function=function.__name__, kwargs=kwargs):
                with self.assertRaises(error):
                    function(*args, **kwargs)
                self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
