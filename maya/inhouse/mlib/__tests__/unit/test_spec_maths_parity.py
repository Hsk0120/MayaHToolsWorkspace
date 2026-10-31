"""数学型(Matrix・EulerRotate・Quaternion・Vector)を、乱数で作った多数の値で om2 と突き合わせる。

固定の期待値だけでは見落としやすい、回転順序・負スケール・シアー・境界付近の角度の組み合わせを、
シード固定の乱数で毎回同じに作り、mlib の結果が同じ om2 の計算と一致することを確かめる。
"""

import math
import random
import sys
import unittest

import maya.api.OpenMaya as om2

import mlib
mlib.reload()
from mlib.maths import EulerRotate, Matrix, Quaternion, Vector

#: 1テストあたりの試行回数。
TRIALS = 200

#: 浮動小数の比較の許容誤差。
TOLERANCE = 1e-8

#: om2 の回転順序の番号と名前。
ORDERS = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")


def _rng(seed):
    """シード固定の乱数生成器を返す。"""
    return random.Random(seed)


def _vector(rng, scale=10.0):
    """各成分が -scale〜scale の3成分を返す。"""
    return tuple(rng.uniform(-scale, scale) for _ in range(3))


def _angles(rng):
    """境界(±π、±π/2)付近も混ぜた回転角(ラジアン)の3成分を返す。"""
    picks = []
    for _ in range(3):
        if rng.random() < 0.2:
            picks.append(rng.choice((math.pi, -math.pi, math.pi / 2, -math.pi / 2, 0.0)) + rng.uniform(-1e-6, 1e-6))
        else:
            picks.append(rng.uniform(-2 * math.pi, 2 * math.pi))
    return tuple(picks)


def _plain_angles(rng):
    """ジンバル付近(中間軸が±π/2)を避けた回転角の3成分を返す。

    中間軸が±π/2 の付近では om2 自身の分解・解の選択でも回転が保たれないため、
    往復を確かめるテストではこちらを使う。
    """
    while True:
        angles = tuple(rng.uniform(-math.pi, math.pi) for _ in range(3))
        if abs(abs(angles[1]) - math.pi / 2) > 0.05:
            return angles


def _scale(rng):
    """0から離れた正負のスケールを返す(負スケールも混ぜる)。"""
    return tuple(rng.choice((-1, 1)) * rng.uniform(0.2, 3.0) for _ in range(3))


def _om_matrix(translate, rotate, scale, shear, order=0):
    """om2.MTransformationMatrix で同じTRSのマトリクスを作る。"""
    tm = om2.MTransformationMatrix()
    tm.setTranslation(om2.MVector(*translate), om2.MSpace.kTransform)
    tm.setRotation(om2.MEulerRotation(*rotate, order))
    tm.setScale(scale, om2.MSpace.kTransform)
    tm.setShear(shear, om2.MSpace.kTransform)
    return tm.asMatrix()


class _ParityCase(unittest.TestCase):
    """値の近さを比べる補助。"""

    def assert_close(self, actual, expected, tolerance=TOLERANCE, msg=None):
        """数値の列が成分ごとに近いことを確かめる。"""
        actual, expected = list(actual), list(expected)
        self.assertEqual(len(actual), len(expected), msg)
        for index, (a, b) in enumerate(zip(actual, expected)):
            self.assertLessEqual(abs(a - b), tolerance * max(1.0, abs(b)), "{}: [{}] {} != {}".format(msg, index, a, b))

    def assert_same_rotation(self, first, second, msg=None):
        """2つのクォータニオンが同じ回転(符号違いを含む)であることを確かめる。"""
        dot = abs(first.x * second.x + first.y * second.y + first.z * second.z + first.w * second.w)
        self.assertAlmostEqual(dot, 1.0, places=7, msg=msg)


