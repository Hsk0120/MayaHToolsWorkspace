"""FootRollの逆足の計算を、rotatePivotを持つtransformの逆足の階層をMayaで組んだ結果と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import FootRoll


def _world(node):
    """ワールド行列。"""
    return om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _position(node):
    """ワールド位置。"""
    return om.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))


class FootRollTest(unittest.TestCase):
    """角度の分配・逆足の階層との一致・作成時の姿勢・単位・Undo・引数検査を確認する。"""

    def setUp(self):
        """回転・移動した足のコントロールの下に支点を、別の階層に足首と母指球のjointを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.control = cmds.createNode("transform", name="footCtrl")
        cmds.setAttr(self.control + ".translate", 3, 0.5, -2)
        cmds.setAttr(self.control + ".rotate", 5, 30, -4)
        positions = {
            "toe": (0.3, 0, 6), "heel": (-0.2, 0, -2.5), "inner": (1.5, 0, 2.5), "outer": (-1.6, 0, 2),
        }
        self.pivots = {}
        for role, position in positions.items():
            node = cmds.createNode("transform", name=role + "Pivot", parent=self.control)
            cmds.setAttr(node + ".translate", *position)
            self.pivots[role] = node
        leg = cmds.createNode("transform", name="leg")
        cmds.setAttr(leg + ".rotate", 0, 20, 0)
        cmds.setAttr(leg + ".translate", 2, 0, -1)
        self.ankle = cmds.createNode("joint", name="ankle", parent=leg)
        cmds.xform(self.ankle, worldSpace=True, translation=_position(self.control) + om.MVector(0.1, 4, -0.3))
        cmds.setAttr(self.ankle + ".rotate", 70, 10, -5)
        self.ball = cmds.createNode("joint", name="ball", parent=self.ankle)
        target = om.MPoint(0, 0.6, 3.5) * _world(self.control)
        cmds.xform(self.ball, worldSpace=True, translation=(target.x, target.y, target.z))
        cmds.setAttr(self.ball + ".rotate", -20, 0, 10)

    def build(self, **kwargs):
        """セットアップを作る。"""
        p = self.pivots
        return FootRoll.create(
            self.control, self.ankle, self.ball, p["toe"], p["heel"], p["inner"], p["outer"], **kwargs
        ).container

    def reference(self, roll, bank, breakAngle, rollAxis="x", bankAxis="z", swivel=0.0, toeTap=0.0,
                  swivelAxis="y"):
        """コントロールの下にrotatePivotを持つ逆足の階層を組み、足首と母指球のワールド行列を返す。"""
        angles = FootRoll.angles(roll, bank, breakAngle)
        angles.update(swivel=swivel, toeTap=toeTap)
        axes = {"outer": bankAxis, "inner": bankAxis, "swivel": swivelAxis}
        parent, frames = self.control, {}
        local = _world(self.control).inverse()
        for role in ("swivel", "outer", "inner", "heel", "toe", "ball", "toeTap"):
            if role == "toeTap":
                parent = frames["toe"]
            node = cmds.createNode("transform", name="ref_" + role, parent=parent)
            source = self.ball if role in ("ball", "swivel", "toeTap") else self.pivots[role]
            pivot = om.MPoint(_position(source)) * local
            cmds.xform(node, rotatePivot=(pivot.x, pivot.y, pivot.z), objectSpace=True)
            frames[role] = node
            parent = node
        results = []
        for role, source, holder in (("ankle", self.ankle, "ball"), ("ball", self.ball, "toeTap")):
            node = cmds.createNode("transform", name="ref_" + role + "Out", parent=frames[holder])
            # 回転0の状態で生成時の姿勢を写してから、各支点を回す。
            rest = _world(source) * _world(frames[holder]).inverse()
            cmds.xform(node, matrix=list(rest), objectSpace=True)
            results.append(node)
        for role, node in frames.items():
            axis = axes.get(role, rollAxis)
            sign = -1 if axis.startswith("-") else 1
            cmds.setAttr(node + ".rotate" + axis[-1].upper(), sign * angles[role])
        return results, frames

    def assertMatrix(self, actual, expected, message=None, tolerance=1e-4):
        """行列が一致する。"""
        self.assertTrue(om.MMatrix(actual).isEquivalent(om.MMatrix(expected), tolerance), message)

    def outputs(self, owner):
        """出力のワールド行列。"""
        return [om.MMatrix(cmds.getAttr(str(owner) + "." + attr)) for attr in ("ankleMatrix", "ballMatrix")]

    def test_angles(self):
        """rollとbankを各支点へ分ける。"""
        self.assertEqual(FootRoll.angles(-20, 0, 30)["heel"], -20)
        self.assertEqual(FootRoll.angles(20, 0, 30)["ball"], 20)
        values = FootRoll.angles(50, -10, 30)
        self.assertEqual((values["heel"], values["ball"], values["toe"]), (0, 30, 20))
        self.assertEqual((values["outer"], values["inner"]), (0, -10))
        self.assertEqual(FootRoll.angles(0, 15, 30)["outer"], 15)

    def test_rest_pose(self):
        """作成直後(roll=bank=0)の出力は、足首と母指球の生成時のワールド行列と一致する。"""
        owner = self.build()
        ankle, ball = self.outputs(owner)
        self.assertMatrix(ankle, _world(self.ankle))
        self.assertMatrix(ball, _world(self.ball))

    def test_matches_reverse_foot_hierarchy(self):
        """roll・bankの組み合わせで、rotatePivotの逆足の階層と同じ行列・角度になる。"""
        owner = self.build(breakAngle=25)
        for roll, bank in ((-30, 0), (15, 0), (25, 0), (60, 0), (0, 20), (0, -25), (45, 12), (-15, -8)):
            with self.subTest(roll=roll, bank=bank):
                cmds.setAttr(str(owner) + ".roll", roll)
                cmds.setAttr(str(owner) + ".bank", bank)
                refs, frames = self.reference(roll, bank, 25)
                ankle, ball = self.outputs(owner)
                self.assertMatrix(ankle, _world(refs[0]), "ankle")
                self.assertMatrix(ball, _world(refs[1]), "ball")
                expected = FootRoll.angles(roll, bank, 25)
                for role, value in expected.items():
                    self.assertAlmostEqual(cmds.getAttr(str(owner) + "." + role + "Angle"), value, places=6)
                cmds.delete(frames["swivel"])

    def test_swivel_and_toe_tap(self):
        """swivelは母指球を中心に足全体を回し、toeTapはつま先の骨だけを回す。"""
        owner = self.build(swivelAxis="-y")
        for roll, bank, swivel, tap in ((0, 0, 30, 0), (0, 0, 0, -25), (40, 10, -20, 15)):
            with self.subTest(roll=roll, bank=bank, swivel=swivel, tap=tap):
                for attr, value in (("roll", roll), ("bank", bank), ("swivel", swivel), ("toeTap", tap)):
                    cmds.setAttr(str(owner) + "." + attr, value)
                refs, frames = self.reference(roll, bank, 30, swivel=swivel, toeTap=tap, swivelAxis="-y")
                ankle, ball = self.outputs(owner)
                self.assertMatrix(ankle, _world(refs[0]), "ankle")
                self.assertMatrix(ball, _world(refs[1]), "ball")
                cmds.delete(frames["swivel"])
        # toeTapだけなら足首は動かず、母指球の位置も変わらない。
        for attr in ("roll", "bank", "swivel"):
            cmds.setAttr(str(owner) + "." + attr, 0)
        cmds.setAttr(str(owner) + ".toeTap", 30)
        ankle, ball = self.outputs(owner)
        self.assertMatrix(ankle, _world(self.ankle))
        self.assertTrue(om.MVector(ball[12], ball[13], ball[14]).isEquivalent(_position(self.ball), 1e-4))
        self.assertFalse(ball.isEquivalent(_world(self.ball), 1e-3))

    def test_ground_contact(self):
        """rollの各段階で支点が地面(コントロールの位置)に残る: 負はかかと、break以下は母指球、超えるとつま先。"""
        owner = self.build(breakAngle=30)
        cmds.setAttr(str(owner) + ".roll", 20)
        ankle_rest = _world(self.ankle)
        ankle_now = self.outputs(owner)[0]
        delta = ankle_rest.inverse() * ankle_now
        ball_point = om.MPoint(_position(self.ball))
        self.assertTrue((ball_point * delta).isEquivalent(ball_point, 1e-4), "ball pivot stays")
        heel_point = om.MPoint(_position(self.pivots["heel"]))
        self.assertGreater((heel_point * delta - heel_point).length(), 0.5)
        cmds.setAttr(str(owner) + ".roll", 70)
        delta = ankle_rest.inverse() * self.outputs(owner)[0]
        self.assertFalse((ball_point * delta).isEquivalent(ball_point, 1e-2), "ball lifts")
        # つま先の先端は、つま先の骨(ballMatrix)に付いた点として地面に残る。
        toe_delta = _world(self.ball).inverse() * self.outputs(owner)[1]
        toe_point = om.MPoint(_position(self.pivots["toe"]))
        self.assertTrue((toe_point * toe_delta).isEquivalent(toe_point, 1e-4), "toe pivot stays")
        cmds.setAttr(str(owner) + ".roll", -25)
        delta = ankle_rest.inverse() * self.outputs(owner)[0]
        self.assertTrue((heel_point * delta).isEquivalent(heel_point, 1e-4), "heel pivot stays")

    def test_control_follow_and_break_angle(self):
        """コントロールを動かすと足全体が付いて行き、breakAngleを変えると母指球とつま先の配分が変わる。"""
        owner = self.build()
        # 参照の階層は生成時の姿勢でコントロールの下に組み、コントロールと一緒に動かす。
        refs, _ = self.reference(40, 0, 10)
        cmds.setAttr(self.control + ".translate", -4, 2, 6)
        cmds.setAttr(self.control + ".rotate", -10, 80, 15)
        cmds.setAttr(str(owner) + ".roll", 40)
        cmds.setAttr(str(owner) + ".breakAngle", 10)
        ankle, ball = self.outputs(owner)
        self.assertMatrix(ankle, _world(refs[0]))
        self.assertMatrix(ball, _world(refs[1]))
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".toeAngle"), 30.0, places=6)

    def test_axes_and_units(self):
        """負の軸は逆回り、UIの単位がmm・radianでも同じ行列になる。"""
        owner = self.build(rollAxis="-x", bankAxis="-z")
        cmds.setAttr(str(owner) + ".roll", 45)
        cmds.setAttr(str(owner) + ".bank", -15)
        refs, _ = self.reference(45, -15, 30, rollAxis="-x", bankAxis="-z")
        expected = [_world(node) for node in refs]
        self.assertMatrix(self.outputs(owner)[0], expected[0])
        cmds.currentUnit(linear="mm", angle="rad")
        cmds.dgdirty(allPlugs=True)
        actual = self.outputs(owner)
        self.assertMatrix(actual[0], expected[0])
        self.assertMatrix(actual[1], expected[1])
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".roll"), 45.0, places=6)

    def test_ownership_and_undo(self):
        """生成した演算ノードはcontainerが所有し、1回のUndoで全体を取り消し、Redoで戻す。"""
        before = set(cmds.ls())
        owner = str(self.build(name="foot"))
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        # containerの作成でMayaが付けるhyperLayoutは除く。
        added = set(cmds.ls()) - before - {owner} - set(cmds.ls(type="hyperLayout"))
        self.assertTrue(added)
        self.assertEqual(added - members, set())
        self.assertTrue(any(cmds.nodeType(node) == "unitConversion" for node in members))
        cmds.undo()
        self.assertFalse(cmds.objExists(owner))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists(owner))

    def test_arguments(self):
        """不正な軸・角度・重複・既存の名前を拒否する。"""
        p = self.pivots
        args = [self.control, self.ankle, self.ball, p["toe"], p["heel"], p["inner"], p["outer"]]
        with self.assertRaises(ValueError):
            FootRoll.create(*args, rollAxis="x", bankAxis="-x")
        with self.assertRaises(ValueError):
            FootRoll.create(*args, rollAxis="x", bankAxis="z", swivelAxis="-z")
        with self.assertRaises(ValueError):
            FootRoll.create(*args, rollAxis="w")
        with self.assertRaises(ValueError):
            FootRoll.create(*args, breakAngle=-1)
        with self.assertRaises(ValueError):
            FootRoll.create(*args, breakAngle=math.inf)
        with self.assertRaises(ValueError):
            FootRoll.create(*(args[:-1] + [p["toe"]]))
        FootRoll.create(*args, name="foot")
        with self.assertRaises(ValueError):
            FootRoll.create(*args, name="foot")


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FootRollTest))
    if not result.wasSuccessful():
        raise AssertionError("FootRoll tests failed")
