"""SkirtLegOffsetの開く角度と行列を、atan2・asin・軸回りのQuaternionで独立に求めた値と比べて確かめる。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import SkirtLegOffset

COUNT = 8
RADIUS = 2.5
LENGTH = 4.0
FLARE = 15.0


def _world(node):
    """ノードのワールド行列。"""
    return om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _translation(vector):
    """平行移動の行列。"""
    matrix = om.MTransformationMatrix()
    matrix.setTranslation(om.MVector(vector), om.MSpace.kTransform)
    return matrix.asMatrix()


def _close(test, first, second, tolerance=1e-4):
    """2つの行列の各成分が誤差の範囲で等しいことを確かめる。"""
    for a, b in zip(first, second):
        test.assertAlmostEqual(a, b, delta=tolerance)


class SkirtLegOffsetTest(unittest.TestCase):
    """作成直後・各姿勢での独立計算との一致・めり込まない角度・アトリビュート・接続・UI単位・所有とUndo・引数。"""

    def setUp(self):
        """傾けた腰の下に、左右の脚(股関節→膝のjoint)と、外へ15度開いた8本のスカートの骨を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.pelvis = cmds.createNode("transform", name="pelvis")
        cmds.setAttr(self.pelvis + ".translate", 1, 10, -2)
        cmds.setAttr(self.pelvis + ".rotate", 5, 25, -3)
        self.hips, self.knees = [], []
        for side, x in (("L", 1.2), ("R", -1.2)):
            cmds.select(clear=True)
            hip = cmds.joint(name="hip" + side)
            cmds.parent(hip, self.pelvis, relative=True)
            cmds.setAttr(hip + ".translate", x, -0.5, 0)
            knee = cmds.joint(name="knee" + side)  # 選択中のhipの子になる
            cmds.setAttr(knee + ".translate", 0, -5, 0)
            self.hips.append(cmds.ls(hip, long=True)[0])
            self.knees.append(cmds.ls(knee, long=True)[0])
        self.skirts, self.tips = [], []
        for index in range(COUNT):
            azimuth = 2 * math.pi * index / COUNT
            out = (math.sin(azimuth), 0.0, math.cos(azimuth))
            cmds.select(clear=True)
            skirt = cmds.joint(name="skirt{}".format(index))
            cmds.parent(skirt, self.pelvis, relative=True)
            cmds.setAttr(skirt + ".translate", RADIUS * out[0], 0, RADIUS * out[2])
            flare = math.radians(FLARE)
            tip = cmds.joint(name="skirtTip{}".format(index))  # 選択中のskirtの子になる
            cmds.setAttr(tip + ".translate", LENGTH * math.sin(flare) * out[0], -LENGTH * math.cos(flare),
                         LENGTH * math.sin(flare) * out[2])
            self.skirts.append(cmds.ls(skirt, long=True)[0])
            self.tips.append(cmds.ls(tip, long=True)[0])
        self.legs = list(zip(self.hips, self.knees))
        inverse = _world(self.pelvis).inverse()
        self.rest = [_world(skirt) * inverse for skirt in self.skirts]
        self.restTip = [_world(tip) * inverse for tip in self.tips]

    def _create(self, **flags):
        flags.setdefault("name", "skirtOffset")
        return SkirtLegOffset.create(self.pelvis, self.skirts, self.legs, **flags)

    def _expected(self, index, clearance=10.0, maxAngle=80.0, spread=45.0, weight=1.0):
        """骨indexの角度・parent空間の行列を独立に求める(atan2・asin・Quaternionの軸回転)。"""
        inverse = _world(self.pelvis).inverse()
        position = om.MVector(self.rest[index][12], self.rest[index][13], self.rest[index][14])
        tip = om.MVector(self.restTip[index][12], self.restTip[index][13], self.restTip[index][14])
        s = (tip - position).normal()
        t = (s ^ position).normal()
        n = t ^ s
        best = 0.0
        for hip, knee in self.legs:
            a = _world(hip) * inverse
            b = _world(knee) * inverse
            leg = om.MVector(b[12] - a[12], b[13] - a[13], b[14] - a[14])
            plane = math.degrees(math.atan2(leg * n, leg * s))
            lateral = math.degrees(math.asin(max(-1.0, min(1.0, (leg * t) / leg.length()))))
            falloff = min(max(1.0 - abs(lateral) / spread, 0.0), 1.0)
            best = max(best, min(max((plane + clearance) * falloff, 0.0), maxAngle))
        angle = best * weight
        rotation = om.MQuaternion(math.radians(angle), t).asMatrix()
        offset = _translation(-position) * rotation * _translation(position)
        return angle, offset, self.rest[index] * offset

    def _check(self, graph, **flags):
        """全ての骨で、出力が独立計算と一致することを確かめる。"""
        owner = str(graph.container)
        for index in range(COUNT):
            angle, offset, matrix = self._expected(index, **flags)
            self.assertAlmostEqual(cmds.getAttr("{}.angle{}".format(owner, index)), angle, delta=1e-3)
            _close(self, cmds.getAttr("{}.offsetMatrix{}".format(owner, index)), offset)
            _close(self, cmds.getAttr("{}.matrix{}".format(owner, index)), matrix)
            _close(self, cmds.getAttr("{}.worldMatrix{}".format(owner, index)), matrix * _world(self.pelvis))

    def test_rest_pose_does_not_move(self):
        """作成直後は脚が離れているので全ての角度が0で、出力は生成時の骨と一致する。"""
        graph = self._create()
        owner = str(graph.container)
        for index in range(COUNT):
            self.assertAlmostEqual(cmds.getAttr("{}.angle{}".format(owner, index)), 0.0, delta=1e-6)
            _close(self, cmds.getAttr("{}.offsetMatrix{}".format(owner, index)), om.MMatrix())
            _close(self, cmds.getAttr("{}.worldMatrix{}".format(owner, index)), _world(self.skirts[index]))
        self._check(graph)

    def test_matches_independent_computation_in_poses(self):
        """前・横・後ろ・ひねり・腰の回転の各姿勢で、角度と行列が独立計算と一致する。"""
        graph = self._create()
        poses = [
            ((-30, 0, 0), (0, 0, 0)), ((-70, 0, 0), (0, 0, 0)), ((-110, 0, 0), (-20, 0, 0)),
            ((-60, 0, 30), (40, 0, -20)), ((0, 0, 50), (0, 0, -50)), ((45, 0, 0), (-45, 30, 0)),
            ((-80, 40, -20), (10, -30, 15)),
        ]
        for left, right in poses:
            cmds.setAttr(self.hips[0] + ".rotate", *left)
            cmds.setAttr(self.hips[1] + ".rotate", *right)
            self._check(graph)
        cmds.setAttr(self.pelvis + ".rotate", -30, 80, 10)
        cmds.setAttr(self.pelvis + ".translate", 5, 3, 1)
        self._check(graph)

    def test_front_skirt_opens_and_back_stays(self):
        """左脚を前へ上げると左前の骨だけが開き、真後ろの骨は動かない。開いた後の骨と脚の角度はclearance。"""
        graph = self._create(spread=90.0)
        owner = str(graph.container)
        cmds.setAttr(self.hips[0] + ".rotateX", -60)
        front = cmds.getAttr(owner + ".angle0")
        self.assertGreater(front, 30.0)
        self.assertAlmostEqual(cmds.getAttr(owner + ".angle4"), 0.0, delta=1e-6)
        # 脚が前の骨の開く面からどれだけ外れていても、開いた骨は面へ写した脚から clearance だけ外側にある。
        inverse = _world(self.pelvis).inverse()
        a, b = _world(self.hips[0]) * inverse, _world(self.knees[0]) * inverse
        leg = om.MVector(b[12] - a[12], b[13] - a[13], b[14] - a[14])
        matrix = om.MMatrix(cmds.getAttr(owner + ".matrix0"))
        tip = self.restTip[0] * self.rest[0].inverse() * matrix
        bone = om.MVector(tip[12] - matrix[12], tip[13] - matrix[13], tip[14] - matrix[14])
        position = om.MVector(self.rest[0][12], self.rest[0][13], self.rest[0][14])
        axis = (om.MVector(self.restTip[0][12], self.restTip[0][13], self.restTip[0][14]) - position).normal()
        t = (axis ^ position).normal()
        projected = leg - t * (leg * t)
        self.assertAlmostEqual(abs(bone * t), 0.0, delta=1e-6)
        self.assertAlmostEqual(math.degrees(projected.angle(bone)), 10.0, delta=1e-3)
        # 脚を上げるほど大きく開く(単調)。
        previous = 0.0
        for angle in range(0, -100, -10):
            cmds.setAttr(self.hips[0] + ".rotateX", angle)
            value = cmds.getAttr(owner + ".angle0")
            self.assertGreaterEqual(value, previous - 1e-6)
            previous = value

    def test_attributes(self):
        """clearance・maxAngle・spread・weight の変更が式どおりに反映される。"""
        graph = self._create()
        owner = str(graph.container)
        cmds.setAttr(self.hips[0] + ".rotate", -75, 0, 20)
        cmds.setAttr(self.hips[1] + ".rotate", -40, 0, -10)
        for attr, value, flags in (
            ("clearance", 25.0, {"clearance": 25.0}), ("maxAngle", 20.0, {"clearance": 25.0, "maxAngle": 20.0}),
            ("spread", 20.0, {"clearance": 25.0, "maxAngle": 20.0, "spread": 20.0}),
            ("weight", 0.5, {"clearance": 25.0, "maxAngle": 20.0, "spread": 20.0, "weight": 0.5}),
        ):
            cmds.setAttr(owner + "." + attr, value)
            self._check(graph, **flags)
        self.assertLessEqual(max(cmds.getAttr("{}.angle{}".format(owner, i)) for i in range(COUNT)), 10.0 + 1e-6)
        cmds.setAttr(owner + ".weight", 0)
        for index in range(COUNT):
            _close(self, cmds.getAttr("{}.offsetMatrix{}".format(owner, index)), om.MMatrix())

    def test_connect_and_skirt_axis(self):
        """connect=Trueで骨のoffsetParentMatrixへ接続され、骨のワールド行列が出力と一致する。軸指定も同じ結果。"""
        graph = self._create(connect=True)
        owner = str(graph.container)
        cmds.setAttr(self.hips[0] + ".rotateX", -70)
        for index in range(COUNT):
            self.assertEqual(cmds.listConnections(self.skirts[index] + ".offsetParentMatrix", source=True,
                                                  destination=False, plugs=True),
                             ["{}.offsetMatrix{}".format(owner, index)])
            _close(self, _world(self.skirts[index]), cmds.getAttr("{}.worldMatrix{}".format(owner, index)))
        self._check(graph)
        # 骨の向きを軸で指定: 先端の向きへ+Xを向けたtransformで同じ角度になる。
        cmds.file(new=True, force=True)
        self.setUp()
        aimed = []
        for index, (skirt, tip) in enumerate(zip(self.skirts, self.tips)):
            node = cmds.createNode("transform", name="aimed{}".format(index), parent=self.pelvis)
            cmds.matchTransform(node, skirt, position=True)
            cmds.delete(cmds.aimConstraint(tip, node, aimVector=(0, 0, 1), upVector=(0, 1, 0),
                                           worldUpType="vector", worldUpVector=(0, 0, 1)))
            aimed.append(cmds.ls(node, long=True)[0])
        cmds.setAttr(self.hips[0] + ".rotateX", -70)
        axis = SkirtLegOffset.create(self.pelvis, aimed, self.legs, name="aimedOffset", skirtAxis="z")
        reference = self._create()
        for index in range(COUNT):
            self.assertAlmostEqual(cmds.getAttr("aimedOffset.angle{}".format(index)),
                                   cmds.getAttr("{}.angle{}".format(reference.container, index)), delta=1e-3)
        self.assertGreater(cmds.getAttr(str(axis.container) + ".angle0"), 1.0)

    def test_ui_units(self):
        """UIの単位がmm・radianでも、角度の出力は度で同じ値になる。"""
        cmds.setAttr(self.hips[0] + ".rotateX", -70)
        graph = self._create()
        before = [cmds.getAttr("{}.angle{}".format(graph.container, i)) for i in range(COUNT)]
        cmds.currentUnit(angle="rad", linear="mm")
        after = [cmds.getAttr("{}.angle{}".format(graph.container, i)) for i in range(COUNT)]
        for a, b in zip(before, after):
            self.assertAlmostEqual(a, b, delta=1e-6)
        cmds.currentUnit(angle="deg", linear="cm")
        cmds.delete(str(graph.container))
        cmds.currentUnit(angle="rad", linear="mm")
        built = self._create(name="builtInRadians")
        cmds.currentUnit(angle="deg", linear="cm")
        self._check(built)

    def test_ownership_and_undo(self):
        """生成した計算ノードは全てcontainerが所有し、1回のUndoで全て消え、Redoで戻る。"""
        before = set(cmds.ls())
        cmds.undoInfo(stateWithoutFlush=True)
        graph = self._create(connect=True)
        owner = str(graph.container)
        created = set(cmds.ls()) - before - {owner}
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        created -= set(cmds.ls(type="hyperLayout"))
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.undo()
        self.assertEqual(set(cmds.ls()) - before, set())
        self.assertFalse(cmds.listConnections(self.skirts[0] + ".offsetParentMatrix", source=True) or [])
        cmds.redo()
        self.assertTrue(cmds.objExists(owner))
        cmds.setAttr(self.hips[0] + ".rotateX", -60)
        self._check(SkirtLegOffset(owner))

    def test_invalid_arguments(self):
        """不正な引数はValueErrorになる。"""
        cases = [
            dict(skirtAxis="w"), dict(maxAngle=-1), dict(maxAngle=200), dict(spread=0), dict(spread=120),
            dict(clearance=float("nan")),
        ]
        for flags in cases:
            with self.assertRaises(ValueError, msg=str(flags)):
                self._create(**flags)
        with self.assertRaises(ValueError):
            SkirtLegOffset.create(self.pelvis, [], self.legs)
        with self.assertRaises(ValueError):
            SkirtLegOffset.create(self.pelvis, self.skirts, [])
        with self.assertRaises(ValueError):
            SkirtLegOffset.create(self.pelvis, self.skirts, [(self.hips[0], self.hips[0])])
        with self.assertRaises(ValueError):
            SkirtLegOffset.create(self.pelvis, [self.pelvis], self.legs)
        with self.assertRaises(ValueError):
            SkirtLegOffset.create(self.pelvis, self.tips, self.legs)  # 子が無いので向きが決まらない
        with self.assertRaises(ValueError):
            SkirtLegOffset.create(self.pelvis, self.tips, self.legs, connect=True, skirtAxis="x")
        center = cmds.createNode("transform", name="center", parent=self.pelvis)
        cmds.createNode("transform", name="centerTip", parent=center)
        cmds.setAttr("centerTip.translate", 0, -3, 0)
        with self.assertRaises(ValueError):
            SkirtLegOffset.create(self.pelvis, [center], self.legs)  # 腰の中心にあり開く面が決まらない
        self._create(name="taken")
        with self.assertRaises(ValueError):
            self._create(name="taken")
        self.assertEqual(cmds.ls(type="container"), ["taken"])


if __name__ == "__main__":
    unittest.main(argv=["test_setup_skirt_leg_offset"], exit=False, verbosity=2)
