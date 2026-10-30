"""mlib.maths の数学型がom2と同じ意味を持つことを固定する仕様テスト(担当D)。

積の順序・行ベクトル/列ベクトル・単位(rad)・回転順序を、om2の型で独立に計算した値と比べる。
可変・ハッシュ不可・添字範囲・戻り値の型(派生型を保つか)もあわせて固定する。シーンは使わない。
"""

import copy
import math
import pickle
import sys
import unittest

import maya.api.OpenMaya as om2

import mlib
mlib.reload()
from mlib.maths import EulerRotate
from mlib.maths import Matrix
from mlib.maths import Quaternion
from mlib.maths import Scale
from mlib.maths import Shear
from mlib.maths import Translate
from mlib.maths import Vector
from mlib.maths.eulerRotate import ORDER_NAMES
from mlib.maths.eulerRotate import orderIndex

#: 検証用の固定した回転(rad)。
ANGLES = (0.3, -1.1, 2.4)
OM2_ORDERS = (om2.MEulerRotation.kXYZ, om2.MEulerRotation.kYZX, om2.MEulerRotation.kZXY,
              om2.MEulerRotation.kXZY, om2.MEulerRotation.kYXZ, om2.MEulerRotation.kZYX)


def _om2_matrix(values):
    """16要素からom2.MMatrixを作る。"""
    return om2.MMatrix(list(values))


def _sample_matrix():
    """平行移動・回転・不均一スケールを含む固定のom2マトリクスを返す。"""
    tm = om2.MTransformationMatrix()
    tm.setTranslation(om2.MVector(1.0, -2.0, 3.5), om2.MSpace.kTransform)
    tm.setRotation(om2.MEulerRotation(0.4, 0.2, -0.7))
    tm.setScale([1.5, 0.5, 2.0], om2.MSpace.kTransform)
    return tm.asMatrix()


