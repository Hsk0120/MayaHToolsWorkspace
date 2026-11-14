"""WaveFloatの波の変位・面の傾き・時刻の扱いを、独立に求めた期待値(接線は差分近似)と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import WaveFloat

WAVES = ((0.6, 9.0, 0.0, 0.6, 0.15), (0.35, 5.0, 50.0, 0.4, 0.1), (0.2, 13.0, -120.0, 0.8, 0.05))


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _translation(vector):
    """位置だけの行列。"""
    return om.MMatrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, vector[0], vector[1], vector[2], 1])


def _offset(x, z, time, waves, drift):
    """波の変位を独立に計算する(各波は x0 の点が楕円の軌道を回る形)。"""
    result = om.MVector()
    for amplitude, wavelength, direction, steepness, speed in waves:
        heading = om.MVector(1, 0, 0).rotateBy(om.MVector.kYaxis, math.radians(direction))
        phase = 2.0 * math.pi / wavelength * (heading.x * x + heading.z * z - speed * time)
        result += heading * (steepness * drift * amplitude * math.cos(phase))
        result += om.MVector(0, amplitude * math.sin(phase), 0)
    return result


def _surfacePoint(x, z, time, waves, drift):
    """静かな水面の点(x, 0, z)が波で動いた先。"""
    return om.MVector(x, 0, z) + _offset(x, z, time, waves, drift)


class WaveFloatTest(unittest.TestCase):
    """作成時の姿勢・波の位置と傾き・割合・進む波・時刻の接続・所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転した親の下に、傾けたコントロールを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm", time="film")
        self.root = cmds.createNode("transform", name="root")
        cmds.setAttr(self.root + ".rotateY", 25)
        cmds.setAttr(self.root + ".translate", 1, 2, -1)
        self.control = cmds.createNode("transform", name="boat", parent=self.root)
        cmds.setAttr(self.control + ".translate", 2.5, 0.5, -1.5)
        cmds.setAttr(self.control + ".rotate", 4, 70, -6)

    def build(self, waves=WAVES, **kwargs):
        """セットアップを作り、波のアトリビュートを設定して、matrixを受ける結果transformを作る。"""
        owner = str(WaveFloat.create(self.control, count=len(waves), **kwargs).container)
        for index, values in enumerate(waves):
            for attr, value in zip(("amplitude", "wavelength", "direction", "steepness", "speed"), values):
                cmds.setAttr("{}.{}{}".format(owner, attr, index), value)
        result = cmds.createNode("transform", name="result")
        cmds.connectAttr(owner + ".matrix", result + ".offsetParentMatrix")
        return owner, result

    def waves(self, owner):
        """containerの現在の波の値。"""
        count = len([attr for attr in cmds.listAttr(owner, userDefined=True) if attr.startswith("amplitude")])
        return [tuple(cmds.getAttr("{}.{}{}".format(owner, attr, index))
                      for attr in ("amplitude", "wavelength", "direction", "steepness", "speed"))
                for index in range(count)]

    def expected(self, owner):
        """現在のコントロールと波から、出力のワールド行列・heave・法線を独立に計算する。"""
        waves = self.waves(owner)
        time, tilt, drift = (cmds.getAttr(owner + "." + attr) for attr in ("time", "tilt", "drift"))
        world = _matrix(self.control + ".worldMatrix[0]")
        p = om.MVector(world[12], world[13], world[14])
        offset = _offset(p.x, p.z, time, waves, drift)
        step = 1e-4
        tangent_x = (_surfacePoint(p.x + step, p.z, time, waves, drift)
                     - _surfacePoint(p.x - step, p.z, time, waves, drift)) / (2 * step)
        tangent_z = (_surfacePoint(p.x, p.z + step, time, waves, drift)
                     - _surfacePoint(p.x, p.z - step, time, waves, drift)) / (2 * step)
        normal = (tangent_z ^ tangent_x).normal()
        x = tangent_x.normal()
        z = x ^ normal
        rotation = om.MMatrix([x.x, x.y, x.z, 0, normal.x, normal.y, normal.z, 0, z.x, z.y, z.z, 0, 0, 0, 0, 1])
        quaternion = om.MQuaternion.slerp(om.MQuaternion(), om.MTransformationMatrix(rotation).rotation(True), tilt)
        matrix = world * _translation(-p) * quaternion.asMatrix() * _translation(p + offset)
        return matrix, offset.y, normal

    def assertMatches(self, owner, result, places=4):
        """出力の行列・結果transform・heave・normalを期待値と比較する。"""
        matrix, heave, normal = self.expected(owner)
        actual = _matrix(owner + ".matrix")
        world = _matrix(result + ".worldMatrix[0]")
        for index in range(16):
            self.assertAlmostEqual(actual[index], matrix[index], places=places)
            self.assertAlmostEqual(world[index], matrix[index], places=places)
        self.assertAlmostEqual(cmds.getAttr(owner + ".heave"), heave, places=places)
        for value, expected in zip(cmds.getAttr(owner + ".normal")[0], normal):
            self.assertAlmostEqual(value, expected, places=places)

    def test_rest_pose_does_not_jump(self):
        """既定の振幅0では、時刻・割合に関わらず出力がコントロールのワールド行列と一致する。"""
        owner = str(WaveFloat.create(self.control, count=3, connectTime=True).container)
        for frame in (1, 37):
            cmds.currentTime(frame)
            actual = _matrix(owner + ".matrix")
            world = _matrix(self.control + ".worldMatrix[0]")
            for index in range(16):
                self.assertAlmostEqual(actual[index], world[index], places=5)
            self.assertAlmostEqual(cmds.getAttr(owner + ".heave"), 0.0, places=6)

    def test_matches_independent_surface(self):
        """複数の時刻・位置・コントロールの向きで、差分近似の接線から求めた面と一致する。"""
        owner, result = self.build()
        for time, translate, rotate in ((0.0, (2.5, 0.5, -1.5), (4, 70, -6)), (17.0, (-4, 1, 3), (0, -30, 0)),
                                        (63.5, (8, -0.5, 6), (10, 140, 5))):
            cmds.setAttr(owner + ".time", time)
            cmds.setAttr(self.control + ".translate", *translate)
            cmds.setAttr(self.control + ".rotate", *rotate)
            self.assertMatches(owner, result)
        # 傾きが十分に出ていること(平らな結果と取り違えていない)。
        self.assertLess(cmds.getAttr(owner + ".normalY"), 0.999)

    def test_ratios(self):
        """tilt=0は向きを変えず移動だけ、drift=0は上下だけ、途中の値は独立計算と一致する。"""
        owner, result = self.build()
        cmds.setAttr(owner + ".time", 11)
        world = _matrix(self.control + ".worldMatrix[0]")
        cmds.setAttr(owner + ".tilt", 0)
        actual = _matrix(owner + ".matrix")
        for index in range(12):
            self.assertAlmostEqual(actual[index], world[index], places=5)
        self.assertMatches(owner, result)
        cmds.setAttr(owner + ".drift", 0)
        actual = _matrix(owner + ".matrix")
        self.assertAlmostEqual(actual[12], world[12], places=5)
        self.assertAlmostEqual(actual[14], world[14], places=5)
        self.assertNotAlmostEqual(actual[13], world[13], places=3)
        cmds.setAttr(owner + ".tilt", 0.4)
        cmds.setAttr(owner + ".drift", 0.7)
        self.assertMatches(owner, result)

    def test_python_formula_and_travelling_wave(self):
        """surface()がDGと一致し、1つの波は speed*time だけ向きDへ進む(同じ形が平行に動く)。"""
        waves = (WAVES[1],)
        owner, _ = self.build(waves=waves)
        cmds.setAttr(owner + ".time", 20)
        world = _matrix(self.control + ".worldMatrix[0]")
        offset, _, _ = WaveFloat.surface(world[12], world[14], 20, waves)
        self.assertAlmostEqual(cmds.getAttr(owner + ".heave"), offset[1], places=5)
        heave = cmds.getAttr(owner + ".heave")
        amplitude, _, direction, _, speed = waves[0]
        heading = om.MVector(1, 0, 0).rotateBy(om.MVector.kYaxis, math.radians(direction))
        cmds.setAttr(owner + ".time", 20 + 30)
        moved = om.MVector(world[12], world[13], world[14]) + heading * (speed * 30)
        cmds.move(moved.x, moved.y, moved.z, self.control, worldSpace=True, absolute=True)
        self.assertAlmostEqual(cmds.getAttr(owner + ".heave"), heave, places=4)
        self.assertLessEqual(abs(heave), amplitude + 1e-6)

    def test_time_connection(self):
        """connectTime=Trueでtimeが現在のフレームに追従し、フレームを戻すと同じ姿勢になる(積分しない)。"""
        owner, result = self.build(connectTime=True)
        cmds.currentTime(24)
        self.assertAlmostEqual(cmds.getAttr(owner + ".time"), 24.0, places=6)
        first = _matrix(owner + ".matrix")
        self.assertMatches(owner, result)
        cmds.currentTime(80)
        self.assertMatches(owner, result)
        cmds.currentTime(24)
        again = _matrix(owner + ".matrix")
        for index in range(16):
            self.assertAlmostEqual(again[index], first[index], places=6)

    def test_ownership_and_undo(self):
        """生成ノードがcontainerに所有され、Undoで全体が消え、Redoで戻る。"""
        before = set(cmds.ls())
        owner = str(WaveFloat.create(self.control, name="undoFloat", connectTime=True).container)
        members = {node for node in cmds.container(owner, query=True, nodeList=True) or []
                   if cmds.nodeType(node) != "hyperLayout"}
        created = {node for node in set(cmds.ls()) - before - {owner} if cmds.nodeType(node) != "hyperLayout"}
        self.assertEqual({cmds.ls(node)[0] for node in members}, created)
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoFloat"))

    def test_invalid_arguments(self):
        """transform以外・範囲外の数と割合・既存の名前を拒否する。"""
        material = cmds.createNode("lambert")
        with self.assertRaises(ValueError):
            WaveFloat.create(material)
        for count in (0, 9, 2.0, True):
            with self.assertRaises(ValueError):
                WaveFloat.create(self.control, count=count)
        for kwargs in ({"tilt": 1.5}, {"drift": -0.1}, {"tilt": float("nan")}):
            with self.assertRaises(ValueError):
                WaveFloat.create(self.control, **kwargs)
        WaveFloat.create(self.control, name="taken")
        with self.assertRaises(ValueError):
            WaveFloat.create(self.control, name="taken")


if __name__ == "__main__":
    unittest.main()
