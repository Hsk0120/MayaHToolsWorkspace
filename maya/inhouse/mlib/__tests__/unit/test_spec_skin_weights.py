"""SkinCluster の頂点単位のウェイト編集(5.0.0)の約束を固定する。

- ``getWeights``/``setWeights`` の ``vertices=``・``normalize=``・``broadcast=``、influence と頂点の入力検証。
- ``getVertexWeights``/``setVertexWeights`` の辞書による1頂点の照会・編集。
- ``pruneWeights``・``mirrorWeights``、形状を受け付ける ``copyWeightsTo``。

読取りと正規化・刈り込みの値は ``cmds.skinPercent`` と突き合わせ、通常経路は Undo 1 回、
fast は Undo キューに何も積まないことを確かめる。
"""

import math
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.components.vertex import Vertex, Vertices
from mlib.nodes import Joint, Node, SkinCluster
from support.specCase import NamespaceCase


class _SkinCase(NamespaceCase):
    """3 本の joint に 2 段の cube(12 頂点)をバインドし、頂点ごとに異なる生のウェイトを書く。"""

    PREFIX = "mlibSpecSkinWeights_"
    CLEAR_SELECTION = True

    def setUp(self):
        super().setUp()
        cmds.select(clear=True)
        self.joints = [cmds.joint(name=self.name("j%d" % i), position=(0, i - 1, 0)) for i in range(3)]
        cmds.select(clear=True)
        self.mesh = cmds.polyCube(name=self.name("mesh"), subdivisionsY=2, constructionHistory=False)[0]
        self.shape = cmds.listRelatives(self.mesh, shapes=True, fullPath=True)[0]
        self.skinName = cmds.skinCluster(self.joints, self.mesh, toSelectedBones=True)[0]
        self.skin = SkinCluster(self.skinName)
        self.count = cmds.polyEvaluate(self.mesh, vertex=True)
        for vertex in range(self.count):
            raw = [vertex % 3 + 1.0, vertex % 4 + 1.0, vertex % 5 + 1.0]
            self.writeRow(vertex, [value / sum(raw) for value in raw])
        cmds.select(clear=True)

    def writeRow(self, vertex, row):
        """頂点の全 influence の生の値を setAttr で書く。"""
        for index, value in enumerate(row):
            cmds.setAttr("{}.weightList[{}].weights[{}]".format(self.skinName, vertex, index), value)

    def vtx(self, vertex):
        return "{}.vtx[{}]".format(self.mesh, vertex)

    def row(self, vertex):
        """cmds.skinPercent で読んだ頂点の全 influence の値。"""
        return cmds.skinPercent(self.skinName, self.vtx(vertex), query=True, value=True)

    def rows(self):
        return [self.row(vertex) for vertex in range(self.count)]

    def assertRowsAlmostEqual(self, actual, expected, places=6):
        self.assertEqual(len(actual), len(expected))
        for a, e in zip(actual, expected):
            self.assertSequenceAlmostEqual(a, e, places=places)


