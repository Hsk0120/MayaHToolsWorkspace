"""10.3.0 で足した数学型の丸めの契約を固定する。

- Vector 系の round/roundIt/組み込み round: 同型で返す、桁数・負の桁数・None、-0.0 の正規化、偶数丸め。
- EulerRotate の round/roundIt: 既定は度で丸める、unit="rad"、回転順序の維持、組み込み round。
- 不正な桁数・単位の例外型と、例外時に roundIt が値を変えないこと。
"""

import math
import unittest

import mlib
mlib.reload()
from mlib.maths import EulerRotate, Scale, Shear, Translate, Vector
from support.specCase import NamespaceCase

VECTOR_TYPES = (Vector, Translate, Scale, Shear)


class VectorRoundTest(NamespaceCase):
    """Vector 系の round・roundIt・組み込み round。"""

    def test_round_keeps_type(self):
        """呼び出した型の新しい値を返し、自身は変えない。"""
        for cls in VECTOR_TYPES:
            with self.subTest(cls=cls.__name__):
                value = cls(1.23456, -2.34567, 3.45678)
                result = value.round(2)
                self.assertIs(type(result), cls)
                self.assertIsNot(result, value)
                self.assertEqual(list(result), [1.23, -2.35, 3.46])
                self.assertEqual(list(value), [1.23456, -2.34567, 3.45678])

    def test_digits(self):
        """None は整数値(float)、負の桁数は整数部を丸める。"""
        value = Vector(12.6, -7.4, 155.0)
        self.assertEqual(list(value.round()), [13.0, -7.0, 155.0])
        self.assertTrue(all(type(item) is float for item in value.round()))
        self.assertEqual(list(value.round(-1)), [10.0, -10.0, 160.0])
        self.assertEqual(list(value.round(0)), [13.0, -7.0, 155.0])

    def test_negative_zero(self):
        """丸めた結果の -0.0 は 0.0 にそろえる。"""
        result = Vector(-0.0001, -0.0, 0.4).round(2)
        for item in result:
            self.assertEqual(math.copysign(1.0, item), 1.0)

    def test_half_to_even(self):
        """組み込みの round と同じく、ちょうど半分は偶数側へ丸める。"""
        self.assertEqual(list(Vector(0.5, 1.5, 2.5).round()), [0.0, 2.0, 2.0])

    def test_round_it(self):
        """roundIt は自身を更新して自身を返す。"""
        for cls in VECTOR_TYPES:
            with self.subTest(cls=cls.__name__):
                value = cls(1.23456, -2.34567, 3.45678)
                self.assertIs(value.roundIt(1), value)
                self.assertEqual(list(value), [1.2, -2.3, 3.5])

    def test_builtin(self):
        """組み込みの round は round メソッドと同じ結果を返す。"""
        value = Translate(1.23456, 2.0, -3.98765)
        result = round(value, 3)
        self.assertIs(type(result), Translate)
        self.assertEqual(list(result), list(value.round(3)))
        self.assertEqual(list(round(value)), [1.0, 2.0, -4.0])

    def test_invalid(self):
        """int・None 以外の桁数は TypeError で、roundIt は値を変えない。"""
        value = Vector(1.25, 2.5, 3.75)
        for ndigits in (True, 1.0, "2", (1,)):
            with self.subTest(ndigits=ndigits):
                self.assertRaises(TypeError, value.round, ndigits)
                self.assertRaises(TypeError, value.roundIt, ndigits)
                self.assertEqual(list(value), [1.25, 2.5, 3.75])


class EulerRoundTest(NamespaceCase):
    """EulerRotate の round・roundIt・組み込み round。"""

    def test_degrees_by_default(self):
        """既定は度で丸め、ラジアンで保持する。回転順序と型を維持する。"""
        value = EulerRotate.fromDegrees(89.99999, -45.00004, 12.3456, order="zxy")
        result = value.round(2)
        self.assertIs(type(result), EulerRotate)
        self.assertEqual(result.orderName, "zxy")
        self.assertSequenceAlmostEqual(result.asDegrees(), (90.0, -45.0, 12.35), places=10)
        self.assertSequenceAlmostEqual(result, [math.radians(90.0), math.radians(-45.0), math.radians(12.35)])
        self.assertSequenceAlmostEqual(value.asDegrees(), (89.99999, -45.00004, 12.3456), places=10)

    def test_radians(self):
        """unit="rad" はラジアンのまま丸める。別名も受け付ける。"""
        value = EulerRotate(1.23456, -0.00001, 3.0)
        for unit in ("rad", "radian", "radians"):
            with self.subTest(unit=unit):
                result = value.round(3, unit=unit)
                self.assertEqual(list(result), [1.235, 0.0, 3.0])
                self.assertEqual(math.copysign(1.0, result[1]), 1.0)

    def test_negative_zero(self):
        """度で丸めた結果の -0.0 も 0.0 にそろえる。"""
        result = EulerRotate.fromDegrees(-0.001, 10.0, -0.0).round(1)
        self.assertEqual(math.copysign(1.0, result.x), 1.0)
        self.assertEqual(math.copysign(1.0, result.z), 1.0)

    def test_round_it(self):
        """roundIt は自身を更新して自身を返し、回転順序を保つ。"""
        value = EulerRotate.fromDegrees(10.04, 20.06, -30.01, order="yxz")
        self.assertIs(value.roundIt(1), value)
        self.assertEqual(value.orderName, "yxz")
        self.assertSequenceAlmostEqual(value.asDegrees(), (10.0, 20.1, -30.0), places=10)

    def test_builtin(self):
        """組み込みの round は度で丸める。"""
        value = EulerRotate.fromDegrees(44.6, 0.2, -179.7)
        result = round(value)
        self.assertIs(type(result), EulerRotate)
        self.assertSequenceAlmostEqual(result.asDegrees(), (45.0, 0.0, -180.0), places=10)

    def test_invalid(self):
        """桁数の型は TypeError、単位は文字列以外 TypeError・未対応 ValueError。roundIt は値を変えない。"""
        value = EulerRotate(0.1, 0.2, 0.3)
        for ndigits in (True, 1.0, "2"):
            with self.subTest(ndigits=ndigits):
                self.assertRaises(TypeError, value.round, ndigits)
                self.assertRaises(TypeError, value.roundIt, ndigits)
        self.assertRaises(TypeError, value.round, 2, unit=1)
        self.assertRaises(ValueError, value.round, 2, unit="frame")
        self.assertRaises(ValueError, value.roundIt, 2, unit="grad")
        self.assertEqual(list(value), [0.1, 0.2, 0.3])


if __name__ == "__main__":
    unittest.main()
