"""EyelidFollowのまぶたの追従・まばたき・交差防止を、OpenMayaで求めた期待値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import EyelidFollow

_ORDERS = {
    "xyz": om.MEulerRotation.kXYZ,
    "yzx": om.MEulerRotation.kYZX,
    "zxy": om.MEulerRotation.kZXY,
    "xzy": om.MEulerRotation.kXZY,
    "yxz": om.MEulerRotation.kYXZ,
    "zyx": om.MEulerRotation.kZYX,
}


def _local(node):
    """matrix * offsetParentMatrix。"""
    return om.MMatrix(cmds.getAttr(node + ".matrix")) * om.MMatrix(cmds.getAttr(node + ".offsetParentMatrix"))


def _rotation(matrix):
    """行列の回転をQuaternionで返す。"""
    return om.MTransformationMatrix(om.MMatrix(matrix)).rotation(asQuaternion=True)


def _euler(pitch, yaw, pitch_axis="x", yaw_axis="y"):
    """Pitchを先・Yawを後に回す回転行列(度)。"""
    roll = [a for a in "xyz" if a not in (pitch_axis, yaw_axis)][0]
    values = {pitch_axis: math.radians(pitch), yaw_axis: math.radians(yaw), roll: 0.0}
    return om.MEulerRotation(values["x"], values["y"], values["z"],
                             _ORDERS[pitch_axis + yaw_axis + roll]).asMatrix()


class EyelidFollowTest(unittest.TestCase):
    """標準ノードの数値評価・作成時の姿勢・まばたき・交差防止・引数検査を確認する。"""

    def setUp(self):
        """頭→目の空間の下に、目と上下のまぶた(回転中心は目の中心)を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.socket = cmds.createNode("transform", name="eyeSocket")
        cmds.setAttr(self.socket + ".translate", 3, 160, 8)
        cmds.setAttr(self.socket + ".rotate", 5, -8, 3)
        self.eye = cmds.createNode("joint", name="eye", parent=self.socket)
        self.upper = cmds.createNode("joint", name="upperLid", parent=self.socket)
        self.lower = cmds.createNode("joint", name="lowerLid", parent=self.socket)
        for node in (self.eye, self.upper, self.lower):
            cmds.setAttr(node + ".translate", 0.5, 0.2, 0.1)
        cmds.setAttr(self.upper + ".rotate", -12, 0, 0)
        cmds.setAttr(self.lower + ".rotate", 15, 0, 0)

    def build(self, **kwargs):
        """セットアップと、出力をoffsetParentMatrixで受ける結果transformを作る。"""
        owner = EyelidFollow.create(self.eye, self.upper, self.lower, **kwargs).container
        results = []
        for role in ("upper", "lower"):
            result = cmds.createNode("transform", name="result_" + role, parent=self.socket)
            cmds.connectAttr(str(owner) + "." + role + "Matrix", result + ".offsetParentMatrix")
            results.append(result)
        return owner, results

    def eyeAngles(self, rest, pitch_axis="x", yaw_axis="y"):
        """親空間での目の差分回転 rest^-1 * L をPitch先・Yaw後のEuler角(度)へ分解する。"""
        rest_rotation = _rotation(rest).asMatrix()
        current = _rotation(_local(self.eye)).asMatrix()
        delta = rest_rotation.inverse() * current
        roll = [a for a in "xyz" if a not in (pitch_axis, yaw_axis)][0]
        euler = om.MTransformationMatrix(delta).rotation()
        euler = euler.reorder(_ORDERS[pitch_axis + yaw_axis + roll])
        values = dict(zip("xyz", (math.degrees(euler.x), math.degrees(euler.y), math.degrees(euler.z))))
        return values[pitch_axis], values[yaw_axis]

    def check(self, owner, results, rest, places=3, pitch_axis="x", yaw_axis="y", **parameters):
        """スカラー出力と、上下のまぶたの出力行列を確認する。"""
        pitch, yaw = self.eyeAngles(rest, pitch_axis, yaw_axis)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".eyePitch"), pitch, places=places)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".eyeYaw"), yaw, places=places)
        expected = EyelidFollow.lidAngles(pitch, yaw, **parameters)
        for attr in ("upperAngle", "lowerAngle", "lidYaw", "gap"):
            self.assertAlmostEqual(cmds.getAttr(str(owner) + "." + attr), expected[attr], places=places)
        self.assertGreaterEqual(cmds.getAttr(str(owner) + ".gap"), -1e-6)
        for lid, result, angle in ((self.upper, results[0], "upperAngle"), (self.lower, results[1], "lowerAngle")):
            lid_local = _local(lid)
            rotation = _rotation(lid_local).asMatrix() * _euler(expected[angle], expected["lidYaw"],
                                                                pitch_axis, yaw_axis)
            transform = om.MTransformationMatrix(rotation)
            transform.setTranslation(om.MTransformationMatrix(lid_local).translation(om.MSpace.kTransform),
                                     om.MSpace.kTransform)
            actual = om.MMatrix(cmds.getAttr(result + ".offsetParentMatrix"))
            self.assertTrue(actual.isEquivalent(transform.asMatrix(), 1e-4), (lid, actual, transform.asMatrix()))
        return expected

    def test_rest_pose_does_not_jump(self):
        """生成直後の出力は、まぶたの入力と同じ行列になる。"""
        cmds.setAttr(self.eye + ".jointOrient", 4, 6, 0)
        cmds.setAttr(self.eye + ".rotate", 3, -7, 2)
        owner, results = self.build()
        for lid, result in ((self.upper, results[0]), (self.lower, results[1])):
            self.assertTrue(om.MMatrix(cmds.getAttr(result + ".offsetParentMatrix")).isEquivalent(_local(lid), 1e-5))
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".upperAngle"), 0.0, places=5)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".lowerAngle"), 0.0, places=5)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".gap"), 40.0, places=5)

    def test_follow_eye_pitch_and_yaw(self):
        """上下・左右を見ると、まぶたが式どおりの割合で追従する。"""
        owner, results = self.build(upperFollow=0.8, lowerFollow=0.4, yawFollow=0.1, openAngle=40)
        rest = _local(self.eye)
        for rotate in ((20, 0, 0), (-25, 0, 0), (0, 30, 0), (15, -35, 0), (-18, 25, 6)):
            cmds.setAttr(self.eye + ".rotate", *rotate)
            expected = self.check(owner, results, rest, upperFollow=0.8, lowerFollow=0.4, yawFollow=0.1,
                                  openAngle=40)
            if rotate[1] == 0 and rotate[2] == 0:
                # 単純なPitchでは、上は0.8倍・下は0.4倍の角度になる。
                self.assertAlmostEqual(expected["upperAngle"], 0.8 * rotate[0], places=4)
                self.assertAlmostEqual(expected["lowerAngle"], 0.4 * rotate[0], places=4)

    def test_eye_with_rest_orientation(self):
        """目の基準回転がある場合も、親空間での差分から角度を求める。"""
        cmds.setAttr(self.eye + ".jointOrient", 10, -20, 5)
        owner, results = self.build()
        rest = _local(self.eye)
        for rotate in ((15, 0, 0), (0, 20, 0), (-10, 12, 0)):
            cmds.setAttr(self.eye + ".rotate", *rotate)
            self.check(owner, results, rest)

    def test_blink_closes_and_meets(self):
        """blinkで上下の縁が閉じ、blinkHeightの位置で合う。"""
        owner, results = self.build(blinkHeight=0.25)
        rest = _local(self.eye)
        cmds.setAttr(self.eye + ".rotate", 10, 5, 0)
        for blink in (0.0, 0.5, 1.0):
            cmds.setAttr(str(owner) + ".blink", blink)
            expected = self.check(owner, results, rest, blink=blink, blinkHeight=0.25)
        self.assertAlmostEqual(expected["gap"], 0.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".gap"), 0.0, places=4)
        # 開いたときの開き(40 + (0.4-0.8)*10 = 36度)のうち、上が0.75、下が0.25を動く。
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".upperAngle"), 8 + 0.75 * 36, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".lowerAngle"), 4 - 0.25 * 36, places=3)

    def test_lids_never_cross(self):
        """追従の差で上が下を越える入力でも、開きは0で止まり、戻すと復帰する。"""
        owner, results = self.build(upperFollow=1.0, lowerFollow=0.0, openAngle=20)
        rest = _local(self.eye)
        parameters = {"upperFollow": 1.0, "lowerFollow": 0.0, "openAngle": 20}
        for pitch in (10, 20, 35, 60, 15, 0):
            cmds.setAttr(self.eye + ".rotate", pitch, 0, 0)
            expected = self.check(owner, results, rest, **parameters)
            if pitch >= 20:
                self.assertAlmostEqual(expected["gap"], 0.0, places=6)
                self.assertAlmostEqual(cmds.getAttr(str(owner) + ".gap"), 0.0, places=4)
                # 合う位置は、交差した上下の縁の間(blinkHeight=0.2)。
                self.assertAlmostEqual(expected["upperAngle"], 20 + 0.2 * (pitch - 20), places=4)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".gap"), 20.0, places=4)

    def test_close_direction_and_axes(self):
        """閉じる向きの符号と、Pitch・Yaw軸の指定に追従する。"""
        owner, results = self.build(name="negative", closeDirection=-1, pitchAxis="z", yawAxis="x")
        rest = _local(self.eye)
        for rotate in ((0, 0, -15), (10, 0, 20), (-20, 0, -30)):
            cmds.setAttr(self.eye + ".rotate", *rotate)
            self.check(owner, results, rest, pitch_axis="z", yaw_axis="x", closeDirection=-1)
        cmds.setAttr(self.eye + ".rotate", 0, 0, -15)
        # 閉じる向きが負なので、-15度は上まぶたを閉じる向きに12度動かす。
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".upperAngle"), -12.0, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".gap"), 40 - 6.0, places=3)

    def test_attributes_drive_graph(self):
        """containerの割合・開き・まばたきを変えると出力が追従する。"""
        owner, results = self.build()
        rest = _local(self.eye)
        cmds.setAttr(self.eye + ".rotate", -14, 22, 0)
        parameters = {"upperFollow": 0.6, "lowerFollow": 0.2, "yawFollow": 0.3, "openAngle": 32,
                      "blink": 0.3, "blinkHeight": 0.6}
        for attr, value in parameters.items():
            cmds.setAttr(str(owner) + "." + attr, value)
        self.check(owner, results, rest, **parameters)

    def test_radian_ui_unit(self):
        """UIの角度単位がradianでも、出力の角度は度のまま一致する。"""
        owner, results = self.build()
        rest = _local(self.eye)
        cmds.setAttr(self.eye + ".rotate", 20, 10, 0)
        degrees = cmds.getAttr(str(owner) + ".upperAngle")
        cmds.currentUnit(angle="rad")
        try:
            cmds.setAttr(self.eye + ".rotate", math.radians(-20), math.radians(10), 0)
            self.assertAlmostEqual(cmds.getAttr(str(owner) + ".eyePitch"), -20, places=3)
            cmds.setAttr(self.eye + ".rotate", math.radians(20), math.radians(10), 0)
            self.assertAlmostEqual(cmds.getAttr(str(owner) + ".upperAngle"), degrees, places=4)
            self.check(owner, results, rest)
        finally:
            cmds.currentUnit(angle="deg")

    def test_invalid_arguments(self):
        """範囲外の値・軸・親子関係の誤り・既存の名前を拒否する。"""
        for kwargs in ({"pitchAxis": "w"}, {"pitchAxis": "y", "yawAxis": "y"}, {"closeDirection": 0},
                       {"upperFollow": 1.5}, {"lowerFollow": -0.1}, {"yawFollow": float("nan")},
                       {"openAngle": 0}, {"openAngle": 180}, {"blinkHeight": 2}):
            with self.assertRaises(ValueError):
                EyelidFollow.create(self.eye, self.upper, self.lower, **kwargs)
        other = cmds.createNode("joint", name="otherLid")
        with self.assertRaises(ValueError):
            EyelidFollow.create(self.eye, self.upper, other)
        with self.assertRaises(ValueError):
            EyelidFollow.create(self.eye, self.upper, self.upper)
        EyelidFollow.create(self.eye, self.upper, self.lower, name="taken")
        with self.assertRaises(ValueError):
            EyelidFollow.create(self.eye, self.upper, self.lower, name="taken")

    def test_undo_removes_graph(self):
        """生成を1回のUndoで取り消せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        EyelidFollow.create(self.eye, self.upper, self.lower, name="undoLids")
        self.assertTrue(cmds.objExists("undoLids"))
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main()
