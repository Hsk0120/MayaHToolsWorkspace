"""BlendShape のターゲット操作(11.1.0 で戻したもの)の契約を固定する。

- ターゲットの指定: 名前・論理番号・weight 要素の Plug。bool・他の Plug は拒否。
- デルタ・頂点マスク: 取得・設定・頂点の除外・しきい値での削減。Undo 1回、fast は同じ結果で Undo なし。
- in-between: 絶対・相対の追加、ウェイトの一覧、除去。
- ミラー・反転(左右対称の平面)、複製、差し替え、編集モード、複数ベースの ``base=``。
"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.components.vertex import Vertices
from mlib.nodes import BlendShape
from support.specCase import NamespaceCase


class _BlendCase(NamespaceCase):
    """x方向に左右対称な平面(5x3頂点)と、+x側の頂点を持ち上げたターゲットを作る。"""

    PREFIX = "mlibSpecBsTargets_"

    def plane(self, text):
        return cmds.polyPlane(name=self.name(text), width=4, height=2, subdivisionsX=4, subdivisionsY=2,
                              constructionHistory=False)[0]

    def lifted(self, text, side=1.0, amount=1.0):
        mesh = self.plane(text)
        for index in range(15):
            point = cmds.xform(f"{mesh}.vtx[{index}]", query=True, translation=True, objectSpace=True)
            if point[0] * side > 0.1:
                cmds.xform(f"{mesh}.vtx[{index}]", translation=(point[0], amount, point[2]), objectSpace=True)
        return mesh

    def setUp(self):
        super().setUp()
        self.base = self.plane("base")
        self.smile = self.lifted("smile")
        self.bs = BlendShape(cmds.blendShape(self.smile, self.base, name=self.name("bs"))[0])
        self.assertEqual(self.bs.getTargetNames(), ["smile"])

    def positive(self):
        """+x側の頂点番号(x > 0)。"""
        return {i for i in range(15) if cmds.xform(f"{self.base}.vtx[{i}]", query=True, translation=True,
                                                     objectSpace=True)[0] > 0.1}

    def negative(self):
        """-x側の頂点番号(x < 0)。"""
        return {i for i in range(15) if cmds.xform(f"{self.base}.vtx[{i}]", query=True, translation=True,
                                                     objectSpace=True)[0] < -0.1}

    def baked(self):
        """ターゲット形状を削除してデルタだけにする。"""
        cmds.delete(self.smile)

    def raw_deltas(self, target=0, item=6000):
        return {vertex: tuple(round(v, 6) for v in delta)
                for vertex, delta in self.bs.getTargetDeltas(target, fullWeight=(item - 5000) / 1000.0).items()}


class TargetSpecifierTest(_BlendCase):

    def test_name_index_and_plug_select_the_same_target(self):
        plug = self.bs.getWeightPlug("smile")
        self.assertEqual(self.bs.getTargetIndex("smile"), 0)
        self.assertEqual(self.bs.getTargetIndex(0), 0)
        self.assertEqual(self.bs.getTargetIndex(plug), 0)
        self.assertEqual(self.bs.getWeightPlug(0).getFullName(), plug.getFullName())
        self.assertEqual(self.bs.getWeightPlug(plug).getFullName(), plug.getFullName())
        for value in ("smile", 0, plug):
            with self.subTest(value=value):
                self.assertEqual(set(self.bs.getTargetDeltas(value)), self.positive())

    def test_rejects_invalid_specifiers(self):
        for value, error in ((True, TypeError), (1.0, TypeError), (None, TypeError), ("nope", ValueError),
                             (5, ValueError), (self.bs.getPlug("envelope"), ValueError)):
            with self.subTest(value=value), self.assertRaises(error):
                self.bs.getTargetIndex(value)
        other = BlendShape(cmds.blendShape(self.lifted("o"), self.plane("ob"), name=self.name("other"))[0])
        with self.assertRaises(ValueError):
            self.bs.getWeightPlug(other.getPlug("weight")[0])

    def test_remove_target_by_plug_undoes_in_one_step(self):
        self.flushUndo()
        self.assertIs(self.bs.removeTarget(self.bs.getWeightPlug(0)), self.bs)
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.bs.getTargetNames(), ["smile"]),
                                   lambda: self.assertEqual(self.bs.getTargetNames(), []))


class DeltaTest(_BlendCase):

    def test_set_deltas_replaces_everything_in_one_undo(self):
        self.baked()
        before = self.raw_deltas()
        self.flushUndo()
        self.assertIs(self.bs.setTargetDeltas("smile", {2: (1, 2, 3), 7: mlib.Vector(0, 0, 1)}), self.bs)
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.raw_deltas(), before),
                                   lambda: self.assertEqual(self.raw_deltas(), {2: (1, 2, 3), 7: (0, 0, 1)}))
        cmds.setAttr(f"{self.bs}.smile", 1.0)
        self.bs.setTargetDeltas(0, {2: (1, 2, 3)})
        moved = cmds.xform(f"{self.base}.vtx[2]", query=True, translation=True, objectSpace=True)
        self.assertAlmostEqual(moved[1], 2.0, places=5)

    def test_connected_target_requires_disconnect(self):
        with self.assertRaises(RuntimeError):
            self.bs.setTargetDeltas(0, {0: (1, 0, 0)})
        self.bs.setTargetDeltas(0, {0: (1, 0, 0)}, disconnect=True)
        self.assertFalse(cmds.listConnections(f"{self.bs}.inputTarget[0].inputTargetGroup[0]"
                                              ".inputTargetItem[6000].inputGeomTarget"))
        self.assertEqual(self.raw_deltas(), {0: (1, 0, 0)})

    def test_connected_target_is_evaluated(self):
        cmds.xform(f"{self.smile}.vtx[0]", translation=(0, 3, 0), relative=True)
        self.assertAlmostEqual(self.bs.getTargetDeltas(0)[0].y, 3.0, places=5)

    def test_fast_matches_normal_without_undo(self):
        self.baked()
        deltas = {i: (i * 0.1, 1.0, -i * 0.2) for i in range(0, 15, 2)}
        self.bs.setTargetDeltas(0, deltas)
        normal = self.raw_deltas()
        self.bs.setTargetDeltas(0, {})
        self.assertEqual(self.raw_deltas(), {})
        self.flushUndo()
        self.bs.setTargetDeltas(0, deltas, fast=True)
        self.assertUndoEmpty()
        self.assertEqual(self.raw_deltas(), normal)

    def test_invalid_deltas(self):
        self.baked()
        for deltas, error in (([1, 2], TypeError), ({99: (0, 0, 0)}, IndexError), ({0: (0, 0)}, ValueError),
                              ({0: (0, 0, float("nan"))}, ValueError), ({"0": (0, 0, 0)}, TypeError)):
            with self.subTest(deltas=deltas), self.assertRaises(error):
                self.bs.setTargetDeltas(0, deltas)
        with self.assertRaises(ValueError):
            self.bs.getTargetDeltas(0, fullWeight=0.5)
        with self.assertRaises(TypeError):
            self.bs.setTargetDeltas(0, {}, fast=1)

    def test_target_vertices_reset_and_reduce(self):
        self.baked()
        self.bs.setTargetDeltas(0, {1: (0.001, 0, 0), 3: (0, 1, 0), 4: (0, 2, 0), 8: (0, 0, 0)})
        vertices = self.bs.getTargetVertices(0)
        self.assertIsInstance(vertices, Vertices)
        self.assertEqual(list(vertices.indices), [1, 3, 4])
        self.assertEqual(list(self.bs.getTargetVertices(0, tolerance=0.01).indices), [3, 4])
        with self.assertRaises(ValueError):
            self.bs.getTargetVertices(0, tolerance=-1)
        self.flushUndo()
        self.assertIs(self.bs.resetTargetVertices(0, [self.bs.getBaseGeometry()[0].getVertex(3)]), self.bs)
        self.assertUndoesInOneStep(lambda: self.assertIn(3, self.raw_deltas()),
                                   lambda: self.assertEqual(sorted(self.raw_deltas()), [1, 4, 8]))
        self.flushUndo()
        self.bs.reduceTargetDeltas(0, tolerance=0.01)
        self.assertUndoesInOneStep(lambda: self.assertEqual(sorted(self.raw_deltas()), [1, 3, 4, 8]),
                                   lambda: self.assertEqual(sorted(self.raw_deltas()), [3, 4]))
        self.flushUndo()
        self.bs.resetTargetVertices(0, 4, fast=True)
        self.bs.reduceTargetDeltas(0, fast=True)
        self.assertUndoEmpty()
        self.assertEqual(sorted(self.raw_deltas()), [1, 3])
        with self.assertRaises(IndexError):
            self.bs.resetTargetVertices(0, [99])
        other = self.plane("other")
        with self.assertRaises(ValueError):
            self.bs.resetTargetVertices(0, mlib.getNode(other).getShape().getVertices([0]))


class TargetWeightsTest(_BlendCase):

    def test_sequence_and_dict(self):
        self.assertEqual(self.bs.getTargetWeights("smile"), [1.0] * 15)
        self.flushUndo()
        values = [i / 14.0 for i in range(15)]
        self.assertIs(self.bs.setTargetWeights("smile", values), self.bs)
        self.assertUndoesInOneStep(
            lambda: self.assertEqual(self.bs.getTargetWeights(0), [1.0] * 15),
            lambda: [self.assertAlmostEqual(a, b, places=6) for a, b in zip(self.bs.getTargetWeights(0), values)])
        self.bs.setTargetWeights(0, {3: 0.25, 9: 0.5})
        weights = self.bs.getTargetWeights(0)
        self.assertEqual((weights[3], weights[9], weights[4]), (0.25, 0.5, 1.0))

    def test_fast_matches_normal_without_undo(self):
        values = {i: 0.1 * (i % 7) for i in range(0, 15, 3)}
        self.bs.setTargetWeights(0, values)
        normal = self.bs.getTargetWeights(0)
        self.bs.setTargetWeights(0, [1.0] * 15)
        self.flushUndo()
        self.bs.setTargetWeights(0, values, fast=True)
        self.assertUndoEmpty()
        self.assertEqual(self.bs.getTargetWeights(0), normal)

    def test_invalid_weights(self):
        for weights, error in (([1.0] * 3, ValueError), ({20: 1.0}, IndexError), ({0: "a"}, TypeError),
                               ({0: float("inf")}, ValueError), ("abc", TypeError)):
            with self.subTest(weights=weights), self.assertRaises(error):
                self.bs.setTargetWeights(0, weights)


class InBetweenTest(_BlendCase):

    def test_absolute_and_relative(self):
        half = self.lifted("half", amount=0.5)
        rel = self.lifted("rel", side=-1.0, amount=0.25)
        self.flushUndo()
        self.assertIs(self.bs.addInBetween("smile", half, 0.5), self.bs)
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.bs.getInBetweenWeights(0), []),
                                   lambda: self.assertEqual(self.bs.getInBetweenWeights(0), [0.5]))
        self.bs.addInBetween(0, half, 0.5)
        self.bs.addInBetween(self.bs.getWeightPlug(0), rel, 0.25, relative=True)
        self.assertEqual(self.bs.getInBetweenWeights("smile"), [0.25, 0.5])
        self.assertEqual(cmds.getAttr(f"{self.bs}.inbetweenInfoGroup[0].inbetweenInfo[5250].inbetweenTargetType"), 1)
        self.assertEqual(cmds.getAttr(f"{self.bs}.inbetweenInfoGroup[0].inbetweenInfo[5500].inbetweenTargetType"), 0)
        self.assertEqual(set(self.bs.getTargetDeltas(0, fullWeight=0.5)), self.positive())
        cmds.setAttr(f"{self.bs}.smile", 0.5)
        point = cmds.xform(f"{self.base}.vtx[4]", query=True, translation=True, objectSpace=True)
        self.assertAlmostEqual(point[1], 0.5, places=5)
        for weight, error in ((1.0, ValueError), (0.0, ValueError), (0.5, ValueError), (0.0005, ValueError),
                              ("a", TypeError)):
            with self.subTest(weight=weight), self.assertRaises(error):
                self.bs.addInBetween(0, half, weight)
        with self.assertRaises(ValueError):
            self.bs.addInBetween(0, cmds.polyCube(name=self.name("cube"))[0], 0.75)
        self.flushUndo()
        self.assertIs(self.bs.removeInBetween("smile", 0.5), self.bs)
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.bs.getInBetweenWeights(0), [0.25, 0.5]),
                                   lambda: self.assertEqual(self.bs.getInBetweenWeights(0), [0.25]))
        for weight in (1.0, 0.75):
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                self.bs.removeInBetween(0, weight)


class MirrorTest(_BlendCase):

    def test_mirror_and_flip(self):
        self.baked()
        positive, negative = self.positive(), self.negative()
        self.flushUndo()
        self.assertIs(self.bs.mirrorTarget("smile", axis="X"), self.bs)
        self.assertUndoesInOneStep(lambda: self.assertEqual(set(self.raw_deltas()), positive),
                                   lambda: self.assertEqual(set(self.raw_deltas()), positive | negative))
        self.bs.mirrorTarget(0, positiveToNegative=False)
        self.assertEqual(set(self.raw_deltas()), set())
        cmds.undo()
        self.flushUndo()
        self.assertIs(self.bs.flipTarget(0, axis="x"), self.bs)
        self.assertUndoesInOneStep(lambda: self.assertEqual(set(self.raw_deltas()), positive),
                                   lambda: self.assertEqual(set(self.raw_deltas()), negative))
        for axis, error in (("w", ValueError), (None, TypeError)):
            with self.subTest(axis=axis), self.assertRaises(error):
                self.bs.flipTarget(0, axis=axis)
        with self.assertRaises(TypeError):
            self.bs.mirrorTarget(0, positiveToNegative=1)

    def test_connected_target_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.bs.mirrorTarget(0)
        with self.assertRaises(RuntimeError):
            self.bs.flipTarget(0)


class DuplicateReplaceEditTest(_BlendCase):

    def test_duplicate(self):
        self.bs.addInBetween(0, self.lifted("half", amount=0.5), 0.5)
        self.bs.setTargetWeights(0, {2: 0.5})
        cmds.setAttr(f"{self.bs}.smile", 0.7)
        self.flushUndo()
        copy = self.bs.duplicateTarget("smile")
        self.assertEqual(copy.getAlias(), "smileCopy")
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.bs.getTargetNames(), ["smile"]),
                                   lambda: self.assertEqual(self.bs.getTargetNames(), ["smile", "smileCopy"]))
        copy = self.bs.duplicateTarget(0, name="grin")
        index = copy.getIndex()
        self.assertEqual(copy.get(), 0.0)
        self.assertEqual(self.raw_deltas(index), self.raw_deltas(0))
        self.assertEqual(self.raw_deltas(index, 5500), self.raw_deltas(0, 5500))
        self.assertEqual(self.bs.getInBetweenWeights("grin"), [0.5])
        self.assertEqual(self.bs.getTargetWeights("grin")[2], 0.5)
        self.assertFalse(copy.isDestination())
        self.assertFalse(cmds.listConnections(f"{self.bs}.inputTarget[0].inputTargetGroup[{index}]", source=True,
                                              destination=False))
        self.assertEqual(cmds.getAttr(f"{self.bs}.targetDirectory[0].childIndices"), [0, index])
        self.assertEqual(self.bs.duplicateTarget(0).getAlias(), "smileCopy")
        self.assertEqual(self.bs.duplicateTarget(0).getAlias(), "smileCopy1")
        for name, error in (("grin", ValueError), ("", ValueError), (3, TypeError), ("envelope", ValueError)):
            with self.subTest(name=name), self.assertRaises(error):
                self.bs.duplicateTarget(0, name=name)

    def test_replace_target(self):
        self.baked()
        other = self.lifted("other", side=-1.0, amount=2.0)
        self.flushUndo()
        self.assertIs(self.bs.replaceTarget("smile", other), self.bs)
        self.assertUndoesInOneStep(lambda: self.assertEqual(set(self.raw_deltas()), self.positive()),
                                   lambda: self.assertEqual(set(self.raw_deltas()), self.negative()))
        self.assertEqual(self.bs.getTargetNames(), ["smile"])
        with self.assertRaises(ValueError):
            self.bs.replaceTarget(0, cmds.polyCube(name=self.name("cube"))[0])
        with self.assertRaises(ValueError):
            self.bs.replaceTarget(0, other, fullWeight=0.5)

    def test_target_edit(self):
        self.baked()
        self.flushUndo()
        self.assertIs(self.bs.targetEdit("smile"), self.bs)
        self.assertEqual(cmds.getAttr(f"{self.bs}.inputTarget[0].sculptTargetIndex"), 0)
        self.bs.targetEdit(state=False)
        self.assertEqual(cmds.getAttr(f"{self.bs}.inputTarget[0].sculptTargetIndex"), -1)
        cmds.undo()
        self.assertEqual(cmds.getAttr(f"{self.bs}.inputTarget[0].sculptTargetIndex"), 0)
        with self.assertRaises(ValueError):
            self.bs.targetEdit()
        with self.assertRaises(ValueError):
            self.bs.targetEdit(0, fullWeight=0.5)
        with self.assertRaises(TypeError):
            self.bs.targetEdit(0, state=1)


class MultiBaseTest(NamespaceCase):

    PREFIX = "mlibSpecBsMulti_"

    def setUp(self):
        super().setUp()
        self.plane = cmds.polyPlane(name=self.name("plane"), subdivisionsX=2, subdivisionsY=2,
                                    constructionHistory=False)[0]
        self.cube = cmds.polyCube(name=self.name("cube"), constructionHistory=False)[0]
        self.bs = BlendShape(cmds.blendShape(self.plane, name=self.name("bs"))[0])
        cmds.blendShape(str(self.bs), edit=True, geometry=self.cube)
        plane_target = cmds.duplicate(self.plane, name=self.name("pt"))[0]
        cube_target = cmds.duplicate(self.cube, name=self.name("ct"))[0]
        cmds.blendShape(str(self.bs), edit=True, target=(self.plane, 0, plane_target, 1.0))
        cmds.blendShape(str(self.bs), edit=True, target=(self.cube, 0, cube_target, 1.0))
        cmds.delete(plane_target, cube_target)

    def test_base_argument(self):
        cube_shape = cmds.listRelatives(self.cube, shapes=True, fullPath=True, noIntermediate=True)[0]
        self.assertEqual(len(self.bs.getTargetWeights(0)), 9)
        self.assertEqual(len(self.bs.getTargetWeights(0, base=self.cube)), 8)
        self.assertEqual(len(self.bs.getTargetWeights(0, base=cube_shape)), 8)
        self.bs.setTargetDeltas(0, {7: (0, 1, 0)}, base=self.cube)
        self.bs.setTargetWeights(0, {1: 0.5}, base=self.cube, fast=True)
        self.assertEqual(self.bs.getTargetDeltas(0), {})
        self.assertEqual(set(self.bs.getTargetDeltas(0, base=self.cube)), {7})
        self.assertEqual(self.bs.getTargetWeights(0)[1], 1.0)
        self.assertEqual(self.bs.getTargetWeights(0, base=self.cube)[1], 0.5)
        self.assertEqual(self.bs.getTargetVertices(0, base=self.cube).shape.getName(),
                         cube_shape.rpartition("|")[2])
        with self.assertRaises(ValueError):
            self.bs.getTargetWeights(0, base=cmds.polySphere(name=self.name("sphere"))[0])
        with self.assertRaises(TypeError):
            self.bs.getTargetWeights(0, base=1)

    def test_duplicate_and_remove_cover_every_base(self):
        self.bs.setTargetDeltas(0, {7: (0, 1, 0)}, base=self.cube)
        copy = self.bs.duplicateTarget(0, name="copy")
        self.assertEqual(set(self.bs.getTargetDeltas(copy, base=self.cube)), {7})
        self.assertEqual(self.bs.getTargetDeltas(copy, base=self.plane), {})
        self.bs.removeTarget("copy")
        self.assertEqual(self.bs.getTargetIndex(0), 0)
        with self.assertRaises(ValueError):
            self.bs.getTargetIndex(copy.getIndex())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
