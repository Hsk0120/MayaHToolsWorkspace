"""PlanetaryGearの各部材と遊星歯車の回転を、試験側で独立に書いたピッチ円の転がり(接点の弧長と接点の速度)で確かめる。"""

import math
import random
import unittest

from maya import cmds

from mlrig.setups import PlanetaryGear

SUN, PLANET = 24.0, 12.0
RING = SUN + 2.0 * PLANET
MODULE = 0.1  # ピッチ円の半径 = MODULE * 歯数(cm)


def _world(node, local):
    """node のローカルの点 local のワールド位置。"""
    m = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    return [sum(local[r] * m[r * 4 + c] for r in range(3)) + m[12 + c] for c in range(3)]


class PlanetaryGearTest(unittest.TestCase):
    """作成時・転がりの条件・接点の速度・各部材の求め方・Python版・空間・軸と単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """太陽歯車(rotateZ = 15 度)と内歯車(rotateZ = -5 度)を入力に、キャリア(rotateZ = 10 度)と、キャリアの子の
        遊星歯車2つ(rotateZ = 3 度・7 度)を求めるリグを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.sun = cmds.createNode("joint", name="sun")
        cmds.setAttr(self.sun + ".rotateZ", 15.0)
        self.ring = cmds.createNode("transform", name="ring")
        cmds.setAttr(self.ring + ".rotateZ", -5.0)
        self.carrier = cmds.createNode("transform", name="carrier")
        cmds.setAttr(self.carrier + ".rotateZ", 10.0)
        distance = MODULE * (SUN + PLANET)
        self.planets = []
        for index, (angle, spin) in enumerate(((0.0, 3.0), (180.0, 7.0))):
            planet = cmds.createNode("transform", name="planet{}".format(index), parent=self.carrier)
            cmds.setAttr(planet + ".translate", distance * math.cos(math.radians(angle)),
                         distance * math.sin(math.radians(angle)), 0.0)
            cmds.setAttr(planet + ".rotateZ", spin)
            self.planets.append(cmds.ls(planet, long=True)[0])
        self.setup = PlanetaryGear.create(self.sun, self.ring, self.carrier, self.planets, SUN, PLANET, name="pgRig")
        self.owner = str(self.setup.container)

    def _angles(self):
        """生成時からの (太陽, 内歯車, キャリア, 遊星0の固定した空間での自転) の変化(度)。"""
        sun = cmds.getAttr(self.sun + ".rotateZ") - 15.0
        ring = cmds.getAttr(self.ring + ".rotateZ") + 5.0
        carrier = cmds.getAttr(self.carrier + ".rotateZ") - 10.0
        planet = cmds.getAttr(self.planets[0] + ".rotateZ") - 3.0 + carrier
        return sun, ring, carrier, planet

    def test_rest(self):
        """生成時は跳ねず、変化の出力は0、固定値は Zs・Zp・Zr = Zs + 2 Zp。"""
        self.assertAlmostEqual(cmds.getAttr(self.carrier + ".rotateZ"), 10.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.planets[0] + ".rotateZ"), 3.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.planets[1] + ".rotateZ"), 7.0, places=6)
        for attribute in ("sunAngle", "ringAngle", "carrierAngle", "planetSpin", "planetAngle"):
            with self.subTest(attribute=attribute):
                self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), 0.0, places=6)
        self.assertEqual(cmds.getAttr(self.owner + ".ringTeeth"), RING)
        self.assertEqual(cmds.getAttr(self.owner + ".sunTeeth"), SUN)
        self.assertEqual(cmds.getAttr(self.owner + ".planetTeeth"), PLANET)

    def test_rolling_without_slip(self):
        """どの入力でも、ピッチ円の接点の弧長が太陽-遊星・内歯車-遊星の両方で一致する(キャリアから見た転がり)。"""
        rs, rp, rr = MODULE * SUN, MODULE * PLANET, MODULE * RING
        rng = random.Random(19)
        for _ in range(20):
            sunTurn, ringTurn = rng.uniform(-900.0, 900.0), rng.uniform(-400.0, 400.0)
            with self.subTest(sun=sunTurn, ring=ringTurn):
                cmds.setAttr(self.sun + ".rotateZ", 15.0 + sunTurn)
                cmds.setAttr(self.ring + ".rotateZ", -5.0 + ringTurn)
                sun, ring, carrier, planet = self._angles()
                # 外接(太陽と遊星): 逆向きに同じ弧長。内接(内歯車と遊星): 同じ向きに同じ弧長
                self.assertAlmostEqual(rs * (sun - carrier) + rp * (planet - carrier), 0.0, places=4)
                self.assertAlmostEqual(rr * (ring - carrier) - rp * (planet - carrier), 0.0, places=4)
                # 2つめの遊星歯車も同じ自転
                self.assertAlmostEqual(cmds.getAttr(self.planets[1] + ".rotateZ") - 7.0,
                                       cmds.getAttr(self.planets[0] + ".rotateZ") - 3.0, places=4)

    def test_contact_points_velocity(self):
        """内歯車を固定(None)にすると、遊星歯車の内歯車との接点の物質点は止まり(瞬間回転中心)、太陽歯車との接点は
        太陽歯車の物質点と同じ速さで動く(シーンのワールド位置の有限差分)。"""
        cmds.file(new=True, force=True)
        sun = cmds.createNode("transform", name="vSun")
        carrier = cmds.createNode("transform", name="vCarrier")
        rs, rp = MODULE * SUN, MODULE * PLANET
        planet = cmds.createNode("transform", name="vPlanet", parent=carrier)
        cmds.setAttr(planet + ".translateX", rs + rp)
        PlanetaryGear.create(sun, None, carrier, [planet], SUN, PLANET, name="vRig")
        step = 1e-3
        for degrees in (0.0, 40.0, 200.0, -130.0):
            with self.subTest(degrees=degrees):
                cmds.setAttr(sun + ".rotateZ", degrees)
                # 接点はキャリアの腕の向き(遊星の中心の向き)の上。遊星のローカルの点に直して追う
                center = _world(planet, (0, 0, 0))
                length = math.hypot(center[0], center[1])
                direction = (center[0] / length, center[1] / length)
                outer = (center[0] + rp * direction[0], center[1] + rp * direction[1])
                inner = (center[0] - rp * direction[0], center[1] - rp * direction[1])
                inverse = cmds.xform(planet, query=True, worldSpace=True, matrix=True)

                def local(point):
                    """ワールドの点を遊星のローカルへ(回転は直交なので転置)。"""
                    dx, dy = point[0] - inverse[12], point[1] - inverse[13]
                    return (dx * inverse[0] + dy * inverse[1], dx * inverse[4] + dy * inverse[5], 0.0)

                outerLocal, innerLocal = local(outer), local(inner)
                sunLocal = (rs * math.cos(math.radians(-degrees)) * direction[0]
                            - rs * math.sin(math.radians(-degrees)) * direction[1],
                            rs * math.sin(math.radians(-degrees)) * direction[0]
                            + rs * math.cos(math.radians(-degrees)) * direction[1], 0.0)
                sunBefore = _world(sun, sunLocal)
                cmds.setAttr(sun + ".rotateZ", degrees + step)
                outerAfter, innerAfter = _world(planet, outerLocal), _world(planet, innerLocal)
                sunAfter = _world(sun, sunLocal)
                speed = math.radians(step) * rs
                self.assertLess(math.hypot(outerAfter[0] - outer[0], outerAfter[1] - outer[1]), speed * 1e-2)
                self.assertAlmostEqual(math.hypot(innerAfter[0] - inner[0], innerAfter[1] - inner[1]) / speed,
                                       1.0, places=2)
                self.assertAlmostEqual(math.hypot(sunAfter[0] - sunBefore[0], sunAfter[1] - sunBefore[1]) / speed,
                                       1.0, places=2)

    def test_driven_members(self):
        """driven = ring・sun でもWillisの式 Zs Δs + Zr Δr = (Zs + Zr) Δc を満たし、キャリア固定なら内歯車は -Zs/Zr 倍。"""
        for driven in ("ring", "sun"):
            with self.subTest(driven=driven):
                cmds.file(new=True, force=True)
                nodes = {key: cmds.createNode("transform", name=driven + key) for key in ("sun", "ring", "carrier")}
                PlanetaryGear.create(nodes["sun"], nodes["ring"], nodes["carrier"], (), SUN, PLANET, driven=driven,
                                     name=driven + "Rig")
                for first, second in ((30.0, 0.0), (0.0, 50.0), (-200.0, 75.0)):
                    inputs = [key for key in ("sun", "ring", "carrier") if key != driven]
                    cmds.setAttr(nodes[inputs[0]] + ".rotateZ", first)
                    cmds.setAttr(nodes[inputs[1]] + ".rotateZ", second)
                    values = {key: cmds.getAttr(nodes[key] + ".rotateZ") for key in nodes}
                    self.assertAlmostEqual(SUN * values["sun"] + RING * values["ring"],
                                           (SUN + RING) * values["carrier"], places=3)
        cmds.file(new=True, force=True)
        sun = cmds.createNode("transform", name="fixedSun")
        ring = cmds.createNode("transform", name="fixedRing")
        PlanetaryGear.create(sun, ring, None, (), SUN, PLANET, driven="ring", name="fixedRig")
        cmds.setAttr(sun + ".rotateZ", 96.0)
        self.assertAlmostEqual(cmds.getAttr(ring + ".rotateZ"), -96.0 * SUN / RING, places=4)

    def test_python_version(self):
        """乱数の入力で Python 版と一致する。"""
        rng = random.Random(7)
        for _ in range(20):
            sunTurn, ringTurn = rng.uniform(-720.0, 720.0), rng.uniform(-720.0, 720.0)
            with self.subTest(sun=sunTurn, ring=ringTurn):
                cmds.setAttr(self.sun + ".rotateZ", 15.0 + sunTurn)
                cmds.setAttr(self.ring + ".rotateZ", -5.0 + ringTurn)
                result = PlanetaryGear.motion(sunTurn, ringTurn, 0.0, SUN, PLANET)
                for attribute in ("sun", "ring", "carrier", "planetSpin", "planetAngle"):
                    plug = attribute + "Angle" if attribute in ("sun", "ring", "carrier") else attribute
                    self.assertAlmostEqual(cmds.getAttr(self.owner + "." + plug), result[attribute], places=4)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".drivenRotate"), 10.0 + result["carrier"], places=4)

    def test_follow_carrier_false(self):
        """followCarrier=False ならキャリアの回転を足した固定した空間での自転を書き、ワールドの向きは子の場合と同じ。"""
        free = cmds.createNode("transform", name="freePlanet")
        cmds.setAttr(free + ".rotateZ", 3.0)
        PlanetaryGear.create(self.sun, None, None, [free], SUN, PLANET, driven="carrier", name="freeRig",
                             followCarrier=False)
        cmds.setAttr(self.ring + ".rotateZ", -5.0)  # 内歯車は動かさない(freeRig では固定)
        cmds.setAttr(self.sun + ".rotateZ", 15.0 + 90.0)
        child = cmds.xform(self.planets[0], query=True, worldSpace=True, rotation=True)[2]
        self.assertAlmostEqual((cmds.getAttr(free + ".rotateZ") - (child - 10.0) + 180.0) % 360.0 - 180.0, 0.0,
                               places=4)

    def test_axes_and_units(self):
        """axis=x・UI単位 mm/rad でも一致し、外部に変換ノードを残さない。"""
        cmds.currentUnit(linear="mm", angle="rad")
        conversions = set(cmds.ls(type="unitConversion"))
        sun = cmds.createNode("transform", name="xSun")
        carrier = cmds.createNode("transform", name="xCarrier")
        planet = cmds.createNode("transform", name="xPlanet")
        setup = PlanetaryGear.create(sun, None, carrier, [planet], 18, 9, name="xRig", axis="x")
        members = set(cmds.container(str(setup.container), query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        for theta in (0.0, 0.7, 3.0, -5.0, 12.0):
            with self.subTest(theta=theta):
                cmds.setAttr(sun + ".rotateX", theta)
                self.assertAlmostEqual(cmds.getAttr(carrier + ".rotateX"), theta * 18.0 / (18.0 + 36.0), places=6)
                self.assertAlmostEqual(cmds.getAttr(planet + ".rotateX"),
                                       -(18.0 / 9.0) * (theta - theta * 18.0 / 54.0), places=6)
                self.assertEqual(cmds.getAttr(carrier + ".rotateY"), 0.0)
        cmds.currentUnit(linear="cm", angle="deg")

    def test_helpers(self):
        """ringTeeth と canSpaceEvenly (Zs + Zr が数で割り切れる)。"""
        self.assertEqual(PlanetaryGear.ringTeeth(24, 12), 48.0)
        self.assertTrue(PlanetaryGear.canSpaceEvenly(24, 12, 3))
        self.assertTrue(PlanetaryGear.canSpaceEvenly(24, 12, 4))
        self.assertFalse(PlanetaryGear.canSpaceEvenly(20, 11, 3))
        self.assertTrue(PlanetaryGear.canSpaceEvenly(20, 11, 2))
        for values in ((0, 12, 3), (24, 12, 0), (24.0, 12, 3), (True, 12, 3)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                PlanetaryGear.canSpaceEvenly(*values)

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("pgRig_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.file(new=True, force=True)
        sun = cmds.createNode("transform", name="undoSun")
        carrier = cmds.createNode("transform", name="undoCarrier")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        PlanetaryGear.create(sun, None, carrier, name="undoGear")
        self.assertTrue(cmds.listConnections(carrier + ".rotateZ", source=True, destination=False))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoGear"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoGear.drivenRotate"))

    def test_arguments(self):
        """軸・driven・歯数・入力なし・transform以外・同じノード・接続済み・名前の重複を拒否し、何も残さない。"""
        other = cmds.createNode("multiplyDivide")
        free = cmds.createNode("transform", name="free")
        spare = cmds.createNode("transform", name="spare")
        before = set(cmds.ls())
        cases = (
            ((self.sun, None, free), {"axis": "w"}),
            ((self.sun, None, free), {"driven": "planet"}),
            ((self.sun, None, free), {"sunTeeth": 0}),
            ((self.sun, None, free), {"planetTeeth": -3}),
            ((self.sun, None, free), {"sunTeeth": True}),
            ((self.sun, None, free), {"planetTeeth": "12"}),
            ((None, None, free), {}),
            ((free, spare, None), {"driven": "carrier", "planets": [free]}),
            ((other, None, free), {}),
            ((self.sun, None, self.sun), {}),
            ((self.sun, None, self.carrier), {}),
            ((self.sun, None, free), {"planets": [self.planets[0]]}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                PlanetaryGear.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            PlanetaryGear.create(self.sun, None, free, name="pgRig")
        self.assertEqual(set(cmds.ls()), before)
        PlanetaryGear.create(self.sun, self.ring, self.carrier, self.planets, name="unconnected", connect=False)
        self.assertTrue(cmds.objExists("unconnected.planetRotate1"))


if __name__ == "__main__":
    unittest.main()