class GetWeightsTest(_SkinCase):
    """getWeights の vertices= と、influence・頂点の入力検証。"""

    def test_vertices_forms_match_skinPercent(self):
        """番号・頂点名・範囲名・Vertex・Vertices のどれでも、指定順の値が skinPercent と一致する。"""
        mesh_node = Node(self.mesh).getShape()
        cases = {
            "int": (3, [3]),
            "list": ([5, 2], [5, 2]),
            "name": (self.vtx(4), [4]),
            "range": (self.mesh + ".vtx[1:3]", [1, 2, 3]),
            "shapeName": (self.shape + ".vtx[7]", [7]),
            "all": (self.mesh + ".vtx[*]", list(range(self.count))),
            "Vertex": (Vertex(mesh_node, 6), [6]),
            "Vertices": (Vertices(mesh_node, [8, 0]), [8, 0]),
            "mixed": ([Vertex(mesh_node, 9), 1, self.vtx(10)], [9, 1, 10]),
        }
        for label, (vertices, expected) in cases.items():
            with self.subTest(vertices=label):
                values = self.skin.getWeights(self.joints[::-1], vertices=vertices)
                flat = [value for vertex in expected for value in self.row(vertex)[::-1]]
                self.assertSequenceAlmostEqual(list(values), flat)
        self.assertEqual(list(self.skin.getWeights(self.joints, vertices=[])), [])
        all_rows = [value for row in self.rows() for value in row]
        self.assertSequenceAlmostEqual(list(self.skin.getWeights(self.joints)), all_rows)

    def test_influence_errors(self):
        """未登録・綴り違いは名前付きの ValueError、頂点や属性は TypeError、空・重複は ValueError。"""
        message = "'arm_R_JNT' is not an influence of {}".format(self.skin.getName())
        for method in ("get", "set"):
            with self.subTest(method=method):
                call = (self.skin.getWeights if method == "get"
                        else lambda joints: self.skin.setWeights(joints, [1.0], broadcast=True))
                with self.assertRaises(ValueError) as context:
                    call(["arm_R_JNT"])
                self.assertEqual(str(context.exception), message)
                other = cmds.createNode("joint", name=self.name("other"))
                with self.assertRaisesRegex(ValueError, "is not an influence of"):
                    call([other])
                vertex = Vertex(Node(self.mesh).getShape(), 0)
                for components in (vertex, [vertex], Vertices(Node(self.mesh).getShape(), [0, 1])):
                    with self.assertRaisesRegex(TypeError, "vertices=.*getVertexWeights"):
                        call(components)
                with self.assertRaisesRegex(TypeError, "component or attribute name"):
                    call(self.vtx(0))
                with self.assertRaisesRegex(ValueError, "at least one influence"):
                    call([])
        with self.assertRaisesRegex(ValueError, "more than once"):
            self.skin.getWeights([self.joints[0], self.joints[0]])

    def test_vertex_errors(self):
        """頂点の重複は ValueError、範囲外は IndexError、頂点以外の型・別形状は TypeError/ValueError。"""
        other = cmds.polyCube(name=self.name("other"), constructionHistory=False)[0]
        cases = (
            ([1, 1], ValueError),
            ([self.count], IndexError),
            ([-1], IndexError),
            ([1.0], TypeError),
            ([True], TypeError),
            (self.mesh + ".e[0]", TypeError),
            (self.mesh, TypeError),
            (other + ".vtx[0]", ValueError),
            (Vertex(Node(other).getShape(), 0), ValueError),
            (object(), TypeError),
        )
        for vertices, error in cases:
            with self.subTest(vertices=repr(vertices)):
                with self.assertRaises(error):
                    self.skin.getWeights(self.joints, vertices=vertices)


