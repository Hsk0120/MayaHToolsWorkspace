"""AimConstraint のオフセット、BlendShape.mirrorTarget の検査、HIKCharacterNode の定義割当の約束を固定する(担当C)。

AimConstraint の角度は UI の角度単位によらず radian。設定は入力を検証してから一括で書き、
ロック・入力接続は ValueError。mirrorTarget は検査の後で Maya 標準の mirrorTarget へ委譲する。
"""

import math
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.maths import EulerRotate
from mlib.nodes import AimConstraint, HIKCharacterNode, Joint, Node
from support.specCase import NamespaceCase


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecNodeRig_"


class AimOffsetTest(_SpecCase):
    """getOffset・setOffset・getOutputRotate。"""

    def setUp(self):
        super().setUp()
        self.target = cmds.createNode("transform", name=self.name("target"), skipSelect=True)
        cmds.setAttr(self.target + ".translate", 0, 5, 0)
        self.driven = cmds.createNode("transform", name=self.name("driven"), skipSelect=True)
        cmds.setAttr(self.driven + ".rotateOrder", 2)
        self.constraint = cmds.aimConstraint(self.target, self.driven)[0]
        self.node = Node(self.constraint)

    def test_offset_in_radians_and_undo(self):
        """getOffset・setOffset は radian の3値。UI 単位によらず、1回の Undo で戻る。"""
        self.assertIsInstance(self.node, AimConstraint)
        self.assertEqual(self.node.getOffset(), (0.0, 0.0, 0.0))
        cmds.flushUndo()
        self.assertIs(self.node.setOffset((0, 0, math.pi / 2)), self.node)
        self.assertAlmostEqual(cmds.getAttr(self.constraint + ".offsetZ"), 90.0)
        cmds.undo()
        self.assertEqual(self.node.getOffset(), (0.0, 0.0, 0.0))
        # currentUnit も Undo に積まれるため、単位の確認は Undo の後で行う。
        self.node.setOffset((0, 0, math.pi / 2))
        cmds.currentUnit(angle="rad")
        self.assertAlmostEqual(self.node.getOffset()[2], math.pi / 2)

    def test_output_rotate_uses_constraint_rotate_order(self):
        """getOutputRotate は constraintRotate を constraintRotateOrder の EulerRotate で返す。"""
        value = self.node.getOutputRotate()
        self.assertIsInstance(value, EulerRotate)
        self.assertEqual(value.order, cmds.getAttr(self.constraint + ".constraintRotateOrder"))
        expected = [math.radians(angle) for angle in cmds.getAttr(self.constraint + ".constraintRotate")[0]]
        for actual, wanted in zip(value, expected):
            self.assertAlmostEqual(actual, wanted)

    def test_set_offset_errors_change_nothing(self):
        """要素数・非有限・変換できない値・ロック・入力接続は ValueError で、何も変えない。"""
        for value in ((1, 2), (1, 2, float("nan")), (1, 2, float("inf")), ("a", 1, 2)):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.node.setOffset(value)
        cmds.setAttr(self.constraint + ".offsetX", lock=True)
        with self.assertRaises(ValueError):
            self.node.setOffset((0.1, 0.2, 0.3))
        cmds.setAttr(self.constraint + ".offsetX", lock=False)
        source = cmds.createNode("transform", name=self.name("source"), skipSelect=True)
        cmds.connectAttr(source + ".rotateY", self.constraint + ".offsetY")
        with self.assertRaises(ValueError):
            self.node.setOffset((0.1, 0.2, 0.3))
        self.assertEqual(self.node.getOffset(), (0.0, 0.0, 0.0))


