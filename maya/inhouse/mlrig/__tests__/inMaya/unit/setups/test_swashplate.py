"""Swashplateのリンクの高さ・ピッチ角を、試験側で独立に書いた斜板の面とホーンの幾何で確かめる。"""

import math
import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import Swashplate

RADIUS = 2.0
HORN = 1.5
MAX_PITCH = 30.0
REACH = HORN * math.sin(math.radians(MAX_PITCH))
AXIS = (1.0, 2.0)


def _matrix(node):
    """ノードのワールドマトリクス。"""
    return om2.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))


class SwashplateTest(unittest.TestCase):
    """作成時・面の上のリンク・ホーン・コレクティブ・サイクリック・止めと復帰・Python版・linkAzimuth・向きと軸・Undo・引数を確認する。"""

    def setUp(self):
        """親(少し回して動かした空間)の下に、回転軸 (1, 2) のローターと高さ3の斜板、ローターの子に3枚のブレードを置く。
        ブレードは生成時に rotateX = 5 度の取り付け角を持つ。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.space = cmds.createNode("transform", name="heli")
        cmds.setAttr(self.space + ".translate", 4.0, 1.0, -2.0)
        cmds.setAttr(self.space + ".rotate", 10.0, 25.0, -5.0)
        self.rotor = cmds.createNode("transform", name="rotor", parent=self.space)
        cmds.setAttr(self.rotor + ".translate", AXIS[0], 6.0, AXIS[1])
        self.plate = cmds.createNode("transform", name="plate", parent=self.space)
        cmds.setAttr(self.plate + ".translate", AXIS[0] + 0.3, 3.0, AXIS[1] - 0.2)
        self.blades = []
        for index in range(3):
            blade = cmds.createNode("transform", name="blade%d" % index, parent=self.rotor)
            cmds.setAttr(blade + ".rotateY", -120.0 * index)
            cmds.setAttr(blade + ".rotateX", 5.0)
            self.blades.append(blade)
        self.setup = Swashplate.create(self.plate, self.rotor, self.blades, RADIUS, HORN, MAX_PITCH, name="swashRig")
        self.owner = str(self.setup.container)

    def _get(self, attribute, index=None):
        """containerの出力の値。"""
        return cmds.getAttr(self.owner + "." + attribute + ("" if index is None else "[%d]" % index))

    def _pose(self, height=3.0, tiltX=0.0, tiltZ=0.0, rotor=0.0):
        """斜板の高さ・傾き(度)とローターの回転(度)を入れる。"""
        cmds.setAttr(self.plate + ".translateY", height)
        cmds.setAttr(self.plate + ".rotateX", tiltX)
        cmds.setAttr(self.plate + ".rotateZ", tiltZ)
        cmds.setAttr(self.rotor + ".rotateY", rotor)

    def _linkPoint(self, index):
        """リンクの位置(親の空間)。方位角 ψ + linkAzimuth、軸から Rs、高さは neutralHeight + linkHeight。"""
        angle = self._get("azimuth", index) + self._get("linkAzimuth")
        angle = math.radians(angle)
        return om2.MPoint(AXIS[0] + RADIUS * math.cos(angle), self._get("neutralHeight") + self._get("linkHeight", index),
                          AXIS[1] - RADIUS * math.sin(angle))

    def test_rest(self):
        """生成時はブレードが跳ねず、コレクティブ・超過は0、固定値は Rs・L・maxPitch・N。"""
        for blade in self.blades:
            self.assertAlmostEqual(cmds.getAttr(blade + ".rotateX"), 5.0, places=6)
        self.assertAlmostEqual(self._get("collective"), 0.0, places=6)
        self.assertAlmostEqual(self._get("neutralHeight"), 3.0, places=6)
        self.assertAlmostEqual(self._get("linkRadius"), RADIUS, places=6)
        self.assertAlmostEqual(self._get("hornLength"), HORN, places=6)
        self.assertAlmostEqual(self._get("maxPitch"), MAX_PITCH, places=6)
        self.assertEqual(self._get("bladeCount"), 3)
        for index in range(3):
            self.assertAlmostEqual(self._get("linkHeight", index), 0.0, places=6)
            self.assertAlmostEqual(self._get("linkExcess", index), 0.0, places=6)

    def test_linkOnPlate(self):
        """リンクの位置は斜板の面の上(斜板のローカルで y = 0)にあり、ホーンの先の高さ L sin θ がリンクの高さに一致する。"""
        random.seed(3)
        for _ in range(12):
            self._pose(3.0 + random.uniform(-0.3, 0.3), random.uniform(-8, 8), random.uniform(-8, 8),
                       random.uniform(-360, 360))
            local = _matrix(self.space) * _matrix(self.plate).inverse()
            for index, blade in enumerate(self.blades):
                point = self._linkPoint(index) * local
                self.assertAlmostEqual(point.y, 0.0, places=6)
                pitch = math.radians(self._get("bladePitch", index))
                self.assertAlmostEqual(HORN * math.sin(pitch), self._get("linkHeight", index), places=6)
                self.assertAlmostEqual(cmds.getAttr(blade + ".rotateX"), 5.0 + math.degrees(pitch), places=5)
                self.assertAlmostEqual(self._get("azimuth", index),
                                       cmds.getAttr(self.rotor + ".rotateY") + 120.0 * index, places=5)

    def test_collective(self):
        """傾けずに上げると、すべてのブレードが同じ asin(h / L) になり、ローターを回しても変わらない。"""
        for rotor in (0.0, 47.0, 200.0):
            self._pose(3.4, rotor=rotor)
            self.assertAlmostEqual(self._get("collective"), 0.4, places=6)
            for index in range(3):
                self.assertAlmostEqual(self._get("linkHeight", index), 0.4, places=6)
                self.assertAlmostEqual(self._get("bladePitch", index), math.degrees(math.asin(0.4 / HORN)), places=5)

    def test_cyclic(self):
        """傾けると、ブレードのリンクの高さはローターの1回転で正弦の形に1周期変わり、等間隔の3枚の平均はコレクティブ。"""
        self._pose(3.2, tiltZ=6.0)
        heights = []
        for rotor in range(0, 360, 15):
            cmds.setAttr(self.rotor + ".rotateY", rotor)
            values = [self._get("linkHeight", index) for index in range(3)]
            self.assertAlmostEqual(sum(values) / 3.0, self._get("collective"), places=6)
            heights.append(values[0])
        # rotateZ の傾き: a = -tan 6°、b = 0 → y = G + Rs tan6° cos ψ(ψ = 0 で最大、180 で最小)
        amplitude = RADIUS * math.tan(math.radians(6.0))
        self.assertAlmostEqual(max(heights) - self._get("collective"), amplitude, places=5)
        self.assertEqual(heights.index(max(heights)), 0)
        self.assertEqual(heights.index(min(heights)), 12)

    def test_limitAndRecover(self):
        """リンクが ±L sin(maxPitch) を超えるとピッチは maxPitch で止まり超過を出し、戻すと超過0で元の角度に戻る。"""
        self._pose(3.0 + REACH + 0.5)
        for index, blade in enumerate(self.blades):
            self.assertAlmostEqual(self._get("bladePitch", index), MAX_PITCH, places=5)
            self.assertAlmostEqual(self._get("linkExcess", index), 0.5, places=5)
            self.assertAlmostEqual(cmds.getAttr(blade + ".rotateX"), 5.0 + MAX_PITCH, places=5)
        self._pose(3.0 - REACH - 0.25)
        for index in range(3):
            self.assertAlmostEqual(self._get("bladePitch", index), -MAX_PITCH, places=5)
            self.assertAlmostEqual(self._get("linkExcess", index), -0.25, places=5)
        self._pose(3.0)
        for index, blade in enumerate(self.blades):
            self.assertAlmostEqual(self._get("linkExcess", index), 0.0, places=6)
            self.assertAlmostEqual(cmds.getAttr(blade + ".rotateX"), 5.0, places=5)

    def test_pythonMatchesGraph(self):
        """motion はDGと同じ値を返す。"""
        random.seed(11)
        for _ in range(10):
            self._pose(3.0 + random.uniform(-1, 1), random.uniform(-10, 10), random.uniform(-10, 10),
                       random.uniform(-720, 720))
            cmds.setAttr(self.owner + ".linkAzimuth", random.uniform(-90, 90))
            matrix = cmds.getAttr(self.plate + ".matrix")
            result = Swashplate.motion(math.radians(cmds.getAttr(self.rotor + ".rotateY")), matrix[4:7], matrix[12:15],
                                       AXIS, RADIUS, HORN, 3, math.radians(self._get("linkAzimuth")), 3.0,
                                       math.radians(MAX_PITCH))
            self.assertAlmostEqual(result["collective"], self._get("collective"), places=6)
            self.assertAlmostEqual(result["tiltA"], self._get("tiltA"), places=6)
            self.assertAlmostEqual(result["tiltB"], self._get("tiltB"), places=6)
            for index in range(3):
                self.assertAlmostEqual(result["linkHeight"][index], self._get("linkHeight", index), places=6)
                self.assertAlmostEqual(result["linkExcess"][index], self._get("linkExcess", index), places=6)
                self.assertAlmostEqual(math.degrees(result["bladePitch"][index]), self._get("bladePitch", index),
                                       places=5)

    def test_linkAzimuth(self):
        """linkAzimuth を 90 度にすると、ローターを 90 度回したときのリンクの高さと同じになる(位相のずれ)。"""
        self._pose(3.1, tiltX=4.0, tiltZ=-3.0, rotor=90.0)
        expected = [self._get("linkHeight", index) for index in range(3)]
        cmds.setAttr(self.rotor + ".rotateY", 0.0)
        cmds.setAttr(self.owner + ".linkAzimuth", 90.0)
        for index in range(3):
            self.assertAlmostEqual(self._get("linkHeight", index), expected[index], places=6)

    def test_directionAndAxis(self):
        """pitchDirection = -1 と pitchAxis = z では、ピッチの増加が rotateZ の減少になる。"""
        cmds.file(new=True, force=True)
        plate = cmds.createNode("transform", name="plate2")
        rotor = cmds.createNode("transform", name="rotor2")
        blade = cmds.createNode("transform", name="bladeZ", parent=rotor)
        cmds.setAttr(blade + ".rotateZ", 2.0)
        setup = Swashplate.create(plate, rotor, [blade], RADIUS, HORN, name="swashZ", pitchAxis="z", pitchDirection=-1.0)
        cmds.setAttr(plate + ".translateY", 0.3)
        pitch = cmds.getAttr(str(setup.container) + ".bladePitch[0]")
        self.assertAlmostEqual(pitch, math.degrees(math.asin(0.3 / HORN)), places=5)
        self.assertAlmostEqual(cmds.getAttr(blade + ".rotateZ"), 2.0 - pitch, places=5)
        self.assertEqual(cmds.getAttr(blade + ".rotateX"), 0.0)

    def test_ownershipAndUndo(self):
        """演算ノードはcontainerが所有し、1回のUndoで作成全体とブレードの接続が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {node for node in cmds.ls() if node.startswith("swashRig_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        self.assertTrue(any(cmds.nodeType(member) == "rowFromMatrix" for member in members))
        cmds.file(new=True, force=True)
        plate = cmds.createNode("transform", name="undoPlate")
        rotor = cmds.createNode("transform", name="undoRotor")
        blade = cmds.createNode("transform", name="undoBlade", parent=rotor)
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        Swashplate.create(plate, rotor, [blade], name="swashUndo")
        self.assertTrue(cmds.listConnections(blade + ".rotateX", source=True, destination=False))
        cmds.undo()
        self.assertFalse(cmds.objExists("swashUndo"))
        self.assertEqual(set(cmds.ls()), before)
        self.assertFalse(cmds.listConnections(blade + ".rotateX", source=True, destination=False))
        cmds.redo()
        self.assertTrue(cmds.objExists("swashUndo.bladeRotate[0]"))

    def test_invalidArguments(self):
        """不正な引数は ValueError。"""
        other = cmds.createNode("transform", name="otherSpace")
        loose = cmds.createNode("transform", name="loosePlate", parent=other)
        free = cmds.createNode("transform", name="freeBlade")
        cases = [
            {"blades": []},
            {"blades": free},
            {"linkRadius": 0.0},
            {"hornLength": -1.0},
            {"maxPitch": 90.0},
            {"maxPitch": True},
            {"pitchAxis": "w"},
            {"pitchDirection": 0.5},
            {"name": self.owner},
            {"swashplate": loose},
            {"blades": [self.blades[0]]},
            {"blades": [self.rotor]},
        ]
        for case in cases:
            arguments = {"swashplate": self.plate, "rotor": self.rotor, "blades": [free], "name": "swashBad"}
            arguments.update(case)
            with self.subTest(case=case), self.assertRaises(ValueError):
                Swashplate.create(**arguments)
        cmds.setAttr(self.plate + ".rotateX", 120.0)
        with self.assertRaises(ValueError):
            Swashplate.create(self.plate, self.rotor, [free], name="swashDown")
        self.assertFalse(cmds.objExists("swashBad"))
        self.assertFalse(cmds.objExists("swashDown"))


if __name__ == "__main__":
    unittest.main()