class SetWeightsTest(_SkinCase):
    """setWeights の vertices=・broadcast=・normalize=。"""

    def test_broadcast_is_required_for_one_row(self):
        """K 個だけを複数頂点へ渡すと broadcast=True か vertices= を促す ValueError で、何も書かない。"""
        before = self.rows()
        with self.assertRaises(ValueError) as context:
            self.skin.setWeights(self.joints, [0.2, 0.3, 0.5])
        self.assertIn("broadcast=True", str(context.exception))
        self.assertIn("vertices=", str(context.exception))
        with self.assertRaisesRegex(ValueError, "broadcast=True requires exactly 3 weights"):
            self.skin.setWeights(self.joints, [0.2, 0.3, 0.5] * self.count, broadcast=True)
        with self.assertRaisesRegex(ValueError, "vertex count times influence count"):
            self.skin.setWeights(self.joints, [0.2, 0.3])
        self.assertRowsAlmostEqual(self.rows(), before)
        self.skin.setWeights(self.joints, [0.2, 0.3, 0.5], broadcast=True)
        self.assertRowsAlmostEqual(self.rows(), [[0.2, 0.3, 0.5]] * self.count)
        # 1 頂点なら K 個は V*K 個と同じなので broadcast は不要。
        self.skin.setWeights(self.joints, [0.5, 0.5, 0.0], vertices=[3])
        self.assertSequenceAlmostEqual(self.row(3), [0.5, 0.5, 0.0])

    def test_vertices_follow_given_order_and_leave_others(self):
        """vertices= の指定順に値が入り、指定しない頂点・列は変わらない。"""
        before = self.rows()
        self.skin.setWeights([self.joints[2], self.joints[0]], [0.1, 0.2, 0.3, 0.4], vertices=[7, 2])
        expected = [list(row) for row in before]
        expected[7][2], expected[7][0] = 0.1, 0.2
        expected[2][2], expected[2][0] = 0.3, 0.4
        self.assertRowsAlmostEqual(self.rows(), expected)
        self.skin.setWeights(self.joints, [], vertices=[])
        self.assertRowsAlmostEqual(self.rows(), expected)

    def test_bool_flags_are_typed(self):
        for flag in ("normalize", "broadcast"):
            with self.subTest(flag=flag):
                with self.assertRaises(TypeError):
                    self.skin.setWeights(self.joints, [0.2, 0.3, 0.5], vertices=[0], **{flag: 1})

    def normalized_by_skinPercent(self, vertex, pairs):
        """cmds.skinPercent(transformValue, normalize=True) の結果を読み、Undo で戻す。"""
        with mlib.decorator.undoChunk("reference"):
            cmds.skinPercent(self.skinName, self.vtx(vertex), transformValue=pairs, normalize=True)
        result = self.row(vertex)
        cmds.undo()
        return result

    def test_normalize_matches_skinPercent(self):
        """指定値を保って他を比率で合わせる正規化が、ロックの有無とも skinPercent と一致する。"""
        j0, j1, j2 = self.joints
        cases = (
            ("one", [j0], [0.6], ()),
            ("two", [j0, j1], [0.1, 0.2], ()),
            ("zero", [j1], [0.0], ()),
            ("full", [j2], [1.0], ()),
            ("lockedOther", [j0], [0.4], (j2,)),
        )
        # 未指定が全てロックの場合(自由列なし)は Maya 2022 と 2027 で結果が異なるため、
        # test_normalize_own_rules で mlib の規則だけを確かめる。
        for fast in (False, True):
            for label, influences, values, locked in cases:
                for vertex in (0, 5, 11):
                    with self.subTest(case=label, vertex=vertex, fast=fast):
                        for joint in locked:
                            cmds.setAttr(joint + ".liw", True)
                        try:
                            before = self.row(vertex)
                            expected = self.normalized_by_skinPercent(vertex, list(zip(influences, values)))
                            self.assertSequenceAlmostEqual(self.row(vertex), before)
                            self.skin.setWeights(influences, values, vertices=[vertex], normalize=True, fast=fast)
                            self.assertSequenceAlmostEqual(self.row(vertex), expected)
                            self.assertAlmostEqual(sum(self.row(vertex)), 1.0, places=9)
                            self.writeRow(vertex, before)
                        finally:
                            for joint in locked:
                                cmds.setAttr(joint + ".liw", False)

    def test_normalize_own_rules(self):
        """指定値の合計が空きを超える・他が全て0の場合は、指定値を比率で縮小・拡大して他を0にする。"""
        j0, j1, j2 = self.joints
        self.skin.setWeights([j0, j1], [0.6, 0.6], vertices=[0], normalize=True)
        self.assertSequenceAlmostEqual(self.row(0), [0.5, 0.5, 0.0])
        self.writeRow(1, [0.0, 0.0, 0.0])
        self.skin.setWeights([j0], [0.25], vertices=[1], normalize=True)
        self.assertSequenceAlmostEqual(self.row(1), [1.0, 0.0, 0.0])
        # 全列を指定すれば、各頂点の行を合計1へ正規化するだけになる。
        self.skin.setWeights(self.joints, [1.0, 1.0, 2.0], vertices=[2, 3], broadcast=True, normalize=True)
        self.assertRowsAlmostEqual([self.row(2), self.row(3)], [[0.25, 0.25, 0.5]] * 2)
        # ロックした列は保ち、残りの空きへ指定値を縮める。
        self.writeRow(4, [0.2, 0.3, 0.5])
        cmds.setAttr(j2 + ".liw", True)
        self.skin.setWeights([j0], [0.9], vertices=[4], normalize=True)
        self.assertSequenceAlmostEqual(self.row(4), [0.5, 0.0, 0.5])
        # 未指定が全てロックなら、指定値を空き(1 - ロック合計)へ合わせる。
        self.writeRow(6, [0.2, 0.3, 0.5])
        cmds.setAttr(j0 + ".liw", True)
        self.skin.setWeights([j1], [0.2], vertices=[6], normalize=True)
        self.assertSequenceAlmostEqual(self.row(6), [0.2, 0.3, 0.5])
        cmds.setAttr(j0 + ".liw", False)
        cmds.setAttr(j2 + ".liw", False)

    def test_normalize_errors_do_not_write(self):
        """負値・合計0・ロック値の超過は ValueError で、頂点を書き換えない。"""
        j0, j1, j2 = self.joints
        self.writeRow(0, [0.0, 0.0, 0.0])
        with self.assertRaisesRegex(ValueError, "zero-total"):
            self.skin.setWeights([j0], [0.0], vertices=[0], normalize=True)
        with self.assertRaisesRegex(ValueError, "negative"):
            self.skin.setWeights([j0], [-0.5], vertices=[1], normalize=True)
        self.writeRow(2, [0.2, 0.3, 1.5])
        cmds.setAttr(j2 + ".liw", True)
        with self.assertRaisesRegex(ValueError, "exceed 1.0"):
            self.skin.setWeights([j0], [0.5], vertices=[2], normalize=True)
        cmds.setAttr(j2 + ".liw", False)
        self.assertSequenceAlmostEqual(self.row(0), [0.0, 0.0, 0.0])
        self.assertSequenceAlmostEqual(self.row(2), [0.2, 0.3, 1.5])

    def test_undo_once_and_fast_without_undo(self):
        """通常経路は Undo 1 回で戻り、fast は Undo キューに積まず、両者は同じ値になる。"""
        before = self.rows()
        self.flushUndo()
        self.skin.setWeights([self.joints[1]], [0.7, 0.1], vertices=[3, 8], normalize=True)
        after = self.rows()
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibSkinClusterSetWeights")
        self.assertUndoesInOneStep(lambda: self.assertRowsAlmostEqual(self.rows(), before),
                                   lambda: self.assertRowsAlmostEqual(self.rows(), after))
        self.flushUndo()
        self.skin.setWeights([self.joints[1]], [0.7, 0.1], vertices=[3, 8], normalize=True, fast=True)
        self.assertUndoEmpty()
        self.assertRowsAlmostEqual(self.rows(), after)


