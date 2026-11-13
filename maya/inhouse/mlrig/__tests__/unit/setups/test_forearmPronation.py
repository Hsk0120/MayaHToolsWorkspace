"""ForearmPronationのTwistの抽出・軸まわりの回転・可動域・出力を、OpenMayaで独立に求めた値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import ForearmPronation, TwistLimit

ULNA_POSITION = (2.0, 10.0, -1.0)
HEAD = om.MVector(0.2, 0.0, 0.8)
ULNA_HEAD = om.MVector(8.0, 0.0, 0.0)
RADIUS_TIP = om.MVector(8.0, 0.0, 1.0)
AXIS = (ULNA_HEAD - HEAD).normal()


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _position(matrix):
    """行列の平行移動をMVectorで返す。"""
    return om.MVector(matrix[12], matrix[13], matrix[14])


def _set_rotation(node, rotation):
    """transformのrotateへMQuaternionの回転を設定する(度)。"""
    euler = rotation.asEulerRotation()
    cmds.setAttr(node + ".rotate", *[math.degrees(value) for value in (euler.x, euler.y, euler.z)])


def _expected_tip(degrees):
    """軸まわりにdegrees度回した橈骨の先(尺骨の空間)を返す。"""
    return HEAD + (RADIUS_TIP - HEAD).rotateBy(om.MQuaternion(math.radians(degrees), AXIS))


class ForearmPronationTest(unittest.TestCase):
    """既定値・軸まわりの回転・Swingの無視・可動域・sign・weight・尺骨の移動・単位・所有・Undo・引数を確認する。"""

    def setUp(self):
        """尺骨の下に尺骨の頭・橈骨の頭・橈骨の先・手を置いたシーンを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.ulna = cmds.createNode("transform", name="ulna")
        cmds.setAttr(self.ulna + ".translate", *ULNA_POSITION)
        self.ulna_tip = self._child("ulnaTip", ULNA_HEAD)
        self.radius = self._child("radius", HEAD)
        self.radius_tip = self._child("radiusTip", RADIUS_TIP)
        self.hand = self._child("hand", om.MVector(8.5, 0, 0))
        self.setup = ForearmPronation.create(self.ulna, self.ulna_tip, self.radius, self.radius_tip, self.hand,
                                             name="forearm")
        self.owner = str(self.setup.container)

    def _child(self, name, position):
        """尺骨の子のtransformを作る。"""
        node = cmds.createNode("transform", name=name, parent=self.ulna)
        cmds.setAttr(node + ".translate", position.x, position.y, position.z)
        return node

    def _get(self, attribute):
        """containerのアトリビュートの値を返す。"""
        return cmds.getAttr(self.owner + "." + attribute)

    def _twist(self, degrees):
        """手を尺骨の空間で軸まわりにdegrees度回す。"""
        _set_rotation(self.hand, om.MQuaternion(math.radians(degrees), AXIS))

    def _tip_in_ulna(self):
        """tipMatrixの位置を尺骨の空間で返す。"""
        point = om.MPoint(_position(_matrix(self.owner + ".tipMatrix"))) * _matrix(self.ulna + ".worldInverseMatrix[0]")
        return om.MVector(point)

    def _assert_vector(self, actual, expected, delta=1e-4):
        """2つのベクトルが一致することを確かめる。"""
        self.assertLess((actual - expected).length(), delta, msg="{} != {}".format(actual, expected))

    def test_defaults_and_rest(self):
        """既定の可動域は回内80度・回外85度、生成時の姿勢では橈骨がそのまま・角度と重みは0。"""
        self.assertAlmostEqual(self._get("pronationLimit"), 80.0, delta=1e-6)
        self.assertAlmostEqual(self._get("supinationLimit"), 85.0, delta=1e-6)
        for attribute in ("handTwist", "rawPronation", "pronation", "excessPronation", "pronationWeight",
                          "supinationWeight"):
            self.assertAlmostEqual(self._get(attribute), 0.0, delta=1e-5)
        self.assertTrue(_matrix(self.owner + ".matrix").isEquivalent(_matrix(self.radius + ".worldMatrix[0]"), 1e-5))
        self._assert_vector(_position(_matrix(self.owner + ".tipMatrix")),
                            _position(_matrix(self.radius_tip + ".worldMatrix[0]")))

    def test_rotation_about_axis(self):
        """範囲内ではhandTwistがそのまま角度になり、橈骨は軸のまわりを剛体のまま回る。"""
        for degrees in (30.0, -45.0, 60.0):
            self._twist(degrees)
            with self.subTest(degrees=degrees):
                self.assertAlmostEqual(self._get("handTwist"), degrees, delta=1e-4)
                self.assertAlmostEqual(self._get("pronation"), degrees, delta=1e-4)
                tip = self._tip_in_ulna()
                self._assert_vector(tip, _expected_tip(degrees))
                head = _position(_matrix(self.owner + ".matrix")) - om.MVector(*ULNA_POSITION)
                self._assert_vector(head, HEAD)
                self.assertAlmostEqual((tip - head).length(), (RADIUS_TIP - HEAD).length(), delta=1e-5)
                # 尺骨の頭は軸の上なので距離が変わらない。
                self.assertAlmostEqual((tip - ULNA_HEAD).length(), (RADIUS_TIP - ULNA_HEAD).length(), delta=1e-5)

    def test_orientation_matches_axis_rotation(self):
        """出力の向きは生成時の橈骨の向きへ軸まわりの回転を掛けたもの。"""
        self._twist(40.0)
        rest = om.MTransformationMatrix(_matrix(self.radius + ".worldMatrix[0]")).rotation(asQuaternion=True)
        expected = rest * om.MQuaternion(math.radians(40.0), AXIS)
        actual = om.MTransformationMatrix(_matrix(self.owner + ".matrix")).rotation(asQuaternion=True)
        angle = math.degrees((actual * expected.inverse()).asAxisAngle()[1]) % 360.0
        self.assertLess(min(angle, 360.0 - angle), 1e-3)

    def test_swing_is_ignored(self):
        """手のSwing(手首の曲げ)はhandTwistに入らない。"""
        perpendicular = (AXIS ^ om.MVector(0, 1, 0)).normal()
        swing = om.MQuaternion(math.radians(35.0), perpendicular)
        twist = om.MQuaternion(math.radians(25.0), AXIS)
        _set_rotation(self.hand, swing)
        self.assertAlmostEqual(self._get("handTwist"), 0.0, delta=1e-4)
        _set_rotation(self.hand, twist * swing)
        self.assertAlmostEqual(self._get("handTwist"), 25.0, delta=1e-4)

    def test_soft_and_hard_limits(self):
        """可動域の超過はsoftTwistと一致し、超過量・重みを出力する。"""
        for degrees in (70.0, 100.0, 150.0, -75.0, -130.0):
            self._twist(degrees)
            expected = TwistLimit.softTwist(degrees, -85.0, 80.0, 0.1)
            with self.subTest(degrees=degrees):
                self.assertAlmostEqual(self._get("pronation"), expected, delta=1e-4)
                self.assertAlmostEqual(self._get("excessPronation"), degrees - expected, delta=1e-4)
                self.assertAlmostEqual(self._get("pronationWeight"), max(expected / 80.0, 0.0), delta=1e-5)
                self.assertAlmostEqual(self._get("supinationWeight"), max(-expected / 85.0, 0.0), delta=1e-5)
                self._assert_vector(self._tip_in_ulna(), _expected_tip(expected))
        cmds.setAttr(self.owner + ".softness", 0.0)
        self._twist(120.0)
        self.assertAlmostEqual(self._get("pronation"), 80.0, delta=1e-2)
        self.assertAlmostEqual(self._get("pronationWeight"), 1.0, delta=1e-3)

    def test_sign_and_weight(self):
        """signは回内の符号だけを反転し、回す向きはhandTwistのまま。weightは伝える割合。"""
        cmds.setAttr(self.owner + ".sign", -1)
        self._twist(30.0)
        self.assertAlmostEqual(self._get("pronation"), -30.0, delta=1e-4)
        self.assertAlmostEqual(self._get("supinationWeight"), 30.0 / 85.0, delta=1e-5)
        self._assert_vector(self._tip_in_ulna(), _expected_tip(30.0))
        cmds.setAttr(self.owner + ".sign", 1)
        cmds.setAttr(self.owner + ".weight", 0.5)
        self.assertAlmostEqual(self._get("pronation"), 15.0, delta=1e-4)
        self._assert_vector(self._tip_in_ulna(), _expected_tip(15.0))

    def test_ulna_moves_with_hand(self):
        """手が尺骨と一緒に動くならTwistは0で、橈骨は尺骨に追従する。手だけ回すと尺骨からの相対で測る。"""
        cmds.setAttr(self.ulna + ".rotate", 20, 40, -30)
        cmds.setAttr(self.ulna + ".translate", -3, 4, 5)
        self.assertAlmostEqual(self._get("handTwist"), 0.0, delta=1e-4)
        self.assertTrue(_matrix(self.owner + ".matrix").isEquivalent(_matrix(self.radius + ".worldMatrix[0]"), 1e-5))
        self._twist(50.0)
        self.assertAlmostEqual(self._get("handTwist"), 50.0, delta=1e-4)
        self._assert_vector(self._tip_in_ulna(), _expected_tip(50.0))

    def test_rest_inputs_are_read_once(self):
        """radius・radiusTip・ulnaTipは生成時の値だけを使うので、出力で駆動しても循環しない。"""
        self._twist(30.0)
        before = _matrix(self.owner + ".tipMatrix")
        cmds.setAttr(self.radius_tip + ".translateZ", 4.0)
        cmds.setAttr(self.ulna_tip + ".translateX", 3.0)
        self.assertTrue(_matrix(self.owner + ".tipMatrix").isEquivalent(before, 1e-6))
        driven = cmds.createNode("transform", name="driven")
        cmds.connectAttr(self.owner + ".matrix", driven + ".offsetParentMatrix")
        self.assertTrue(_matrix(driven + ".worldMatrix[0]").isEquivalent(_matrix(self.owner + ".matrix"), 1e-6))

    def test_interosseous_distance(self):
        """橈骨の中点と尺骨の中点の距離は、尺骨の空間の式と一致し、回内すると変わる。"""
        for degrees in (0.0, 60.0, -60.0):
            self._twist(degrees)
            expected = ((HEAD + _expected_tip(degrees)) * 0.5 - ULNA_HEAD * 0.5).length()
            with self.subTest(degrees=degrees):
                self.assertAlmostEqual(self._get("interosseousDistance"), expected, delta=1e-5)
        self._twist(60.0)
        first = self._get("interosseousDistance")
        self._twist(0.0)
        self.assertGreater(abs(first - self._get("interosseousDistance")), 1e-3)

    def test_parent_scale(self):
        """親の回転・scaleに追従する。"""
        group = cmds.createNode("transform", name="group")
        cmds.setAttr(group + ".rotate", 15, 30, 45)
        cmds.setAttr(group + ".scale", 2, 2, 2)
        cmds.parent(self.ulna, group)
        self._twist(45.0)
        self.assertAlmostEqual(self._get("handTwist"), 45.0, delta=1e-4)
        self._assert_vector(self._tip_in_ulna(), _expected_tip(45.0), delta=1e-3)

    def test_ui_units(self):
        """UIの角度・長さの単位によらず、角度は度・距離はcmで出す。"""
        for angle, linear, scale in (("rad", "cm", 1.0), ("deg", "mm", 10.0), ("rad", "m", 0.01)):
            cmds.file(new=True, force=True)
            cmds.currentUnit(angle=angle, linear=linear)
            nodes = {"ulna": cmds.createNode("transform", name="ulna")}
            for label, position in (("ulnaTip", ULNA_HEAD), ("radius", HEAD), ("radiusTip", RADIUS_TIP),
                                    ("hand", om.MVector(8.5, 0, 0))):
                nodes[label] = cmds.createNode("transform", name=label, parent=nodes["ulna"])
                cmds.setAttr(nodes[label] + ".translate", position.x * scale, position.y * scale, position.z * scale)
            owner = str(ForearmPronation.create(nodes["ulna"], nodes["ulnaTip"], nodes["radius"], nodes["radiusTip"],
                                                nodes["hand"], name="units").container)
            turn = om.MQuaternion(math.radians(30.0), AXIS).asEulerRotation()
            factor = 1.0 if angle == "rad" else 180.0 / math.pi
            cmds.setAttr(nodes["hand"] + ".rotate", turn.x * factor, turn.y * factor, turn.z * factor)
            with self.subTest(angle=angle, linear=linear):
                self.assertAlmostEqual(cmds.getAttr(owner + ".handTwist"), 30.0, delta=1e-3)
                self.assertAlmostEqual(cmds.getAttr(owner + ".pronation"), 30.0, delta=1e-3)
                expected = ((HEAD + _expected_tip(30.0)) * 0.5 - ULNA_HEAD * 0.5).length()
                self.assertAlmostEqual(cmds.getAttr(owner + ".interosseousDistance"), expected, delta=1e-4)
                self._assert_vector(_position(om.MMatrix(cmds.getAttr(owner + ".tipMatrix"))), _expected_tip(30.0),
                                    delta=1e-3)
        cmds.currentUnit(angle="deg", linear="cm")

    def test_owner_and_undo(self):
        """計算ノードはcontainerに入り、生成は1回のUndo/Redoで消える・戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True))
        outside = [node for node in cmds.ls(type="unitConversion") if node not in members]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        nodes = [cmds.createNode("transform", name="undo" + label)
                 for label in ("Ulna", "Tip", "Radius", "RadiusTip", "Hand")]
        cmds.setAttr(nodes[1] + ".translateX", 5)
        cmds.setAttr(nodes[2] + ".translateZ", 1)
        cmds.setAttr(nodes[3] + ".translateX", 5)
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        ForearmPronation.create(*nodes, name="undoForearm")
        self.assertTrue(cmds.objExists("undoForearm"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoForearm"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoForearm.tipMatrix"))

    def test_arguments(self):
        """角度・softness・weight・signの不正、transform以外・同じノード・同じ位置・名前の重複を拒否する。"""
        inputs = (self.ulna, self.ulna_tip, self.radius, self.radius_tip, self.hand)
        for kwargs in ({"pronationLimit": 0.0}, {"supinationLimit": 180.0}, {"pronationLimit": float("nan")},
                       {"softness": 1.5}, {"weight": -0.1}, {"sign": 0}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    ForearmPronation.create(*inputs, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            ForearmPronation.create(node, self.ulna_tip, self.radius, self.radius_tip, self.hand, name="bad")
        with self.assertRaises(ValueError):
            ForearmPronation.create(self.ulna, self.ulna_tip, self.radius, self.radius_tip, self.ulna, name="bad")
        with self.assertRaises(ValueError):
            ForearmPronation.create(self.ulna, self.ulna_tip, self.radius, self.radius, self.hand, name="bad")
        with self.assertRaises(ValueError):
            ForearmPronation.create(self.ulna, self.radius, self.radius, self.radius_tip, self.hand, name="bad")
        with self.assertRaises(ValueError):
            ForearmPronation.create(*inputs, name="forearm")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
