"""WheelRollの前進距離・自転角・滑らない転がりを、Pythonの式とOpenMayaで求めた期待値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import WheelRoll

_AXES = {"x": 0, "y": 1, "z": 2}


def _local(node):
    """matrix * offsetParentMatrix。"""
    return om.MMatrix(cmds.getAttr(node + ".matrix")) * om.MMatrix(cmds.getAttr(node + ".offsetParentMatrix"))


class WheelRollTest(unittest.TestCase):
    """標準ノードの数値評価・生成時の姿勢・滑らない転がり・引数検査を確認する。"""

    def setUp(self):
        """回転した世界の親の下に、車体の移動用コントローラーと、jointOrientを持つ車輪を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.world = cmds.createNode("transform", name="world")
        cmds.setAttr(self.world + ".rotateY", 30)
        self.vehicle = cmds.createNode("transform", name="vehicle", parent=self.world)
        cmds.setAttr(self.vehicle + ".translate", 1, 0, 2)
        self.wheel = cmds.createNode("joint", name="wheel", parent=self.vehicle)
        cmds.setAttr(self.wheel + ".translate", 5, 3, 8)
        cmds.setAttr(self.wheel + ".jointOrient", 0, 0, 0)
        cmds.setAttr(self.wheel + ".rotate", 10, 0, 0)
        self.radius = 3.0

    def build(self, **kwargs):
        """セットアップと、出力をoffsetParentMatrixで受ける結果transformを車体の下に作る。"""
        kwargs.setdefault("radius", self.radius)
        owner = WheelRoll.create(self.vehicle, self.wheel, **kwargs).container
        result = cmds.createNode("transform", name="result_wheel", parent=self.vehicle)
        cmds.connectAttr(str(owner) + ".matrix", result + ".offsetParentMatrix")
        return owner, result

    def check(self, owner, result, travel, spin_axis="x", radius=None, direction=1, offset=0.0):
        """前進距離・回転角・出力行列を確認する。"""
        radius = self.radius if radius is None else radius
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".travel"), travel, places=4)
        spin = WheelRoll.spinAngle(travel, radius, direction, offset)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".spin"), spin, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".revolutions"), spin / 360.0, places=5)
        values = [0.0, 0.0, 0.0]
        values[_AXES[spin_axis]] = math.radians(spin)
        expected = om.MEulerRotation(*values).asMatrix() * _local(self.wheel)
        actual = om.MMatrix(cmds.getAttr(result + ".offsetParentMatrix"))
        self.assertTrue(actual.isEquivalent(expected, 1e-4))
        return spin

    def test_rest_pose_does_not_jump(self):
        """生成直後の出力は、車輪の入力と同じ行列になる。"""
        owner, result = self.build()
        self.assertTrue(om.MMatrix(cmds.getAttr(result + ".offsetParentMatrix")).isEquivalent(_local(self.wheel), 1e-5))
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".travel"), 0.0, places=6)

    def test_forward_travel(self):
        """前進方向の移動だけを数え、横・上下の移動は回転に含めない。"""
        owner, result = self.build()
        for translate, travel in (((1, 0, 12), 10), ((1, 0, -4), -6), ((7, 2, 2), 0), ((-3, 5, 2 + math.pi * 6), math.pi * 6)):
            cmds.setAttr(self.vehicle + ".translate", *translate)
            self.check(owner, result, travel)
        # 円周(2πr)だけ進むと、ちょうど1回転する。
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".revolutions"), 1.0, places=5)

    def test_contact_point_does_not_slip(self):
        """車輪の真下の点(接地点)は、前進しても地面に対して止まっている(1フレームの差分で確認)。"""
        cmds.setAttr(self.wheel + ".rotate", 0, 0, 0)
        owner, result = self.build()
        # 生成時(回転0)に車輪の真下にある点を、車輪のローカル(-Y方向に半径)で表す。
        bottom = om.MPoint(0, -self.radius, 0)
        before = bottom * om.MMatrix(cmds.getAttr(result + ".worldMatrix[0]"))
        cmds.setAttr(self.vehicle + ".translateZ", 2 + 1e-3)
        after = bottom * om.MMatrix(cmds.getAttr(result + ".worldMatrix[0]"))
        center_moved = 1e-3
        # 中心は1e-3動くが、接地点の移動は2次の微小量(約 d^2/2r)に収まる。
        self.assertLess((after - before).length(), center_moved * 1e-2)
        # 比較: 回転しない入力の車輪では、同じ点が中心と同じだけ動く(滑る)。
        input_after = bottom * om.MMatrix(cmds.getAttr(self.wheel + ".worldMatrix[0]"))
        self.assertAlmostEqual((input_after - before).length(), center_moved, places=7)

    def test_axes_direction_and_attributes(self):
        """前進軸・車軸・向きの指定と、半径・offsetの変更に追従する。"""
        owner, result = self.build(name="other", forwardAxis="x", spinAxis="z", direction=-1)
        cmds.setAttr(self.vehicle + ".translate", 9, 0, 2)
        self.check(owner, result, 8, spin_axis="z", direction=-1)
        cmds.setAttr(str(owner) + ".radius", 2.0)
        cmds.setAttr(str(owner) + ".offset", 15.0)
        self.check(owner, result, 8, spin_axis="z", radius=2.0, direction=-1, offset=15.0)

    def test_unit_settings(self):
        """UIの単位がm・radianでも、travelはcm、spinは度のまま。"""
        owner, result = self.build()
        cmds.setAttr(self.vehicle + ".translateZ", 7)
        expected = (cmds.getAttr(str(owner) + ".travel"), cmds.getAttr(str(owner) + ".spin"))
        cmds.currentUnit(linear="m", angle="rad")
        try:
            self.assertAlmostEqual(cmds.getAttr(str(owner) + ".travel"), expected[0], places=4)
            self.assertAlmostEqual(cmds.getAttr(str(owner) + ".spin"), expected[1], places=3)
            self.check(owner, result, 5)
        finally:
            cmds.currentUnit(linear="cm", angle="deg")

    def test_invalid_arguments(self):
        """範囲外の値・軸・同じノード・既存の名前を拒否する。"""
        for kwargs in ({"forwardAxis": "w"}, {"spinAxis": "q"}, {"direction": 0}, {"radius": 0},
                       {"radius": float("nan")}):
            kwargs.setdefault("radius", 3.0)
            with self.assertRaises(ValueError):
                WheelRoll.create(self.vehicle, self.wheel, **kwargs)
        with self.assertRaises(ValueError):
            WheelRoll.create(self.wheel, self.wheel, 3.0)
        WheelRoll.create(self.vehicle, self.wheel, 3.0, name="taken")
        with self.assertRaises(ValueError):
            WheelRoll.create(self.vehicle, self.wheel, 3.0, name="taken")

    def test_undo_removes_graph(self):
        """生成を1回のUndoで取り消せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        WheelRoll.create(self.vehicle, self.wheel, 3.0, name="undoWheel")
        self.assertTrue(cmds.objExists("undoWheel"))
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main()