class VertexWeightsTest(_SkinCase):
    """getVertexWeights/setVertexWeights。"""

    def test_get_matches_skinPercent(self):
        """influence の Node をキーに、物理順で skinPercent と同じ値を返す。nonzero は 0 を除く。"""
        mesh_node = Node(self.mesh).getShape()
        for vertex in (0, 4, Vertex(mesh_node, 6), self.vtx(9)):
            with self.subTest(vertex=str(vertex)):
                weights = self.skin.getVertexWeights(vertex)
                index = vertex if isinstance(vertex, int) else (vertex.index if isinstance(vertex, Vertex) else 9)
                self.assertEqual([node.getUuid() for node in weights],
                                 [node.getUuid() for node in self.skin.getInfluences()])
                self.assertTrue(all(isinstance(node, Joint) for node in weights))
                self.assertSequenceAlmostEqual(list(weights.values()), self.row(index))
        self.writeRow(1, [0.0, 0.25, 0.75])
        weights = self.skin.getVertexWeights(1, nonzero=True)
        self.assertEqual([node.getName() for node in weights], [cmds.ls(j)[0] for j in self.joints[1:]])
        with self.assertRaisesRegex(ValueError, "exactly one vertex"):
            self.skin.getVertexWeights([0, 1])
        with self.assertRaisesRegex(ValueError, "exactly one vertex"):
            self.skin.getVertexWeights(self.mesh + ".vtx[0:1]")
        with self.assertRaises(TypeError):
            self.skin.getVertexWeights(None)
        with self.assertRaises(TypeError):
            self.skin.getVertexWeights(0, nonzero=1)

    def test_set_normalize_matches_skinPercent(self):
        """既定の normalize=True は skinPercent(transformValue) と同じ値になり、False は指定列だけを書く。"""
        j0, j1, j2 = self.joints
        before = self.row(5)
        with mlib.decorator.undoChunk("reference"):
            cmds.skinPercent(self.skinName, self.vtx(5), transformValue=[(j1, 0.3)], normalize=True)
        expected = self.row(5)
        cmds.undo()
        self.assertIs(self.skin.setVertexWeights(5, {j1: 0.3}), self.skin)
        self.assertSequenceAlmostEqual(self.row(5), expected)
        self.skin.setVertexWeights(self.vtx(5), {j0: 0.05, j2: 0.05}, normalize=False)
        self.assertSequenceAlmostEqual(self.row(5), [0.05, expected[1], 0.05])
        # getVertexWeights の辞書をそのまま戻せる。
        self.writeRow(5, before)
        weights = self.skin.getVertexWeights(5)
        self.writeRow(5, [1.0, 0.0, 0.0])
        self.skin.setVertexWeights(5, weights)
        self.assertSequenceAlmostEqual(self.row(5), before)

    def test_set_undo_fast_and_errors(self):
        j0 = self.joints[0]
        before = self.row(2)
        self.flushUndo()
        self.skin.setVertexWeights(2, {j0: 0.9})
        after = self.row(2)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibSkinClusterSetVertexWeights")
        self.assertUndoesInOneStep(lambda: self.assertSequenceAlmostEqual(self.row(2), before),
                                   lambda: self.assertSequenceAlmostEqual(self.row(2), after))
        self.flushUndo()
        self.skin.setVertexWeights(2, {j0: 0.9}, fast=True)
        self.assertUndoEmpty()
        self.assertSequenceAlmostEqual(self.row(2), after)
        cases = (
            ((2, [(j0, 0.5)]), TypeError),
            ((2, {}), ValueError),
            ((2, {"arm_R_JNT": 0.5}), ValueError),
            (([2, 3], {j0: 0.5}), ValueError),
            ((2, {j0: float("nan")}), ValueError),
            ((self.count, {j0: 0.5}), IndexError),
        )
        for args, error in cases:
            with self.subTest(args=repr(args)):
                with self.assertRaises(error):
                    self.skin.setVertexWeights(*args)
        self.assertSequenceAlmostEqual(self.row(2), after)


