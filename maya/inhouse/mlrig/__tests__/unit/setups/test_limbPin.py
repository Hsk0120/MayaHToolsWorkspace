"""LimbPinの長さを、OpenMayaで独立に求めた値と、Maya標準のIK(ikRPsolver+poleVectorConstraint)の結果で確かめる。"""

import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import LimbPin


def _world(node):
    """ノードのワールド位置(cm)。"""
    return om.MTransformationMatrix(om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))).translation(om.MSpace.kWorld)


def _local(node, space):
    """ノードのワールド位置を、transform ``space`` のワールド逆行列の空間へ移した点(cm)。"""
    point = om.MPoint(_world(node))
    return om.MVector(point * om.MMatrix(cmds.getAttr(space + ".worldInverseMatrix[0]")))


def _expected(slide, pin, rest, near, far):
    """slide・pin・作成時の長さ・付け根→操作子・操作子→目標の長さから、上下の長さを独立に求める。"""
    upper, lower = rest
    delta = slide * (lower if slide >= 0.0 else upper)
    upper, lower = upper + delta, lower - delta
    return upper + pin * (near - upper), lower + pin * (far - lower)


class LimbPinTest(unittest.TestCase):
    """作成時の不変・slide・pinとIK・符号と軸・UI単位・所有・引数を確かめる。"""

    def setUp(self):
        """回転・移動・一様scale 2 の胴の下に、肩・肘・手首のjointと、極ベクトルの操作子・目標を作る。"""
        cmds.file(new=True, force=True)
        random.seed(17)
        self.body = cmds.createNode("transform", name="body")
        cmds.setAttr(self.body + ".translate", 3.0, 10.0, -2.0)
        cmds.setAttr(self.body + ".rotate", 20.0, -35.0, 10.0)
        cmds.setAttr(self.body + ".scale", 2.0, 2.0, 2.0)
        self.arm = self.chain("arm", 1.0)
        self.pole = cmds.createNode("transform", name="pole", parent=self.body)
        cmds.setAttr(self.pole + ".translate", 4.0, 0.5, -3.0)
        self.target = cmds.createNode("transform", name="target", parent=self.body)
        cmds.setAttr(self.target + ".translate", 7.0, 0.0, 0.0)

    def chain(self, label, sign):
        """胴の下に肩(1,0,0)・肘(+4)・手首(+3.5)の3つのjointを作る。``sign`` で骨の向きを反転する。"""
        shoulder = cmds.createNode("joint", name=label + "_shoulder", parent=self.body)
        cmds.setAttr(shoulder + ".translate", 1.0, 0.5, 0.0)
        cmds.setAttr(shoulder + ".jointOrient", 0.0, 0.0, -15.0)
        elbow = cmds.createNode("joint", name=label + "_elbow", parent=shoulder)
        cmds.setAttr(elbow + ".translateX", 4.0 * sign)
        cmds.setAttr(elbow + ".jointOrient", 0.0, 0.0, 30.0)
        wrist = cmds.createNode("joint", name=label + "_wrist", parent=elbow)
        cmds.setAttr(wrist + ".translateX", 3.5 * sign)
        return [shoulder, elbow, wrist]

    def tearDown(self):
        """シーンを破棄する。"""
        cmds.currentUnit(linear="cm", angle="deg")
        cmds.file(new=True, force=True)

    def lengths(self, setup):
        """出力の上下の長さ(cm)。"""
        owner = str(setup.container)
        return cmds.getAttr(owner + ".upperLength"), cmds.getAttr(owner + ".lowerLength")

    def check(self, setup, arm, sign=1.0, rest=(4.0, 3.5)):
        """出力の長さと、肘・手首の translateX が独立計算と一致することを確かめる。"""
        owner = str(setup.container)
        slide, pin = cmds.getAttr(owner + ".slide"), cmds.getAttr(owner + ".pin")
        shoulder = om.MVector(cmds.getAttr(arm[0] + ".translate")[0])
        if cmds.currentUnit(query=True, linear=True) != "cm":
            shoulder = om.MVector([om.MDistance.uiToInternal(value) for value in shoulder])
        pole, target = _local(self.pole, self.body), _local(self.target, self.body)
        upper, lower = _expected(slide, pin, rest, (pole - shoulder).length(), (target - pole).length())
        got = self.lengths(setup)
        if cmds.currentUnit(query=True, linear=True) != "cm":
            got = [om.MDistance.uiToInternal(value) for value in got]
        self.assertAlmostEqual(got[0], upper, places=5)
        self.assertAlmostEqual(got[1], lower, places=5)
        for joint, length in ((arm[1], upper), (arm[2], lower)):
            value = cmds.getAttr(joint + ".translateX")
            if cmds.currentUnit(query=True, linear=True) != "cm":
                value = om.MDistance.uiToInternal(value)
            self.assertAlmostEqual(value, sign * length, places=5)
        return upper, lower

    def test_rest_unchanged(self):
        """slide 0・pin 0 では作成の前後で各jointのワールド行列が変わらない。"""
        before = [cmds.getAttr(joint + ".worldMatrix[0]") for joint in self.arm]
        setup = LimbPin.create(*self.arm, pole=self.pole, target=self.target, name="pin")
        after = [cmds.getAttr(joint + ".worldMatrix[0]") for joint in self.arm]
        for first, second in zip(before, after):
            for a, b in zip(first, second):
                self.assertAlmostEqual(a, b, places=9)
        self.assertEqual(self.check(setup, self.arm), (4.0, 3.5))

    def test_slide_keeps_total(self):
        """slide は合計 7.5 を保ち、1で下が0、-1で上が0、間は作成時の長さに比例して振り分ける。"""
        setup = LimbPin.create(*self.arm, pole=self.pole, target=self.target, name="pin")
        owner = str(setup.container)
        for slide in (-1.0, -0.6, -0.1, 0.0, 0.25, 0.7, 1.0):
            cmds.setAttr(owner + ".slide", slide)
            upper, lower = self.check(setup, self.arm)
            self.assertAlmostEqual(upper + lower, 7.5, places=6)
        cmds.setAttr(owner + ".slide", 1.0)
        self.assertAlmostEqual(self.lengths(setup)[1], 0.0, places=6)
        cmds.setAttr(owner + ".slide", -1.0)
        self.assertAlmostEqual(self.lengths(setup)[0], 0.0, places=6)
        # 作成時の長さを書き換えると、その長さを基準にする。
        cmds.setAttr(owner + ".slide", 0.5)
        cmds.setAttr(owner + ".restUpper", 5.0)
        self.check(setup, self.arm, rest=(5.0, 3.5))

    def test_pin_with_ik(self):
        """pin=1 で、同じ操作子を極ベクトルにした ikRPsolver の肘が操作子に、手首が目標に一致する(12姿勢)。"""
        setup = LimbPin.create(*self.arm, pole=self.pole, target=self.target, name="pin", pin=1.0)
        handle = cmds.ikHandle(startJoint=self.arm[0], endEffector=self.arm[2], solver="ikRPsolver",
                               name="armIk")[0]
        cmds.parent(handle, self.target)
        cmds.setAttr(handle + ".translate", 0.0, 0.0, 0.0)
        cmds.poleVectorConstraint(self.pole, handle)
        owner = str(setup.container)
        for _ in range(12):
            cmds.setAttr(self.pole + ".translate", random.uniform(1.0, 6.0), random.uniform(-3.0, 3.0),
                         random.uniform(-4.0, 4.0))
            cmds.setAttr(self.target + ".translate", random.uniform(2.0, 9.0), random.uniform(-4.0, 4.0),
                         random.uniform(-4.0, 4.0))
            cmds.setAttr(owner + ".slide", random.uniform(-1.0, 1.0))
            self.check(setup, self.arm)
            self.assertTrue((_world(self.arm[1]) - _world(self.pole)).length() < 1e-3)
            self.assertTrue((_world(self.arm[2]) - _world(self.target)).length() < 1e-3)
        # pin の途中は slide 後の長さと届く長さの線形補間。
        for pin in (0.0, 0.3, 0.75):
            cmds.setAttr(owner + ".pin", pin)
            self.check(setup, self.arm, rest=(4.0, 3.5))

    def test_negative_axis(self):
        """骨の向きが -X(右の腕)でも、作成時の符号を保ったまま長さを入れる。軸 y も使える。"""
        right = self.chain("right", -1.0)
        setup = LimbPin.create(*right, pole=self.pole, target=self.target, name="right", slide=0.4, pin=0.5)
        self.check(setup, right, sign=-1.0)
        self.assertLess(cmds.getAttr(right[1] + ".translateX"), 0.0)
        up = self.chain("up", 1.0)
        for joint in up[1:]:
            cmds.setAttr(joint + ".translateY", cmds.getAttr(joint + ".translateX"))
            cmds.setAttr(joint + ".translateX", 0.0)
        setup = LimbPin.create(*up, pole=self.pole, target=self.target, name="up", axis="y", slide=-0.5)
        self.assertAlmostEqual(cmds.getAttr(up[1] + ".translateY"), 2.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(up[2] + ".translateY"), 5.5, places=6)
        self.assertEqual(cmds.getAttr(up[1] + ".translateX"), 0.0)

    def test_ui_units(self):
        """UI単位がmm・radでも同じ長さになり、自動の単位変換ノードが入らない。"""
        cmds.currentUnit(linear="mm", angle="rad")
        setup = LimbPin.create(*self.arm, pole=self.pole, target=self.target, name="pin", slide=0.3, pin=0.6)
        self.check(setup, self.arm)
        cmds.setAttr(self.target + ".translate", 50.0, 20.0, 10.0)
        self.check(setup, self.arm)
        owned = set(cmds.ls(cmds.container(str(setup.container), query=True, nodeList=True) or []))
        self.assertFalse(set(cmds.ls(type="unitConversion")) - owned)

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消えて長さが戻り、Redoで戻る。"""
        before = set(cmds.ls())
        setup = LimbPin.create(*self.arm, pole=self.pole, target=self.target, name="pin", slide=0.5)
        owner = str(setup.container)
        added = set(cmds.ls()) - before - {owner}
        members = set(cmds.ls(cmds.container(owner, query=True, nodeList=True) or []))
        self.assertTrue(added)
        self.assertEqual({node for node in added if cmds.nodeType(node) != "hyperLayout"} - members, set())
        self.assertAlmostEqual(cmds.getAttr(self.arm[1] + ".translateX"), 5.75, places=6)
        cmds.undo()
        self.assertFalse(cmds.objExists(owner))
        self.assertEqual(set(cmds.ls()) - before, set())
        self.assertAlmostEqual(cmds.getAttr(self.arm[1] + ".translateX"), 4.0, places=6)
        cmds.redo()
        self.assertTrue(cmds.objExists(owner))
        self.check(LimbPin(owner), self.arm)

    def test_arguments(self):
        """不正なjoint・親子の違い・軸・範囲外の値・長さ0・既存の名前を拒否する。"""
        shoulder, elbow, wrist = self.arm
        cases = [
            dict(start=shoulder, mid=wrist, end=elbow),
            dict(start=shoulder, mid=elbow, end=elbow),
            dict(start=self.body, mid=elbow, end=wrist),
            dict(start=shoulder, mid=elbow, end=wrist, pole=cmds.createNode("multMatrix")),
            dict(start=shoulder, mid=elbow, end=wrist, target=wrist),
            dict(start=shoulder, mid=elbow, end=wrist, axis="w"),
            dict(start=shoulder, mid=elbow, end=wrist, slide=1.5),
            dict(start=shoulder, mid=elbow, end=wrist, pin=-0.1),
            dict(start=shoulder, mid=elbow, end=wrist, axis="z"),
        ]
        for case in cases:
            arguments = dict(pole=self.pole, target=self.target, name="bad")
            arguments.update(case)
            with self.assertRaises(ValueError):
                LimbPin.create(**arguments)
        self.assertFalse(cmds.objExists("bad"))
        LimbPin.create(*self.arm, pole=self.pole, target=self.target, name="good")
        with self.assertRaises(ValueError):
            LimbPin.create(*self.arm, pole=self.pole, target=self.target, name="good")


if __name__ == "__main__":
    unittest.main()
