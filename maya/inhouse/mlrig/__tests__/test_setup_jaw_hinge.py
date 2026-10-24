"""JawHingeの閉じ側の柔らかい制限と前方スライドを、OpenMayaで求めた期待値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import JawHinge

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


def _translation(matrix):
    """行列の平行移動をMVectorで返す。"""
    return om.MTransformationMatrix(om.MMatrix(matrix)).translation(om.MSpace.kTransform)


class JawHingeTest(unittest.TestCase):
    """標準ノードの数値評価・作成時の姿勢・閉じ側の制限・スライド・引数検査を確認する。"""

    def setUp(self):
        """頭の下に、基準回転と位置を持つ顎のjointを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.head = cmds.createNode("transform", name="head")
        cmds.setAttr(self.head + ".translate", 0, 150, 2)
        cmds.setAttr(self.head + ".rotate", 4, 0, -3)
        self.jaw = cmds.createNode("joint", name="jaw", parent=self.head)
        cmds.setAttr(self.jaw + ".translate", 0, -2, 3)
        cmds.setAttr(self.jaw + ".jointOrient", 30, 0, 0)

    def build(self, **kwargs):
        """セットアップと、出力をoffsetParentMatrixで受ける結果transformを作る。"""
        owner = JawHinge.create(self.jaw, **kwargs).container
        result = cmds.createNode("transform", name="result_jaw", parent=self.head)
        cmds.connectAttr(str(owner) + ".matrix", result + ".offsetParentMatrix")
        return owner, result

    def deltaEuler(self, rest, order="xyz"):
        """親空間での差分回転 rest^-1 * L のEuler角(rad)。"""
        delta = _rotation(rest).asMatrix().inverse() * _rotation(_local(self.jaw)).asMatrix()
        return om.MTransformationMatrix(delta).rotation().reorder(_ORDERS[order])

    def check(self, owner, result, rest, softness=2.0, slide=(0.0, 0.0, 0.02), open_direction=1,
              pitch_axis="x", order="xyz"):
        """出力の角度・回転・位置を確認し、(開き角, 制限後)を返す。"""
        euler = self.deltaEuler(rest, order)
        index = "xyz".index(pitch_axis)
        angle = open_direction * math.degrees(euler[index])
        limited = JawHinge.limitedOpen(angle, softness)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".openAngle"), angle, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".limitedOpen"), limited, places=3)
        values = [euler.x, euler.y, euler.z]
        values[index] = math.radians(open_direction * limited)
        expected_rotation = _rotation(rest).asMatrix() * om.MEulerRotation(
            values[0], values[1], values[2], _ORDERS[order]).asMatrix()
        transform = om.MTransformationMatrix(expected_rotation)
        offset = om.MVector(*slide) * limited
        transform.setTranslation(_translation(_local(self.jaw)) + offset, om.MSpace.kTransform)
        actual = om.MMatrix(cmds.getAttr(result + ".offsetParentMatrix"))
        self.assertTrue(actual.isEquivalent(transform.asMatrix(), 1e-4), (actual, transform.asMatrix()))
        self.assertTrue(om.MVector(cmds.getAttr(str(owner) + ".slideOffset")[0]).isEquivalent(offset, 1e-5))
        return angle, limited

    def test_rest_pose_does_not_jump(self):
        """生成直後(閉じた姿勢)の出力は入力と同じ行列になる。"""
        owner, result = self.build()
        actual = om.MMatrix(cmds.getAttr(result + ".offsetParentMatrix"))
        self.assertTrue(actual.isEquivalent(_local(self.jaw), 1e-4))
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".openAngle"), 0.0, places=5)

    def test_open_passes_through(self):
        """softness以上に開くと、回転は入力のまま、位置はslideだけ前へ出る。"""
        owner, result = self.build(softness=2.0, slide=(0, -0.01, 0.03))
        rest = _local(self.jaw)
        for rotate in ((5, 0, 0), (25, 0, 0), (35, 8, 0), (20, -6, 3)):
            cmds.setAttr(self.jaw + ".rotate", *rotate)
            angle, limited = self.check(owner, result, rest, softness=2.0, slide=(0, -0.01, 0.03))
            self.assertAlmostEqual(angle, limited, places=6)
        cmds.setAttr(self.jaw + ".rotate", 25, 0, 0)
        # 純粋な開きでは移動量は slide*25。
        offset = cmds.getAttr(str(owner) + ".slideOffset")[0]
        self.assertAlmostEqual(offset[1], -0.25, places=4)
        self.assertAlmostEqual(offset[2], 0.75, places=4)

    def test_over_close_is_stopped(self):
        """閉じた姿勢を越える入力は-softness度の手前で止まり、単調に戻る。"""
        owner, result = self.build(softness=3.0)
        rest = _local(self.jaw)
        previous = None
        for value in (6, 3, 1.5, 0, -3, -10, -40):
            cmds.setAttr(self.jaw + ".rotate", value, 0, 0)
            angle, limited = self.check(owner, result, rest, softness=3.0)
            self.assertGreater(limited, -3.0)
            if previous is not None:
                self.assertLessEqual(limited, previous + 1e-9)
            previous = limited
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".limitedOpen"), -3.0, places=4)
        for value in (-10, 0, 10):
            cmds.setAttr(self.jaw + ".rotate", value, 0, 0)
            self.check(owner, result, rest, softness=3.0)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".limitedOpen"), 10.0, places=4)

    def test_hard_limit(self):
        """softness=0では、閉じ側の入力をほぼ0度で止める。"""
        owner, result = self.build(softness=0.0)
        rest = _local(self.jaw)
        cmds.setAttr(self.jaw + ".rotate", -20, 0, 0)
        angle, limited = self.check(owner, result, rest, softness=0.0)
        # 漸近値-0.001度には浮動小数の丸めで到達し得る。
        self.assertGreaterEqual(limited, -1e-3)
        self.assertAlmostEqual(angle, -20.0, places=2)

    def test_open_direction_and_axes(self):
        """開く向きの符号とPitch・Yaw軸の指定に追従する。"""
        owner, result = self.build(name="negative", openDirection=-1, pitchAxis="z", yawAxis="y")
        rest = _local(self.jaw)
        for rotate in ((0, 0, -20), (0, 10, -15), (0, 0, 12)):
            cmds.setAttr(self.jaw + ".rotate", *rotate)
            self.check(owner, result, rest, open_direction=-1, pitch_axis="z", order="zyx")

    def test_attributes_drive_graph(self):
        """containerのsoftness・slideを変えると出力が追従する。"""
        owner, result = self.build()
        rest = _local(self.jaw)
        cmds.setAttr(self.jaw + ".rotate", -3, 0, 0)
        cmds.setAttr(str(owner) + ".softness", 8)
        cmds.setAttr(str(owner) + ".slide", 0.05, 0, -0.02, type="double3")
        angle, limited = self.check(owner, result, rest, softness=8, slide=(0.05, 0, -0.02))
        self.assertGreater(limited, angle)

    def test_radian_ui_unit(self):
        """UIの角度単位がradianでも、角度の出力は度のまま一致する。"""
        owner, result = self.build()
        rest = _local(self.jaw)
        cmds.currentUnit(angle="rad")
        try:
            cmds.setAttr(self.jaw + ".rotate", math.radians(-15), 0, 0)
            self.assertAlmostEqual(cmds.getAttr(str(owner) + ".openAngle"), -15, places=3)
            self.check(owner, result, rest)
        finally:
            cmds.currentUnit(angle="deg")

    def test_invalid_arguments(self):
        """範囲外の値・軸・親の無いtransform・既存の名前を拒否する。"""
        for kwargs in ({"pitchAxis": "w"}, {"pitchAxis": "x", "yawAxis": "x"}, {"openDirection": 2},
                       {"softness": -1}, {"softness": 60}, {"softness": float("nan")},
                       {"slide": (0, 0)}, {"slide": (0, float("inf"), 0)}):
            with self.assertRaises(ValueError):
                JawHinge.create(self.jaw, **kwargs)
        orphan = cmds.createNode("transform", name="orphan")
        with self.assertRaises(ValueError):
            JawHinge.create(orphan)
        JawHinge.create(self.jaw, name="taken")
        with self.assertRaises(ValueError):
            JawHinge.create(self.jaw, name="taken")

    def test_undo_removes_graph(self):
        """生成を1回のUndoで取り消せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        JawHinge.create(self.jaw, name="undoJaw")
        self.assertTrue(cmds.objExists("undoJaw"))
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main()
