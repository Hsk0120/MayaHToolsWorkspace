"""RotationMinimizingFramesの回転最小化フレームを、Pythonの式・平面曲線の性質・細かい分割の参照と比べる。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import RotationMinimizingFrames


def _helix(count, radius=5.0, pitch=3.0, turns=1.2, start=0.0):
    """らせん上のcount点。"""
    points = []
    for index in range(count):
        a = start + 2 * math.pi * turns * index / (count - 1)
        points.append([radius * math.cos(a), pitch * a, radius * math.sin(a)])
    return points


class RotationMinimizingFramesTest(unittest.TestCase):
    """標準ノードの数値評価・回転最小化の性質・作成時の姿勢・引数検査を確認する。"""

    def setUp(self):
        """世界直下に、らせんに沿って並んだ9つのtransformを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.nodes = []
        for index, point in enumerate(_helix(9)):
            node = cmds.createNode("transform", name="point{}".format(index))
            cmds.setAttr(node + ".translate", *point)
            self.nodes.append(node)
        cmds.setAttr(self.nodes[0] + ".rotate", 10, 20, 0)

    def move(self, points):
        """各transformを指定の位置へ動かす。"""
        for node, point in zip(self.nodes, points):
            cmds.setAttr(node + ".translate", *point)

    def outputs(self, owner):
        """各出力のワールド行列。"""
        return [om.MMatrix(cmds.getAttr("{}.matrix{}".format(owner, i))) for i in range(len(self.nodes))]

    def points(self):
        """各transformのワールド位置。"""
        return [cmds.xform(node, q=True, worldSpace=True, translation=True) for node in self.nodes]

    def up(self):
        """最初のtransformのワールドのY軸。"""
        matrix = om.MMatrix(cmds.getAttr(self.nodes[0] + ".worldMatrix[0]"))
        return [matrix[4], matrix[5], matrix[6]]

    def checkFrames(self, owner):
        """keepOffset=Falseの出力の各行が、Python版の(t, r, t×r)と位置に一致し、正規直交であることを確認する。"""
        expected = RotationMinimizingFrames.frames(self.points(), self.up())
        for matrix, (t, r), point in zip(self.outputs(owner), expected, self.points()):
            rows = [om.MVector(matrix[4 * i], matrix[4 * i + 1], matrix[4 * i + 2]) for i in range(4)]
            self.assertTrue(rows[0].isEquivalent(om.MVector(t), 1e-4))
            self.assertTrue(rows[1].isEquivalent(om.MVector(r), 1e-4))
            self.assertTrue(rows[2].isEquivalent(om.MVector(t) ^ om.MVector(r), 1e-4))
            self.assertTrue(rows[3].isEquivalent(om.MVector(point), 1e-4))
            for i in range(3):
                self.assertAlmostEqual(rows[i].length(), 1.0, places=4)
                self.assertAlmostEqual(rows[i] * rows[(i + 1) % 3], 0.0, places=4)
        return expected

    def test_rest_pose_does_not_jump(self):
        """keepOffset=Trueでは、生成直後の出力が各transformのワールド行列と一致する。"""
        owner = RotationMinimizingFrames.create(self.nodes).container
        for node, matrix in zip(self.nodes, self.outputs(owner)):
            self.assertTrue(matrix.isEquivalent(om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]")), 1e-4))

    def test_matches_double_reflection(self):
        """点を動かしても、DGのフレームがdouble reflectionのPython版と一致する。"""
        owner = RotationMinimizingFrames.create(self.nodes, keepOffset=False).container
        self.checkFrames(owner)
        for points in (_helix(9, radius=3, pitch=5, turns=0.8), _helix(9, radius=6, pitch=1, turns=1.5, start=1.0),
                       [[i * 2.0, math.sin(i) * 3, 0.5 * i * i] for i in range(9)]):
            self.move(points)
            self.checkFrames(owner)

    def test_planar_curve_keeps_normal(self):
        """平面曲線で最初の基準ベクトルが平面の法線なら、全ての点で法線のまま(回転最小化の性質)。"""
        cmds.setAttr(self.nodes[0] + ".rotate", 0, 0, 0)
        owner = RotationMinimizingFrames.create(self.nodes, keepOffset=False).container
        self.move([[8 * math.cos(a), 0.0, 8 * math.sin(a)] for a in (i * 0.5 for i in range(9))])
        for matrix in self.outputs(owner):
            reference = om.MVector(matrix[4], matrix[5], matrix[6])
            self.assertAlmostEqual(abs(reference.y), 1.0, places=5)

    def test_close_to_fine_reference(self):
        """粗い点列(1点あたり約54度回る)でも、20倍に細かく分割した参照とのねじれの増え方の差が1度未満。"""
        owner = RotationMinimizingFrames.create(self.nodes, keepOffset=False).container
        fine = _helix(161)
        up = self.up()
        reference = RotationMinimizingFrames.frames(fine, up)
        twists = []
        for index, matrix in enumerate(self.outputs(owner)):
            t = om.MVector(matrix[0], matrix[1], matrix[2])
            r = om.MVector(matrix[4], matrix[5], matrix[6])
            fine_t, fine_r = (om.MVector(v) for v in reference[index * 20])
            # 接線の差分近似の違いを除くため、参照のフレームを接線が重なる最小の回転で合わせてから、
            # 接線まわりのねじれの差だけを比べる。
            aligned = fine_r.rotateBy(om.MQuaternion(fine_t, t))
            twists.append(math.degrees(r.angle(aligned)))
        print("twist difference to fine reference (deg):", ["{:.3f}".format(v) for v in twists])
        # 最初の基準ベクトルは接線の近似が違うと一定量ずれるため、2点目からのねじれの増え方を比べる。
        # 両端は片側差分の接線で近似が粗いので除き、間の点(中心差分)だけで判定する。
        interior = twists[1:-1]
        self.assertLess(max(interior) - min(interior), 1.0)

    def test_no_flip_when_tangent_passes_up(self):
        """接線が真上を通って曲がっても、隣り合う基準ベクトルの角度は接線の曲がりを超えない(裏返らない)。"""
        cmds.setAttr(self.nodes[0] + ".rotate", 0, 0, 0)
        owner = RotationMinimizingFrames.create(self.nodes, keepOffset=False).container
        # 横向きから真上を通り反対の横向きへ曲がる半円。
        self.move([[-6 * math.cos(a), 6 * math.sin(a), 0.3 * math.sin(3 * a)] for a in
                   (math.pi * i / 8 for i in range(9))])
        frames = self.checkFrames(owner)
        for (t0, r0), (t1, r1) in zip(frames, frames[1:]):
            turn = math.degrees(om.MVector(t0).angle(om.MVector(t1)))
            self.assertLessEqual(math.degrees(om.MVector(r0).angle(om.MVector(r1))), turn + 1e-3)

    def test_root_twist_propagates(self):
        """最初のtransformを接線まわりにねじると、全てのフレームが同じ角度だけねじれる。"""
        cmds.setAttr(self.nodes[0] + ".rotate", 0, 0, 0)
        owner = RotationMinimizingFrames.create(self.nodes, keepOffset=False).container
        before = self.outputs(owner)
        tangent = om.MVector(before[0][0], before[0][1], before[0][2])
        rotation = om.MQuaternion(math.radians(30), tangent)
        euler = rotation.asEulerRotation()
        cmds.setAttr(self.nodes[0] + ".rotate", *[math.degrees(v) for v in (euler.x, euler.y, euler.z)])
        after = self.outputs(owner)
        for m0, m1 in zip(before, after):
            r0 = om.MVector(m0[4], m0[5], m0[6])
            r1 = om.MVector(m1[4], m1[5], m1[6])
            self.assertAlmostEqual(math.degrees(r0.angle(r1)), 30.0, places=2)

    def test_length_units(self):
        """UIの長さ単位がmでも、出力の位置はcmのまま。"""
        owner = RotationMinimizingFrames.create(self.nodes, keepOffset=False).container
        expected = self.outputs(owner)
        cmds.currentUnit(linear="m")
        try:
            for a, b in zip(expected, self.outputs(owner)):
                self.assertTrue(a.isEquivalent(b, 1e-5))
        finally:
            cmds.currentUnit(linear="cm")

    def test_invalid_arguments(self):
        """数・軸・同じ位置・既存の名前を拒否する。"""
        with self.assertRaises(ValueError):
            RotationMinimizingFrames.create(self.nodes[:2])
        with self.assertRaises(ValueError):
            RotationMinimizingFrames.create(self.nodes, upAxis="w")
        with self.assertRaises(ValueError):
            RotationMinimizingFrames.create([self.nodes[0], self.nodes[0], self.nodes[1]])
        same = cmds.createNode("transform", name="samePlace")
        cmds.setAttr(same + ".translate", *cmds.getAttr(self.nodes[1] + ".translate")[0])
        with self.assertRaises(ValueError):
            RotationMinimizingFrames.create([self.nodes[0], self.nodes[1], same])
        RotationMinimizingFrames.create(self.nodes, name="taken")
        with self.assertRaises(ValueError):
            RotationMinimizingFrames.create(self.nodes, name="taken")

    def test_undo_removes_graph(self):
        """生成を1回のUndoで取り消せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        RotationMinimizingFrames.create(self.nodes, name="undoFrames")
        self.assertTrue(cmds.objExists("undoFrames"))
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


class CurveRotationMinimizingFramesTest(unittest.TestCase):
    """fromCurve(曲線の接線を使う版)の数値評価・曲線の変形・上方向・引数検査を確認する。"""

    COUNT = 7

    def setUp(self):
        """回転・移動したtransformの下に、3次元に曲がった3次のNURBS曲線を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        points = [(0, 0, 0), (3, 4, 1), (6, 2, 5), (9, -3, 4), (12, 1, 0), (15, 5, -2)]
        self.curve = cmds.curve(name="spineCurve", degree=3, point=points)
        cmds.setAttr(self.curve + ".rotate", 15, -30, 10)
        cmds.setAttr(self.curve + ".translate", 2, 3, -1)

    def samples(self):
        """各点のワールド位置と曲線の接線(cmds.pointOnCurveで独立に求める。transformを渡すとワールドの値を返す)。"""
        points, tangents = [], []
        for index in range(self.COUNT):
            u = index / float(self.COUNT - 1)
            points.append(cmds.pointOnCurve(self.curve, parameter=u, turnOnPercentage=True, position=True))
            tangents.append(cmds.pointOnCurve(self.curve, parameter=u, turnOnPercentage=True, normalizedTangent=True))
        return points, tangents

    def test_samples_are_world(self):
        """比較に使うpointOnCurveの値がワールドであることを、CVのワールド位置で確かめる(端点は最初のCV)。"""
        first = cmds.xform(self.curve + ".cv[0]", q=True, worldSpace=True, translation=True)
        self.assertTrue(om.MVector(self.samples()[0][0]).isEquivalent(om.MVector(first), 1e-4))

    def check(self, owner, up):
        """DGの各フレームが、曲線の接線を使うPython版のdouble reflectionと一致することを確認する。"""
        points, tangents = self.samples()
        expected = RotationMinimizingFrames.frames(points, up, tangents)
        for index, ((t, r), point) in enumerate(zip(expected, points)):
            matrix = om.MMatrix(cmds.getAttr("{}.matrix{}".format(owner, index)))
            rows = [om.MVector(matrix[4 * i], matrix[4 * i + 1], matrix[4 * i + 2]) for i in range(4)]
            self.assertTrue(rows[0].isEquivalent(om.MVector(t), 1e-4), index)
            self.assertTrue(rows[1].isEquivalent(om.MVector(r), 1e-4), index)
            self.assertTrue(rows[2].isEquivalent(om.MVector(t) ^ om.MVector(r), 1e-4), index)
            self.assertTrue(rows[3].isEquivalent(om.MVector(point), 1e-4), index)
            # 両端を含む全ての点で、Xは曲線の接線そのもの。
            self.assertTrue(rows[0].isEquivalent(om.MVector(tangents[index]).normal(), 1e-4), index)
        return expected

    def test_matches_curve_tangents(self):
        """曲線の位置・接線から、double reflectionのPython版と同じフレームになる。"""
        owner = RotationMinimizingFrames.fromCurve(self.curve, self.COUNT).container
        self.check(owner, [0.0, 1.0, 0.0])

    def test_follows_curve_deformation(self):
        """CVを動かして曲線が変形すると、フレームが追従する。"""
        owner = RotationMinimizingFrames.fromCurve(self.curve, self.COUNT, upVector=(0, 0, 1)).container
        for index, offset in ((2, (0, 6, -3)), (4, (-2, -5, 6)), (5, (3, 8, 2))):
            cmds.xform("{}.cv[{}]".format(self.curve, index), relative=True, objectSpace=True, translation=offset)
            self.check(owner, [0.0, 0.0, 1.0])

    def test_up_node_twist(self):
        """upNodeを最初の接線まわりにねじると、全てのフレームが同じ角度だけねじれる。"""
        control = cmds.createNode("transform", name="twistControl")
        owner = RotationMinimizingFrames.fromCurve(self.curve, self.COUNT, upNode=control, upAxis="y").container
        before = [om.MMatrix(cmds.getAttr("{}.matrix{}".format(owner, i))) for i in range(self.COUNT)]
        tangent = om.MVector(before[0][0], before[0][1], before[0][2])
        euler = om.MQuaternion(math.radians(40), tangent).asEulerRotation()
        cmds.setAttr(control + ".rotate", *[math.degrees(v) for v in (euler.x, euler.y, euler.z)])
        up = om.MVector(0, 1, 0) * om.MMatrix(cmds.getAttr(control + ".worldMatrix[0]"))
        self.check(owner, [up.x, up.y, up.z])
        for index in range(self.COUNT):
            after = om.MMatrix(cmds.getAttr("{}.matrix{}".format(owner, index)))
            r0 = om.MVector(before[index][4], before[index][5], before[index][6])
            r1 = om.MVector(after[4], after[5], after[6])
            self.assertAlmostEqual(math.degrees(r0.angle(r1)), 40.0, places=2)

    def test_planar_curve_keeps_normal(self):
        """平面上の曲線で上方向が平面の法線なら、全ての点で基準ベクトルは法線のまま。"""
        planar = cmds.curve(name="planarCurve", degree=3,
                            point=[(0, 0, 0), (4, 0, 6), (9, 0, 2), (12, 0, -5), (16, 0, 1)])
        owner = RotationMinimizingFrames.fromCurve(planar, 6, name="planar").container
        for index in range(6):
            matrix = om.MMatrix(cmds.getAttr("{}.matrix{}".format(owner, index)))
            self.assertAlmostEqual(abs(matrix[5]), 1.0, places=5)

    def test_length_units(self):
        """UIの長さ単位がmでも、出力の位置はcmのまま。"""
        owner = RotationMinimizingFrames.fromCurve(self.curve, self.COUNT).container
        expected = [om.MMatrix(cmds.getAttr("{}.matrix{}".format(owner, i))) for i in range(self.COUNT)]
        cmds.currentUnit(linear="m")
        try:
            for index in range(self.COUNT):
                actual = om.MMatrix(cmds.getAttr("{}.matrix{}".format(owner, index)))
                self.assertTrue(actual.isEquivalent(expected[index], 1e-5))
        finally:
            cmds.currentUnit(linear="cm")

    def test_invalid_arguments(self):
        """点の数・曲線でないノード・上方向・軸・既存の名前を拒否する。"""
        for kwargs in ({"count": 2}, {"count": 4.0}, {"count": 5, "upVector": (0, 0, 0)},
                       {"count": 5, "upAxis": "w"}):
            count = kwargs.pop("count")
            with self.assertRaises(ValueError):
                RotationMinimizingFrames.fromCurve(self.curve, count, **kwargs)
        other = cmds.createNode("transform", name="notCurve")
        with self.assertRaises(ValueError):
            RotationMinimizingFrames.fromCurve(other, 5)
        RotationMinimizingFrames.fromCurve(self.curve, 5, name="taken")
        with self.assertRaises(ValueError):
            RotationMinimizingFrames.fromCurve(self.curve, 5, name="taken")

    def test_undo_removes_graph(self):
        """生成を1回のUndoで取り消せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        RotationMinimizingFrames.fromCurve(self.curve, 5, name="undoCurveFrames")
        self.assertTrue(cmds.objExists("undoCurveFrames"))
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main()
