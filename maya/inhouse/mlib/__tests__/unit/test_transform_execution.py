"""Transformの計算・書込みと数学値の所有権を検証する。"""

import unittest
from unittest.mock import patch

import maya.cmds as cmds

import mlib
from mlib.maths import EulerRotate, Matrix, Quaternion, Transformation


class TransformExecutionTest(unittest.TestCase):
    """計算モードの非更新と既存の書込み先・戻り値を保持する。"""

    def setUp(self):
        """独立シーンと既定単位を初期化する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True)

    def test_calculation_modes_do_not_write_or_change_return_types(self):
        """7種の計算setterはsafe併用時も値とUndo履歴を変更しない。"""
        for kind in ("transform", "joint"):
            node = mlib.createNode(kind)
            before = node.getTransformation()
            calls = (
                (lambda **flags: node.setTranslate((3, 4, 5), **flags), list),
                (lambda **flags: node.setRotate((.1, .2, .3), **flags), list),
                (lambda **flags: node.setScale((2, 3, 4), **flags), list),
                (lambda **flags: node.setShearing((.1, .2, .3), **flags), list),
                (lambda **flags: node.setQuaternion(Quaternion(), **flags), list),
                (lambda **flags: node.setMatrix(Matrix(translate=(3, 4, 5)), **flags), dict),
                (lambda **flags: node.setTransformation(Transformation(t=(3, 4, 5)), **flags), Transformation),
            )
            cmds.flushUndo()
            for safe in (False, True):
                for call, expected_type in calls:
                    with self.subTest(kind=kind, safe=safe, result=expected_type):
                        self.assertIsInstance(call(get=True, safe=safe), expected_type)
                        self.assertTrue(node.getTransformation().isEquivalent(before))
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
                    before = {name: tuple(node.getPlug(name).get()) for name in names}
                    planned = node.setQuaternion(q, get=True, **flags)
                    self.assertEqual({name: tuple(node.getPlug(name).get()) for name in names}, before)
                    self.assertIs(node.setQuaternion(q, **flags), node)
                    for name in names:
                        expected = planned if name == target else before[name]
                        for actual, value in zip(node.getPlug(name).get(), expected):
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
        self.assertEqual(tuple(node.getTranslate(at=0)), (0, 0, 0))
        self.assertEqual(node.setTranslate((5, 0, 0), at=0, get=True), [3, 0, 0])
        self.assertEqual(tuple(node.getPlug("translate").get()), (2, 0, 0))
        node.setTranslate((5, 0, 0), at=0)
        self.assertEqual(tuple(node.getPlug("translate").get()), (3, 0, 0))
        self.assertEqual(node.setTranslate((5, 0, 0), at=0, get=True), [2, 0, 0])

    def test_transform_forwards_fast_to_each_channel(self):
        """行列からのチャンネル更新はfastを明示して渡し、Undo APIを呼ばない。"""
        node = mlib.createNode("transform")
        cmds.flushUndo()
        with patch.object(cmds, "setAttr", side_effect=AssertionError("cmds setAttr")), \
                patch.object(cmds, "undoInfo", side_effect=AssertionError("cmds undoInfo")):
            node.setMatrix(Matrix(translate=(7, 8, 9)), fast=True)
        self.assertEqual(tuple(node.getPlug("translate").get()), (7, 8, 9))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_scene_snapshot_requires_explicit_write_back(self):
        """取得したTransformationの保持成分を編集してもシーンは変えない。"""
        node = mlib.createNode("transform")
        node.getPlug("translate").set((1, 2, 3))
        snapshot = node.getTransformation()
        snapshot.translate.x = 9
        self.assertEqual(tuple(node.getPlug("translate").get()), (1, 2, 3))
        node.setTransformation(snapshot)
        self.assertEqual(tuple(node.getPlug("translate").get()), (9, 2, 3))


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

        def prepare(instance, value, unit="rad"):
            """値の準備中に独立した通常更新を一度だけ行う。"""
            if instance is plug and not called:
                called.append(True)
                normal.getPlug("tx").set(5)
            return original(instance, value, unit)

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
        node.setTranslate((1, 2, 3), fast=True)
        node.setTranslate((4, 5, 6), fast=False)
        cmds.undo()
        self.assertEqual(tuple(node.getPlug("translate").get()), (1, 2, 3))
        cmds.redo()
        self.assertEqual(tuple(node.getPlug("translate").get()), (4, 5, 6))


class MathComponentOwnershipTest(unittest.TestCase):
    """保管成分・導出成分と全体置換後の参照寿命を検証する。"""

    def test_transformation_keeps_live_components_until_whole_replacement(self):
        """取得成分は直接編集できるが、matrix代入後の成分へは追従しない。"""
        value = Transformation(t=(1, 2, 3))
        held = value.translate
        self.assertIs(held, value.t)
        held.x = 9
        self.assertEqual(value.translate.x, 9)
        derived = value.matrix
        derived.translate = (99, 99, 99)
        self.assertEqual(tuple(value.translate), (9, 2, 3))
        duplicate = value.copy()
        self.assertIsNot(duplicate.translate, value.translate)
        value.matrix = Matrix(translate=(4, 5, 6))
        self.assertIsNot(held, value.translate)
        held.x = -10
        self.assertEqual(tuple(value.translate), (4, 5, 6))

    def test_inplace_product_preserves_container_and_replaces_components(self):
        """*=は容器を維持し、保持済みの成分参照は旧値のまま残す。"""
        value = Transformation(t=(1, 2, 3))
        owner = value
        held = value.translate
        value *= Matrix(translate=(4, 0, 0))
        self.assertIs(value, owner)
        self.assertIsNot(value.translate, held)
        self.assertEqual(tuple(held), (1, 2, 3))
        self.assertEqual(tuple(value.translate), (5, 2, 3))
        held.x = 20
        self.assertEqual(value.translate.x, 5)

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