class MatrixParityTest(_ParityCase):
    """Matrixの合成・分解・変換を om2 と突き合わせる。"""

    def test_compose_matches_transformation_matrix(self):
        """compose(translate, rotate, scale, shear)は同じ値の MTransformationMatrix と一致する。"""
        rng = _rng(1)
        for trial in range(TRIALS):
            t, r, s, sh = _vector(rng), _angles(rng), _scale(rng), _vector(rng, 0.5)
            with self.subTest(trial=trial):
                self.assert_close(Matrix.compose(t, r, s, sh), _om_matrix(t, r, s, sh), msg="compose")

    def test_properties_match_om2_decomposition(self):
        """translate・scale・shear・quaternion・euler・decompose は om2 の分解と一致する。"""
        rng = _rng(2)
        for trial in range(TRIALS):
            matrix = Matrix(_om_matrix(_vector(rng), _plain_angles(rng), _scale(rng), _vector(rng, 0.5)))
            tm = om2.MTransformationMatrix(om2.MMatrix(matrix))
            with self.subTest(trial=trial):
                self.assert_close(matrix.translate, list(matrix)[12:15], msg="translate")
                self.assert_close(matrix.scale, tm.scale(om2.MSpace.kTransform), msg="scale")
                self.assert_close(matrix.shear, tm.shear(om2.MSpace.kTransform), msg="shear")
                self.assert_close(matrix.euler, tm.rotation(), msg="euler")
                self.assert_same_rotation(matrix.quaternion, tm.rotation(asQuaternion=True), msg="quaternion")
                parts = matrix.decompose()
                self.assert_close(parts["translate"], matrix.translate, msg="decompose translate")
                self.assert_close(parts["scale"], matrix.scale, msg="decompose scale")
                recomposed = Matrix.compose(parts["translate"], parts["euler"], parts["scale"], parts["shear"])
                self.assertTrue(recomposed.isEquivalent(matrix, 1e-7), "decompose -> compose")

    def test_setters_keep_other_components(self):
        """translate・rotate・scale・shear の代入は、ほかの成分を保って再合成する。"""
        rng = _rng(3)
        for trial in range(TRIALS):
            t, r, s, sh = _vector(rng), _plain_angles(rng), tuple(abs(v) for v in _scale(rng)), _vector(rng, 0.5)
            new_t, new_r, new_s, new_sh = (_vector(rng), _plain_angles(rng), tuple(abs(v) for v in _scale(rng)),
                                           _vector(rng, 0.5))
            with self.subTest(trial=trial):
                for name, value, expected in (("translate", new_t, (new_t, r, s, sh)),
                                              ("rotate", new_r, (t, new_r, s, sh)),
                                              ("scale", new_s, (t, r, new_s, sh)),
                                              ("shear", new_sh, (t, r, s, new_sh))):
                    matrix = Matrix.compose(t, r, s, sh)
                    setattr(matrix, name, value)
                    self.assertTrue(matrix.isEquivalent(Matrix.compose(*expected), 1e-7), name)

    def test_point_vector_inverse_and_transpose(self):
        """transformPoint・transformVector・inverse・transpose・adjoint・homogenize を om2 と比べる。"""
        rng = _rng(4)
        for trial in range(TRIALS):
            om_matrix = _om_matrix(_vector(rng), _angles(rng), _scale(rng), _vector(rng, 0.5))
            matrix = Matrix(om_matrix)
            point = _vector(rng)
            with self.subTest(trial=trial):
                expected = om2.MPoint(*point) * om_matrix
                self.assert_close(matrix.transformPoint(point), (expected.x, expected.y, expected.z), 1e-7, "point")
                direction = om2.MVector(*point) * om_matrix
                self.assert_close(matrix.transformVector(point), direction, 1e-7, "vector")
                self.assertIsInstance(matrix.inverse(), Matrix)
                self.assertTrue((matrix * matrix.inverse()).isEquivalent(Matrix(), 1e-7), "inverse")
                self.assert_close(matrix.transpose(), om_matrix.transpose(), msg="transpose")
                self.assert_close(matrix.transpose().transpose(), matrix, msg="transpose twice")
                self.assert_close(matrix.adjoint(), om_matrix.adjoint(), 1e-6, "adjoint")
                self.assert_close(matrix.homogenize(), om_matrix.homogenize(), msg="homogenize")

    def test_multiplication_and_mirror(self):
        """積の順序は om2 と同じで、同じ軸のミラーを2回かけると元に戻る。"""
        rng = _rng(5)
        for trial in range(TRIALS):
            a = _om_matrix(_vector(rng), _angles(rng), _scale(rng), (0, 0, 0))
            b = _om_matrix(_vector(rng), _angles(rng), _scale(rng), (0, 0, 0))
            with self.subTest(trial=trial):
                self.assert_close(Matrix(a) * Matrix(b), a * b, 1e-7, "a*b")
                self.assertIsInstance(Matrix(a) * Matrix(b), Matrix)
                for axis in ("x", "y", "z"):
                    pivot = _vector(rng)
                    twice = Matrix(a).mirror(axis, pivot).mirror(axis, pivot)
                    self.assertTrue(twice.isEquivalent(Matrix(a), 1e-7), axis)

    def test_singular_matrix_is_rejected(self):
        """スケール0のマトリクスは逆・分解を ValueError で拒否し、translate は使える。"""
        matrix = Matrix.compose((1, 2, 3), (0.1, 0.2, 0.3), (0, 1, 1))
        with self.assertRaises(ValueError):
            matrix.inverse()
        with self.assertRaises(ValueError):
            matrix.decompose()
        self.assert_close(matrix.translate, (1, 2, 3))
        matrix.translate = (4, 5, 6)
        self.assert_close(list(matrix)[12:15], (4, 5, 6))