class MirrorTargetTest(_SpecCase):
    """mirrorTarget の検査と Undo。"""

    def setUp(self):
        super().setUp()
        self.base = cmds.polyPlane(name=self.name("base"), subdivisionsX=2, subdivisionsY=1,
                                   constructionHistory=False)[0]
        self.target = cmds.duplicate(self.base, name=self.name("target"))[0]
        cmds.move(0, 1, 0, self.target + ".vtx[0]", relative=True)
        self.blend = cmds.blendShape(self.target, self.base, name=self.name("blend"))[0]
        self.node = Node(self.blend)

    def test_connected_target_rejected(self):
        """ターゲットのメッシュが接続中なら ValueError で、何も変えない。"""
        with self.assertRaisesRegex(ValueError, "baked targets"):
            self.node.mirrorTarget(0)
        self.assertEqual(set(self.node.getTargetDeltas(0)), {0})

    def test_argument_errors(self):
        """無い番号・軸・方向は ValueError。方向は int の 0/1 だけ(bool も不可)。"""
        cmds.delete(self.target)
        with self.assertRaisesRegex(ValueError, "Unknown target index"):
            self.node.mirrorTarget(5)
        with self.assertRaisesRegex(ValueError, "axis"):
            self.node.mirrorTarget(0, axis="W")
        for direction in (2, -1, True, 1.0):
            with self.subTest(direction=direction):
                with self.assertRaisesRegex(ValueError, "direction must be 0 or 1"):
                    self.node.mirrorTarget(0, direction=direction)
        self.assertEqual(set(self.node.getTargetDeltas(0)), {0})

    def test_mirror_and_undo_once(self):
        """反対側の頂点にデルタを写し、1回の Undo で戻る。"""
        cmds.delete(self.target)
        before = set(self.node.getTargetDeltas(0))
        cmds.flushUndo()
        self.assertIs(self.node.mirrorTarget(0, axis="X", direction=1), self.node)
        self.assertGreater(len(self.node.getTargetDeltas(0)), len(before))
        cmds.undo()
        self.assertEqual(set(self.node.getTargetDeltas(0)), before)


class HumanIKDefinitionTest(_SpecCase):
    """HIKCharacterNode の作成・定義割当の検査。"""

    def setUp(self):
        super().setUp()
        # HumanIK の MEL は名前空間の外にも補助ノードを作るため、作成前のノード一覧を覚えて後で消す。
        self.before = set(cmds.ls(long=True))
        self.character = HIKCharacterNode.createCharacter(self.name("Character"))

    def tearDown(self):
        created = [name for name in set(cmds.ls(long=True)) - self.before if cmds.objExists(name)]
        for name in created:
            if cmds.objExists(name):
                cmds.lockNode(name, lock=False)
        created = [name for name in created
                   if cmds.objExists(name) and name not in (cmds.ls(undeletable=True, long=True) or [])]
        if created:
            cmds.delete(created)
        super().tearDown()

    def test_create_and_lock_state(self):
        """作成直後は未ロック。空の名前は ValueError。"""
        self.assertIsInstance(self.character, HIKCharacterNode)
        self.assertFalse(self.character.isDefinitionLocked())
        for value in ("", None, 3):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "character name"):
                    HIKCharacterNode.createCharacter(value)

    def test_set_joint(self):
        """標準の骨名へ joint を割り当て、None を返す。joint で取り出せる。"""
        hips = cmds.createNode("joint", name=self.name("hips"), skipSelect=True)
        self.assertIsNone(self.character.joint("Hips"))
        self.assertIsNone(self.character.setJoint("Hips", Node(hips)))
        self.assertEqual(self.character.joint("Hips"), Joint(hips))

    def test_set_joint_errors(self):
        """無い骨名は ValueError、joint 以外・骨名が文字列以外は TypeError、ロック後は RuntimeError。"""
        hips = cmds.createNode("joint", name=self.name("hips"), skipSelect=True)
        other = cmds.createNode("transform", name=self.name("notJoint"), skipSelect=True)
        with self.assertRaisesRegex(ValueError, "Unknown HumanIK role"):
            self.character.setJoint("mlibNoRole", hips)
        with self.assertRaisesRegex(TypeError, "Expected a joint"):
            self.character.setJoint("Hips", other)
        with self.assertRaisesRegex(TypeError, "role must be"):
            self.character.setJoint(5, hips)
        with self.assertRaisesRegex(ValueError, "Unknown HumanIK role"):
            self.character.joint("mlibNoRole")
        self.character.getPlug("InputCharacterizationLock").set(True)
        self.assertTrue(self.character.isDefinitionLocked())
        with self.assertRaisesRegex(RuntimeError, "Unlock the character definition"):
            self.character.setJoint("Hips", hips)


if __name__ == "__main__":
    unittest.main()