class ValueTypeContractTest(unittest.TestCase):
    """全ての数学型に共通する、可変・ハッシュ不可・om2の派生であることを固定する。"""

    def test_unhashable_and_om2_subclasses(self):
        """全ての数学型はハッシュ不可で、om2の値型を継承する。"""
        values = [(Vector(), om2.MVector), (Translate(), om2.MVector), (Scale(), om2.MVector),
                  (Shear(), om2.MVector), (Quaternion(), om2.MQuaternion),
                  (EulerRotate(), om2.MEulerRotation), (Matrix(), om2.MMatrix)]
        for value, base in values:
            self.assertIsInstance(value, base)
            with self.assertRaises(TypeError):
                hash(value)
            with self.assertRaises(TypeError):
                {value: 1}

    def test_defaults(self):
        """既定値はゼロベクトル・単位クォータニオン・xyz順の0回転・単位マトリクス。"""
        self.assertEqual(tuple(Vector()), (0.0, 0.0, 0.0))
        self.assertEqual(tuple(Scale()), (0.0, 0.0, 0.0))
        self.assertEqual(tuple(Quaternion()), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(EulerRotate().order, om2.MEulerRotation.kXYZ)
        self.assertEqual(Matrix(), om2.MMatrix())
        self.assertEqual(Matrix.identity(), om2.MMatrix())

    def test_copy_and_pickle_keep_type_and_independence(self):
        """copy・deepcopy・pickleは同じ型の独立した値を作る。"""
        values = [Translate(1, 2, 3), Quaternion(0.1, 0.2, 0.3, 0.9),
                  EulerRotate(0.1, 0.2, 0.3, "zyx"), Matrix(translate=(1, 2, 3))]
        for value in values:
            for duplicate in (copy.copy(value), copy.deepcopy(value), pickle.loads(pickle.dumps(value))):
                self.assertIs(type(duplicate), type(value))
                self.assertEqual(duplicate, value)
                self.assertIsNot(duplicate, value)
        vector = Translate(1, 2, 3)
        duplicate = copy.copy(vector)
        duplicate.x = 9
        self.assertEqual(vector.x, 1.0)


class VectorSpecTest(unittest.TestCase):
    """Vector系の演算・添字・比較・補助メソッドを固定する。"""

    def test_constructor_forms(self):
        """成分・列・キーワード・MPoint(wで割らない)から作れる。不正なキーワードはTypeError。"""
        self.assertEqual(tuple(Vector(1, 2, 3)), (1.0, 2.0, 3.0))
        self.assertEqual(tuple(Vector([1, 2, 3])), (1.0, 2.0, 3.0))
        self.assertEqual(tuple(Vector(x=1, z=3)), (1.0, 0.0, 3.0))
        self.assertEqual(tuple(Vector(om2.MPoint(2, 4, 6, 2))), (2.0, 4.0, 6.0))
        self.assertEqual(tuple(Vector(1, 2)), tuple(om2.MVector(1, 2)))
        with self.assertRaises(TypeError):
            Vector(1, x=2)
        with self.assertRaises(TypeError):
            Vector(w=1)
        with self.assertRaises(ValueError):
            Vector("a", "b", "c")

    def test_mutable_components_and_index_range(self):
        """成分・添字へ代入でき、添字は-3〜2。範囲外はIndexError、整数以外はTypeError。"""
        value = Vector(1, 2, 3)
        value.x = 5
        value[1] = 6
        value[-1] = 7
        self.assertEqual(tuple(value), (5.0, 6.0, 7.0))
        self.assertEqual(value[-3], 5.0)
        self.assertEqual(value[0:2], (5.0, 6.0))
        for index in (3, -4, 10):
            with self.assertRaises(IndexError):
                value[index]
            with self.assertRaises(IndexError):
                value[index] = 0
        with self.assertRaises(TypeError):
            value["x"]
        with self.assertRaises(TypeError):
            value[0:2] = (1, 2)

    def test_matrix_products_match_om2(self):
        """v*mは行ベクトルの方向変換、m*vは列ベクトルの積(v*mᵀ)でom2と一致する。"""
        matrix = _sample_matrix()
        mlib_matrix = Matrix(matrix)
        vector = Vector(1.0, 2.0, 3.0)
        row = vector * mlib_matrix
        self.assertIs(type(row), Vector)
        self.assertTrue(row.isEquivalent(om2.MVector(1.0, 2.0, 3.0) * matrix, 1e-12))
        column = mlib_matrix * vector
        self.assertIs(type(column), Vector)
        self.assertTrue(column.isEquivalent(om2.MVector(1.0, 2.0, 3.0) * matrix.transpose(), 1e-12))
        # 平行移動は含まない。
        self.assertTrue((Vector(0, 0, 0) * mlib_matrix).isEquivalent((0, 0, 0)))

    def test_arithmetic_result_types(self):
        """+ - ^ は基底Vector、*=などの自身更新は派生型を保つ。v*wは内積、v*=wはfloatになる。"""
        a, b = Translate(1, 2, 3), Translate(-2, 0.5, 4)
        self.assertIs(type(a + b), Vector)
        self.assertIs(type(a - b), Vector)
        self.assertIs(type(a ^ b), Vector)
        self.assertIs(type(a * 2), Vector)
        self.assertIs(type(2 * a), Vector)
        self.assertIs(type(-a), Vector)
        self.assertIs(type(om2.MVector(1, 0, 0) + a), Vector)
        self.assertAlmostEqual(a * b, om2.MVector(1, 2, 3) * om2.MVector(-2, 0.5, 4))
        self.assertTrue((a ^ b).isEquivalent(om2.MVector(1, 2, 3) ^ om2.MVector(-2, 0.5, 4)))
        same = a
        same += b
        self.assertIs(same, a)
        self.assertIs(type(same), Translate)
        same /= 2
        self.assertIs(type(same), Translate)
        dot = Vector(1, 2, 3)
        dot *= Vector(1, 1, 1)
        self.assertIsInstance(dot, float)
        self.assertEqual(dot, 6.0)
        with self.assertRaises(ZeroDivisionError):
            Vector(1, 1, 1) / 0

    def test_equality(self):
        """==はMVector系と3個の数値のtuple/listとの成分の完全一致。派生型の違いは問わない。"""
        self.assertEqual(Translate(1, 2, 3), Vector(1, 2, 3))
        self.assertEqual(Vector(1, 2, 3), om2.MVector(1, 2, 3))
        self.assertEqual(Vector(1, 2, 3), (1, 2, 3))
        self.assertEqual([1.0, 2.0, 3.0], Vector(1, 2, 3))
        self.assertNotEqual(Vector(1, 2, 3), (1, 2, 4))
        self.assertNotEqual(Vector(1, 2, 3), (1, 2))
        self.assertNotEqual(Vector(1, 0, 0), (True, False, False))
        self.assertNotEqual(Vector(1, 2, 3), ("1", 2, 3))
        self.assertNotEqual(Vector(1, 2, 3), om2.MPoint(1, 2, 3))
        self.assertNotEqual(Vector(1, 2, 3), None)
        self.assertNotEqual(Vector(1, 2, 3), Vector(1, 2, 3.0000001))

    def test_sequence_operands(self):
        """+ / - は3個の数値のtuple/listを相手にでき、om2で同じ成分を加減した値と一致する。"""
        a = Translate(1, 2, 3)
        om = om2.MVector(1, 2, 3)
        cases = (
            (a + (1, 1, 1), om + om2.MVector(1, 1, 1)),
            ((1, 1, 1) + a, om + om2.MVector(1, 1, 1)),
            (a - [0.5, 1, 0], om - om2.MVector(0.5, 1, 0)),
            ([0.5, 1, 0] - a, om2.MVector(0.5, 1, 0) - om),
        )
        for result, expected in cases:
            with self.subTest(result=result):
                self.assertIs(type(result), Vector)
                self.assertEqual(result, expected)
        same = Translate(1, 2, 3)
        before = same
        same += (1, 1, 1)
        same -= [0, 0, 1]
        self.assertIs(same, before)
        self.assertIs(type(same), Translate)
        self.assertEqual(same, (2, 3, 3))
        for invalid in ((1, 2), (1, 2, 3, 4), ("1", 2, 3), (True, 0, 0), om2.MPoint(1, 2, 3), None, {1, 2, 3}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(TypeError):
                    a + invalid
                with self.assertRaises(TypeError):
                    a - invalid
        with self.assertRaises(TypeError):
            value = Vector()
            value += (1, 2)

    def test_quaternion_from_euler_and_matrix(self):
        """Quaternion(EulerRotate)はasQuaternion()、Quaternion(Matrix)はMTransformationMatrixの回転と一致する。"""
        for order in ORDER_NAMES:
            euler = EulerRotate(0.3, -1.1, 2.4, order)
            with self.subTest(order=order):
                result = Quaternion(euler)
                self.assertIs(type(result), Quaternion)
                self.assertEqual(result, euler.asQuaternion())
                raw = om2.MEulerRotation(0.3, -1.1, 2.4, orderIndex(order))
                self.assertEqual(Quaternion(raw), raw.asQuaternion())
        source = _sample_matrix()
        expected = om2.MTransformationMatrix(source).rotation(asQuaternion=True)
        for value in (source, Matrix(source)):
            with self.subTest(type=type(value).__name__):
                result = Quaternion(value)
                self.assertIs(type(result), Quaternion)
                for actual, wanted in zip(result, expected):
                    self.assertAlmostEqual(actual, wanted, places=12)
        self.assertEqual(Quaternion(Matrix()), Quaternion())

    def test_measure_methods_match_om2(self):
        """dot・cross・length・lengthSq・distanceToはom2の計算と一致する。"""
        a, b = Vector(1, -2, 2), Vector(4, 0.5, -1)
        oa, ob = om2.MVector(1, -2, 2), om2.MVector(4, 0.5, -1)
        self.assertAlmostEqual(a.dot(b), oa * ob)
        self.assertAlmostEqual(a.dot((4, 0.5, -1)), oa * ob)
        self.assertTrue(a.cross(b).isEquivalent(oa ^ ob))
        self.assertIs(type(Translate(1, 0, 0).cross((0, 1, 0))), Vector)
        self.assertAlmostEqual(a.lengthSq(), oa.length() ** 2)
        self.assertAlmostEqual(a.lengthSq(), 9.0)
        self.assertAlmostEqual(a.distanceTo(b), om2.MPoint(oa).distanceTo(om2.MPoint(ob)))
        self.assertAlmostEqual(a.distanceTo(om2.MPoint(4, 0.5, -1)), (oa - ob).length())

    def test_normalization(self):
        """unitはゼロを拒否し、normalはom2に従いゼロを受け付ける。unitItは失敗時に変更しない。"""
        value = Translate(3, 0, 4)
        unit = value.unit()
        self.assertIs(type(unit), Vector)
        self.assertTrue(unit.isEquivalent((0.6, 0.0, 0.8)))
        self.assertEqual(tuple(value), (3.0, 0.0, 4.0))
        self.assertIs(value.unitIt(), value)
        self.assertIs(type(value), Translate)
        self.assertAlmostEqual(value.length(), 1.0)
        zero = Vector()
        with self.assertRaises(ValueError):
            zero.unit()
        with self.assertRaises(ValueError):
            zero.unitIt()
        self.assertEqual(tuple(zero), (0.0, 0.0, 0.0))
        normal = zero.normal()
        self.assertIs(type(normal), Vector)
        self.assertEqual(normal, om2.MVector().normal())

    def test_angle_to(self):
        """angleToはradで0〜π、微小角も精度を保ち、ゼロベクトルはValueError。"""
        self.assertAlmostEqual(Vector(1, 0, 0).angleTo((0, 1, 0)), math.pi / 2)
        self.assertAlmostEqual(Vector(1, 0, 0).angleTo((-1, 0, 0)), math.pi)
        self.assertAlmostEqual(Vector(1, 0, 0).angleTo((1, 1e-8, 0)), 1e-8, places=15)
        self.assertEqual(Vector(1, 0, 0).angleTo((2, 0, 0)), 0.0)
        with self.assertRaises(ValueError):
            Vector().angleTo((1, 0, 0))
        with self.assertRaises(ValueError):
            Vector(1, 0, 0).angleTo((0, 0, 0))

    def test_is_equivalent_uses_om2(self):
        """isEquivalentはom2のisEquivalentと同じ結果になる。"""
        cases = [((0, 0, 0), (0.6, 0.6, 0), 0.7), ((0, 0, 0), (0.6, 0.6, 0), 0.9),
                 ((1, 2, 3), (1, 2, 3 + 1e-11), 1e-10), ((1, 2, 3), (1, 2, 3.1), 0.05)]
        for left, right, tolerance in cases:
            self.assertEqual(Vector(left).isEquivalent(right, tolerance),
                             om2.MVector(left).isEquivalent(om2.MVector(right), tolerance))
        # docstringどおり、成分ごとの差ではなく距離(約0.849)で判定する。
        self.assertFalse(Vector(0, 0, 0).isEquivalent((0.6, 0.6, 0), 0.7))
        self.assertTrue(Vector(0, 0, 0).isEquivalent((0.6, 0.6, 0), 0.85))

    def test_rotations_match_om2(self):
        """rotateBy・rotateTo・transformAsNormalはom2と一致し、mlibの型を返す。"""
        quaternion = om2.MQuaternion(0.7, om2.MVector(1, 2, 3))
        value = Vector(1, 0.5, -2)
        rotated = value.rotateBy(Quaternion(quaternion))
        self.assertIs(type(rotated), Vector)
        self.assertTrue(rotated.isEquivalent(om2.MVector(1, 0.5, -2).rotateBy(quaternion), 1e-12))
        axis_rotated = value.rotateBy(om2.MVector.kYaxis, 0.5)
        self.assertTrue(axis_rotated.isEquivalent(om2.MVector(1, 0.5, -2).rotateBy(om2.MVector.kYaxis, 0.5)))
        target = Vector(1, 0, 0).rotateTo(om2.MVector(0, 1, 0))
        self.assertIs(type(target), Quaternion)
        self.assertTrue(target.isEquivalent(om2.MVector(1, 0, 0).rotateTo(om2.MVector(0, 1, 0)), 1e-12))
        matrix = _sample_matrix()
        normal = Vector(0, 1, 0).transformAsNormal(matrix)
        self.assertIs(type(normal), Vector)
        self.assertTrue(normal.isEquivalent(om2.MVector(0, 1, 0).transformAsNormal(matrix), 1e-12))
        self.assertEqual(tuple(value), (1.0, 0.5, -2.0))

    def test_lerp_mirror_and_from_iterable(self):
        """lerpは外挿も行い基底Vectorを返す。mirrorは同型の複製、mirrorItは自身を更新する。"""
        a, b = Translate(0, 0, 0), Vector(2, 4, -2)
        self.assertEqual(tuple(a.lerp(b, 0)), (0.0, 0.0, 0.0))
        self.assertEqual(tuple(a.lerp(b, 1)), (2.0, 4.0, -2.0))
        self.assertEqual(tuple(a.lerp(b, 1.5)), (3.0, 6.0, -3.0))
        self.assertIs(type(a.lerp(b, 0.5)), Vector)
        value = Translate(3, 2, 1)
        mirrored = value.mirror("x", pivot=(1, 0, 0))
        self.assertIs(type(mirrored), Translate)
        self.assertEqual(tuple(mirrored), (-1.0, 2.0, 1.0))
        self.assertEqual(tuple(value.mirror("yz")), (-3.0, 2.0, 1.0))
        self.assertEqual(tuple(value.mirror(2)), (3.0, 2.0, -1.0))
        self.assertIs(value.mirrorIt("XY"), value)
        self.assertEqual(tuple(value), (3.0, 2.0, -1.0))
        for axis in ("w", "xx", "", "xyz", 3):
            with self.assertRaises(ValueError):
                value.mirror(axis)
        with self.assertRaises(TypeError):
            value.mirror(None)
        self.assertIs(type(Scale.fromIterable(iter([1, 2, 3]))), Scale)
        with self.assertRaises(ValueError):
            Vector.fromIterable([1, 2])


class QuaternionSpecTest(unittest.TestCase):
    """Quaternionの積の順序・正規化・分解をom2と比べて固定する。"""

    def setUp(self):
        """固定の2つの回転を用意する。"""
        self.om_a = om2.MQuaternion(0.6, om2.MVector(1, 0.2, -0.4))
        self.om_b = om2.MQuaternion(-1.3, om2.MVector(0.1, 1, 0.5))
        self.a = Quaternion(self.om_a)
        self.b = Quaternion(self.om_b)

    def test_product_order_matches_om2_and_matrix(self):
        """a*bはaを先に適用する回転で、om2の積・マトリクスの積と同じ順序。"""
        product = self.a * self.b
        self.assertIs(type(product), Quaternion)
        self.assertTrue(product.isEquivalent(self.om_a * self.om_b, 1e-12))
        vector = om2.MVector(1, 2, 3)
        self.assertTrue(vector.rotateBy(product).isEquivalent(vector.rotateBy(self.om_a).rotateBy(self.om_b), 1e-9))
        self.assertTrue(product.asMatrix().isEquivalent(self.a.asMatrix() * self.b.asMatrix(), 1e-9))
        self.assertIs(type(self.om_a * self.b), Quaternion)
        target = Quaternion(self.a)
        target *= self.b
        self.assertTrue(target.isEquivalent(product, 0.0))

    def test_scalar_and_componentwise_operations(self):
        """数値*qは4成分のスカラー倍。q*数値・除算はTypeError。加減算は成分ごと。"""
        scaled = 2 * self.a
        self.assertIs(type(scaled), Quaternion)
        self.assertEqual(tuple(scaled), tuple(2 * v for v in self.a))
        with self.assertRaises(TypeError):
            self.a * 2
        with self.assertRaises(TypeError):
            self.a / 2
        total = self.a + self.b
        self.assertEqual(tuple(total), tuple(x + y for x, y in zip(self.a, self.b)))
        self.assertEqual(tuple(-self.a), tuple(-v for v in self.a))
        value = Quaternion(self.a)
        same = value
        value += self.b
        self.assertIs(value, same)

    def test_index_and_equality(self):
        """lenは4、添字は-4〜3。qと-qは同じ回転でも==ではない。"""
        self.assertEqual(len(self.a), 4)
        self.assertEqual(self.a[-1], self.a.w)
        self.assertEqual(self.a[-4], self.a.x)
        for index in (4, -5):
            with self.assertRaises(IndexError):
                self.a[index]
        self.assertNotEqual(self.a, -self.a)
        self.assertAlmostEqual(self.a.angleTo(-self.a), 0.0, places=7)

    def test_from_axis_angle_matches_om2(self):
        """fromAxisAngleはom2.MQuaternion(angle, axis)と一致し、ゼロ軸はValueError。"""
        made = Quaternion.fromAxisAngle((0, 0, 2), math.pi / 3)
        self.assertTrue(made.isEquivalent(om2.MQuaternion(math.pi / 3, om2.MVector(0, 0, 1)), 1e-12))
        self.assertAlmostEqual(made.length(), 1.0)
        with self.assertRaises(ValueError):
            Quaternion.fromAxisAngle((0, 0, 0), 1.0)

    def test_normalization_and_inverse(self):
        """unit・inverseはゼロを拒否し、normalはom2に従う。非単位のinverseもom2と一致する。"""
        zero = Quaternion(0, 0, 0, 0)
        for method in (zero.unit, zero.unitIt, zero.inverse):
            with self.assertRaises(ValueError):
                method()
        self.assertEqual(tuple(zero), (0.0, 0.0, 0.0, 0.0))
        self.assertTrue(zero.normal().isEquivalent(om2.MQuaternion(0, 0, 0, 0).normal(), 0.0))
        value = Quaternion(1, 2, 3, 4)
        self.assertTrue(value.inverse().isEquivalent(om2.MQuaternion(1, 2, 3, 4).inverse(), 1e-12))
        self.assertIs(type(value.conjugate()), Quaternion)
        self.assertEqual(tuple(value.conjugate()), (-1.0, -2.0, -3.0, 4.0))
        self.assertAlmostEqual(value.unit().length(), 1.0)
        self.assertEqual(tuple(value), (1.0, 2.0, 3.0, 4.0))
        self.assertIs(value.unitIt(), value)
        self.assertAlmostEqual(value.length(), 1.0)
        self.assertAlmostEqual(Quaternion(1, 2, 3, 4).dot(Quaternion(1, 0, 0, 1)), 5.0)

    def test_rotate_vector_normalizes_a_copy(self):
        """rotateVectorは正規化したコピーで回し、長さを変えない。自身は変更しない。"""
        doubled = 2 * self.a
        result = doubled.rotateVector((1, 2, 3))
        self.assertIs(type(result), Vector)
        self.assertTrue(result.isEquivalent(om2.MVector(1, 2, 3).rotateBy(self.om_a), 1e-9))
        self.assertAlmostEqual(doubled.length(), 2.0)
        with self.assertRaises(ValueError):
            Quaternion(0, 0, 0, 0).rotateVector((1, 0, 0))

    def test_angle_to_and_slerp(self):
        """angleToは二重被覆を考慮したrad、slerpは正規化した入力でom2のslerpと一致する。"""
        quarter = Quaternion.fromAxisAngle((0, 1, 0), math.pi / 2)
        self.assertAlmostEqual(Quaternion().angleTo(quarter), math.pi / 2)
        self.assertAlmostEqual(Quaternion().angleTo(Quaternion(0, 0, 0, -1)), 0.0)
        half = Quaternion().slerp(quarter, 0.5)
        self.assertIs(type(half), Quaternion)
        self.assertAlmostEqual(Quaternion().angleTo(half), math.pi / 4)
        self.assertTrue(Quaternion.slerp(Quaternion(), quarter, 0.5).isEquivalent(half, 1e-12))
        expected = om2.MQuaternion.slerp(self.om_a.normal(), self.om_b.normal(), 0.3, 0)
        self.assertTrue(self.a.slerp(self.b, 0.3).isEquivalent(expected, 1e-12))
        with self.assertRaises(ValueError):
            Quaternion(0, 0, 0, 0).slerp(quarter, 0.5)

    def test_axis_angle_forms(self):
        """asCanonicalAxisAngleは角度0〜π、回転なしの軸は(1,0,0)。asAxisAngleはom2に従う。"""
        axis, angle = Quaternion().asCanonicalAxisAngle()
        self.assertEqual(tuple(axis), (1.0, 0.0, 0.0))
        self.assertEqual(angle, 0.0)
        negative = -Quaternion.fromAxisAngle((0, 0, 1), 0.5)
        axis, angle = negative.asCanonicalAxisAngle()
        self.assertTrue(axis.isEquivalent((0, 0, 1), 1e-12))
        self.assertAlmostEqual(angle, 0.5)
        axis, angle = self.a.asAxisAngle()
        om_axis, om_angle = self.om_a.asAxisAngle()
        self.assertIs(type(axis), Vector)
        self.assertTrue(axis.isEquivalent(om_axis, 1e-12))
        self.assertAlmostEqual(angle, om_angle)

    def test_swing_twist_recomposes(self):
        """asSwingTwistは(swing, twist)を返し、twist*swingが元の回転になる。"""
        swing, twist = self.a.asSwingTwist((0, 1, 0))
        self.assertAlmostEqual((twist * swing).angleTo(self.a), 0.0, places=7)
        self.assertAlmostEqual(twist.x, 0.0)
        self.assertAlmostEqual(twist.z, 0.0)
        self.assertAlmostEqual(swing.length(), 1.0)
        with self.assertRaises(ValueError):
            self.a.asSwingTwist((0, 0, 0))

    def test_conversions_match_om2(self):
        """asMatrix・asEulerRotation・exp・log・squad・squadPtはom2と一致し、mlibの型を返す。"""
        self.assertIs(type(self.a.asMatrix()), Matrix)
        self.assertTrue(self.a.asMatrix().isEquivalent(self.om_a.asMatrix(), 1e-12))
        self.assertIs(type(self.a.asUnitMatrix()), Matrix)
        self.assertTrue((2 * self.a).asUnitMatrix().isEquivalent(self.om_a.asMatrix(), 1e-12))
        euler = self.a.asEulerRotation()
        self.assertIs(type(euler), EulerRotate)
        self.assertTrue(euler.isEquivalent(self.om_a.asEulerRotation(), 1e-12))
        self.assertTrue(self.a.asEulerRotate().isEquivalent(euler, 0.0))
        self.assertIs(type(self.a.log()), Quaternion)
        self.assertTrue(self.a.log().isEquivalent(self.om_a.log(), 1e-12))
        self.assertTrue(self.a.log().exp().isEquivalent(self.om_a.log().exp(), 1e-12))
        c = Quaternion.fromAxisAngle((1, 1, 0), 0.4)
        middle = Quaternion.squadPt(self.a, self.b, c)
        self.assertIs(type(middle), Quaternion)
        self.assertTrue(middle.isEquivalent(om2.MQuaternion.squadPt(self.om_a, self.om_b, c), 1e-12))
        value = Quaternion.squad(self.a, middle, middle, self.b, 0.25)
        self.assertIs(type(value), Quaternion)
        self.assertTrue(value.isEquivalent(om2.MQuaternion.squad(self.om_a, middle, middle, self.om_b, 0.25), 1e-12))

    def test_decomposed_euler_rotate_order(self):
        """asDecomposedEulerRotateはMEulerRotation.decomposeと同じ角度・指定順序を返す。"""
        for name, om_order in zip(ORDER_NAMES, OM2_ORDERS):
            euler = self.a.asDecomposedEulerRotate(name)
            expected = om2.MEulerRotation.decompose(self.om_a.normal().asMatrix(), om_order)
            self.assertEqual(euler.order, om_order)
            self.assertTrue(euler.isEquivalent(expected, 1e-12))
        with self.assertRaises(ValueError):
            self.a.asDecomposedEulerRotate("abc")

    def test_mirror_matches_matrix_mirror(self):
        """mirrorはMatrix.mirrorと同じビヘイビアミラーで、同型の複製を返す。"""
        mirrored = self.a.mirror("x")
        self.assertIs(type(mirrored), Quaternion)
        expected = self.a.asUnitMatrix().mirror("x").quaternion
        self.assertAlmostEqual(mirrored.angleTo(expected), 0.0, places=7)
        value = Quaternion(self.a)
        self.assertIs(value.mirrorIt("x"), value)
        self.assertAlmostEqual(value.angleTo(mirrored), 0.0, places=7)


class EulerRotateSpecTest(unittest.TestCase):
    """EulerRotateの回転順序・単位・合成をom2と比べて固定する。"""

    def test_order_index(self):
        """orderIndexは名前(大小文字不問)と0〜5を受け、bool・範囲外・小数はValueError。"""
        for index, name in enumerate(ORDER_NAMES):
            self.assertEqual(orderIndex(name), index)
            self.assertEqual(orderIndex(name.upper()), index)
            self.assertEqual(orderIndex(index), index)
            self.assertEqual(index, OM2_ORDERS[index])
        for value in (True, False, 6, -1, 1.0, "xxy", None):
            with self.assertRaises(ValueError):
                orderIndex(value)

    def test_constructor_does_not_reorder(self):
        """生成時のorderは成分を並べ替えず、名前でも番号でも指定できる。"""
        value = EulerRotate(0.1, 0.2, 0.3, "zyx")
        self.assertEqual(value.order, om2.MEulerRotation.kZYX)
        self.assertEqual(value.orderName, "zyx")
        self.assertEqual(tuple(value), (0.1, 0.2, 0.3))
        self.assertEqual(EulerRotate((0.1, 0.2, 0.3), 2).orderName, "zxy")
        self.assertEqual(EulerRotate(om2.MEulerRotation(0.1, 0.2, 0.3, om2.MEulerRotation.kYXZ)).orderName, "yxz")
        value.orderName = 1
        self.assertEqual(value.orderName, "yzx")
        self.assertEqual(tuple(value), (0.1, 0.2, 0.3))
        with self.assertRaises(ValueError):
            value.orderName = "bad"
        with self.assertRaises(ValueError):
            EulerRotate(0, 0, 0, "bad")

    def test_degrees_are_conversion_only(self):
        """内部値はrad。fromDegrees/asDegreesは換算だけでUI単位を参照しない。"""
        value = EulerRotate.fromDegrees(90, -45, 400, "yzx")
        self.assertAlmostEqual(value.x, math.pi / 2)
        self.assertAlmostEqual(value.z, math.radians(400))
        self.assertEqual(value.orderName, "yzx")
        degrees = value.asDegrees()
        self.assertIsInstance(degrees, tuple)
        for actual, expected in zip(degrees, (90, -45, 400)):
            self.assertAlmostEqual(actual, expected)

    def test_matrix_and_quaternion_match_om2_for_all_orders(self):
        """全ての回転順序でasMatrix・asQuaternionはom2と一致する。"""
        for order in range(6):
            value = EulerRotate(ANGLES[0], ANGLES[1], ANGLES[2], order)
            expected = om2.MEulerRotation(ANGLES[0], ANGLES[1], ANGLES[2], OM2_ORDERS[order])
            self.assertIs(type(value.asMatrix()), Matrix)
            self.assertTrue(value.asMatrix().isEquivalent(expected.asMatrix(), 1e-12))
            self.assertIs(type(value.asQuaternion()), Quaternion)
            self.assertTrue(value.asQuaternion().isEquivalent(expected.asQuaternion(), 1e-12))

    def test_xyz_order_applies_x_first_in_row_vector_convention(self):
        """xyz順は行ベクトル規約でX→Y→Zの順に適用する(Rx*Ry*Rz)。"""
        value = EulerRotate(ANGLES[0], ANGLES[1], ANGLES[2], "xyz")
        rx = EulerRotate(ANGLES[0], 0, 0).asMatrix()
        ry = EulerRotate(0, ANGLES[1], 0).asMatrix()
        rz = EulerRotate(0, 0, ANGLES[2]).asMatrix()
        self.assertTrue(value.asMatrix().isEquivalent(rx * ry * rz, 1e-12))
        zyx = EulerRotate(ANGLES[0], ANGLES[1], ANGLES[2], "zyx")
        self.assertTrue(zyx.asMatrix().isEquivalent(rz * ry * rx, 1e-12))

    def test_reorder_keeps_orientation(self):
        """reorderは同じ向きの新しい値を返し、自身は変更しない。"""
        value = EulerRotate(ANGLES[0], ANGLES[1], ANGLES[2], "xyz")
        reordered = value.reorder(om2.MEulerRotation.kZXY)
        self.assertIs(type(reordered), EulerRotate)
        self.assertEqual(reordered.orderName, "zxy")
        self.assertTrue(reordered.asMatrix().isEquivalent(value.asMatrix(), 1e-9))
        self.assertEqual(value.orderName, "xyz")
        self.assertEqual(tuple(value), ANGLES)

    def test_inherited_solutions_match_om2(self):
        """bound・closestCut・closestSolution・alternateSolution・inverse・asVectorと静的版はom2と一致する。"""
        source = om2.MEulerRotation(4.0, -3.5, 7.0, om2.MEulerRotation.kYZX)
        target = om2.MEulerRotation(0.1, 0.2, 0.3, om2.MEulerRotation.kYZX)
        value = EulerRotate(source)
        pairs = [
            (value.bound(), source.bound()),
            (value.closestCut(target), source.closestCut(target)),
            (value.closestSolution(target), source.closestSolution(target)),
            (value.alternateSolution(), source.alternateSolution()),
            (value.inverse(), source.inverse()),
            (EulerRotate.computeBound(source), om2.MEulerRotation.computeBound(source)),
            (EulerRotate.computeClosestCut(source, target), om2.MEulerRotation.computeClosestCut(source, target)),
            (EulerRotate.computeClosestSolution(source, target),
             om2.MEulerRotation.computeClosestSolution(source, target)),
            (EulerRotate.computeAlternateSolution(source), om2.MEulerRotation.computeAlternateSolution(source)),
            (EulerRotate.decompose(_sample_matrix(), om2.MEulerRotation.kZXY),
             om2.MEulerRotation.decompose(_sample_matrix(), om2.MEulerRotation.kZXY)),
        ]
        for actual, expected in pairs:
            self.assertIs(type(actual), EulerRotate)
            self.assertTrue(actual.isEquivalent(expected, 1e-12))
        vector = value.asVector()
        self.assertIs(type(vector), Vector)
        self.assertTrue(vector.isEquivalent(source.asVector(), 1e-12))
        self.assertTrue(value.isEquivalent(source, 0.0))

    def test_operators_follow_om2(self):
        """+ -は右辺を左辺の順序へ変換するom2の規則、*は数値のスケールまたは回転合成。"""
        left = EulerRotate(0.1, 0.2, 0.3, "xyz")
        right = EulerRotate(0.4, -0.5, 0.6, "zyx")
        om_left = om2.MEulerRotation(0.1, 0.2, 0.3, om2.MEulerRotation.kXYZ)
        om_right = om2.MEulerRotation(0.4, -0.5, 0.6, om2.MEulerRotation.kZYX)
        for actual, expected in ((left + right, om_left + om_right), (left - right, om_left - om_right),
                                 (left * right, om_left * om_right), (left * 2.0, om_left * 2.0)):
            self.assertIs(type(actual), EulerRotate)
            self.assertTrue(actual.isEquivalent(expected, 1e-12))
        self.assertTrue((2.0 * left).isEquivalent(left * 2.0, 0.0))
        self.assertTrue((left / 2.0).isEquivalent(left * 0.5, 1e-15))
        self.assertIs(type(-left), EulerRotate)
        value = EulerRotate(left)
        same = value
        value += right
        self.assertIs(value, same)

    def test_equality_and_is_equivalent_include_order(self):
        """==とisEquivalentは回転順序を含めて比較する。列はxyzのradとして扱う。"""
        self.assertNotEqual(EulerRotate(0.1, 0.2, 0.3, "xyz"), EulerRotate(0.1, 0.2, 0.3, "zyx"))
        self.assertFalse(EulerRotate(0.1, 0.2, 0.3, "zyx").isEquivalent(EulerRotate(0.1, 0.2, 0.3, "xyz"), 1.0))
        self.assertTrue(EulerRotate(0.1, 0.2, 0.3).isEquivalent((0.1, 0.2, 0.3)))
        self.assertFalse(EulerRotate(0.1, 0.2, 0.3, "zyx").isEquivalent((0.1, 0.2, 0.3)))
        value = EulerRotate(0.1, 0.2, 0.3)
        value[2] = 1.0
        self.assertEqual(value.z, 1.0)
        with self.assertRaises(IndexError):
            value[3]

    def test_mirror_keeps_order(self):
        """mirrorは回転順序を保ち、Matrix.mirrorと同じ向きになる。"""
        value = EulerRotate(ANGLES[0], ANGLES[1], ANGLES[2], "yxz")
        mirrored = value.mirror("x")
        self.assertEqual(mirrored.orderName, "yxz")
        self.assertTrue(mirrored.asMatrix().isEquivalent(value.asMatrix().mirror("x"), 1e-9))


class MatrixSpecTest(unittest.TestCase):
    """Matrixの積・点/方向の変換・合成と分解をom2と比べて固定する。"""

    def setUp(self):
        """固定の2つのマトリクスを用意する。"""
        self.om_a = _sample_matrix()
        tm = om2.MTransformationMatrix()
        tm.setRotation(om2.MEulerRotation(-0.2, 1.0, 0.3))
        tm.setTranslation(om2.MVector(-4, 0, 2), om2.MSpace.kTransform)
        self.om_b = tm.asMatrix()
        self.a = Matrix(self.om_a)
        self.b = Matrix(self.om_b)

    def test_products_match_om2(self):
        """a*b・a@bはaを先に適用するom2の積で、型はtype(a)。om2が左辺でもMatrix。"""
        for product in (self.a * self.b, self.a @ self.b):
            self.assertIs(type(product), Matrix)
            self.assertTrue(product.isEquivalent(self.om_a * self.om_b, 1e-12))
        self.assertIs(type(self.om_a * self.b), Matrix)
        self.assertTrue((self.om_a * self.b).isEquivalent(self.om_a * self.om_b, 1e-12))
        point = om2.MPoint(1, 2, 3)
        self.assertTrue(om2.MPoint(point * (self.a * self.b)).isEquivalent((point * self.om_a) * self.om_b, 1e-9))
        value = Matrix(self.a)
        same = value
        value @= self.b
        self.assertIs(value, same)
        with self.assertRaises(TypeError):
            self.a @ Vector(1, 2, 3)
        with self.assertRaises(TypeError):
            self.a @ 2

    def test_point_and_vector_transforms(self):
        """transformPointはw=1で平行移動を含み、transformVectorはw=0の方向変換。MPointのwは無視する。"""
        point = self.a.transformPoint((1, 2, 3))
        self.assertIs(type(point), Translate)
        expected = om2.MPoint(1, 2, 3) * self.om_a
        self.assertTrue(point.isEquivalent(om2.MVector(expected), 1e-12))
        self.assertTrue(self.a.transformPoint(om2.MPoint(1, 2, 3, 5)).isEquivalent(point, 1e-12))
        direction = self.a.transformVector(om2.MPoint(1, 2, 3, 5))
        self.assertIs(type(direction), Vector)
        self.assertTrue(direction.isEquivalent(om2.MVector(1, 2, 3) * self.om_a, 1e-12))
        column = self.a * om2.MPoint(1, 2, 3)
        self.assertIs(type(column), Vector)

    def test_compose_matches_transformation_matrix(self):
        """compose(translate, rotate, scale, shear)はMTransformationMatrixの合成と一致する。"""
        tm = om2.MTransformationMatrix()
        tm.setTranslation(om2.MVector(1, 2, 3), om2.MSpace.kTransform)
        tm.setRotation(om2.MEulerRotation(0.3, -0.4, 0.5, om2.MEulerRotation.kZXY))
        tm.setScale([2.0, 0.5, 1.5], om2.MSpace.kTransform)
        tm.setShear([0.1, 0.2, -0.3], om2.MSpace.kTransform)
        composed = Matrix.compose(translate=(1, 2, 3), rotate=EulerRotate(0.3, -0.4, 0.5, "zxy"),
                                  scale=(2.0, 0.5, 1.5), shear=(0.1, 0.2, -0.3))
        self.assertTrue(composed.isEquivalent(tm.asMatrix(), 1e-12))
        self.assertTrue(Matrix(translate=(1, 2, 3)).isEquivalent(Matrix.compose(translate=(1, 2, 3))))
        quaternion = Matrix.compose(rotate=Quaternion(0, 0, 0, 2))
        self.assertTrue(quaternion.isEquivalent(Matrix(), 1e-12))
        with self.assertRaises(ValueError):
            Matrix.compose(rotate=Quaternion(0, 0, 0, 0))
        with self.assertRaises(ValueError):
            Matrix.compose(translate=(1, 2))

    def test_decompose_matches_om2(self):
        """decomposeはMTransformationMatrixと同じ値を独立した数学値で返す。"""
        parts = self.a.decompose()
        self.assertEqual(set(parts), {"translate", "euler", "quaternion", "scale", "shear"})
        tm = om2.MTransformationMatrix(self.om_a)
        self.assertIs(type(parts["translate"]), Translate)
        self.assertIs(type(parts["scale"]), Scale)
        self.assertIs(type(parts["shear"]), Shear)
        self.assertTrue(parts["translate"].isEquivalent(tm.translation(om2.MSpace.kTransform), 1e-12))
        self.assertTrue(parts["euler"].isEquivalent(tm.rotation(), 1e-12))
        self.assertTrue(parts["scale"].isEquivalent(tm.scale(om2.MSpace.kTransform), 1e-12))
        parts["translate"].x = 99
        self.assertNotEqual(self.a[12], 99)
        self.assertTrue(self.a.translate.isEquivalent(parts["translate"] * 0 + tm.translation(om2.MSpace.kTransform)))

    def test_negative_determinant_uses_negative_z_scale(self):
        """負の行列式ではZスケールを負にして分解する(MTransformationMatrixと同じ)。"""
        mirrored = Matrix.compose(scale=(-1, 1, 1))
        scale = mirrored.scale
        self.assertLess(scale.z, 0.0)
        self.assertTrue(scale.isEquivalent(om2.MTransformationMatrix(mirrored).scale(om2.MSpace.kTransform), 1e-12))

    def test_component_properties(self):
        """translateの取得値は複製で、代入は添字12〜14だけを書く。分解できない場合はValueError。"""
        value = Matrix(self.a)
        translate = value.translate
        translate.x = 100
        self.assertNotEqual(value[12], 100)
        value.translate = (7, 8, 9)
        self.assertEqual((value[12], value[13], value[14]), (7.0, 8.0, 9.0))
        self.assertTrue(value.scale.isEquivalent(self.a.scale, 1e-12))
        value.scale = (1, 1, 1)
        self.assertTrue(value.scale.isEquivalent((1, 1, 1), 1e-12))
        self.assertTrue(value.rotate.isEquivalent(self.a.rotate, 1e-9))
        zero = Matrix.compose(scale=(0, 1, 1))
        zero.translate = (1, 2, 3)
        self.assertEqual(zero[12], 1.0)
        for name in ("scale", "shear", "rotate", "quaternion", "euler"):
            with self.assertRaises(ValueError, msg=name):
                getattr(zero, name)
        with self.assertRaises(ValueError):
            zero.decompose()

    def test_values_rows_and_index(self):
        """valuesは行優先16要素のtuple、rowsは4行のtuple。添字は-16〜15と(行,列)。"""
        values = self.a.values
        self.assertIsInstance(values, tuple)
        self.assertEqual(len(values), 16)
        self.assertEqual(values[12:15], (self.om_a[12], self.om_a[13], self.om_a[14]))
        self.assertEqual(self.a.rows[3][:3], values[12:15])
        self.assertEqual(self.a[3, 0], self.om_a[12])
        self.assertEqual(self.a[-1, -1], 1.0)
        self.assertEqual(self.a[-16], self.om_a[0])
        for index in (16, -17, (4, 0), (0, -5), (1, 2, 3)):
            with self.assertRaises(IndexError):
                self.a[index]
        value = Matrix()
        value[0, 3] = 5
        self.assertEqual(value[3], 5.0)

    def test_constructor_validation_keeps_value(self):
        """16要素・4行4列・MFloatMatrixから作れる。解釈できない入力はValueError。"""
        self.assertEqual(Matrix(list(range(16)))[15], 15.0)
        self.assertEqual(Matrix([list(range(4))] * 4)[7], 3.0)
        self.assertTrue(Matrix.fromMMatrix(om2.MFloatMatrix(self.om_a)).isEquivalent(self.om_a, 1e-6))
        self.assertIs(type(Matrix.fromMMatrix(self.om_a)), Matrix)
        for bad in (list(range(15)), ["a"] * 16, 5):
            with self.assertRaises(ValueError):
                Matrix(bad)

    def test_inverse_and_inherited_methods(self):
        """inverseは特異ならValueError、adjoint・homogenize・transposeはom2と一致する。"""
        inverse = self.a.inverse()
        self.assertIs(type(inverse), Matrix)
        self.assertTrue((self.a * inverse).isEquivalent(Matrix(), 1e-9))
        with self.assertRaises(ValueError):
            Matrix.compose(scale=(0, 1, 1)).inverse()
        for actual, expected in ((self.a.adjoint(), self.om_a.adjoint()),
                                 (self.a.homogenize(), self.om_a.homogenize()),
                                 (self.a.transpose(), self.om_a.transpose())):
            self.assertIs(type(actual), Matrix)
            self.assertTrue(actual.isEquivalent(expected, 1e-12))
        self.assertTrue(self.a.isEquivalent(list(self.om_a), 1e-12))

    def test_mirror_preserves_determinant_sign(self):
        """ビヘイビアミラーは行列式の符号を保ち、平行移動はpivotを中心に反転する。"""
        mirrored = self.a.mirror("x", pivot=(1, 0, 0))
        self.assertIs(type(mirrored), Matrix)
        self.assertGreater(mirrored.det4x4() * self.a.det4x4(), 0.0)
        self.assertAlmostEqual(mirrored[12], 2.0 - self.a[12])
        self.assertTrue(mirrored.scale.isEquivalent(self.a.scale, 1e-9))
        value = Matrix(self.a)
        self.assertIs(value.mirrorIt("x", pivot=(1, 0, 0)), value)
        self.assertTrue(value.isEquivalent(mirrored, 0.0))
        with self.assertRaises(ValueError):
            self.a.mirror("q")

    def test_from_transformation_matrix(self):
        """fromTransformationはom2.MTransformationMatrixからマトリクスを作る。"""
        tm = om2.MTransformationMatrix(self.om_a)
        self.assertTrue(Matrix.fromTransformation(tm).isEquivalent(self.om_a, 1e-12))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
