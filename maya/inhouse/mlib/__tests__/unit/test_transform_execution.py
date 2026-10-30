"""Transformの計算・書込みと数学値の所有権を検証する。"""

import math
import unittest
from unittest.mock import patch

import maya.cmds as cmds

import mlib
from mlib.maths import EulerRotate, Matrix, Quaternion


class TransformExecutionTest(unittest.TestCase):
    """計算モードの非更新と既存の書込み先・戻り値を保持する。"""

    def setUp(self):
        """独立シーンと既定単位を初期化する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True)

    def test_calculation_modes_do_not_write_or_change_return_types(self):
        """6種の計算setterはsafe併用時も値とUndo履歴を変更しない。"""
        for kind in ("transform", "joint"):
            node = mlib.createNode(kind)
            before = node.getMatrix()
            calls = (
                (lambda **flags: node.setTranslation((3, 4, 5), **flags), list),
                (lambda **flags: node.setRotate((.1, .2, .3), **flags), list),
                (lambda **flags: node.setScale((2, 3, 4), **flags), list),
                (lambda **flags: node.setShear((.1, .2, .3), **flags), list),
                (lambda **flags: node.setQuaternion(Quaternion(), **flags), list),
                (lambda **flags: node.setMatrix(Matrix(translate=(3, 4, 5)), **flags), dict),
            )
            cmds.flushUndo()
            for safe in (False, True):
                for call, expected_type in calls:
                    with self.subTest(kind=kind, safe=safe, result=expected_type):
                        self.assertIsInstance(call(get=True, safe=safe), expected_type)
                        self.assertTrue(node.getMatrix().isEquivalent(before))
                        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_quaternion_calculation_and_write_use_the_same_target(self):
        """r/joとノード型が選ぶチャンネルだけを計算値で更新する。"""
        q = EulerRotate(.2, -.3, .4).asQuaternion()
        for kind in ("transform", "joint"):
            for flags, target in (({}, "rotate"),
                                  ({"r": False}, "jointOrient" if kind == "joint" else "rotateAxis"),
                                  ({"r": False, "jo": False}, "rotateAxis")):
                with self.subTest(kind=kind, flags=flags):
                    node = mlib.createNode(kind)
                    names = ("rotate", "rotateAxis", "jointOrient") if kind == "joint" else ("rotate", "rotateAxis")
                    before = {name: tuple(node.getPlug(name).get(unit="rad")) for name in names}
                    planned = node.setQuaternion(q, get=True, unit="rad", **flags)
                    in_degrees = node.setQuaternion(q, get=True, **flags)
                    for degrees, radians in zip(in_degrees, planned):
                        self.assertAlmostEqual(degrees, math.degrees(radians), places=9)
                    self.assertEqual({name: tuple(node.getPlug(name).get(unit="rad")) for name in names}, before)
                    self.assertIs(node.setQuaternion(q, **flags), node)
                    for name in names:
                        expected = planned if name == target else before[name]
                        for actual, value in zip(node.getPlug(name).get(unit="rad"), expected):
                            self.assertAlmostEqual(actual, value, places=7)

    def test_matrix_safe_writes_keep_locked_component_in_both_modes(self):
        """safe行列設定はロック成分を残し、通常・fastとも自身を返す。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                node = mlib.createNode("transform")
                node.getPlug("translateY").setLocked(True)
                self.assertIs(node.setMatrix(Matrix(translate=(4, 5, 6)), safe=True, fast=fast), node)
                self.assertEqual(tuple(node.getPlug("translate").get()), (4, 0, 6))
                self.assertTrue(node.getPlug("translateY").isLocked())

    def test_at_zero_retains_its_existing_difference_calculation(self):
        """at=0の現在値に依存する計算を、通常の絶対設定へ変更しない。"""
        node = mlib.createNode("transform")
        node.getPlug("translate").set((2, 0, 0))
        self.assertEqual(tuple(node.getTranslation(at=0)), (0, 0, 0))
        self.assertEqual(node.setTranslation((5, 0, 0), at=0, get=True), [3, 0, 0])
        self.assertEqual(tuple(node.getPlug("translate").get()), (2, 0, 0))
        node.setTranslation((5, 0, 0), at=0)
        self.assertEqual(tuple(node.getPlug("translate").get()), (3, 0, 0))
        self.assertEqual(node.setTranslation((5, 0, 0), at=0, get=True), [2, 0, 0])

    def test_transform_forwards_fast_to_each_channel(self):
        """行列からのチャンネル更新はfastを明示して渡し、Undo APIを呼ばない。"""
        node = mlib.createNode("transform")
        cmds.flushUndo()
        with patch.object(cmds, "setAttr", side_effect=AssertionError("cmds setAttr")), \
                patch.object(cmds, "undoInfo", side_effect=AssertionError("cmds undoInfo")):
            node.setMatrix(Matrix(translate=(7, 8, 9)), fast=True)
        self.assertEqual(tuple(node.getPlug("translate").get()), (7, 8, 9))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

class ExplicitFastTest(unittest.TestCase):
    """fastは各呼出しの引数だけで選び、外側の状態を参照しない。"""

    def setUp(self):
        """独立したシーンと有効なUndoキューを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def test_callback_without_fast_keeps_normal_undo(self):
        """fast更新の途中から呼ぶ別の通常更新を、fastへ暗黙に切り替えない。"""
        direct = mlib.createNode("transform")
        normal = mlib.createNode("transform")
        plug = direct.getPlug("translate")
        cls = type(plug)
        original = cls._set_components
        called = []

        def prepare(instance, value):
            """値の準備中に独立した通常更新を一度だけ行う。"""
            if instance is plug and not called:
                called.append(True)
                normal.getPlug("tx").set(5)
            return original(instance, value)

        cmds.flushUndo()
        with patch.object(cls, "_set_components", prepare):
            plug.set((1, 2, 3), fast=True)
        self.assertEqual(called, [True])
        self.assertFalse(cmds.undoInfo(query=True, undoQueueEmpty=True))
        cmds.undo()
        self.assertEqual(normal.getPlug("tx").get(), 0)
        self.assertEqual(tuple(plug.get()), (1, 2, 3))

    def test_false_call_after_fast_uses_normal_backend(self):
        """fastの直後でもfast=Falseはcmdsを使い、通常のUndo/Redoを維持する。"""
        node = mlib.createNode("transform")
        cmds.flushUndo()
        node.setTranslation((1, 2, 3), fast=True)
        node.setTranslation((4, 5, 6), fast=False)
        cmds.undo()
        self.assertEqual(tuple(node.getPlug("translate").get()), (1, 2, 3))
        cmds.redo()
        self.assertEqual(tuple(node.getPlug("translate").get()), (4, 5, 6))


class MathComponentOwnershipTest(unittest.TestCase):
    """数学値の導出成分の参照寿命を検証する。"""

    def test_matrix_component_copies_need_explicit_assignment(self):
        """Matrix成分の編集は、プロパティへ代入するまで元の値を変えない。"""
        matrix = Matrix(translate=(1, 2, 3))
        held = matrix.translate
        held.x = 9
        self.assertEqual(tuple(matrix.translate), (1, 2, 3))
        matrix.translate = held
        self.assertEqual(tuple(matrix.translate), (9, 2, 3))
        rotation = matrix.rotate
        rotation.z = .3
        self.assertAlmostEqual(matrix.rotate.z, 0)
        matrix.rotate = rotation
        self.assertTrue(matrix.rotate.isEquivalent(rotation))


if __name__ == "__main__":
    unittest.main()
