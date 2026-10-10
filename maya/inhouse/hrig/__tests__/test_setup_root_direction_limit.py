"""根元方向制約を、独立した行列計算と姿勢遷移で検証する。"""

import math
import random
import tempfile
import unittest
from pathlib import Path

from maya import cmds
from maya.api import OpenMaya as om

from hrig.setups import RootDirectionLimit


class RootDirectionLimitTest(unittest.TestCase):
    """cone、取付位置、退化時、保存、Undoを実DGで確認する。"""

    def setUp(self):
        """独立した腕参照と胴体guideを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg")
        self.group = cmds.createNode("transform", name="character")
        self.guides = []
        for index, y in enumerate((0, 5, 10)):
            node = cmds.createNode("transform", name="body{}".format(index), parent=self.group)
            cmds.setAttr(node + ".ty", y)
            self.guides.append(node)
        self.source = cmds.createNode("transform", name="socket", parent=self.group)
        cmds.setAttr(self.source + ".translate", 5, 7, 0)

    def build(self, **kwargs):
        """新しいグラフを構築する。

        Args:
            **kwargs: createへ渡す設定。

        Returns:
            RootDirectionLimit: 作成したグラフ。
        """
        return RootDirectionLimit.create(self.source, self.guides, **kwargs)

    def assertState(self, graph, angle=45, aim="x"):
        """出力行列の方向・位置・直交性を独立に照合する。

        Args:
            graph (RootDirectionLimit): 検証対象。
            angle (float): 半角、度。
            aim (str): 符号付きの出力長手軸。

        Returns:
            MMatrix: 現在の出力行列。
        """
        matrix = om.MMatrix(cmds.getAttr(graph.output.getFullName() + ".worldMatrix[0]"))
        source = om.MMatrix(cmds.getAttr(self.source + ".worldMatrix[0]"))
        self.assertTrue(all(math.isfinite(v) for v in matrix))
        self.assertLess((om.MVector(*tuple(matrix)[12:15]) - om.MVector(*tuple(source)[12:15])).length(), 2e-4)
        reference = om.MMatrix(cmds.getAttr(self.guides[0] + ".worldMatrix[0]"))
        n = om.MVector(*cmds.getAttr(graph.container.getFullName() + ".outward")[0])
        n = (n * reference).normal()
        axis = "xyz".index(aim[-1])
        direction = om.MVector(*tuple(matrix)[axis * 4:axis * 4 + 3]).normal()
        if aim.startswith("-"):
            direction *= -1
        self.assertGreaterEqual(direction * n, math.cos(math.radians(angle)) - 2e-5)
        rows = [om.MVector(*tuple(matrix)[index * 4:index * 4 + 3]).normal() for index in range(3)]
        self.assertLess(max(abs(rows[a] * rows[b]) for a, b in ((0, 1), (1, 2), (2, 0))), 1e-5)
        self.assertGreater((rows[0] ^ rows[1]) * rows[2], 0.99999)
        return matrix

    def test_random_poses_and_antipodes(self):
        """大回転・真逆・境界とランダム姿勢を確認する。"""
        graph = self.build()
        rng = random.Random(2718)
        poses = [(0, 0, 0), (0, 180, 0), (180, 0, 0), (0, 45, 0), (0, -45, 0)]
        poses += [tuple(rng.uniform(-360, 360) for _ in range(3)) for _ in range(160)]
        for rotation in poses:
            cmds.setAttr(self.source + ".rotate", *rotation)
            self.assertState(graph)

    def test_body_bend_moves_reference(self):
        """腹・胸が動くと方向が更新され、常にcone条件を満たす。"""
        graph = self.build()
        before = cmds.getAttr(graph.container.getFullName() + ".outward")[0]
        cmds.setAttr(self.source + ".ry", 180)
        for bend in range(-80, 81, 4):
            cmds.setAttr(self.guides[1] + ".translate", 1, 5, bend / 30)
            cmds.setAttr(self.guides[1] + ".rx", bend / 2)
            cmds.setAttr(self.guides[2] + ".translate", 2, 8, bend / 10)
            cmds.setAttr(self.guides[2] + ".rx", bend)
            self.assertState(graph)
        after = cmds.getAttr(graph.container.getFullName() + ".outward")[0]
        self.assertGreater(sum((a - b) ** 2 for a, b in zip(before, after)), 1e-3)

    def test_safe_direction_is_kept(self):
        """安全範囲では元の長手方向を保ち、固定の外向きに潰さない。"""
        graph = self.build()
        for degrees in (-30, -15, 0, 15, 30):
            cmds.setAttr(self.source + ".ry", degrees)
            output = self.assertState(graph)
            source = om.MMatrix(cmds.getAttr(self.source + ".worldMatrix[0]"))
            a = om.MVector(*tuple(output)[:3]).normal()
            b = om.MVector(*tuple(source)[:3]).normal()
            self.assertGreater(a * b, 0.99999)

    def test_evaluation_modes_and_frame_jumps(self):
        """DG/Serial/Parallelと任意フレームジャンプで同じ結果になる。"""
        graph = self.build()
        for frame, rotation, bend in ((1, -220, 0), (24, 0, 40), (48, 220, -40), (96, 0, 10)):
            cmds.setKeyframe(self.source, attribute="ry", time=frame, value=rotation)
            cmds.setKeyframe(self.guides[1], attribute="rx", time=frame, value=bend)
        frames = (1, 48, 24, 96, 17, 70, 3, 95, 32)
        previous_mode = cmds.evaluationManager(query=True, mode=True)[0]
        expected = {}
        try:
            for mode in ("off", "serial", "parallel"):
                cmds.evaluationManager(mode=mode)
                for frame in frames:
                    cmds.currentTime(frame)
                    matrix = self.assertState(graph)
                    if mode == "off":
                        expected[frame] = tuple(matrix)
                    else:
                        self.assertLess(max(abs(a - b) for a, b in zip(matrix, expected[frame])), 1e-5)
        finally:
            cmds.evaluationManager(mode=previous_mode)

    def test_crossing_180_is_continuous(self):
        """反平行付近を細かく動かし、回転の跳びがないことを確認する。"""
        graph = self.build()
        previous = None
        for degrees in [179.5 + i * 0.002 for i in range(501)]:
            cmds.setAttr(self.source + ".ry", degrees)
            matrix = self.assertState(graph)
            q = om.MTransformationMatrix(matrix).rotation(asQuaternion=True)
            if previous is not None:
                dot = abs(sum(a * b for a, b in zip(q, previous)))
                self.assertLess(2 * math.acos(min(1, dot)), math.radians(0.01))
            previous = q

    def test_guide_and_radial_degeneracy(self):
        """中心線上・guide縮退・折返しでも有限の姿勢を返す。"""
        graph = self.build()
        for point in ((0, 5, 0), (0, 0, 0), (0.000001, 5, 0), (5, 10000, 0)):
            cmds.setAttr(self.source + ".translate", *point)
            self.assertState(graph)
        for guide in self.guides:
            cmds.setAttr(guide + ".translate", 0, 0, 0)
        cmds.setAttr(self.guides[1] + ".rz", 180)
        self.assertState(graph)

    def test_common_transform_and_units(self):
        """共通TRS、m表示での構築、単位変更を確認する。"""
        cmds.currentUnit(linear="m", angle="rad")
        graph = self.build()
        for scale in (0.1, 1, 3):
            cmds.setAttr(self.group + ".scale", scale, scale, scale)
            cmds.setAttr(self.group + ".translate", 10, -2, 3)
            cmds.setAttr(self.group + ".rotate", 0.2, -0.6, 1.0)
            self.assertState(graph)
        matrix = self.assertState(graph)
        cmds.currentUnit(linear="mm", angle="deg")
        after = self.assertState(graph)
        self.assertLess(max(abs(a - b) for a, b in zip(matrix, after)), 1e-6)

    def test_signed_axes_and_live_angle(self):
        """符号付き軸の右手系とangle/softnessの編集を確認する。"""
        for index, aim in enumerate(("x", "-x", "y", "-y", "z", "-z")):
            graph = self.build(name="axis{}".format(index), aimAxis=aim,
                               upAxis="z" if aim.endswith("y") else "y")
            for angle in (1, 20, 45, 70, 89):
                graph.container.getPlug("angle").set(angle)
                for soft in (0, 0.02, 0.2):
                    graph.container.getPlug("softness").set(soft)
                    self.assertState(graph, angle, aim)

    def test_undo_redo_and_save(self):
        """構築の単一Undo、全メンバー所有、保存再読込を確認する。"""
        cmds.select(self.source)
        before = set(cmds.ls())
        graph = self.build()
        owner, output = graph.container.getFullName(), graph.output.getFullName()
        created = set(cmds.ls()) - before
        members = set(cmds.container(owner, query=True, nodeList=True))
        metadata = {node for node in created if cmds.nodeType(node) == "hyperLayout"}
        self.assertEqual(created - {owner} - metadata, members)
        cmds.undo()
        self.assertFalse(cmds.objExists(owner))
        cmds.redo()
        self.assertTrue(cmds.objExists(output))
        cmds.setAttr(self.source + ".ry", 180)
        matrix = self.assertState(graph)
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "root.ma")
            cmds.file(rename=path)
            cmds.file(save=True, type="mayaAscii")
            cmds.file(path, open=True, force=True)
            graph = RootDirectionLimit(owner)
            after = self.assertState(graph)
            self.assertLess(max(abs(a - b) for a, b in zip(matrix, after)), 1e-6)
        self.assertFalse(cmds.ls(type="expression"))
        self.assertFalse(cmds.ls(type="closestPointOnMesh"))

    def test_invalid_inputs_are_atomic(self):
        """不正入力で部分的な生成物を残さない。"""
        before = set(cmds.ls())
        for kwargs in ({"angle": 0}, {"angle": 90}, {"softness": -1},
                       {"aimAxis": "w"}, {"aimAxis": "y"}, {"bodySideAxis": "y"}):
            with self.assertRaises(ValueError):
                self.build(**kwargs)
            self.assertEqual(set(cmds.ls()), before)
        cmds.setAttr(self.source + ".sx", 2)
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual(set(cmds.ls()), before)
