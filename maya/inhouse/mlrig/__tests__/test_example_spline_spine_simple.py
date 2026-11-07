"""スプラインIKの背骨の簡易版(mlrig.examples.spline_spine_simple)を、実際の行列で検証する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.examples import spline_spine_simple as spline_spine


def _position(node):
    return om.MVector(*cmds.xform(node, query=True, worldSpace=True, translation=True))


def _matrix(node):
    return om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))


def _axis(node, index):
    m = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    return om.MVector(*m[index * 4:index * 4 + 3]).normal()


def _angle(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, a * b))))


class SplineSpineTest(unittest.TestCase):
    """作った背骨の基準姿勢・伸縮・体積・ねじれ・向きの固定・FK・接線・Undoを確かめる。"""

    def setUp(self):
        """空のシーンに背骨を作る(腰の高さ100、長さ50、骨6本)。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg")
        self.spine = spline_spine.build(name="spine", joint_count=6, length=50.0, height=100.0)

    def test_rest_pose(self):
        """基準姿勢では、変形用の骨が +Y に等間隔で並び、X が上・Z が正面を向く。"""
        self.assertEqual(len(self.spine.deform), 6)
        for index, joint in enumerate(self.spine.deform):
            position = _position(joint)
            self.assertAlmostEqual(position.y, 100 + 10 * index, places=3, msg=str(joint))
            self.assertAlmostEqual(position.x, 0, places=3)
            self.assertAlmostEqual(position.z, 0, places=3)
            self.assertLess(_angle(_axis(joint, 0), om.MVector(0, 1, 0)), 0.01, str(joint))
            self.assertLess(_angle(_axis(joint, 2), om.MVector(0, 0, 1)), 0.01, str(joint))
            self.assertAlmostEqual(cmds.getAttr("{}.scaleY".format(joint)), 1.0, places=4)

    def test_stretch_squash_and_limits(self):
        """胸を動かすと骨列が伸縮し、maxStretch / maxSquash を超えると胸に届かない。"""
        top = self.spine.deform[-1]
        middle = self.spine.deform[len(self.spine.deform) // 2]
        cmds.setAttr("{}.translateY".format(self.spine.chest), 10)  # 比 1.2
        self.assertLess((_position(top) - _position(self.spine.chest)).length(), 0.05)
        self.assertLess(cmds.getAttr("{}.scaleY".format(middle)), 0.95)  # 伸びると細くなる
        cmds.setAttr("{}.translateY".format(self.spine.chest), 50)  # 比 2.0 → 1.5 で止まる
        self.assertAlmostEqual(_position(top).y, 175, delta=0.5)
        cmds.setAttr("{}.translateY".format(self.spine.chest), -20)  # 比 0.6
        self.assertLess((_position(top) - _position(self.spine.chest)).length(), 0.05)
        self.assertGreater(cmds.getAttr("{}.scaleY".format(middle)), 1.1)  # 縮むと太くなる
        cmds.setAttr("{}.volume".format(self.spine.cog), 0)
        self.assertAlmostEqual(cmds.getAttr("{}.scaleY".format(middle)), 1.0, places=4)
        # 両端は体積の影響を受けない。
        self.assertAlmostEqual(cmds.getAttr("{}.scaleY".format(self.spine.deform[0])), 1.0, places=4)

    def test_twist_distribution(self):
        """胸を Y 軸で回すと、ねじれが根元から胸へ徐々に配分される。"""
        cmds.setAttr("{}.rotateY".format(self.spine.chest), 60)
        angles = []
        for joint in self.spine.deform:
            z = _axis(joint, 2)
            angles.append(math.degrees(math.atan2(z.x, z.z)))
        self.assertAlmostEqual(angles[0], 0, delta=0.5)
        self.assertAlmostEqual(angles[-1], 60, delta=0.5)
        for a, b in zip(angles, angles[1:]):
            self.assertGreaterEqual(b, a - 0.01)
        self.assertTrue(10 < angles[len(angles) // 2] < 50, angles)

    def test_lock_orientation(self):
        """lockOriChest=1 なら最上段の骨は胸の回転に合い、0 ならカーブの接線に沿う。

        胸側の接線は胸の子で一緒に回るので、接線のコントローラーを横へずらし、接線の向きを胸の回転と変えてから比べる。
        """
        cmds.setAttr("{}.translateZ".format(self.spine.tangents[1]), -12)
        cmds.setAttr("{}.rotateX".format(self.spine.chest), 40)
        top = self.spine.deform[-1]
        expected = om.MVector(0, math.cos(math.radians(40)), math.sin(math.radians(40)))
        self.assertLess(_angle(_axis(top, 0), expected), 0.05)
        cmds.setAttr("{}.lockOriChest".format(self.spine.cog), 0)
        self.assertGreater(_angle(_axis(top, 0), expected), 5)
        tangent = (_position(top) - _position(self.spine.deform[-2])).normal()
        self.assertLess(_angle(_axis(top, 0), tangent), 10)

    def test_lock_orientation_hips(self):
        """lockOriHips=1 なら最下段の骨は腰の回転に合う。0 でも基準姿勢へ戻すと元の向きになる。"""
        cmds.setAttr("{}.translateZ".format(self.spine.tangents[0]), 12)
        cmds.setAttr("{}.rotateX".format(self.spine.hips), -30)
        bottom = self.spine.deform[0]
        expected = om.MVector(0, math.cos(math.radians(30)), -math.sin(math.radians(30)))
        self.assertLess(_angle(_axis(bottom, 0), expected), 0.05)
        cmds.setAttr("{}.lockOriHips".format(self.spine.cog), 0)
        self.assertGreater(_angle(_axis(bottom, 0), expected), 5)
        cmds.setAttr("{}.rotateX".format(self.spine.hips), 0)
        cmds.setAttr("{}.translateZ".format(self.spine.tangents[0]), 0)
        self.assertLess(_angle(_axis(bottom, 0), om.MVector(0, 1, 0)), 0.01)

    def test_fk_offsets_and_tangents(self):
        """FKを回すと上の段が一緒に動き、カーブの CV は接線のコントローラーの位置に来る。"""
        top = self.spine.deform[-1]
        before = _position(top)
        cmds.setAttr("{}.rotateZ".format(self.spine.fk[1]), 30)
        self.assertGreater((_position(top) - before).length(), 5)
        self.assertLess((_position(self.spine.deform[1]) - om.MVector(0, 110, 0)).length(), 1e-3)
        cmds.setAttr("{}.rotateZ".format(self.spine.fk[1]), 0)
        cmds.setAttr("{}.translate".format(self.spine.tangents[0]), 3, 2, -4, type="double3")
        curve = self.spine.curve.getFullName()
        cv = om.MVector(*cmds.pointPosition("{}.cv[1]".format(curve), world=True))
        self.assertLess((cv - _position(self.spine.tangents[0])).length(), 1e-3)

    def test_cog_moves_everything_and_undo(self):
        """cog を動かすと全体が動く。作成は1回の Undo で消える。"""
        cmds.setAttr("{}.translate".format(self.spine.cog), 10, 5, -3, type="double3")
        for index, joint in enumerate(self.spine.deform):
            self.assertLess((_position(joint) - om.MVector(10, 105 + 10 * index, -3)).length(), 1e-3)
        cmds.undo()  # translate の変更
        second = spline_spine.build(name="second", joint_count=4, length=30.0, height=0.0)
        self.assertEqual(len(second.deform), 4)
        cmds.undo()
        self.assertFalse(cmds.objExists("second_rig"))
        self.assertTrue(cmds.objExists("spine_rig"))
        with self.assertRaises(ValueError):
            spline_spine.build(name="spine")
        with self.assertRaises(ValueError):
            spline_spine.build(name="bad", joint_count=3)


    def test_no_container_matrix_nodes_or_tangent_attributes(self):
        """コンテナ・マトリクスのノード・接線の倍率を作らず、追従はコンストレイントで行う。"""
        nodes = cmds.ls("spine_*")
        for kind in ("container", "multMatrix", "decomposeMatrix", "pickMatrix", "blendMatrix"):
            self.assertEqual(cmds.ls(nodes, type=kind), [], kind)
        for attr in ("tangentHips", "tangentChest"):
            self.assertFalse(cmds.attributeQuery(attr, node=str(self.spine.cog), exists=True), attr)
        for joint in self.spine.deform:
            self.assertTrue(cmds.listRelatives(str(joint), type="parentConstraint"), str(joint))
        # 向きの固定は parentConstraint(maintainOffset)でコントローラーを直接使う(_ori・orientConstraint なし)。
        self.assertEqual(cmds.ls(nodes, type="orientConstraint"), [])
        self.assertEqual(cmds.ls("spine_*_ori"), [])
        self.assertTrue(cmds.ls(nodes, type="pointConstraint"))

    def test_rig_scale(self):
        """リグ全体を拡大すると、骨の位置も同じ割合で広がり、伸縮しない。"""
        cmds.setAttr("spine_rig.scale", 2, 2, 2, type="double3")
        for index, joint in enumerate(self.spine.deform):
            self.assertLess((_position(joint) - om.MVector(0, 2 * (100 + 10 * index), 0)).length(), 1e-2, str(joint))
            self.assertAlmostEqual(cmds.getAttr("{}.scaleY".format(joint)), 1.0, places=3)


class SimpleSplineSpineTest(unittest.TestCase):
    """伸縮なしのシンプル版(stretch=False)を確かめる。"""

    def setUp(self):
        """空のシーンにシンプル版を作る(腰の高さ100、長さ50、骨6本)。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg")
        self.spine = spline_spine.build(name="simple", joint_count=6, length=50.0, height=100.0, stretch=False)

    def _segments(self):
        return [(_position(b) - _position(a)).length() for a, b in zip(self.spine.deform, self.spine.deform[1:])]

    def test_no_stretch_attributes_or_nodes(self):
        """伸縮・体積のアトリビュートとノードを作らない。基準姿勢は通常版と同じ。"""
        for attr in ("maxStretch", "maxSquash", "volume"):
            self.assertFalse(cmds.attributeQuery(attr, node=str(self.spine.cog), exists=True), attr)
        for attr in ("lockOriHips", "lockOriChest"):
            self.assertTrue(cmds.attributeQuery(attr, node=str(self.spine.cog), exists=True), attr)
        self.assertFalse(cmds.objExists("simple_curveInfo"))
        self.assertFalse(cmds.objExists("simple_stretchClamp"))
        for index, joint in enumerate(self.spine.deform):
            self.assertAlmostEqual(_position(joint).y, 100 + 10 * index, places=3)

    def test_lengths_stay_fixed(self):
        """胸を遠ざけても近づけても骨の長さは変わらず、断面も変わらない。"""
        cmds.setAttr("{}.translateY".format(self.spine.chest), 20)
        for length in self._segments():
            self.assertAlmostEqual(length, 10, places=3)
        # 伸びないので、一番上の骨は胸に届かない。
        self.assertGreater((_position(self.spine.deform[-1]) - _position(self.spine.chest)).length(), 15)
        cmds.setAttr("{}.translateY".format(self.spine.chest), -15)
        for length in self._segments():
            self.assertAlmostEqual(length, 10, places=3)
        for joint in self.spine.deform:
            self.assertAlmostEqual(cmds.getAttr("{}.scaleY".format(joint)), 1.0, places=6)

    def test_bend_twist_and_lock(self):
        """長さを変えない範囲の曲げ・ねじれ・向きの固定は通常版と同じに働く。"""
        cmds.setAttr("{}.translate".format(self.spine.chest), 0, -6, 18, type="double3")
        cmds.setAttr("{}.rotate".format(self.spine.chest), 40, 0, 0, type="double3")
        expected = om.MVector(0, math.cos(math.radians(40)), math.sin(math.radians(40)))
        self.assertLess(_angle(_axis(self.spine.deform[-1], 0), expected), 0.05)
        for length in self._segments():
            self.assertAlmostEqual(length, 10, places=3)
        cmds.setAttr("{}.rotate".format(self.spine.chest), 0, 60, 0, type="double3")
        cmds.setAttr("{}.translate".format(self.spine.chest), 0, 0, 0, type="double3")
        z = _axis(self.spine.deform[-1], 2)
        self.assertAlmostEqual(math.degrees(math.atan2(z.x, z.z)), 60, delta=0.5)


class NoFkSplineSpineTest(unittest.TestCase):
    """FKコントローラーなし(fk=False)を確かめる。"""

    def setUp(self):
        """空のシーンに、FKありとFKなしの背骨を同じ寸法で作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg")
        self.withFk = spline_spine.build(name="withFk", joint_count=6, length=50.0, height=100.0)
        self.spine = spline_spine.build(name="noFk", joint_count=6, length=50.0, height=100.0, fk=False)

    def test_no_fk_nodes(self):
        """FKのグループ・コントローラーを作らず、変形用の骨は6本ある。"""
        self.assertEqual(self.spine.fk, [])
        self.assertFalse(cmds.objExists("noFk_fk_grp"))
        self.assertEqual(cmds.ls("noFk_fk*"), [])
        self.assertEqual(len(self.spine.deform), 6)
        # lockOri と向きの固定の transform・reverse は作らない。
        for attr in ("lockOriHips", "lockOriChest"):
            self.assertFalse(cmds.attributeQuery(attr, node=str(self.spine.cog), exists=True), attr)
        self.assertEqual(cmds.ls("noFk_*Lock*"), [])
        self.assertEqual(cmds.ls("noFk_*", type="reverse"), [])
        # 最下段は腰へ parentConstraint(1ターゲット)、最上段はIKの骨へ point・胸へ orient、中間はIKの骨へ parent。
        first, last = self.spine.deform[0], self.spine.deform[-1]
        constraint = cmds.listRelatives(str(first), type="parentConstraint")[0]
        self.assertEqual(cmds.parentConstraint(constraint, query=True, targetList=True), ["noFk_hips_ctrl"])
        self.assertTrue(cmds.listRelatives(str(last), type="pointConstraint"))
        constraint = cmds.listRelatives(str(last), type="orientConstraint")[0]
        self.assertEqual(cmds.orientConstraint(constraint, query=True, targetList=True), ["noFk_chest_ctrl"])
        for joint in self.spine.deform[1:-1]:
            self.assertTrue(cmds.listRelatives(str(joint), type="parentConstraint"), str(joint))

    def test_matches_fk_version_when_fk_is_not_used(self):
        """FKを回していないFKあり版と、同じ姿勢で変形用の骨のワールドマトリクスが一致する。"""
        poses = [
            {"chest.translate": (0, 10, 6), "chest.rotate": (30, 20, 0)},
            {"hips.rotate": (-20, 0, 10), "tan0.translate": (3, 0, 5), "tan1.translate": (-2, 0, -4)},
            {"chest.translate": (5, -12, 15), "chest.rotate": (70, -40, 25), "hips.translate": (2, 3, -4)},
            {"chest.translate": (0, 50, 0), "chest.rotate": (0, 150, 0)},  # 伸縮の上限を超えて胸に届かない
        ]
        for pose in poses:
            for rig in (self.withFk, self.spine):
                prefix = "withFk" if rig is self.withFk else "noFk"
                for key, value in pose.items():
                    node, attr = key.split(".")
                    plug = "{}_{}_ctrl.{}".format(prefix, node, attr)
                    if isinstance(value, tuple):
                        cmds.setAttr(plug, *value, type="double3")
                    else:
                        cmds.setAttr(plug, value)
            for a, b in zip(self.withFk.deform, self.spine.deform):
                ma, mb = _matrix(a), _matrix(b)
                for i in range(16):
                    self.assertAlmostEqual(ma[i], mb[i], places=4, msg="{} {}".format(pose, b))

    def test_lock_and_stretch_still_work(self):
        """向きの固定と伸縮は、FKなしでも働く。"""
        cmds.setAttr("{}.translateZ".format(self.spine.tangents[1]), -12)
        cmds.setAttr("{}.rotateX".format(self.spine.chest), 40)
        expected = om.MVector(0, math.cos(math.radians(40)), math.sin(math.radians(40)))
        self.assertLess(_angle(_axis(self.spine.deform[-1], 0), expected), 0.05)
        cmds.setAttr("{}.rotateX".format(self.spine.chest), 0)
        cmds.setAttr("{}.translateZ".format(self.spine.tangents[1]), 0)
        cmds.setAttr("{}.translateY".format(self.spine.chest), 10)
        self.assertLess((_position(self.spine.deform[-1]) - _position(self.spine.chest)).length(), 0.05)


if __name__ == "__main__":
    unittest.main(argv=["spline_spine_simple"], exit=False, verbosity=2)
