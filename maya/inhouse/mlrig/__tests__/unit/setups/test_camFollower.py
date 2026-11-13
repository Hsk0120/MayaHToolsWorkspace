"""CamFollowerの休止・上昇・休止・下降を、試験側で独立に書いた運動曲線の式とDGの数値微分で確かめる。"""

import math
import random
import unittest

from maya import cmds

from mlrig.setups import CamFollower

RISE = 2.0
UP, HOLD, DOWN = 120.0, 60.0, 120.0


def _expected(degrees, law="cycloidal", rise=RISE):
    """試験側の独立な式。カムの角度(度)から変位(cm)を区間ごとに求める。"""
    wrapped = degrees % 360.0
    if wrapped < UP:
        u, sign, base = wrapped / UP, 1.0, 0.0
    elif wrapped < UP + HOLD:
        return rise
    elif wrapped < UP + HOLD + DOWN:
        u, sign, base = (wrapped - UP - HOLD) / DOWN, -1.0, rise
    else:
        return 0.0
    if law == "cycloidal":
        shape = u - math.sin(2.0 * math.pi * u) / (2.0 * math.pi)
    else:
        shape = (1.0 - math.cos(math.pi * u)) / 2.0
    return base + sign * rise * shape


class CamFollowerTest(unittest.TestCase):
    """作成時・区間ごとの変位・連続性・Python版・速度・運動曲線・rise/phase・軸と単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """カムを rotateZ = 25 度、従動節を translateY = 3cm に置いて生成する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.cam = cmds.createNode("joint", name="cam")
        cmds.setAttr(self.cam + ".rotateZ", 25.0)
        self.follower = cmds.createNode("joint", name="follower")
        cmds.setAttr(self.follower + ".translateY", 3.0)
        self.setup = CamFollower.create(self.cam, self.follower, RISE, UP, HOLD, DOWN, name="camFollower")
        self.owner = str(self.setup.container)

    def _turn(self, degrees):
        """生成時から degrees 度カムを回し、従動節の上昇量(cm)を返す。"""
        cmds.setAttr(self.cam + ".rotateZ", 25.0 + degrees)
        return cmds.getAttr(self.follower + ".translateY") - 3.0

    def test_rest(self):
        """生成時は従動節が跳ねず、上昇の直前で lift・velocity・進みが0。"""
        self.assertAlmostEqual(cmds.getAttr(self.follower + ".translateY"), 3.0, places=6)
        for attribute in ("lift", "velocity", "riseProgress", "returnProgress", "turn", "camAngle"):
            with self.subTest(attribute=attribute):
                self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), 0.0, places=6)

    def test_segments(self):
        """下の休止・上昇・上の休止・下降の各区間で、試験側の式と一致する(正負の回転・複数回転)。"""
        for turn in (-2, -1, 0, 1, 3):
            for local in (0.0, 30.0, 60.0, 90.0, 119.0, 120.0, 150.0, 179.0, 200.0, 240.0, 299.0, 300.0, 330.0):
                with self.subTest(turn=turn, local=local):
                    self.assertAlmostEqual(self._turn(turn * 360.0 + local), _expected(local), places=5)
                    if local > 0.0:  # 360度の倍数ちょうどは浮動小数の丸めで段がどちらにも転ぶ(変位はどちらも0)
                        self.assertEqual(cmds.getAttr(self.owner + ".turn"), float(turn))
        self.assertAlmostEqual(self._turn(60.0), RISE / 2.0, places=6)  # 上昇の中央でちょうど半分
        self.assertAlmostEqual(self._turn(150.0), RISE, places=6)
        self.assertAlmostEqual(self._turn(330.0), 0.0, places=6)

    def test_continuous_at_boundaries(self):
        """区間の切り替わり(0・120・180・300・360度)の前後で、変位も速度も連続する。"""
        for edge in (0.0, UP, UP + HOLD, UP + HOLD + DOWN, 360.0, -360.0 + UP):
            with self.subTest(edge=edge):
                before = self._turn(edge - 1e-3)
                speedBefore = cmds.getAttr(self.owner + ".velocity")
                after = self._turn(edge + 1e-3)
                speedAfter = cmds.getAttr(self.owner + ".velocity")
                self.assertAlmostEqual(before, after, delta=1e-5)
                self.assertAlmostEqual(speedBefore, speedAfter, delta=1e-3)

    def test_python_version_and_velocity(self):
        """乱数の角度で Python 版の全出力と一致し、velocity は DG の変位の数値微分と一致する。"""
        rng = random.Random(7)
        arguments = (RISE, math.radians(UP), math.radians(HOLD), math.radians(DOWN))
        for _ in range(30):
            degrees = rng.uniform(-720.0, 720.0)
            with self.subTest(degrees=degrees):
                lift = self._turn(degrees)
                result = CamFollower.motion(math.radians(degrees), *arguments)
                self.assertAlmostEqual(lift, result["lift"], places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".lift"), result["lift"], places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".camAngle"), math.degrees(result["camAngle"]), places=4)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".riseProgress"), result["riseProgress"], places=6)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".returnProgress"), result["returnProgress"], places=6)
                velocity = cmds.getAttr(self.owner + ".velocity")
                self.assertAlmostEqual(velocity, result["velocity"], places=5)
                step = 1e-2
                slope = (self._turn(degrees + step) - self._turn(degrees - step)) / math.radians(2.0 * step)
                self.assertAlmostEqual(velocity, slope, places=3)
        # サイクロイドの速度の最大は上昇の中央で 2h/β1
        self._turn(60.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".velocity"), 2.0 * RISE / math.radians(UP), places=5)

    def test_harmonic_rise_and_phase(self):
        """harmonic 曲線、rise の変更、phase の加算が試験側の式と一致する。"""
        cmds.setAttr(self.owner + ".rise", 3.0)
        self.assertAlmostEqual(self._turn(90.0), _expected(90.0, rise=3.0), places=5)
        cmds.setAttr(self.owner + ".phase", 100.0)
        self.assertAlmostEqual(self._turn(90.0), _expected(190.0, rise=3.0), places=5)
        follower = cmds.createNode("transform", name="harmonicFollower")
        CamFollower.create(self.cam, follower, 1.5, UP, HOLD, DOWN, law="harmonic", name="harmonicCam")
        for degrees in (0.0, 45.0, 60.0, 150.0, 260.0, 320.0):
            with self.subTest(degrees=degrees):
                cmds.setAttr(self.cam + ".rotateZ", 25.0 + 90.0 + degrees)  # 作成時のカムは 25 + 90 度
                self.assertAlmostEqual(cmds.getAttr(follower + ".translateY"), _expected(degrees, "harmonic", 1.5),
                                       places=5)

    def test_axes_units_and_no_low_dwell(self):
        """axis=x・followerAxis=z・UI単位 mm/rad・下の休止なし(合計360度)でも式と一致し、外部に変換ノードを残さない。"""
        cmds.currentUnit(linear="mm", angle="rad")
        conversions = set(cmds.ls(type="unitConversion"))
        cam = cmds.createNode("transform", name="xCam")
        follower = cmds.createNode("transform", name="zFollower")
        setup = CamFollower.create(cam, follower, 1.0, 180.0, 0.0, 180.0, name="xCamFollower", axis="x",
                                   followerAxis="z")
        owner = str(setup.container)
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        for degrees in (45.0, 90.0, 180.0, 270.0):
            with self.subTest(degrees=degrees):
                cmds.setAttr(cam + ".rotateX", math.radians(degrees))
                u = (degrees % 180.0) / 180.0
                shape = u - math.sin(2.0 * math.pi * u) / (2.0 * math.pi)
                expected = shape if degrees < 180.0 else 1.0 - shape
                self.assertAlmostEqual(cmds.getAttr(follower + ".translateZ"), expected * 10.0, places=4)  # mm
        cmds.currentUnit(linear="cm", angle="deg")

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("camFollower_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.file(new=True, force=True)
        cam = cmds.createNode("transform", name="undoCam")
        follower = cmds.createNode("transform", name="undoFollower")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        CamFollower.create(cam, follower, name="undoCamFollower")
        self.assertTrue(cmds.listConnections(follower + ".translateY", source=True, destination=False))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoCamFollower"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoCamFollower.translate"))

    def test_arguments(self):
        """軸・運動曲線・角度・上昇量・transform以外・同じノード・接続済みの移動・名前の重複を拒否し、何も残さない。"""
        other = cmds.createNode("multiplyDivide")
        free = cmds.createNode("transform", name="free")
        before = set(cmds.ls())
        cases = (
            ((self.cam, free), {"axis": "w"}),
            ((self.cam, free), {"followerAxis": "q"}),
            ((self.cam, free), {"law": "linear"}),
            ((self.cam, free, -1.0), {}),
            ((self.cam, free, True), {}),
            ((self.cam, free, 1.0, 0.0), {}),
            ((self.cam, free, 1.0, 120.0, -1.0), {}),
            ((self.cam, free, 1.0, 120.0, 60.0, 0.0), {}),
            ((self.cam, free, 1.0, 200.0, 60.0, 120.0), {}),
            ((self.cam, free, "2"), {}),
            ((other, free), {}),
            ((self.cam, self.cam), {}),
            ((self.cam, self.follower), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                CamFollower.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            CamFollower.create(self.cam, free, name="camFollower")
        self.assertEqual(set(cmds.ls()), before)
        CamFollower.create(self.cam, self.follower, name="unconnected", connect=False)
        self.assertTrue(cmds.objExists("unconnected.translate"))


if __name__ == "__main__":
    unittest.main()
