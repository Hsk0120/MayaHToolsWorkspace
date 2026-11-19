"""DifferentialGearの各部材とスパイダーの回転を、試験側で独立に書いた接点の速度の一致(滑らずにかみ合う)で確かめる。"""

import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import DifferentialGear

SIDE, SPIDER = 16.0, 10.0
SIDE_OFFSET = 1.0  # サイドギヤの中心の車軸方向の距離 = スパイダーのピッチ半径(cm)
SPIDER_RADIUS = SIDE_OFFSET * SIDE / SPIDER  # スパイダーの中心の車軸からの距離 = サイドギヤのピッチ半径(cm)


def _matrix(node, attribute="worldMatrix"):
    """node のワールドのマトリクス(または逆マトリクス)。"""
    return om2.MMatrix(cmds.getAttr(node + "." + attribute))


def _world(node, local):
    """node のローカルの点 local のワールド位置。"""
    return om2.MPoint(local) * _matrix(node)


def _local(node, world):
    """ワールドの点を node のローカルへ。"""
    return om2.MPoint(world) * _matrix(node, "worldInverseMatrix")


class DifferentialGearTest(unittest.TestCase):
    """作成時・平均の関係・接点の速度・各部材の求め方・符号・Python版・軸と単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """左(rotateX = 20 度)・右(rotateX = -10 度)を入力にケース(rotateX = 5 度)を求め、ケースの子のスパイダー3つ
        (+Y の外向き、-Y の外向き、+Z の内向き。軸はローカルの Y)を自転させるリグを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.left = cmds.createNode("joint", name="left")
        cmds.setAttr(self.left + ".translateX", -SIDE_OFFSET)
        cmds.setAttr(self.left + ".rotateX", 20.0)
        self.right = cmds.createNode("transform", name="right")
        cmds.setAttr(self.right + ".translateX", SIDE_OFFSET)
        cmds.setAttr(self.right + ".rotateX", -10.0)
        self.case = cmds.createNode("transform", name="case")
        cmds.setAttr(self.case + ".rotateX", 5.0)
        self.spiders = []
        # 軸が +Y で外向き、-Y で外向き(jointOrientZ 180 で Y が下)、+Z で内向き(jointOrientX -90 で Y が -Z)
        layout = (((0, SPIDER_RADIUS, 0), (0, 0, 0)), ((0, -SPIDER_RADIUS, 0), (0, 0, 180)),
                  ((0, 0, SPIDER_RADIUS), (-90, 0, 0)))
        for index, (position, orient) in enumerate(layout):
            spider = cmds.createNode("joint", name="spider{}".format(index), parent=self.case)
            cmds.setAttr(spider + ".translate", *position)
            cmds.setAttr(spider + ".jointOrient", *orient)
            self.spiders.append(cmds.ls(spider, long=True)[0])
        for spider, spin in zip(self.spiders, (3.0, 7.0, -4.0)):
            cmds.setAttr(spider + ".rotateY", spin)
        self.setup = DifferentialGear.create(self.left, self.right, self.case, self.spiders, SIDE, SPIDER,
                                             name="dgRig")
        self.owner = str(self.setup.container)

    def test_rest(self):
        """生成時は跳ねず、変化の出力は0、固定値は歯数と符号(外向き +1・外向き +1・内向き -1)。"""
        self.assertAlmostEqual(cmds.getAttr(self.case + ".rotateX"), 5.0, places=6)
        for spider, spin in zip(self.spiders, (3.0, 7.0, -4.0)):
            self.assertAlmostEqual(cmds.getAttr(spider + ".rotateY"), spin, places=6)
        for attribute in ("leftAngle", "rightAngle", "caseAngle", "sideSpin", "spiderSpin"):
            with self.subTest(attribute=attribute):
                self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attribute), 0.0, places=6)
        self.assertEqual(cmds.getAttr(self.owner + ".sideTeeth"), SIDE)
        self.assertEqual(cmds.getAttr(self.owner + ".spiderTeeth"), SPIDER)
        self.assertEqual([cmds.getAttr(self.owner + ".spiderSign" + str(i)) for i in range(3)], [1.0, 1.0, -1.0])

    def test_average(self):
        """ケースの回転の変化は左右の変化の平均。"""
        rng = random.Random(20)
        for _ in range(20):
            left, right = rng.uniform(-900.0, 900.0), rng.uniform(-900.0, 900.0)
            with self.subTest(left=left, right=right):
                cmds.setAttr(self.left + ".rotateX", 20.0 + left)
                cmds.setAttr(self.right + ".rotateX", -10.0 + right)
                self.assertAlmostEqual(cmds.getAttr(self.case + ".rotateX") - 5.0, (left + right) / 2.0, places=4)

    def test_contact_points_velocity(self):
        """各スパイダーと左右のサイドギヤの接点で、両方の物質点のワールドの変位が一致する(滑らずにかみ合う)。
        式を使わず、シーンのワールド位置の有限差分で確かめる。"""
        step = 1e-3
        rng = random.Random(3)
        for _ in range(6):
            left, right = rng.uniform(-360.0, 360.0), rng.uniform(-360.0, 360.0)
            cmds.setAttr(self.left + ".rotateX", left)
            cmds.setAttr(self.right + ".rotateX", right)
            pairs = []
            for spider in self.spiders:
                center = _world(spider, (0, 0, 0))
                for side in (self.left, self.right):
                    # 接点 = スパイダーの中心を、サイドギヤの中心と同じ車軸方向の位置へ移した点
                    axial = _world(side, (0, 0, 0)).x
                    contact = om2.MPoint(axial, center.y, center.z)
                    pairs.append((spider, side, _local(spider, contact), _local(side, contact), contact))
            for delta in ((step, 0.0), (0.0, step)):
                with self.subTest(left=left, right=right, delta=delta):
                    cmds.setAttr(self.left + ".rotateX", left + delta[0])
                    cmds.setAttr(self.right + ".rotateX", right + delta[1])
                    for spider, side, spiderLocal, sideLocal, contact in pairs:
                        moved = _world(spider, spiderLocal) - contact
                        expected = _world(side, sideLocal) - contact
                        self.assertLess((moved - expected).length(), 1e-3 * expected.length() + 1e-8,
                                        (spider, side, moved, expected))
                    cmds.setAttr(self.left + ".rotateX", left)
                    cmds.setAttr(self.right + ".rotateX", right)

    def test_driven_members(self):
        """driven = left・right でも ΔL + ΔR = 2 ΔC を満たし、片側を固定するともう片側はケースの2倍。"""
        for driven in ("left", "right"):
            with self.subTest(driven=driven):
                cmds.file(new=True, force=True)
                nodes = {key: cmds.createNode("transform", name=driven + key) for key in ("left", "right", "case")}
                DifferentialGear.create(nodes["left"], nodes["right"], nodes["case"], driven=driven,
                                        name=driven + "Rig")
                inputs = [key for key in ("left", "right", "case") if key != driven]
                for first, second in ((30.0, 0.0), (0.0, 50.0), (-200.0, 75.0)):
                    cmds.setAttr(nodes[inputs[0]] + ".rotateX", first)
                    cmds.setAttr(nodes[inputs[1]] + ".rotateX", second)
                    values = {key: cmds.getAttr(nodes[key] + ".rotateX") for key in nodes}
                    self.assertAlmostEqual(values["left"] + values["right"], 2.0 * values["case"], places=4)
        cmds.file(new=True, force=True)
        left = cmds.createNode("transform", name="heldLeft")
        case = cmds.createNode("transform", name="heldCase")
        DifferentialGear.create(left, None, case, driven="left", name="heldRig")
        cmds.setAttr(case + ".rotateX", 96.0)
        self.assertAlmostEqual(cmds.getAttr(left + ".rotateX"), 192.0, places=4)

    def test_python_version(self):
        """乱数の入力で Python 版と一致し、スパイダーは spiderSign × spiderSpin だけ回る。"""
        rng = random.Random(7)
        for _ in range(20):
            left, right = rng.uniform(-720.0, 720.0), rng.uniform(-720.0, 720.0)
            with self.subTest(left=left, right=right):
                cmds.setAttr(self.left + ".rotateX", 20.0 + left)
                cmds.setAttr(self.right + ".rotateX", -10.0 + right)
                result = DifferentialGear.motion(left, right, 0.0, SIDE, SPIDER)
                for key in ("left", "right", "case"):
                    self.assertAlmostEqual(cmds.getAttr(self.owner + "." + key + "Angle"), result[key], places=4)
                for key in ("sideSpin", "spiderSpin"):
                    self.assertAlmostEqual(cmds.getAttr(self.owner + "." + key), result[key], places=4)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".drivenRotate"), 5.0 + result["case"], places=4)
                for spider, spin, sign in zip(self.spiders, (3.0, 7.0, -4.0), (1.0, 1.0, -1.0)):
                    self.assertAlmostEqual(cmds.getAttr(spider + ".rotateY"), spin + sign * result["spiderSpin"],
                                           places=4)

    def test_spider_sign(self):
        """左右を入れ替えた側・右だけで向きを決めても、符号は同じ規則(右なら逆)になる。"""
        self.assertEqual(DifferentialGear.spiderSign(self.case, self.left, self.spiders[0]), 1.0)
        self.assertEqual(DifferentialGear.spiderSign(self.case, self.right, self.spiders[0], sideIsLeft=False), 1.0)
        self.assertEqual(DifferentialGear.spiderSign(self.case, self.right, self.spiders[0]), -1.0)
        self.assertEqual(DifferentialGear.spiderSign(self.case, self.left, self.spiders[2]), -1.0)

    def test_axes_and_units(self):
        """axis=z・spiderAxis=x・UI単位 mm/rad でも一致し、外部に変換ノードを残さない。"""
        cmds.currentUnit(linear="mm", angle="rad")
        conversions = set(cmds.ls(type="unitConversion"))
        left = cmds.createNode("transform", name="zLeft")
        cmds.setAttr(left + ".translateZ", -10.0)
        case = cmds.createNode("transform", name="zCase")
        spider = cmds.createNode("transform", name="zSpider", parent=case)
        cmds.setAttr(spider + ".translateX", 16.0)
        setup = DifferentialGear.create(left, None, case, [spider], 16, 10, driven="left", name="zRig", axis="z",
                                        spiderAxis="x")
        members = set(cmds.container(str(setup.container), query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        for theta in (0.0, 0.7, 3.0, -5.0, 12.0):
            with self.subTest(theta=theta):
                cmds.setAttr(case + ".rotateZ", theta)
                self.assertAlmostEqual(cmds.getAttr(left + ".rotateZ"), 2.0 * theta, places=6)
                # 左は -Z 側、軸 +X は外向き: 符号 +1、spiderSpin = 1.6 (ΔL - ΔC) = 1.6 θ
                self.assertAlmostEqual(cmds.getAttr(spider + ".rotateX"), 1.6 * theta, places=6)
                self.assertEqual(cmds.getAttr(case + ".rotateX"), 0.0)
        cmds.currentUnit(linear="cm", angle="deg")

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("dgRig_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.file(new=True, force=True)
        left = cmds.createNode("transform", name="undoLeft")
        right = cmds.createNode("transform", name="undoRight")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        DifferentialGear.create(left, right, None, name="undoGear", driven="right")
        self.assertTrue(cmds.listConnections(right + ".rotateX", source=True, destination=False))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoGear"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoGear.drivenRotate"))

    def test_arguments(self):
        """軸・driven・歯数・入力なし・transform以外・同じノード・向きを決められないスパイダー・接続済み・名前の重複を
        拒否し、何も残さない。"""
        other = cmds.createNode("multiplyDivide")
        free = cmds.createNode("transform", name="free")
        onAxle = cmds.createNode("transform", name="onAxle", parent=self.case)
        tangent = cmds.createNode("transform", name="tangent", parent=self.case)
        cmds.setAttr(tangent + ".translateY", SPIDER_RADIUS)
        cmds.setAttr(tangent + ".rotateX", 90.0)  # ローカルの Y が車軸のまわりの接線(Z)を向く
        flat = cmds.createNode("transform", name="flat")
        cmds.setAttr(flat + ".translateY", SPIDER_RADIUS)
        before = set(cmds.ls())
        cases = (
            ((self.left, None, free), {"axis": "w"}),
            ((self.left, None, free), {"spiderAxis": "w"}),
            ((self.left, None, free), {"driven": "spider"}),
            ((self.left, None, free), {"sideTeeth": 0}),
            ((self.left, None, free), {"spiderTeeth": -3}),
            ((self.left, None, free), {"sideTeeth": True}),
            ((self.left, None, free), {"spiderTeeth": "10"}),
            ((None, None, free), {}),
            ((other, None, free), {}),
            ((self.left, None, self.left), {}),
            ((self.left, None, self.case), {}),
            ((self.left, None, free), {"spiders": [self.spiders[0]]}),
            ((self.left, None, None), {"driven": "case", "spiders": [flat]}),
            ((None, self.right, self.case), {"driven": "left", "spiders": [onAxle], "connect": False}),
            ((None, self.right, self.case), {"driven": "left", "spiders": [tangent], "connect": False}),
            ((free, None, self.case), {"driven": "right", "spiders": [flat], "connect": False}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                DifferentialGear.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            DifferentialGear.create(self.left, None, free, name="dgRig")
        self.assertEqual(set(cmds.ls()), before)
        DifferentialGear.create(self.left, self.right, self.case, self.spiders, name="unconnected", connect=False)
        self.assertTrue(cmds.objExists("unconnected.spiderRotate2"))


if __name__ == "__main__":
    unittest.main()