class EulerRotateParityTest(_ParityCase):
    """EulerRotateの変換と解の選び方を om2 と突き合わせる。"""

    def test_quaternion_matrix_and_order_names(self):
        """各回転順序で asQuaternion・asMatrix・reorder・orderName が om2 と一致する。"""
        rng = _rng(6)
        for trial in range(TRIALS):
            angles, order = _angles(rng), rng.randrange(6)
            euler = EulerRotate(*angles, order)
            om_euler = om2.MEulerRotation(*angles, order)
            with self.subTest(trial=trial, order=ORDERS[order]):
                self.assertEqual(euler.orderName, ORDERS[order])
                self.assert_same_rotation(euler.asQuaternion(), om_euler.asQuaternion())
                self.assert_close(euler.asMatrix(), om_euler.asMatrix(), msg="matrix")
                target = rng.randrange(6)
                reordered = euler.reorder(target)
                self.assertIsInstance(reordered, EulerRotate)
                self.assertEqual(reordered.order, target)
                self.assert_same_rotation(reordered.asQuaternion(), om_euler.asQuaternion())
                self.assert_close(euler.asDegrees(), [math.degrees(v) for v in angles], msg="degrees")

    def test_solutions_match_om2(self):
        """closestSolution・alternateSolution・closestCut・bound は om2 と同じ値を返し、回転順序を保つ。

        ジンバル付近では om2 の結果自体が元と別の回転になることがあるため、回転の同一性は
        om2 の結果と比べる(mlib が om2 と同じ結果を返すことを確かめる)。
        """
        rng = _rng(7)
        for trial in range(TRIALS):
            angles, order = _angles(rng), rng.randrange(6)
            target_angles = _angles(rng)
            euler, om_euler = EulerRotate(*angles, order), om2.MEulerRotation(*angles, order)
            target = om2.MEulerRotation(*target_angles, order)
            with self.subTest(trial=trial):
                self.assert_close(euler.closestSolution(target), om_euler.closestSolution(target), msg="closestSolution")
                self.assert_close(euler.alternateSolution(), om_euler.alternateSolution(), msg="alternateSolution")
                self.assert_close(euler.closestCut(target), om_euler.closestCut(target), msg="closestCut")
                self.assert_close(euler.bound(), om_euler.bound(), msg="bound")
                for result, expected in ((euler.closestSolution(target), om_euler.closestSolution(target)),
                                         (euler.alternateSolution(), om_euler.alternateSolution()),
                                         (euler.bound(), om_euler.bound())):
                    self.assertIsInstance(result, EulerRotate)
                    self.assertEqual(result.order, expected.order)
                    self.assert_same_rotation(result.asQuaternion(), expected.asQuaternion())

    def test_order_name_setter_keeps_values(self):
        """orderName の代入は値を変えず順序だけを変え、不正な名前は拒否する。"""
        euler = EulerRotate(0.1, 0.2, 0.3)
        for order, name in enumerate(ORDERS):
            euler.orderName = name
            self.assertEqual(euler.order, order)
            self.assert_close(euler, (0.1, 0.2, 0.3))
        with self.assertRaises((ValueError, TypeError)):
            euler.orderName = "abc"


