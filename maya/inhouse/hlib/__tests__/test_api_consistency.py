"""改名後の入口、引数別名、OpenMaya値の戻り型を検証する。"""
import inspect
import unittest

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import hlib
from hlib.maths import EulerRotate, Matrix, Quaternion, Vector


class ValueReturnTest(unittest.TestCase):
    """コピーと自身更新を区別し、標準APIとの数値一致を確認する。"""

    def test_native_copy_methods(self):
        """継承した数学演算もhlib型を返し、入力を変更しない。"""
        v = Vector(1, 2, 3)
        q = Quaternion.fromAxisAngle((1, 0, 0), .4)
        e = EulerRotate(.2, -.3, .4)
        m = Matrix(rotate=e, translate=(1, 2, 3), scale=(2, 3, 4))
        cases = [
            (v, 'normal', (), Vector, om2.MVector),
            (v, 'rotateBy', (q,), Vector, om2.MVector),
            (v, 'rotateTo', (Vector(0, 1, 0),), Quaternion, om2.MVector),
            (v, 'transformAsNormal', (m,), Vector, om2.MVector),
            (q, 'normal', (), Quaternion, om2.MQuaternion),
            (q, 'log', (), Quaternion, om2.MQuaternion),
            (q, 'exp', (), Quaternion, om2.MQuaternion),
            (q, 'asMatrix', (), Matrix, om2.MQuaternion),
            (q, 'asEulerRotation', (), EulerRotate, om2.MQuaternion),
            (e, 'asMatrix', (), Matrix, om2.MEulerRotation),
            (e, 'asQuaternion', (), Quaternion, om2.MEulerRotation),
            (e, 'asVector', (), Vector, om2.MEulerRotation),
            (e, 'inverse', (), EulerRotate, om2.MEulerRotation),
            (e, 'reorder', (om2.MEulerRotation.kZYX,), EulerRotate, om2.MEulerRotation),
            (e, 'bound', (), EulerRotate, om2.MEulerRotation),
            (e, 'alternateSolution', (), EulerRotate, om2.MEulerRotation),
            (e, 'closestCut', (EulerRotate(),), EulerRotate, om2.MEulerRotation),
            (e, 'closestSolution', (EulerRotate(),), EulerRotate, om2.MEulerRotation),
            (m, 'adjoint', (), Matrix, om2.MMatrix),
            (m, 'homogenize', (), Matrix, om2.MMatrix),
        ]
        for value, method, args, cls, native in cases:
            with self.subTest(type=type(value).__name__, method=method):
                before = tuple(value)
                expected = getattr(native, method)(native(value), *args)
                actual = getattr(value, method)(*args)
                self.assertIs(type(actual), cls)
                self.assertIsNot(actual, value)
                for a, b in zip(actual, expected):
                    self.assertAlmostEqual(a, b, places=11)
                self.assertEqual(tuple(value), before)
                if isinstance(actual, EulerRotate):
                    self.assertEqual(actual.order, expected.order)

    def test_native_static_and_compound_results(self):
        """静的APIと複合戻り値の数学成分もhlib型になる。"""
        e = EulerRotate(.2, .3, .4)
        q = Quaternion.fromAxisAngle((1, 0, 0), .2)
        for name, args in [('computeAlternateSolution', (e,)), ('computeBound', (e,)),
                           ('computeClosestCut', (e, EulerRotate())),
                           ('computeClosestSolution', (e, EulerRotate())),
                           ('decompose', (e.asMatrix(), e.order))]:
            self.assertIs(type(getattr(EulerRotate, name)(*args)), EulerRotate)
        self.assertIs(type(Quaternion.squad(q, q, q, q, .5)), Quaternion)
        self.assertIs(type(Quaternion.squadPt(q, q, q)), Quaternion)
        axis, angle = q.asAxisAngle()
        native_axis, native_angle = om2.MQuaternion.asAxisAngle(q)
        self.assertIs(type(axis), Vector)
        self.assertEqual(tuple(axis), tuple(native_axis))
        self.assertEqual(angle, native_angle)

    def test_in_place_identity_and_strict_operations(self):
        """自身更新は同一オブジェクトを返し、厳密版はゼロを拒否する。"""
        for value, method in [(Vector(1, 2, 3), 'normalize'),
                              (Quaternion.fromAxisAngle((1, 0, 0), .4), 'invertIt'),
                              (EulerRotate(.2, .3, .4), 'invertIt')]:
            self.assertIs(getattr(value, method)(), value)
        for cls in (Vector, Quaternion):
            value = cls(1, 2, 3) if cls is Vector else cls(1, 2, 3, 4)
            before = tuple(value)
            self.assertIsNot(value.unit(), value)
            self.assertEqual(tuple(value), before)
            self.assertIs(value.unitIt(), value)
            zero = cls(0, 0, 0) if cls is Vector else cls(0, 0, 0, 0)
            self.assertIs(type(zero.normal()), cls)
            with self.assertRaises(ValueError):
                zero.unitIt()
            self.assertTrue(all(x == 0 for x in zero))

    def test_retired_names(self):
        """廃止した別名を残さず、正式名だけを公開する。"""
        for cls, names in [(hlib.nodes.Transform, ('getT','setT','getQ','setQ','getS','setS','getSh','setSh','getM','setM','getX','setX')),
                           (Vector, ('normalized','mirrored')),
                           (Quaternion, ('toMatrix','toEuler','toAxisAngle','toSwingTwist','normalized','mirrored')),
                           (EulerRotate, ('toMatrix','toQuaternion','mirrored')),
                           (Matrix, ('determinant','toTransformation','mirrored'))]:
            for name in names:
                with self.subTest(cls=cls, name=name):
                    self.assertIsNone(inspect.getattr_static(cls, name, None))


class ArgumentAliasTest(unittest.TestCase):
    """新規引数別名と既存コレクション転送を検証する。"""

    def setUp(self):
        """引数別名を検証するノードを作成する。"""
        self.nodes = [hlib.createNode('transform'), hlib.createNode('multMatrix')]

    def tearDown(self):
        """検証用ノードを削除する。"""
        cmds.delete([str(n) for n in self.nodes if n.isValid()])

    def test_short_long_and_duplicate(self):
        """両名は同じ入口へ渡り、二重指定では編集しない。"""
        node, calc = self.nodes
        node.getPlug('tx').set(4)
        node.resetAttrs(attrs=['tx'])
        self.assertEqual(node.getPlug('tx').get(), 0)
        node.getPlug('tx').set(4)
        with self.assertRaises(TypeError):
            node.resetAttrs(attrs=['tx'], attributes=['tx'])
        self.assertEqual(node.getPlug('tx').get(), 4)
        node.resetAttrs(attributes=['tx'])
        array = calc.getPlug('matrixIn')
        self.assertEqual(array.getElement(idx=0, create=True), array.getElement(index=0))
        with self.assertRaises(TypeError):
            array.getElement(0, idx=1)
        with self.assertRaises(TypeError):
            array.getElement(idx=0, index=0)
        hlib.nodes.Transforms([node]).resetAttrs(attrs=['tx'])


if __name__ == '__main__':
    unittest.main()
