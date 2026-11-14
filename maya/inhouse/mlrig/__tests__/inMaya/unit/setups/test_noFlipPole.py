"""NoFlipPoleのポールの位置を、OpenMayaで独立に求めた脚の軸まわりの回転と比べ、IKの膝が反転しないことを確かめる。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import NoFlipPole

DISTANCE = 8.0


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _point(node):
    """ノードのワールド位置。"""
    return om.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))


def _expected(start, end, control, offset, twist, distance, position, axis=(0, 0, 1)):
    """脚の軸まわりのクォータニオン回転で、期待するポールの位置を求める(実装の枠の式とは別の求め方)。"""
    a, b = _point(start), _point(end)
    leg = (b - a).normal()
    forward = om.MVector(*axis) * _matrix(control + ".worldMatrix[0]")
    side = (forward - leg * (forward * leg)).normal()
    # 行ベクトル規約のR_Y(θ)はXを(cosθ, 0, -sinθ)へ回す = 脚の軸まわりの右手回りの回転。
    turned = side.rotateBy(om.MQuaternion(offset + twist, leg))
    return a + (b - a) * position + turned * distance


def _kneeDirection(start, mid, end):
    """脚の軸に垂直な、膝の向き(正規化)。"""
    a, k, b = _point(start), _point(mid), _point(end)
    leg = (b - a).normal()
    knee = k - a
    return (knee - leg * (knee * leg)).normal()


class NoFlipPoleTest(unittest.TestCase):
    """作成時に膝が跳ねない・式との一致・反転しない・kneeTwist・mid無し/軸・UI単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """少し前に曲がった脚とRP IK、足のコントロール(Y回りに15度)を作り、ポールを付ける。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        cmds.select(clear=True)
        self.hip = cmds.joint(name="hip", position=(1, 10, 0))
        self.knee = cmds.joint(name="knee", position=(1.3, 5, 1.2))
        self.ankle = cmds.joint(name="ankle", position=(1, 0.5, 0))
        cmds.select(clear=True)
        self.handle = cmds.ikHandle(startJoint=self.hip, endEffector=self.ankle, solver="ikRPsolver",
                                    name="legIk")[0]
        self.control = cmds.createNode("transform", name="footCtrl")
        cmds.setAttr(self.control + ".translate", 1, 0.5, 0)
        cmds.setAttr(self.control + ".rotateY", 15)
        self.handle = cmds.parent(self.handle, self.control)[0]
        self.restKnee = _point(self.knee)
        self.setup = NoFlipPole.create(self.hip, self.control, mid=self.knee, name="pole", distance=DISTANCE)
        self.owner = str(self.setup.container)
        self.pole = cmds.createNode("transform", name="pole_loc")
        cmds.connectAttr(self.owner + ".matrix", self.pole + ".offsetParentMatrix")
        cmds.poleVectorConstraint(self.pole, self.handle)

    def _offset(self):
        return math.radians(cmds.getAttr(self.owner + ".offset"))

    def _assertPole(self, twist=0.0, distance=DISTANCE, position=0.5, tolerance=1e-4):
        expected = _expected(self.hip, self.control, self.control, self._offset(), twist, distance, position)
        out = _matrix(self.owner + ".matrix")
        for index, value in enumerate(expected):
            self.assertAlmostEqual(out[12 + index], value, delta=tolerance)
        return om.MVector(out[12], out[13], out[14])

    def test_rest(self):
        """作成直後はポールが今の膝の曲がる面の上(膝の側)にあり、ポールを付けても膝が跳ねない。"""
        self.assertTrue((_point(self.knee) - self.restKnee).length() < 1e-4,
                        (_point(self.knee), self.restKnee))
        pole = self._assertPole()
        a, b = _point(self.hip), _point(self.control)
        leg = (b - a).normal()
        toPole = pole - a
        direction = (toPole - leg * (toPole * leg)).normal()
        self.assertAlmostEqual(direction * _kneeDirection(self.hip, self.knee, self.ankle), 1.0, delta=1e-6)
        self.assertAlmostEqual((toPole - leg * (toPole * leg)).length(), DISTANCE, delta=1e-4)
        self.assertAlmostEqual(toPole * leg, (b - a).length() * 0.5, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".legLength"), (b - a).length(), delta=1e-5)

    def test_matches_formula(self):
        """コントロールを動かし・回すと、独立に求めた位置に一致し、行列のYは脚の軸を向く。"""
        poses = (((1, 0.5, 0), (0, 15, 0)), ((3, 2, 4), (0, 60, 0)), ((-2, 4, -5), (10, -80, 5)),
                 ((1, 7, 6), (30, 170, -20)), ((4, -1, 2), (0, -150, 0)))
        for translate, rotate in poses:
            with self.subTest(translate=translate, rotate=rotate):
                cmds.setAttr(self.control + ".translate", *translate)
                cmds.setAttr(self.control + ".rotate", *rotate)
                self._assertPole()
                out = _matrix(self.owner + ".matrix")
                leg = (_point(self.control) - _point(self.hip)).normal()
                self.assertAlmostEqual(om.MVector(out[4], out[5], out[6]) * leg, 1.0, delta=1e-5)

    def test_does_not_flip(self):
        """足を股関節の後ろから前上まで振り上げても、膝は足の前の向きに対して同じ角度を保つ。

        足先(前の向き)が脚の延長と平行になる姿勢は向きが決まらないため、前方75度までにする。
        比較として、作成時のポールの位置に固定したワールドのポールでは、同じ動きで膝の向きが反転する。
        """
        fixed = cmds.createNode("transform", name="fixedPole")
        cmds.xform(fixed, worldSpace=True, translation=list(_point(self.pole)))
        cmds.select(clear=True)
        joints = [cmds.joint(name="fixed" + role, position=list(_point(source)))
                  for role, source in (("Hip", self.hip), ("Knee", self.knee), ("Ankle", self.ankle))]
        cmds.select(clear=True)
        other = cmds.ikHandle(startJoint=joints[0], endEffector=joints[2], solver="ikRPsolver",
                              name="fixedIk")[0]
        cmds.poleVectorConstraint(fixed, other)
        fixedSigns = []
        previous = None
        for step in range(46):
            angle = math.radians(-60 + 3 * step)
            # 股関節を中心に、足を後ろ下から前上へ弧を描いて振り上げる(脚の長さ9cm)。
            point = (1, 10 - 9 * math.cos(angle), 9 * math.sin(angle))
            cmds.setAttr(self.control + ".translate", *point)
            cmds.setAttr(other + ".translate", *point)
            knee = _kneeDirection(self.hip, self.knee, self.ankle)
            leg = (_point(self.control) - _point(self.hip)).normal()
            forward = om.MVector(0, 0, 1) * _matrix(self.control + ".worldMatrix[0]")
            side = (forward - leg * (forward * leg)).normal()
            target = side.rotateBy(om.MQuaternion(self._offset(), leg))
            self.assertGreater(knee * target, math.cos(math.radians(0.5)), step)
            if previous is not None:
                self.assertGreater(knee * previous, math.cos(math.radians(10)), step)
            previous = knee
            fixedKnee = _kneeDirection(joints[0], joints[1], joints[2])
            fixedSigns.append(fixedKnee * om.MVector(0, 0, 1) > 0)
        self.assertIn(False, fixedSigns)
        self.assertIn(True, fixedSigns)

    def test_knee_twist_and_attributes(self):
        """kneeTwistで脚の軸まわりに回り、distance・positionで距離と高さが変わる。"""
        before = self._assertPole()
        cmds.setAttr(self.owner + ".kneeTwist", 90)
        after = self._assertPole(twist=math.radians(90))
        a, b = _point(self.hip), _point(self.control)
        leg = (b - a).normal()
        center = a + (b - a) * 0.5
        self.assertAlmostEqual((before - center) * (after - center), 0.0, delta=1e-4)
        self.assertGreater(((before - center) ^ (after - center)) * leg, 0.0)
        cmds.setAttr(self.owner + ".distance", 3)
        cmds.setAttr(self.owner + ".position", 0.25)
        self._assertPole(twist=math.radians(90), distance=3.0, position=0.25)

    def test_without_mid_and_axis(self):
        """midが無ければoffset=0でコントロールの前の向きに置き、forwardAxis=-xも使える。"""
        cmds.file(new=True, force=True)
        start = cmds.createNode("transform", name="shoulder")
        cmds.setAttr(start + ".translate", 0, 12, 0)
        end = cmds.createNode("transform", name="wrist")
        cmds.setAttr(end + ".translate", 8, 11, 1)
        control = cmds.createNode("transform", name="handCtrl")
        cmds.setAttr(control + ".rotate", 0, 30, 0)
        setup = NoFlipPole.create(start, end, control=control, name="armPole", forwardAxis="-x")
        owner = str(setup.container)
        self.assertEqual(cmds.getAttr(owner + ".offset"), 0.0)
        distance = (_point(end) - _point(start)).length()
        self.assertAlmostEqual(cmds.getAttr(owner + ".distance"), distance, delta=1e-5)
        expected = _expected(start, end, control, 0.0, 0.0, distance, 0.5, axis=(-1, 0, 0))
        out = _matrix(owner + ".matrix")
        for index, value in enumerate(expected):
            self.assertAlmostEqual(out[12 + index], value, delta=1e-4)

    def test_ui_units(self):
        """UI単位がmm・ラジアンでも、distanceはmm、kneeTwistはラジアンとして正しく効く。"""
        cmds.setAttr(self.control + ".translate", 2, 1, 3)
        cmds.currentUnit(linear="mm", angle="rad")
        cmds.setAttr(self.owner + ".distance", 50.0)
        cmds.setAttr(self.owner + ".kneeTwist", math.pi / 3)
        cmds.currentUnit(linear="cm", angle="deg")
        self._assertPole(twist=math.pi / 3, distance=5.0)

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.owner + ".matrix", pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "joint", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        start = cmds.createNode("transform", name="undoHip")
        cmds.setAttr(start + ".translateY", 10)
        end = cmds.createNode("transform", name="undoFoot")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        NoFlipPole.create(start, end, name="undoPole")
        self.assertTrue(cmds.objExists("undoPole"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoPole"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoPole.matrix"))

    def test_arguments(self):
        """軸・距離・割合・transform以外・同じノード・前の向きが脚と平行・名前の重複を拒否する。"""
        for kwargs in ({"forwardAxis": "w"}, {"distance": 0.0}, {"distance": float("nan")},
                       {"position": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                NoFlipPole.create(self.hip, self.control, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        for args in ((node, self.control), (self.hip, self.hip)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                NoFlipPole.create(*args, name="bad")
        with self.assertRaises(ValueError):
            NoFlipPole.create(self.hip, self.control, mid=self.hip, name="bad")
        with self.assertRaises(ValueError):
            NoFlipPole.create(self.hip, self.control, name="bad", forwardAxis="y")
        with self.assertRaises(ValueError):
            NoFlipPole.create(self.hip, self.control, name="pole")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
