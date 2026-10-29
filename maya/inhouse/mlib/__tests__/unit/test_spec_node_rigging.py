"""AimConstraint のオフセットの約束を固定する(担当C)。

AimConstraint の角度は UI の角度単位によらず既定で度(unit="rad"でラジアン)。設定は入力を検証してから一括で書き、
ロック・入力接続は ValueError。
"""

import math
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.maths import EulerRotate
from mlib.nodes import AimConstraint, Node
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

    def test_offset_in_degrees_and_undo(self):
        """getOffset・setOffset は既定で度の3値(unit="rad"はラジアン)。UI 単位によらず、1回の Undo で戻る。"""
        self.assertIsInstance(self.node, AimConstraint)
        self.assertEqual(self.node.getOffset(), (0.0, 0.0, 0.0))
        cmds.flushUndo()
        self.assertIs(self.node.setOffset((0, 0, 90)), self.node)
        self.assertAlmostEqual(cmds.getAttr(self.constraint + ".offsetZ"), 90.0)
        cmds.undo()
        self.assertEqual(self.node.getOffset(), (0.0, 0.0, 0.0))
        # currentUnit も Undo に積まれるため、単位の確認は Undo の後で行う。
        self.node.setOffset((0, 0, math.pi / 2), unit="rad")
        cmds.currentUnit(angle="rad")
        self.assertAlmostEqual(self.node.getOffset()[2], 90.0)
        self.assertAlmostEqual(self.node.getOffset(unit="rad")[2], math.pi / 2)
        self.node.setRestRotate((10, 20, 30), fast=True)
        self.assertAlmostEqual(self.node.getRestRotate()[1], 20.0)
        with self.assertRaises(ValueError):
            self.node.setOffset((0, 0, 0), unit="grad")

    def test_output_rotate_uses_constraint_rotate_order(self):
        """getOutputRotate は constraintRotate を constraintRotateOrder の EulerRotate で返す。"""
        value = self.node.getOutputRotate()
        self.assertIsInstance(value, EulerRotate)
        self.assertEqual(value.order, cmds.getAttr(self.constraint + ".constraintRotateOrder"))
        expected = [math.radians(angle) for angle in cmds.getAttr(self.constraint + ".constraintRotate")[0]]
        for actual, wanted in zip(value, expected):
            self.assertAlmostEqual(actual, wanted)

    def test_set_offset_errors_change_nothing(self):
        """要素数・非有限・変換できない値は ValueError、ロック・入力接続は RuntimeError で、何も変えない。"""
        for value in ((1, 2), (1, 2, float("nan")), (1, 2, float("inf")), ("a", 1, 2)):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.node.setOffset(value)
        cmds.setAttr(self.constraint + ".offsetX", lock=True)
        with self.assertRaises(RuntimeError):
            self.node.setOffset((0.1, 0.2, 0.3))
        cmds.setAttr(self.constraint + ".offsetX", lock=False)
        source = cmds.createNode("transform", name=self.name("source"), skipSelect=True)
        cmds.connectAttr(source + ".rotateY", self.constraint + ".offsetY")
        with self.assertRaises(RuntimeError):
            self.node.setOffset((0.1, 0.2, 0.3))
        self.assertEqual(self.node.getOffset(), (0.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