class PruneWeightsTest(_SkinCase):
    """pruneWeights。"""

    def setUp(self):
        super().setUp()
        rows = ([0.02, 0.48, 0.5], [0.04, 0.04, 0.92], [0.3, 0.3, 0.4], [0.01, 0.01, 0.01])
        for vertex in range(self.count):
            self.writeRow(vertex, rows[vertex % len(rows)])

    def test_matches_skinPercent(self):
        """閾値未満を0にして正規化した値が skinPercent(pruneWeights) と一致し、Undo 1 回で戻る。"""
        before = self.rows()
        for threshold in (0.0, 0.03, 0.05, 0.3, 0.5):
            with self.subTest(threshold=threshold):
                with mlib.decorator.undoChunk("reference"):
                    cmds.skinPercent(self.skinName, self.mesh, pruneWeights=threshold)
                expected = self.rows()
                cmds.undo()
                self.assertRowsAlmostEqual(self.rows(), before)
                self.flushUndo()
                self.assertIs(self.skin.pruneWeights(threshold), self.skin)
                self.assertRowsAlmostEqual(self.rows(), expected)
                if self.rows() != before:
                    self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibSkinClusterPruneWeights")
                    self.assertUndoesInOneStep(lambda: self.assertRowsAlmostEqual(self.rows(), before),
                                               lambda: self.assertRowsAlmostEqual(self.rows(), expected))
                else:
                    cmds.undo()
                self.assertRowsAlmostEqual(self.rows(), before)

    def test_without_normalize_and_locks(self):
        """normalize=False は0にするだけ。ロックした influence は刈り込まず、正規化でも値を保つ。"""
        self.skin.pruneWeights(0.05, normalize=False)
        self.assertSequenceAlmostEqual(self.row(0), [0.0, 0.48, 0.5])
        self.assertSequenceAlmostEqual(self.row(1), [0.0, 0.0, 0.92])
        self.assertSequenceAlmostEqual(self.row(3), [0.01, 0.01, 0.01])
        self.writeRow(0, [0.02, 0.48, 0.5])
        self.writeRow(1, [0.04, 0.04, 0.92])
        cmds.setAttr(self.joints[0] + ".liw", True)
        self.skin.pruneWeights(0.05)
        self.assertSequenceAlmostEqual(self.row(0), [0.02, 0.48, 0.5])
        self.assertSequenceAlmostEqual(self.row(1), [0.04, 0.0, 0.96])
        cmds.setAttr(self.joints[0] + ".liw", False)

    def test_threshold_errors(self):
        for threshold, error in ((True, TypeError), ("0.1", TypeError), (None, TypeError),
                                 (-0.1, ValueError), (float("nan"), ValueError), (math.inf, ValueError)):
            with self.subTest(threshold=threshold):
                with self.assertRaises(error):
                    self.skin.pruneWeights(threshold)
        with self.assertRaises(TypeError):
            self.skin.pruneWeights(0.1, normalize=None)


