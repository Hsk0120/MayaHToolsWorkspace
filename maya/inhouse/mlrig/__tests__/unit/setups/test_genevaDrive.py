"""GenevaDriveの間欠回転を、駆動輪の子のピンの位置(溝の向きに一致するか)で独立に確かめる。"""

import math
import random
import unittest

from maya import cmds
import maya.api.OpenMaya as om

from mlrig.setups import GenevaDrive

SLOTS = 4
CENTER = 6.0
PIN = CENTER * math.sin(math.pi / SLOTS)


def _wrap(angle, period):
    """angle を -period/2〜period/2 へ折り返す。"""
    return (angle + period / 2.0) % period - period / 2.0


class GenevaDriveTest(unittest.TestCase):
    """休止・送り・溝とピンの一致・1回転の送り・連続性・Python版・速度比・単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """原点に従動輪、+X に軸間距離 6cm で駆動輪を置き、駆動輪の +X 側(従動輪と反対)にピンを付ける。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.wheel = cmds.createNode("joint", name="wheel")
        cmds.setAttr(self.wheel + ".rotateZ", 10.0)
        self.driver = cmds.createNode("joint", name="driver")
        cmds.setAttr(self.driver + ".translateX", CENTER)
        self.pin = cmds.createNode("transform", name="pin", parent=self.driver)
        cmds.setAttr(self.pin + ".translateX", PIN)
        self.setup = GenevaDrive.create(self.driver, self.wheel, SLOTS, name="geneva")
        self.owner = str(self.setup.container)

    def _turn(self, degrees):
        """駆動輪を回し、従動輪の rotateZ(度)を返す。"""
        cmds.setAttr(self.driver + ".rotateZ", degrees)
        return cmds.getAttr(self.wheel + ".rotateZ")

    def _pinInWheel(self):
        """従動輪のローカルでのピンの位置。"""
        point = om.MPoint(cmds.xform(self.pin, query=True, worldSpace=True, translation=True))
        return point * om.MMatrix(cmds.getAttr(self.wheel + ".worldInverseMatrix[0]"))

    def test_rest(self):
        """生成時は従動輪が跳ねず、休止中で step・indexAngle・speedRatio が0。"""
        self.assertAlmostEqual(cmds.getAttr(self.wheel + ".rotateZ"), 10.0, places=6)
        self.assertEqual(cmds.getAttr(self.owner + ".engaged"), 0.0)
        self.assertEqual(cmds.getAttr(self.owner + ".step"), 0.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".indexAngle"), 0.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".speedRatio"), 0.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".crankAngle"), -180.0, places=6)

    def test_pin_stays_in_slot(self):
        """溝に入っている間は、従動輪のローカルで見たピンが常に溝の線(π/n - 生成時の回転 + 2πj/n)の上にあり、軸間距離より内側。"""
        slotPitch = 2.0 * math.pi / SLOTS
        engagedCount = 0
        for degrees in range(-400, 760, 7):
            with self.subTest(degrees=degrees):
                self._turn(float(degrees))
                if cmds.getAttr(self.owner + ".engaged") < 0.5:
                    continue
                engagedCount += 1
                local = self._pinInWheel()
                angle = math.atan2(local.y, local.x) - (math.pi / SLOTS - math.radians(10.0))  # 生成時の従動輪は10度
                self.assertAlmostEqual(_wrap(angle, slotPitch), 0.0, places=5)
                self.assertLess(math.hypot(local.x, local.y), CENTER + 1e-6)
        self.assertGreater(engagedCount, 20)

    def test_dwell_locks_and_turn_advances(self):
        """休止中は従動輪が動かず、駆動輪の1回転ごとに 360/n 度だけ逆向きに送られる(逆に回すと戻る)。"""
        dwell = 90.0 - 180.0 / SLOTS  # α0(度)。駆動輪の 180 ± α0 の外側が休止
        for turn in (-2, -1, 0, 1, 2):
            for local in (0.0, 40.0, 180.0 - dwell - 1.0, 180.0 + dwell + 1.0, 300.0, 359.0):
                with self.subTest(turn=turn, local=local):
                    moved = turn + (1 if local > 180.0 else 0)
                    self.assertAlmostEqual(self._turn(turn * 360.0 + local), 10.0 - moved * 360.0 / SLOTS, places=5)
                    self.assertEqual(cmds.getAttr(self.owner + ".engaged"), 0.0)
                    self.assertAlmostEqual(cmds.getAttr(self.owner + ".speedRatio"), 0.0, places=6)

    def test_continuous_at_engagement_edges(self):
        """ピンが溝へ出入りする角度(180 ± α0)と、段の切り替わり(360度の倍数)の前後で値が連続する。"""
        dwell = 90.0 - 180.0 / SLOTS
        for edge in (180.0 - dwell, 180.0 + dwell, 360.0, -180.0 + dwell, 0.0):
            before, after = self._turn(edge - 1e-4), self._turn(edge + 1e-4)
            with self.subTest(edge=edge):
                self.assertAlmostEqual(before, after, delta=1e-3)

    def test_python_version_and_speed_ratio(self):
        """乱数の角度で Python 版の全出力と一致し、speedRatio は数値微分と一致する(溝の中央で λ/(1-λ))。"""
        rng = random.Random(4)
        for _ in range(30):
            degrees = rng.uniform(-720.0, 720.0)
            with self.subTest(degrees=degrees):
                wheel = self._turn(degrees)
                result = GenevaDrive.motion(math.radians(degrees), SLOTS)
                self.assertAlmostEqual(wheel, 10.0 - math.degrees(result["indexAngle"]), places=5)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".indexAngle"),
                                       math.degrees(result["indexAngle"]), places=5)
                self.assertEqual(cmds.getAttr(self.owner + ".engaged"), result["engaged"])
                self.assertEqual(cmds.getAttr(self.owner + ".step"), result["step"])
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".speedRatio"), result["speedRatio"], places=5)
                step = 1e-3
                slope = (GenevaDrive.motion(math.radians(degrees + step), SLOTS)["indexAngle"]
                         - GenevaDrive.motion(math.radians(degrees - step), SLOTS)["indexAngle"]) / math.radians(2 * step)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".speedRatio"), slope, places=3)
        self._turn(180.0)
        ratio = math.sin(math.pi / SLOTS)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".speedRatio"), ratio / (1.0 - ratio), places=5)

    def test_phase_slots_axis_and_units(self):
        """phase で向きを合わせ、溝6本・axis=x・UI単位 mm/rad でも Python 版と一致し、外部に変換ノードを残さない。"""
        cmds.setAttr(self.owner + ".phase", 15.0)
        self.assertAlmostEqual(self._turn(0.0), 25.0, places=5)
        cmds.currentUnit(linear="mm", angle="rad")
        conversions = set(cmds.ls(type="unitConversion"))
        driver = cmds.createNode("transform", name="xDriver")
        wheel = cmds.createNode("transform", name="xWheel")
        cmds.setAttr(driver + ".rotateX", 0.3)
        setup = GenevaDrive.create(driver, wheel, 6, name="xGeneva", axis="x")
        owner = str(setup.container)
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        cmds.setAttr(driver + ".rotateX", 0.3 + 2.5)
        expected = -GenevaDrive.motion(2.5, 6)["indexAngle"]
        self.assertAlmostEqual(cmds.getAttr(wheel + ".rotateX"), expected, places=5)
        cmds.currentUnit(linear="cm", angle="deg")
        self.assertAlmostEqual(cmds.getAttr(wheel + ".rotateX"), math.degrees(expected), places=4)

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("geneva_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.file(new=True, force=True)
        driver = cmds.createNode("transform", name="undoDriver")
        wheel = cmds.createNode("transform", name="undoWheel")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        GenevaDrive.create(driver, wheel, name="undoGeneva")
        self.assertTrue(cmds.listConnections(wheel + ".rotateZ", source=True, destination=False))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoGeneva"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoGeneva.rotate"))

    def test_arguments(self):
        """溝の数・軸・transform以外・同じノード・接続済みの回転・名前の重複を拒否し、何も残さない。"""
        other = cmds.createNode("multiplyDivide")
        free = cmds.createNode("transform", name="free")
        before = set(cmds.ls())
        cases = (
            ((self.driver, free, 2), {}),
            ((self.driver, free, 4.0), {}),
            ((self.driver, free, True), {}),
            ((self.driver, free, 4), {"axis": "w"}),
            ((other, free, 4), {}),
            ((self.driver, self.driver, 4), {}),
            ((self.driver, self.wheel, 4), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                GenevaDrive.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            GenevaDrive.create(self.driver, free, name="geneva")
        self.assertEqual(set(cmds.ls()), before)
        GenevaDrive.create(self.driver, self.wheel, name="unconnected", connect=False)
        self.assertTrue(cmds.objExists("unconnected.rotate"))


if __name__ == "__main__":
    unittest.main()