class QuaternionParityTest(_ParityCase):
    """Quaternionの演算を om2 と突き合わせる。"""

    def test_products_conversions_and_slerp(self):
        """積の順序・逆・asEulerRotate・slerp・exp/log・回転したベクトルが om2 と一致する。"""
        rng = _rng(8)
        for trial in range(TRIALS):
            a = om2.MEulerRotation(*_angles(rng)).asQuaternion()
            b = om2.MEulerRotation(*_angles(rng)).asQuaternion()
            qa, qb = Quaternion(a), Quaternion(b)
            t = rng.random()
            with self.subTest(trial=trial):
                self.assert_close(qa * qb, a * b, msg="product")
                self.assertIsInstance(qa * qb, Quaternion)
                self.assert_close(qa.inverse(), a.inverse(), msg="inverse")
                euler = qa.asEulerRotate()
                self.assertIsInstance(euler, EulerRotate)
                self.assert_close(euler, a.asEulerRotation(), msg="euler")
                self.assert_close(qa.slerp(qb, t), om2.MQuaternion.slerp(a, b, t), msg="slerp")
                self.assert_close(qa.log(), a.log(), msg="log")
                self.assert_close(qa.log().exp(), a.log().exp(), msg="exp")
                vector = _vector(rng)
                self.assert_close(qa.rotateVector(vector), om2.MVector(*vector).rotateBy(a), 1e-7, "rotateVector")

    def test_axis_angle_and_squad(self):
        """fromAxisAngle と asAxisAngle が往復し、squad は om2 と一致する。"""
        rng = _rng(9)
        for trial in range(TRIALS):
            axis = om2.MVector(*_vector(rng)).normal()
            angle = rng.uniform(0.01, math.pi - 0.01)
            quaternion = Quaternion.fromAxisAngle(axis, angle)
            with self.subTest(trial=trial):
                result_axis, result_angle = quaternion.asAxisAngle()
                self.assertAlmostEqual(result_angle, angle, places=7)
                self.assert_close(result_axis, axis, 1e-7, "axis")
                p, a, b, q = (om2.MEulerRotation(*_angles(rng)).asQuaternion() for _ in range(4))
                t = rng.random()
                expected = om2.MQuaternion.squad(p, a, b, q, t)
                self.assert_close(Quaternion.squad(p, a, b, q, t), expected, msg="squad")


class VectorParityTest(_ParityCase):
    """Vectorの演算を om2 と突き合わせる。"""

    def test_products_rotations_and_lengths(self):
        """dot・cross・lengthSq・rotateTo・rotateBy・angleTo・lerp が om2 と一致する。"""
        rng = _rng(10)
        for trial in range(TRIALS):
            a, b = _vector(rng), _vector(rng)
            va, vb, oa, ob = Vector(*a), Vector(*b), om2.MVector(*a), om2.MVector(*b)
            with self.subTest(trial=trial):
                self.assertAlmostEqual(va.dot(vb), oa * ob, places=7)
                self.assert_close(va.cross(vb), oa ^ ob, 1e-7, "cross")
                self.assertAlmostEqual(va.lengthSq(), oa.length() ** 2, places=6)
                rotation = va.rotateTo(vb)
                self.assertIsInstance(rotation, Quaternion)
                self.assert_same_rotation(rotation, oa.rotateTo(ob))
                euler = om2.MEulerRotation(*_angles(rng))
                self.assert_close(va.rotateBy(euler), oa.rotateBy(euler), 1e-7, "rotateBy")
                self.assertAlmostEqual(va.angleTo(vb), oa.angle(ob), places=7)
                t = rng.random()
                self.assert_close(va.lerp(vb, t), oa + (ob - oa) * t, 1e-7, "lerp")
                self.assertIsInstance(va + vb, Vector)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if result.wasSuccessful() else 1)