class MirrorWeightsTest(NamespaceCase):
    """mirrorWeights。中央・左右の joint に 6 分割の plane をバインドする。"""

    PREFIX = "mlibSpecSkinMirror_"
    CLEAR_SELECTION = True

    def setUp(self):
        super().setUp()
        cmds.select(clear=True)
        self.center = cmds.joint(name=self.name("C_jnt"), position=(0, 0, 0))
        self.left = cmds.joint(name=self.name("L_jnt"), position=(2, 0, 0))
        cmds.select(self.center)
        self.right = cmds.joint(name=self.name("R_jnt"), position=(-2, 0, 0))
        cmds.select(clear=True)
        self.plane = cmds.polyPlane(name=self.name("plane"), width=6, height=2, subdivisionsX=6,
                                    subdivisionsY=1, constructionHistory=False)[0]
        self.skinName = cmds.skinCluster(self.center, self.left, self.right, self.plane, toSelectedBones=True)[0]
        self.skin = SkinCluster(self.skinName)
        cmds.skinPercent(self.skinName, self.plane + ".vtx[*]", transformValue=[(self.center, 1.0)])
        positions = cmds.xform(self.plane + ".vtx[*]", query=True, worldSpace=True, translation=True)
        xs = positions[0::3]
        self.plus = [i for i, x in enumerate(xs) if x > 2.5]
        self.minus = [i for i, x in enumerate(xs) if x < -2.5]
        cmds.skinPercent(self.skinName, [self.vtx(i) for i in self.plus], transformValue=[(self.left, 1.0)])

    def vtx(self, index):
        return "{}.vtx[{}]".format(self.plane, index)

    def row(self, index):
        return cmds.skinPercent(self.skinName, self.vtx(index), query=True, value=True)

    def test_positive_to_negative_and_undo(self):
        """+X 側を -X 側へ写し(左の joint は右の joint へ)、Undo 1 回で戻る。"""
        before = [self.row(i) for i in self.minus]
        self.flushUndo()
        self.assertIs(self.skin.mirrorWeights(), self.skin)
        for index in self.minus:
            self.assertSequenceAlmostEqual(self.row(index), [0.0, 0.0, 1.0], places=6)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibSkinClusterMirrorWeights")
        cmds.undo()
        self.assertEqual([self.row(i) for i in self.minus], before)

    def test_negative_to_positive(self):
        """positiveToNegative=False は -X 側(中央の joint)を +X 側へ写す。"""
        self.skin.mirrorWeights("YZ", positiveToNegative=False, influenceAssociation="closestJoint")
        for index in self.plus:
            self.assertSequenceAlmostEqual(self.row(index), [1.0, 0.0, 0.0], places=6)

    def test_argument_errors(self):
        cases = (
            ({"axis": "yz"}, ValueError),
            ({"axis": 0}, TypeError),
            ({"positiveToNegative": "yes"}, TypeError),
            ({"surfaceAssociation": "nearest"}, ValueError),
            ({"influenceAssociation": ()}, ValueError),
            ({"influenceAssociation": ("label", "name", "closestJoint", "oneToOne")}, ValueError),
            ({"influenceAssociation": ("label", "label")}, ValueError),
            ({"influenceAssociation": ("byName",)}, ValueError),
            ({"influenceAssociation": 1}, TypeError),
            ({"normalize": 1}, TypeError),
        )
        for kwargs, error in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(error):
                    self.skin.mirrorWeights(**kwargs)


class CopyWeightsToGeometryTest(NamespaceCase):
    """copyWeightsTo へ形状・Transform を渡す。"""

    PREFIX = "mlibSpecSkinCopyGeo_"
    CLEAR_SELECTION = True

    def setUp(self):
        super().setUp()
        cmds.select(clear=True)
        self.root = cmds.joint(name=self.name("root"), position=(0, 0, 0))
        self.tip = cmds.joint(name=self.name("tip"), position=(0, 2, 0))
        cmds.select(clear=True)
        self.source = cmds.polyCylinder(name=self.name("source"), height=2, subdivisionsHeight=4)[0]
        cmds.move(0, 1, 0, self.source)
        self.skin = SkinCluster(cmds.skinCluster(self.root, self.tip, self.source, toSelectedBones=True,
                                                 maximumInfluences=2)[0])
        cmds.skinPercent(self.skin.getFullName(), self.source + ".vtx[*]", transformValue=[(self.root, 1.0)])
        cmds.skinPercent(self.skin.getFullName(), [self.source + ".vtx[80:99]", self.source + ".vtx[101]"],
                         transformValue=[(self.tip, 1.0)])
        self.target = cmds.polyCylinder(name=self.name("target"), height=2, subdivisionsHeight=4,
                                        subdivisionsAxis=10)[0]
        cmds.move(0, 1, 0, self.target)
        cmds.select(clear=True)

    def weights(self, skin, index):
        return cmds.skinPercent(skin.getFullName(), "{}.vtx[{}]".format(self.target, index), query=True, value=True)

    def test_unbound_geometry_is_bound_then_copied(self):
        """未バインドの Transform・Shape は同じ influence でバインドしてから写し、Undo 1 回でバインドごと戻る。"""
        for label in ("transform", "shape"):
            with self.subTest(target=label):
                target = self.target if label == "transform" else Node(self.target).getShape()
                self.flushUndo()
                result = self.skin.copyWeightsTo(target)
                self.assertIsInstance(result, SkinCluster)
                self.assertTrue(result.deforms(self.target))
                self.assertEqual(sorted(n.getUuid() for n in result.getInfluences()),
                                 sorted(n.getUuid() for n in self.skin.getInfluences()))
                self.assertEqual(result.getMaxInfluences(), 2)
                self.assertSequenceAlmostEqual(self.weights(result, 5), [1.0, 0.0], places=6)
                self.assertSequenceAlmostEqual(self.weights(result, 45), [0.0, 1.0], places=6)
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibSkinClusterCopyWeightsTo")
                cmds.undo()
                self.assertFalse(Node(self.target).getSkinClusters())
                self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_bound_geometry_uses_its_skinCluster(self):
        """既にバインド済みの形状はその skinCluster へ写す。"""
        existing = SkinCluster(cmds.skinCluster(self.root, self.tip, self.target, toSelectedBones=True)[0])
        result = self.skin.copyWeightsTo(self.target)
        self.assertEqual(result.getUuid(), existing.getUuid())
        self.assertSequenceAlmostEqual(self.weights(result, 45), [0.0, 1.0], places=6)


if __name__ == "__main__":
    unittest.main()
