"""hlib.maths の値型(om2 を継承した Vector 系・Quaternion・EulerRotation・Matrix)を検証する。

hlib.maths は maya.api.OpenMaya の MVector / MQuaternion / MEulerRotation / MMatrix を
継承するため mayapy で実行する(maya.cmds を使うテストは standalone 初期化済みの
環境を前提とする)。hlib パッケージ全体ではなく maths だけを仮パッケージとして読み込む。
"""

import copy
import importlib
import math
from pathlib import Path
import pickle
import sys
import types

import maya.api.OpenMaya as om2


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "hlib_math_test"

package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE_NAME] = package
module = importlib.import_module(f"{PACKAGE_NAME}.maths")


Vector = module.Vector
Translation = module.Translation
EulerRotation = module.EulerRotation
Quaternion = module.Quaternion
Scale = module.Scale
Shear = module.Shear
Matrix = module.Matrix
ORDER_NAMES = module.eulerRotation.ORDER_NAMES


def test_translation_is_vector_like():
    t = Translation(1.0, 2.0, 3.0)
    assert isinstance(t, Vector)
    assert tuple(t) == (1.0, 2.0, 3.0)


def test_vector_dot_cross_length_and_normalized():
    x = Vector(1.0, 0.0, 0.0)
    y = Vector(0.0, 1.0, 0.0)
    assert x.dot(y) == 0.0
    assert x.dot(x) == 1.0
    assert tuple(x.cross(y)) == (0.0, 0.0, 1.0)
    assert type(x.cross(y)) is Vector
    assert Vector(3.0, 4.0, 0.0).length() == 5.0
    normalized = Vector(0.0, 0.0, 5.0).normalized()
    assert type(normalized) is Vector
    assert tuple(normalized) == (0.0, 0.0, 1.0)


def test_vector_neg_truediv_and_length_squared():
    v = Vector(1.0, -2.0, 3.0)
    assert tuple(-v) == (-1.0, 2.0, -3.0)
    assert type(-v) is Vector
    assert tuple(Vector(2.0, 4.0, 6.0) / 2.0) == (1.0, 2.0, 3.0)
    assert type(Vector(2.0, 4.0, 6.0) / 2.0) is Vector
    assert Vector(3.0, 4.0, 0.0).length_squared() == 25.0


def test_vector_distance_to_and_angle_to():
    a = Translation(0.0, 0.0, 0.0)
    b = Translation(3.0, 4.0, 0.0)
    assert a.distance_to(b) == 5.0
    assert b.distance_to(a) == 5.0

    x = Vector(1.0, 0.0, 0.0)
    y = Vector(0.0, 1.0, 0.0)
    assert math.isclose(x.angle_to(y), math.pi / 2.0)
    assert math.isclose(x.angle_to(x), 0.0, abs_tol=1e-12)
    assert math.isclose(x.angle_to(Vector(-1.0, 0.0, 0.0)), math.pi)

    try:
        x.angle_to(Vector(0.0, 0.0, 0.0))
    except ValueError:
        pass
    else:
        raise AssertionError("angle_to with a zero vector should raise ValueError")


def test_vector_is_equivalent_and_lerp():
    a = Vector(1.0, 2.0, 3.0)
    b = Vector(1.0 + 1e-12, 2.0, 3.0)
    assert a.is_equivalent(b)
    assert not a.is_equivalent(Vector(1.1, 2.0, 3.0))
    assert not a.is_equivalent(Vector(1.1, 2.0, 3.0), tolerance=1e-3)
    assert a.is_equivalent(Vector(1.0009, 2.0, 3.0), tolerance=1e-3)

    start = Vector(0.0, 0.0, 0.0)
    end = Vector(10.0, 20.0, 30.0)
    assert tuple(start.lerp(end, 0.0)) == (0.0, 0.0, 0.0)
    assert tuple(start.lerp(end, 1.0)) == (10.0, 20.0, 30.0)
    assert tuple(start.lerp(end, 0.5)) == (5.0, 10.0, 15.0)
    assert type(start.lerp(end, 0.5)) is Vector


def test_vector_normalized_rejects_zero_vector():
    try:
        Vector(0.0, 0.0, 0.0).normalized()
    except ValueError:
        pass
    else:
        raise AssertionError("Vector(0, 0, 0).normalized() should raise ValueError")


def test_scale_and_shear_are_distinct():
    rotation = EulerRotation(0.0, 90.0, 0.0)
    scale = Scale(2.0, 3.0, 4.0)
    shear = Shear(0.1, 0.2, 0.3)
    # EulerRotation は om2.MEulerRotation の派生で、Vector(om2.MVector)の派生ではない。
    assert isinstance(rotation, om2.MEulerRotation)
    assert not isinstance(rotation, Vector)
    assert isinstance(scale, Vector)
    assert isinstance(shear, Vector)
    assert isinstance(scale, om2.MVector)
    assert type(rotation) is not type(scale)
    assert type(scale) is not type(shear)


def test_euler_rotation_converts_to_a_unit_quaternion():
    rotation = EulerRotation(0.0, 0.0, 0.0)
    quaternion = rotation.to_quaternion()
    assert isinstance(quaternion, Quaternion)
    assert tuple(quaternion) == (0.0, 0.0, 0.0, 1.0)


def test_euler_rotation_displays_degrees_but_stores_radians():
    rotation = EulerRotation(math.pi / 2.0, 0.0, -math.pi / 4.0)
    assert tuple(rotation) == (math.pi / 2.0, 0.0, -math.pi / 4.0)
    assert rotation.as_degrees() == (90.0, 0.0, -45.0)
    assert "degrees=(90, 0, -45)" in repr(rotation)


def test_xyz_euler_quaternion_round_trip_preserves_angles():
    rotation = EulerRotation(0.2, -0.4, 0.6)
    round_trip = rotation.to_quaternion().to_euler()
    assert all(math.isclose(actual, expected, abs_tol=1e-12) for actual, expected in zip(round_trip, rotation))


def _quaternions_represent_the_same_rotation(a, b, tolerance=1e-9):
    # 四元数の二重被覆(q と -q は同じ回転)を考慮した近似比較。
    return math.isclose(abs(a.dot(b)), 1.0, abs_tol=tolerance)


def test_euler_quaternion_round_trip_all_rotation_orders():
    orders = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")
    angle_sets = (
        (0.2, -0.4, 0.6),
        (1.1, 0.3, -2.5),
        (-3.0, 2.8, 0.05),
        (0.0, 0.0, 0.0),
    )
    for order in orders:
        for angles in angle_sets:
            rotation = EulerRotation(*angles, order)
            quaternion = rotation.to_quaternion()
            round_trip = quaternion.to_euler(order)
            # order は om2 の番号(int)。名前は order_name で取得する。
            assert round_trip.order_name == order
            assert round_trip.order == ORDER_NAMES.index(order)
            assert _quaternions_represent_the_same_rotation(quaternion, round_trip.to_quaternion())


def test_euler_quaternion_round_trip_at_gimbal_lock():
    # 各回転順序で中間軸が正負それぞれ90度(ジンバルロック)になる姿勢を確認する。
    orders_and_middle_axis = (("xyz", 1), ("yzx", 2), ("zxy", 0), ("xzy", 2), ("yxz", 0), ("zyx", 1))
    for order, middle_axis in orders_and_middle_axis:
        for sign in (1.0, -1.0):
            angles = [0.7, -1.2, 2.1]
            angles[middle_axis] = sign * math.pi / 2.0
            rotation = EulerRotation(*angles, order)
            quaternion = rotation.to_quaternion()
            round_trip = quaternion.to_euler(order)
            assert _quaternions_represent_the_same_rotation(quaternion, round_trip.to_quaternion())


def test_quaternion_to_euler_rejects_unsupported_order():
    try:
        Quaternion().to_euler("abc")
    except ValueError:
        pass
    else:
        raise AssertionError("to_euler with an unsupported order should raise ValueError")


def test_euler_rotation_to_quaternion_matches_maya_rotate_order():
    orders = {
        "xyz": om2.MEulerRotation.kXYZ, "yzx": om2.MEulerRotation.kYZX, "zxy": om2.MEulerRotation.kZXY,
        "xzy": om2.MEulerRotation.kXZY, "yxz": om2.MEulerRotation.kYXZ, "zyx": om2.MEulerRotation.kZYX,
    }
    angles = (0.3, -0.5, 0.9)
    for order, om2_order in orders.items():
        # 名前と om2 の番号は同じ回転順序を表す。
        assert EulerRotation(*angles, order) == EulerRotation(*angles, om2_order)
        rotation = EulerRotation(*angles, order)
        quaternion = rotation.to_quaternion()
        expected = om2.MEulerRotation(*angles, om2_order).asQuaternion()
        assert quaternion.isEquivalent(expected, 1e-12)
        # to_euler は om2 の分解を使うため、角度の枝ではなく回転そのもので比較する。
        round_trip = quaternion.to_euler(order)
        assert round_trip.order == om2_order
        assert round_trip.asMatrix().isEquivalent(expected.asMatrix(), 1e-12)


def test_euler_rotation_from_degrees():
    rotation = EulerRotation.from_degrees(90.0, 0.0, -45.0)
    assert isinstance(rotation, EulerRotation)
    assert rotation.as_degrees() == (90.0, 0.0, -45.0)
    assert math.isclose(rotation.x, math.pi / 2.0)


def test_quaternion_dot_length_conjugate_and_inverse():
    identity = Quaternion()
    assert identity.dot(identity) == 1.0
    assert identity.length() == 1.0

    q = Quaternion(0.0, 0.0, math.sin(math.pi / 4.0), math.cos(math.pi / 4.0))
    conjugate = q.conjugate()
    assert tuple(conjugate) == (-q.x, -q.y, -q.z, q.w)

    inverse = q.inverse()
    product = q * inverse
    assert math.isclose(product.w, 1.0, abs_tol=1e-12)
    assert all(math.isclose(value, 0.0, abs_tol=1e-12) for value in (product.x, product.y, product.z))


def test_quaternion_rotate_vector_matches_euler_rotation():
    rotation = EulerRotation.from_degrees(0.0, 90.0, 0.0)
    quaternion = rotation.to_quaternion()
    rotated = quaternion.rotate_vector(Vector(1.0, 0.0, 0.0))
    assert math.isclose(rotated.x, 0.0, abs_tol=1e-12)
    assert math.isclose(rotated.y, 0.0, abs_tol=1e-12)
    assert math.isclose(rotated.z, -1.0, abs_tol=1e-12)


def test_quaternion_angle_to_and_slerp():
    identity = Quaternion()
    ninety = EulerRotation.from_degrees(0.0, 90.0, 0.0).to_quaternion()
    assert math.isclose(identity.angle_to(ninety), math.pi / 2.0, abs_tol=1e-9)
    assert math.isclose(identity.angle_to(identity), 0.0, abs_tol=1e-12)

    halfway = identity.slerp(ninety, 0.5)
    forty_five = EulerRotation.from_degrees(0.0, 45.0, 0.0).to_quaternion()
    assert math.isclose(halfway.angle_to(forty_five), 0.0, abs_tol=1e-9)
    assert tuple(identity.slerp(ninety, 0.0)) == tuple(identity)


def test_quaternion_axis_angle_round_trip():
    axis = Vector(0.0, 1.0, 0.0)
    quaternion = Quaternion.from_axis_angle(axis, math.pi / 2.0)
    recovered_axis, recovered_angle = quaternion.to_axis_angle()
    assert math.isclose(recovered_angle, math.pi / 2.0, abs_tol=1e-9)
    assert recovered_axis.is_equivalent(axis, tolerance=1e-9)


def test_quaternion_swing_twist_recomposes_and_isolates_twist_axis():
    axis = Vector(1.0, 0.0, 0.0)

    # 捻りのみ(axis周りの回転)なら swing は単位四元数になる。
    pure_twist = Quaternion.from_axis_angle(axis, math.radians(40.0))
    swing, twist = pure_twist.to_swing_twist(axis)
    assert swing.angle_to(Quaternion()) < 1e-9
    assert twist.angle_to(pure_twist) < 1e-9

    # 曲げのみ(axisに直交する回転)なら twist は単位四元数になる。
    pure_swing = Quaternion.from_axis_angle(Vector(0.0, 1.0, 0.0), math.radians(65.0))
    swing, twist = pure_swing.to_swing_twist(axis)
    assert twist.angle_to(Quaternion()) < 1e-9
    assert swing.angle_to(pure_swing) < 1e-9

    # 任意姿勢でも、om2 の積の順序(左を先に適用)で twist * swing が元の回転を
    # 再現し、twist は axis 周りのみ。
    mixed = Quaternion.from_axis_angle(Vector(0.3, 0.6, -0.2), math.radians(133.0))
    swing, twist = mixed.to_swing_twist(axis)
    recomposed = twist * swing
    assert recomposed.isEquivalent(mixed, 1e-12)
    assert recomposed.angle_to(mixed) < 1e-9
    assert twist.rotate_vector(axis).is_equivalent(axis, tolerance=1e-9)
    assert swing.rotate_vector(axis).is_equivalent(mixed.rotate_vector(axis), tolerance=1e-9)


def test_matrix_exposes_translation_scale_and_shear_values():
    m = Matrix(
        translate=(1.0, 2.0, 3.0),
        scale=(2.0, 3.0, 4.0),
        shear=(0.1, 0.2, 0.3),
    )
    assert isinstance(m.translate, Translation)
    assert isinstance(m.rotation, EulerRotation)
    assert isinstance(m.rotation, EulerRotation)
    assert isinstance(m.euler, EulerRotation)
    assert isinstance(m.quaternion, Quaternion)
    assert isinstance(m.scale, Scale)
    assert isinstance(m.shear, Shear)
    assert tuple(m.translate) == (1.0, 2.0, 3.0)
    assert all(math.isclose(value, 0.0, abs_tol=1e-12) for value in m.rotation)
    assert all(math.isclose(actual, expected) for actual, expected in zip(m.scale, (2.0, 3.0, 4.0)))
    assert all(math.isclose(actual, expected) for actual, expected in zip(m.shear, (0.1, 0.2, 0.3)))


def test_matrix_is_a_real_4x4_value_with_point_and_vector_transforms():
    matrix = Matrix(translate=(10.0, 20.0, 30.0), scale=(2.0, 3.0, 4.0))
    assert len(matrix) == 16
    assert matrix[3, 3] == 1.0
    assert tuple(matrix.transform_point(Vector(1.0, 1.0, 1.0))) == (12.0, 23.0, 34.0)
    assert tuple(matrix.transform_vector(Vector(1.0, 1.0, 1.0))) == (2.0, 3.0, 4.0)


def test_matrix_multiply_inverse_and_transpose():
    matrix = Matrix(translate=(5.0, -2.0, 1.0), scale=(2.0, 3.0, 4.0))
    identity = matrix * matrix.inverse()
    assert all(math.isclose(identity[index], 1.0 if index in (0, 5, 10, 15) else 0.0) for index in range(16))
    assert matrix.transpose()[3, 0] == matrix[0, 3]


def test_matrix_decompose_round_trip_preserves_trs_and_shear():
    original = Matrix(
        translate=(1.0, 2.0, 3.0),
        rotate=(0.2, -0.4, 0.6),
        scale=(2.0, 3.0, 4.0),
        shear=(0.1, 0.2, 0.3),
    )
    components = original.decompose()
    rebuilt = Matrix.compose(
        translate=components["translate"],
        rotate=components["quaternion"],
        scale=components["scale"],
        shear=components["shear"],
    )
    assert all(math.isclose(actual, expected, abs_tol=1e-8) for actual, expected in zip(rebuilt, original))


def test_matrix_identity():
    identity = Matrix.identity()
    assert isinstance(identity, Matrix)
    assert tuple(identity) == tuple(Matrix())
    assert all(identity[index] == (1.0 if index in (0, 5, 10, 15) else 0.0) for index in range(16))


def test_matrix_determinant():
    assert Matrix.identity().determinant() == 1.0
    assert math.isclose(Matrix(scale=(2.0, 3.0, 4.0)).determinant(), 24.0)
    # 平行移動は行列式に影響しない。
    assert math.isclose(Matrix(translate=(5.0, -2.0, 1.0), scale=(2.0, 3.0, 4.0)).determinant(), 24.0)
    # X軸を反転(負スケール)すると行列式の符号が反転する。
    assert math.isclose(Matrix(scale=(-2.0, 3.0, 4.0)).determinant(), -24.0)


def test_matrix_is_equivalent():
    a = Matrix(translate=(1.0, 2.0, 3.0))
    b = Matrix(translate=(1.0 + 1e-12, 2.0, 3.0))
    assert a.is_equivalent(b)
    assert a != b
    assert not a.is_equivalent(Matrix(translate=(1.1, 2.0, 3.0)))
    assert a.is_equivalent(Matrix(translate=(1.0009, 2.0, 3.0)), tolerance=1e-3)


def test_matrix_matmul_operator_matches_mul():
    a = Matrix(translate=(1.0, 2.0, 3.0))
    b = Matrix(scale=(2.0, 2.0, 2.0))
    assert tuple(a @ b) == tuple(a * b)
    assert type(a @ b) is Matrix
    # ベクトルとの積は om2 の意味論に従う。@ は行列同士だけ。
    _assert_raises(TypeError, lambda: a @ Vector(1.0, 1.0, 1.0))


def test_matrix_vector_products_follow_om2():
    rotate_z = Matrix(translate=(10.0, 0.0, 0.0), rotate=(0.0, 0.0, math.radians(90.0)))
    x_axis = Vector(1.0, 0.0, 0.0)
    # v * m: 行ベクトル規約の方向変換(平行移動を含まない)。
    row = x_axis * rotate_z
    assert type(row) is Vector
    assert row.is_equivalent(Vector(0.0, 1.0, 0.0), tolerance=1e-12)
    assert row == rotate_z.transform_vector(x_axis)
    # m * v: om2 と同じく列ベクトルとしての積(v * mᵀ)。
    column = rotate_z * x_axis
    assert type(column) is Vector
    assert column.is_equivalent(Vector(0.0, -1.0, 0.0), tolerance=1e-12)
    assert column == om2.MMatrix(rotate_z) * om2.MVector(x_axis)
    assert column.is_equivalent(x_axis * rotate_z.transpose(), tolerance=1e-12)
    # 位置は transform_point か MPoint との積で変換する。
    point = rotate_z.transform_point(x_axis)
    assert type(point) is Translation
    assert point.is_equivalent(Vector(10.0, 1.0, 0.0), tolerance=1e-12)
    assert (om2.MPoint(x_axis) * rotate_z).isEquivalent(om2.MPoint(point), 1e-12)
    # in-place の *= は自身を行ベクトル規約で変換し、型を保つ。
    moved = Translation(1.0, 0.0, 0.0)
    alias = moved
    moved *= rotate_z
    assert moved is alias and type(moved) is Translation
    assert moved.is_equivalent(Vector(0.0, 1.0, 0.0), tolerance=1e-12)


def test_matrix_mmatrix_and_transformation_bridge():
    import maya.api.OpenMaya as om2

    matrix = Matrix(translate=(1.0, 2.0, 3.0), scale=(2.0, 3.0, 4.0))

    mmatrix = matrix.to_mmatrix()
    assert isinstance(mmatrix, om2.MMatrix)
    assert tuple(mmatrix) == tuple(matrix)

    round_tripped = Matrix.from_mmatrix(mmatrix)
    assert round_tripped == matrix

    transformation = matrix.to_transformation()
    assert isinstance(transformation, om2.MTransformationMatrix)

    from_transformation = Matrix.from_transformation(transformation)
    assert from_transformation.is_equivalent(matrix, tolerance=1e-9)


def test_matrix_values_and_rows_accessors():
    matrix = Matrix(translate=(1.0, 2.0, 3.0))
    assert matrix.values == tuple(matrix)
    rows = matrix.rows
    assert len(rows) == 4
    assert all(len(row) == 4 for row in rows)
    assert rows[3] == (1.0, 2.0, 3.0, 1.0)


def test_matrix_mirrored_is_a_180_degree_behavior_mirror():
    # 単位行列をX軸でミラーすると、X軸周りに180度回転した姿勢になる
    # (Maya の mirrorJoint -mirrorBehavior と同じ規約。行列式の符号は保存される)。
    mirrored_identity = Matrix.identity().mirrored(axis=0)
    assert mirrored_identity.rows == (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, -1.0, 0.0, 0.0),
        (0.0, 0.0, -1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    assert math.isclose(mirrored_identity.determinant(), 1.0)

    # 平行移動はミラーした軸成分だけが反転する。
    translate_only = Matrix(translate=(1.0, 2.0, 3.0))
    assert tuple(translate_only.mirrored(axis=0).translate) == (-1.0, 2.0, 3.0)
    assert tuple(translate_only.mirrored(axis=1).translate) == (1.0, -2.0, 3.0)
    assert tuple(translate_only.mirrored(axis=2).translate) == (1.0, 2.0, -3.0)

    # 回転を含む行列でも行列式の符号(=固有ハンド性)は変わらない。
    rotated = Matrix(translate=(1.0, 2.0, 3.0), rotate=(0.3, -0.6, 1.1))
    for axis in (0, 1, 2):
        mirrored = rotated.mirrored(axis=axis)
        assert math.isclose(mirrored.determinant(), rotated.determinant(), abs_tol=1e-9)
        # ミラーは対合(involution): 同じ軸で2回適用すると元に戻る。
        assert mirrored.mirrored(axis=axis).is_equivalent(rotated, tolerance=1e-9)

    try:
        Matrix.identity().mirrored(axis=3)
    except ValueError:
        pass
    else:
        raise AssertionError("mirrored with an invalid axis should raise ValueError")


def test_vector_from_iterable():
    v = Vector.from_iterable([1.0, 2.0, 3.0])
    assert isinstance(v, Vector)
    assert tuple(v) == (1.0, 2.0, 3.0)

    try:
        Vector.from_iterable([1.0, 2.0])
    except ValueError:
        pass
    else:
        raise AssertionError("from_iterable with wrong length should raise ValueError")


def _assert_raises(exception, function):
    """function() が exception を送出することを確認する。"""
    try:
        function()
    except exception:
        return
    raise AssertionError("{} was not raised".format(exception.__name__))


def _samples():
    """om2 を継承した各型の代表値を返す。"""
    return [
        Vector(1.0, 2.0, 3.0),
        Translation(1.0, -2.0, 3.5),
        Scale(2.0, 3.0, 4.0),
        Shear(0.1, 0.2, 0.3),
        Quaternion(0.1, 0.2, 0.3, 0.9),
        EulerRotation(0.1, 0.2, 0.3, "zyx"),
        Matrix(translate=(1.0, 2.0, 3.0), rotate=(0.1, 0.2, 0.3), scale=(1.0, 2.0, 3.0)),
    ]


def test_types_inherit_om2_and_are_accepted_by_om2_functions():
    assert isinstance(Vector(), om2.MVector)
    assert isinstance(Translation(), om2.MVector)
    assert isinstance(Quaternion(), om2.MQuaternion)
    assert isinstance(EulerRotation(), om2.MEulerRotation)
    assert isinstance(Matrix(), om2.MMatrix)

    matrix = Matrix(translate=(1.0, 2.0, 3.0), rotate=EulerRotation(0.3, -0.5, 0.9, "zyx"), scale=(2.0, 3.0, 4.0))
    transformation = om2.MTransformationMatrix(matrix)
    assert transformation.asMatrix().isEquivalent(matrix, 1e-12)
    assert transformation.translation(om2.MSpace.kTransform) == om2.MVector(1.0, 2.0, 3.0)
    data = om2.MFnMatrixData().create(matrix)
    assert om2.MFnMatrixData(data).matrix() == matrix
    assert om2.MMatrix(matrix) == matrix

    euler = EulerRotation(0.3, -0.5, 0.9, "zyx")
    assert om2.MEulerRotation(euler).order == om2.MEulerRotation.kZYX
    assert om2.MEulerRotation.decompose(Matrix(rotate=euler), euler.order).asMatrix().isEquivalent(
        euler.asMatrix(), 1e-12)
    quaternion = euler.to_quaternion()
    assert om2.MQuaternion(quaternion) == quaternion
    assert Vector(1.0, 0.0, 0.0).rotateBy(quaternion).isEquivalent(
        Vector(1.0, 0.0, 0.0).rotateBy(euler), 1e-12)
    assert om2.MPoint(Translation(1.0, 2.0, 3.0)) == om2.MPoint(1.0, 2.0, 3.0)
    # om2 の型からの生成(コピーコンストラクタ)も受け付ける。
    assert Vector(om2.MPoint(1.0, 2.0, 3.0)) == Vector(1.0, 2.0, 3.0)
    assert Matrix(om2.MMatrix()) == Matrix()
    assert Quaternion(math.pi / 2.0, Vector(0.0, 1.0, 0.0)).isEquivalent(
        Quaternion.from_axis_angle((0.0, 1.0, 0.0), math.pi / 2.0), 1e-12)


def test_equality_with_foreign_types_never_raises():
    for value in _samples():
        assert (value == None) is False  # noqa: E711
        assert (value != None) is True  # noqa: E711
        assert (None == value) is False  # noqa: E711
        assert (value == "abc") is False
        assert (value != "abc") is True
        assert (value == tuple(value)) is False
        assert value == copy.copy(value)
    # 別系統の om2 型とも例外にせず False。
    assert (Vector(1.0, 2.0, 3.0) == om2.MPoint(1.0, 2.0, 3.0)) is False
    assert (Vector(0.1, 0.2, 0.3) == EulerRotation(0.1, 0.2, 0.3)) is False
    assert (Matrix() == Quaternion()) is False
    # om2 と同じ値の比較で、同じ om2 系統なら派生型が違っても等しくなり得る。
    assert Translation(1.0, 2.0, 3.0) == Scale(1.0, 2.0, 3.0)
    assert Vector(1.0, 2.0, 3.0) == om2.MVector(1.0, 2.0, 3.0)
    assert om2.MVector(1.0, 2.0, 3.0) == Translation(1.0, 2.0, 3.0)
    assert Matrix() == om2.MMatrix() and om2.MMatrix() == Matrix()
    assert Quaternion() == om2.MQuaternion()
    # EulerRotation は回転順序も比較する。
    assert EulerRotation(0.1, 0.2, 0.3, "xyz") != EulerRotation(0.1, 0.2, 0.3, "zyx")


def test_values_are_mutable_and_unhashable():
    for value in _samples():
        _assert_raises(TypeError, lambda: hash(value))
        _assert_raises(TypeError, lambda: {value})

    vector = Vector(1.0, 2.0, 3.0)
    vector.x = 5.0
    vector[2] = 6.0
    assert tuple(vector) == (5.0, 2.0, 6.0)

    quaternion = Quaternion()
    quaternion.w = 2.0
    assert quaternion.length() == 2.0

    euler = EulerRotation(0.1, 0.2, 0.3)
    euler.order_name = "YXZ"
    assert euler.order == om2.MEulerRotation.kYXZ
    euler.order = 5
    assert euler.order_name == "zyx"
    _assert_raises(ValueError, lambda: setattr(euler, "order_name", "abc"))

    matrix = Matrix()
    matrix[3, 0] = 7.0
    matrix[13] = 8.0
    assert tuple(matrix.translate) == (7.0, 8.0, 0.0)
    # 成分のプロパティは複製を返すため、戻り値の書き換えは行列へ影響しない。
    matrix.translate.x = 99.0
    assert matrix[3, 0] == 7.0
    # += は同じオブジェクトを書き換える(別名にも伝わる)。
    alias = vector
    vector += Vector(1.0, 1.0, 1.0)
    assert alias is vector and tuple(alias) == (6.0, 3.0, 7.0)


def test_copy_deepcopy_and_pickle_rebuild_through_constructor():
    duplicators = [copy.copy, copy.deepcopy]
    duplicators.extend(
        (lambda value, protocol=protocol: pickle.loads(pickle.dumps(value, protocol)))
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1)
    )
    for value in _samples():
        for duplicate in duplicators:
            result = duplicate(value)
            assert type(result) is type(value)
            assert result is not value
            assert result == value
            # om2 の C++ 実体が確保されていること(未初期化なら値の読み取りで落ちる)。
            assert list(result) == list(value)
    rotation = pickle.loads(pickle.dumps(EulerRotation(0.1, 0.2, 0.3, "zyx")))
    assert rotation.order_name == "zyx"
    nested = copy.deepcopy({"matrix": Matrix(translate=(1.0, 2.0, 3.0)), "values": [Vector(1.0, 2.0, 3.0)]})
    assert tuple(nested["matrix"].translate) == (1.0, 2.0, 3.0)
    assert type(nested["values"][0]) is Vector


def test_in_place_operators_guard_types_and_keep_subclass():
    def add_list():
        value = Vector(1.0, 2.0, 3.0)
        value += [1.0, 2.0, 3.0]
        return value

    def multiply_matrix_by_string():
        value = Matrix()
        value *= "abc"
        return value

    def multiply_quaternion_by_list():
        value = Quaternion()
        value *= [0.0, 0.0, 0.0, 1.0]
        return value

    def add_list_to_euler():
        value = EulerRotation()
        value += [0.1, 0.2, 0.3]
        return value

    for function in (add_list, multiply_matrix_by_string, multiply_quaternion_by_list, add_list_to_euler):
        _assert_raises(TypeError, function)

    translation = Translation(1.0, 2.0, 3.0)
    original = translation
    translation += Vector(1.0, 1.0, 1.0)
    translation -= om2.MVector(0.5, 0.5, 0.5)
    translation *= 2
    translation /= 4.0
    assert translation is original and type(translation) is Translation
    assert tuple(translation) == (0.75, 1.25, 1.75)

    matrix = Matrix(translate=(1.0, 0.0, 0.0))
    original_matrix = matrix
    matrix *= Matrix(scale=(2.0, 2.0, 2.0))
    assert matrix is original_matrix and type(matrix) is Matrix
    assert tuple(matrix.translate) == (2.0, 0.0, 0.0)

    quaternion = Quaternion()
    original_quaternion = quaternion
    quaternion *= Quaternion.from_axis_angle((0.0, 0.0, 1.0), 0.5)
    assert quaternion is original_quaternion and type(quaternion) is Quaternion

    euler = EulerRotation(0.1, 0.2, 0.3, "zyx")
    original_euler = euler
    euler += EulerRotation(0.1, 0.1, 0.1, "zyx")
    assert euler is original_euler and type(euler) is EulerRotation and euler.order_name == "zyx"


def test_division_by_zero_raises_zero_division_error():
    _assert_raises(ZeroDivisionError, lambda: Vector(1.0, 2.0, 3.0) / 0)
    _assert_raises(ZeroDivisionError, lambda: Vector(1.0, 2.0, 3.0) / 0.0)

    def divide_in_place():
        value = Vector(1.0, 2.0, 3.0)
        value /= 0
        return value

    _assert_raises(ZeroDivisionError, divide_in_place)
    _assert_raises(TypeError, lambda: Vector(1.0, 2.0, 3.0) / Vector(1.0, 1.0, 1.0))


def test_mixed_arithmetic_with_om2_types_returns_hlib_types():
    a = Vector(1.0, 2.0, 3.0)
    b = Vector(-4.0, 5.5, 0.25)
    raw = om2.MVector(1.0, 1.0, 1.0)
    # ベクトル: hlib が片方にあれば結果は基底の Vector。
    for result in (a + raw, raw + a, a - raw, raw - a, Translation(1.0, 2.0, 3.0) + Translation(1.0, 1.0, 1.0),
                   2 * a, a * 2.0, a / 2.0, -Translation(1.0, 2.0, 3.0), a ^ b, a.cross(b), a.lerp(b, 0.5)):
        assert type(result) is Vector
    assert tuple(raw - a) == (0.0, -1.0, -2.0)
    assert a * b == a.dot(b) == 1.0 * -4.0 + 2.0 * 5.5 + 3.0 * 0.25
    assert isinstance(a * b, float)
    assert a ^ b == a.cross(b)
    _assert_raises(TypeError, lambda: a + (1.0, 2.0, 3.0))
    _assert_raises(TypeError, lambda: a + None)
    _assert_raises(TypeError, lambda: a * Quaternion())

    # 行列: hlib の Matrix がどちらにあっても結果は Matrix。
    m = Matrix(translate=(1.0, 2.0, 3.0), rotate=(0.1, 0.2, 0.3))
    raw_matrix = om2.MMatrix(m)
    for result in (m * raw_matrix, raw_matrix * m, m @ raw_matrix, raw_matrix @ m, m * 2.0, 2 * m,
                   m + raw_matrix, raw_matrix + m, m - raw_matrix, m.inverse(), m.transpose()):
        assert type(result) is Matrix
    assert (m * raw_matrix) == (raw_matrix * raw_matrix)
    assert (raw_matrix * m) == (raw_matrix * raw_matrix)
    # om2 の型が左辺でベクトル・点と組む場合は om2 の結果(基底型)。
    assert type(om2.MVector(1.0, 0.0, 0.0) * m) is om2.MVector
    assert type(om2.MPoint(1.0, 0.0, 0.0) * m) is om2.MPoint
    assert type(Vector(1.0, 0.0, 0.0) * raw_matrix) is Vector

    # 四元数・Euler: 結果は hlib の型。
    q = Quaternion.from_axis_angle((0.0, 1.0, 0.0), 0.5)
    raw_q = om2.MQuaternion(q)
    for result in (q * raw_q, raw_q * q, q + raw_q, raw_q + q, q - raw_q, -q, q.conjugate(), q.inverse(),
                   q.normalized(), q.slerp(raw_q, 0.5), Quaternion.slerp(raw_q, q, 0.5)):
        assert type(result) is Quaternion
    e = EulerRotation(0.1, 0.2, 0.3, "zyx")
    raw_e = om2.MEulerRotation(0.1, 0.1, 0.1, om2.MEulerRotation.kZYX)
    for result in (e + raw_e, raw_e + e, e - raw_e, raw_e - e, e * 2.0, 2.0 * e, e * raw_e, raw_e * e, e * q, -e):
        assert type(result) is EulerRotation
    assert (e + raw_e).order_name == "zyx"

    # om2 名(camelCase)のメソッドは om2 の基底型を返す。
    assert type(a.normal()) is om2.MVector
    assert type(q.asMatrix()) is om2.MMatrix
    assert type(q.normal()) is om2.MQuaternion
    assert type(e.reorder(om2.MEulerRotation.kXYZ)) is om2.MEulerRotation
    assert type(e.asQuaternion()) is om2.MQuaternion
    assert type(m.adjoint()) is om2.MMatrix
    assert type(m.to_mmatrix()) is om2.MMatrix


def test_quaternion_product_follows_om2_order():
    first = EulerRotation(0.3, 0.0, 0.0).to_quaternion()
    second = EulerRotation(0.0, 0.7, 0.0).to_quaternion()
    product = first * second
    # q1 * q2 は q1 を先に適用する回転(行列の積と同じ順序)。
    assert product.asMatrix().isEquivalent(first.asMatrix() * second.asMatrix(), 1e-12)
    assert Matrix(rotate=product).is_equivalent(Matrix(rotate=first) * Matrix(rotate=second), 1e-12)
    assert first.to_matrix().is_equivalent(Matrix(rotate=first), 1e-14)
    # Hamilton 積 second ⊗ first に等しい。
    hamilton = Quaternion(
        second.w * first.x + second.x * first.w + second.y * first.z - second.z * first.y,
        second.w * first.y - second.x * first.z + second.y * first.w + second.z * first.x,
        second.w * first.z + second.x * first.y - second.y * first.x + second.z * first.w,
        second.w * first.w - second.x * first.x - second.y * first.y - second.z * first.z,
    )
    assert product.isEquivalent(hamilton, 1e-12)
    # XYZ 順序の Euler は X、Y、Z の順に適用した四元数の積。
    x, y, z = 0.2, -0.4, 0.6
    composed = (EulerRotation(x, 0.0, 0.0).to_quaternion() * EulerRotation(0.0, y, 0.0).to_quaternion()
                * EulerRotation(0.0, 0.0, z).to_quaternion())
    assert composed.isEquivalent(EulerRotation(x, y, z).to_quaternion(), 1e-12)


def test_quaternion_constructor_forms_and_precise_angles():
    assert tuple(Quaternion()) == (0.0, 0.0, 0.0, 1.0)
    assert tuple(Quaternion([0.0, 0.0, 0.0, 2.0])) == (0.0, 0.0, 0.0, 2.0)
    axis_angle = Quaternion(math.pi / 2.0, Vector(0.0, 0.0, 1.0))
    assert axis_angle.rotate_vector((1.0, 0.0, 0.0)).is_equivalent(Vector(0.0, 1.0, 0.0), 1e-12)
    between = Quaternion(Vector(1.0, 0.0, 0.0), Vector(0.0, 1.0, 0.0))
    assert between.isEquivalent(axis_angle, 1e-12)
    assert len(Quaternion()) == 4 and Quaternion(0.1, 0.2, 0.3, 0.4)[3] == 0.4
    _assert_raises(ValueError, lambda: Quaternion(0.0, 0.0, 0.0, 0.0).normalized())
    _assert_raises(ValueError, lambda: Quaternion(0.0, 0.0, 0.0, 0.0).inverse())
    _assert_raises(ValueError, lambda: Quaternion.from_axis_angle((0.0, 0.0, 0.0), 1.0))
    # 角度差は 0 付近でも精度を保つ(acos では 1e-8 程度が限界)。
    tiny = Quaternion.from_axis_angle((0.0, 0.0, 1.0), 1e-10)
    assert math.isclose(Quaternion().angle_to(tiny), 1e-10, rel_tol=1e-6)
    assert math.isclose(Vector(1.0, 0.0, 0.0).angle_to(Vector(1.0, 1e-9, 0.0)), 1e-9, rel_tol=1e-6)
    axis, angle = tiny.to_axis_angle()
    assert math.isclose(angle, 1e-10, rel_tol=1e-6) and axis.is_equivalent(Vector(0.0, 0.0, 1.0), 1e-9)


def test_euler_rotation_constructor_forms_and_order():
    assert tuple(EulerRotation()) == (0.0, 0.0, 0.0) and EulerRotation().order_name == "xyz"
    assert EulerRotation(0.1, 0.2, 0.3, "ZYX").order == om2.MEulerRotation.kZYX
    assert EulerRotation(0.1, 0.2, 0.3, order="zxy").order_name == "zxy"
    assert EulerRotation(0.1, 0.2, 0.3, 4).order_name == "yxz"
    assert tuple(EulerRotation([0.1, 0.2, 0.3])) == (0.1, 0.2, 0.3)
    assert EulerRotation((0.1, 0.2, 0.3), "yzx").order_name == "yzx"
    assert EulerRotation(Vector(0.1, 0.2, 0.3), order="xzy").order_name == "xzy"
    source = EulerRotation(0.1, 0.2, 0.3, "zyx")
    duplicate = EulerRotation(source)
    assert duplicate == source and duplicate is not source and duplicate.order_name == "zyx"
    assert EulerRotation(om2.MEulerRotation(0.1, 0.2, 0.3, 5)).order_name == "zyx"
    assert EulerRotation.from_iterable((0.1, 0.2, 0.3), "zyx") == source
    _assert_raises(ValueError, lambda: EulerRotation(0.0, 0.0, 0.0, "abc"))
    _assert_raises(ValueError, lambda: EulerRotation(0.0, 0.0, 0.0, 6))
    _assert_raises(ValueError, lambda: EulerRotation(0.0, 0.0, 0.0, True))
    _assert_raises(TypeError, lambda: EulerRotation(0.0, 0.0, 0.0, "xyz", order="zyx"))
    _assert_raises(TypeError, lambda: EulerRotation(0.0, 0.0))
    _assert_raises(TypeError, lambda: EulerRotation(0.0, 0.0, 0.0, unknown=1))
    assert repr(EulerRotation.from_degrees(90.0, 0.0, -45.0, "zyx")) == "EulerRotation(degrees=(90, 0, -45), order='zyx')"
    assert len(list(source)) == 3
    assert source.is_equivalent(EulerRotation(0.1, 0.2, 0.3 + 1e-12, "zyx"))
    assert not source.is_equivalent(EulerRotation(0.1, 0.2, 0.3, "xyz"))
    assert source.to_matrix().is_equivalent(Matrix(rotate=source), 1e-15)


def test_matrix_compose_honours_euler_order_and_keeps_zero_scale():
    euler = EulerRotation(0.3, -0.5, 0.9, "zyx")
    expected = om2.MEulerRotation(0.3, -0.5, 0.9, om2.MEulerRotation.kZYX).asMatrix()
    assert Matrix(rotate=euler).is_equivalent(expected, 1e-12)
    # 3成分は従来どおり XYZ 順序。
    assert Matrix(rotate=(0.3, -0.5, 0.9)).is_equivalent(om2.MEulerRotation(0.3, -0.5, 0.9).asMatrix(), 1e-12)
    matrix = Matrix(translate=(1.0, 2.0, 3.0), scale=(2.0, 2.0, 2.0))
    matrix.rotation = euler
    assert tuple(matrix.translate) == (1.0, 2.0, 3.0)
    assert matrix.scale.is_equivalent(Vector(2.0, 2.0, 2.0), 1e-12)
    assert matrix.quaternion.isEquivalent(euler.to_quaternion(), 1e-12)
    matrix.rotate = Quaternion()
    assert matrix.rotation.is_equivalent(EulerRotation(), 1e-12)
    # ゼロや微小なスケールは MTransformationMatrix のように 1e-12 へ丸めない。
    assert Matrix(scale=(0.0, 1.0, 1.0))[0, 0] == 0.0
    assert Matrix(scale=(1e-13, 1.0, 1.0))[0, 0] == 1e-13
    flat = Matrix([0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 2.0, 3.0, 1.0])
    _assert_raises(ValueError, lambda: flat.scale)
    _assert_raises(ValueError, lambda: flat.decompose())
    flat.translate = (7.0, 8.0, 9.0)
    assert tuple(flat.translate) == (7.0, 8.0, 9.0)
    # 不正な入力は ValueError(失敗時に自身は変わらない)。
    _assert_raises(ValueError, lambda: Matrix((1.0, 2.0, 3.0)))
    _assert_raises(ValueError, lambda: Matrix(5))
    _assert_raises(ValueError, lambda: Matrix(rotate=Quaternion(0.0, 0.0, 0.0, 0.0)))
    unchanged = Matrix(translate=(1.0, 2.0, 3.0))
    before = tuple(unchanged)

    def set_zero_quaternion():
        unchanged.rotation = Quaternion(0.0, 0.0, 0.0, 0.0)

    _assert_raises(ValueError, set_zero_quaternion)
    assert tuple(unchanged) == before
    # 16要素・4x4・生成器を受け付ける。要素は om2 と同じく数値だけ(文字列は ValueError)。
    assert Matrix(float(i) for i in range(16))[5] == 5.0
    assert Matrix([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [1, 2, 3, 1]])[3, 1] == 2.0
    assert Matrix(((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (1, 2, 3, 1)))[3, 2] == 3.0
    _assert_raises(ValueError, lambda: Matrix(["1", "0", "0", "0", "0", "1", "0", "0",
                                               "0", "0", "1", "0", "4", "5", "6", "1"]))
    _assert_raises(ValueError, lambda: Matrix([["1", 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]))


def test_matrix_inverse_rejects_only_singular_matrices():
    singular = Matrix([1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 2.0, 3.0, 1.0])
    _assert_raises(ValueError, singular.inverse)
    tiny = Matrix(scale=(1e-13, 1.0, 1.0))
    assert math.isclose(tiny.inverse()[0, 0], 1e13)
    matrix = Matrix(translate=(1.0, 2.0, 3.0), rotate=(0.3, 0.2, 0.1), scale=(2.0, 3.0, 4.0))
    assert (matrix * matrix.inverse()).is_equivalent(Matrix.identity(), 1e-12)


def test_matrix_negative_determinant_decomposes_like_transformation_matrix():
    matrix = Matrix(translate=(1.0, 2.0, 3.0), rotate=(0.3, -0.2, 0.5), scale=(-2.0, 3.0, 4.0), shear=(0.1, 0.0, 0.2))
    parts = matrix.decompose()
    transformation = om2.MTransformationMatrix(matrix)
    # om2 と同じく Z スケールを負にし、回転側で 180 度を補う。
    assert parts["scale"].is_equivalent(Vector(*transformation.scale(om2.MSpace.kTransform)), 1e-12)
    assert parts["scale"].z < 0.0 and parts["scale"].x > 0.0
    assert parts["quaternion"].isEquivalent(transformation.rotation(asQuaternion=True), 1e-12)
    assert parts["euler"].isEquivalent(transformation.rotation(), 1e-12)
    assert parts["rotation"] == parts["euler"] and parts["rotation"] is not parts["euler"]
    rebuilt = Matrix.compose(parts["translate"], parts["quaternion"], parts["scale"], parts["shear"])
    assert rebuilt.is_equivalent(matrix, 1e-12)
    # setter も同じ規約で再合成し、行列そのものは変わらない。
    edited = Matrix(matrix)
    edited.shear = parts["shear"]
    assert edited.is_equivalent(matrix, 1e-12)


def test_matrix_indexing_and_iteration():
    matrix = Matrix(translate=(1.0, 2.0, 3.0))
    assert matrix[3, 1] == 2.0 and matrix[-1, 0] == 1.0 and matrix[-1] == 1.0
    assert matrix[12:15] == (1.0, 2.0, 3.0)
    assert list(matrix) == list(om2.MMatrix(matrix))
    _assert_raises(IndexError, lambda: matrix[4, 0])
    _assert_raises(IndexError, lambda: matrix[16])
    matrix[0, 1] = 0.5
    assert matrix.getElement(0, 1) == 0.5


def test_matrix_flat_index_is_range_checked_before_reaching_om2():
    # om2 の MMatrix は添字を検査しない。Python は負の添字に16を1回だけ足すため、
    # -17 以下がそのまま届くと範囲外のメモリを読み書きする。hlib 側で必ず拒否する。
    matrix = Matrix(list(range(16)))
    for index in range(-16, 16):
        assert matrix[index] == float(index % 16)
    before = list(matrix)
    for index in (-17, -100, 16, 100):
        _assert_raises(IndexError, lambda index=index: matrix[index])

        def assign(index=index):
            matrix[index] = 99.0

        _assert_raises(IndexError, assign)
    assert list(matrix) == before
    _assert_raises(TypeError, lambda: matrix[1.5])
    _assert_raises(TypeError, lambda: matrix[1.5, 0])
    _assert_raises(IndexError, lambda: matrix[0, -5])
    matrix[-1] = 42.0
    assert matrix[15] == 42.0


def test_matrix_results_keep_non_finite_values_per_element():
    # 演算結果の包み直しで inf / NaN が他の要素へ広がらないこと(om2 の結果と同じ)。
    inf = float("inf")
    source = Matrix([inf, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0])
    raw = om2.MMatrix(source)
    for actual, expected in (
        (source.transpose(), raw.transpose()),
        (source * 2.0, raw * 2.0),
        (2.0 * source, raw * 2.0),
        (source + Matrix(), raw + om2.MMatrix()),
        (source - Matrix(), raw - om2.MMatrix()),
    ):
        assert type(actual) is Matrix
        for a, b in zip(actual, expected):
            assert a == b or (math.isnan(a) and math.isnan(b)), (list(actual), list(expected))


def test_quaternion_scalar_multiplication_follows_om2():
    q = Quaternion(0.1, 0.2, 0.3, 0.9)
    scaled = 2 * q
    assert type(scaled) is Quaternion
    assert list(scaled) == list(2 * om2.MQuaternion(q))
    assert list(2.5 * q) == list(2.5 * om2.MQuaternion(q))
    # om2 と同じく右からの数値倍・除算は未対応。
    _assert_raises(TypeError, lambda: q * 2)
    _assert_raises(TypeError, lambda: q / 2)


def test_euler_rotation_division_by_number_keeps_order():
    rotation = EulerRotation(0.2, 0.4, 0.6, "zxy")
    half = rotation / 2
    assert type(half) is EulerRotation and half.order_name == "zxy"
    assert tuple(half) == (0.1, 0.2, 0.3)
    original = rotation
    rotation /= 4.0
    assert rotation is original and rotation.order_name == "zxy"
    assert tuple(rotation) == (0.05, 0.1, 0.15)
    _assert_raises(ZeroDivisionError, lambda: rotation / 0)
    _assert_raises(TypeError, lambda: rotation / EulerRotation())


def test_user_subclass_attributes_survive_copy_and_pickle():
    # __slots__ を持たない利用者の派生クラスの属性(__dict__)も複製・pickle で保たれる。
    classes = []
    for base, args in ((Translation, (1.0, 2.0, 3.0)), (Quaternion, (0.0, 0.0, 0.0, 1.0)),
                       (EulerRotation, (0.1, 0.2, 0.3, "yxz")), (Matrix, (list(range(16)),))):
        name = "UserSubclass" + base.__name__
        cls = type(name, (base,), {"__module__": PACKAGE_NAME})
        cls.__qualname__ = name
        setattr(package, name, cls)
        classes.append((cls, args))
    for cls, args in classes:
        value = cls(*args)
        value.tag = ["tag"]
        duplicates = [copy.copy(value), copy.deepcopy(value)]
        duplicates.extend(pickle.loads(pickle.dumps(value, protocol))
                          for protocol in range(pickle.HIGHEST_PROTOCOL + 1))
        for duplicate in duplicates:
            assert type(duplicate) is cls and duplicate == value and duplicate.tag == ["tag"]
        assert duplicates[0].tag is value.tag
        assert duplicates[1].tag is not value.tag
        shared = copy.deepcopy([value, value])
        assert shared[0] is shared[1]
    # hlib 自身の型は __dict__ を持たず、state を付けない。
    assert len(Translation(1.0, 2.0, 3.0).__reduce_ex__(2)) == 2


def _register_user_class(name, bases, namespace):
    """pickle できるよう、テスト用パッケージに利用者の派生クラスを登録する。"""
    namespace = dict(namespace, __module__=PACKAGE_NAME)
    cls = type(name, bases, namespace)
    cls.__qualname__ = name
    setattr(package, name, cls)
    return cls


def test_component_indices_are_range_checked_and_accept_slices():
    # om2 の型は負の範囲外の添字(v[-4] など)でも最後の成分を読み書きする。hlib は検査する。
    for value, size in ((Vector(1.0, 2.0, 3.0), 3), (Translation(1.0, 2.0, 3.0), 3),
                        (Quaternion(0.1, 0.2, 0.3, 0.9), 4), (EulerRotation(0.1, 0.2, 0.3, "zyx"), 3)):
        components = tuple(value)
        for index in range(-size, size):
            assert value[index] == components[index]
        for index in (-size - 1, -1000, size, 1000):
            _assert_raises(IndexError, lambda index=index: value[index])

            def assign(index=index):
                value[index] = 99.0

            _assert_raises(IndexError, assign)
        assert tuple(value) == components
        _assert_raises(TypeError, lambda: value[1.0])
        assert value[0:2] == components[0:2] and value[::-1] == components[::-1]
        value[-1] = 7.0
        assert value[size - 1] == 7.0
    _assert_raises(TypeError, lambda: Vector().__setitem__(slice(0, 2), (1.0, 2.0)))


def test_constructors_accept_keywords_and_reject_non_numbers():
    assert tuple(Vector(x=1.0, z=3.0)) == (1.0, 0.0, 3.0)
    assert tuple(Translation(1.0, y=2.0)) == (1.0, 2.0, 0.0)
    assert tuple(Quaternion(w=0.5)) == (0.0, 0.0, 0.0, 0.5)
    rotation = EulerRotation(x=0.1, z=0.3, order="zyx")
    assert tuple(rotation) == (0.1, 0.0, 0.3) and rotation.order_name == "zyx"
    _assert_raises(TypeError, lambda: Vector(1.0, x=2.0))
    _assert_raises(TypeError, lambda: Vector(w=1.0))
    _assert_raises(TypeError, lambda: Quaternion(v=1.0))
    # om2 と同じく成分は数値だけ(以前の dataclass 版は float() で文字列も受け付けた)。
    for function in (lambda: Vector("1", "2", "3"), lambda: Vector(["1", "2", "3"]),
                     lambda: Quaternion("0", "0", "0", "1"), lambda: EulerRotation("1", 2.0, 3.0),
                     lambda: Vector(1.0, 2.0, 3.0, 4.0)):
        _assert_raises(ValueError, function)
    # om2 の他の形はそのまま使える。
    assert tuple(Vector((1, 2))) == (1.0, 2.0, 0.0)
    assert Vector(om2.MFloatVector(1.0, 2.0, 3.0)) == Vector(1.0, 2.0, 3.0)
    # __init__ を呼び直すと値を設定し直す(om2 と同じ)。
    vector = Vector(1.0, 2.0, 3.0)
    vector.__init__()
    assert tuple(vector) == (0.0, 0.0, 0.0)
    rotation.__init__(0.2, 0.3, 0.4)
    assert tuple(rotation) == (0.2, 0.3, 0.4) and rotation.order_name == "xyz"
    matrix = Matrix(translate=(1.0, 2.0, 3.0))
    matrix.__init__()
    assert matrix == Matrix()


def test_instances_created_without_init_are_usable():
    # om2 は C++ の実体を __init__ で確保するため、__new__ だけの om2 の型はアクセス時に
    # Maya ごと落ちる。hlib の型は __new__ で確保するので落ちない(落ちればこのテストごと失敗する)。
    assert tuple(Vector.__new__(Vector)) == (0.0, 0.0, 0.0)
    assert repr(Translation.__new__(Translation)) == "Translation(0.0, 0.0, 0.0)"
    assert tuple(Quaternion.__new__(Quaternion)) == (0.0, 0.0, 0.0, 1.0)
    assert EulerRotation.__new__(EulerRotation).order == 0
    assert Matrix.__new__(Matrix) == Matrix()

    class SwallowingEuler(EulerRotation):
        def __init__(self, *args):
            try:
                super().__init__(*args)
            except ValueError:
                pass

    class SwallowingMatrix(Matrix):
        def __init__(self, *args):
            try:
                super().__init__(*args)
            except ValueError:
                pass

    class NoSuperVector(Vector):
        def __init__(self, *args):
            pass

    assert tuple(SwallowingEuler(0.0, 0.0, 0.0, "bad")) == (0.0, 0.0, 0.0)
    assert SwallowingMatrix((1.0, 2.0)) == Matrix()
    assert tuple(NoSuperVector(1.0, 2.0, 3.0)) == (0.0, 0.0, 0.0)


def test_in_place_operators_missing_from_om2_keep_the_object():
    # om2 の MQuaternion には += / -= が、MVector には ^= が、MMatrix には @= が無い。
    # hlib では同じオブジェクトを書き換えて型を保つ。
    user_quaternion = _register_user_class("UserQuaternionInPlace", (Quaternion,), {})
    quaternion = user_quaternion(0.1, 0.2, 0.3, 0.9)
    alias = quaternion
    quaternion += Quaternion(1.0, 0.0, 0.0, 0.0)
    quaternion -= om2.MQuaternion(0.0, 1.0, 0.0, 0.0)
    assert quaternion is alias and type(quaternion) is user_quaternion
    assert list(quaternion) == list(om2.MQuaternion(0.1, 0.2, 0.3, 0.9) + om2.MQuaternion(1.0, 0.0, 0.0, 0.0)
                                    - om2.MQuaternion(0.0, 1.0, 0.0, 0.0))

    translation = Translation(1.0, 0.0, 0.0)
    alias = translation
    translation ^= Vector(0.0, 1.0, 0.0)
    assert translation is alias and type(translation) is Translation
    assert tuple(translation) == (0.0, 0.0, 1.0)

    matrix = Matrix(translate=(1.0, 0.0, 0.0))
    alias = matrix
    matrix @= Matrix(scale=(2.0, 2.0, 2.0))
    assert matrix is alias and tuple(matrix.translate) == (2.0, 0.0, 0.0)

    def xor_list():
        value = Vector(1.0, 0.0, 0.0)
        value ^= [0.0, 1.0, 0.0]
        return value

    def add_list_to_quaternion():
        value = Quaternion()
        value += [0.0, 0.0, 0.0, 1.0]
        return value

    def matmul_vector():
        value = Matrix()
        value @= Vector(1.0, 0.0, 0.0)
        return value

    for function in (xor_list, add_list_to_quaternion, matmul_vector):
        _assert_raises(TypeError, function)


def test_equality_with_unrelated_types_defers_to_the_other_operand():
    class AlwaysEqual(object):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    anything = AlwaysEqual()
    for value in _samples():
        # om2 系統外の値は相手の比較に委ねる(左右どちらでも同じ結果)。
        assert (value == anything) is True and (anything == value) is True
        assert (value != anything) is False and (anything != value) is False
        # om2 の型(API 1.0 を含む)は om2 側が TypeError を送出するため、hlib 側で確定させる。
        assert (value == om2.MObject()) is False and (value != om2.MObject()) is True
        assert (value == om2.MPoint()) is False
    import maya.OpenMaya as om1

    assert (Vector() == om1.MVector()) is False and (Vector() != om1.MVector()) is True


def test_copy_and_pickle_do_not_call_user_init_and_keep_slots():
    def tagged_init(self, tag, *args, **kwargs):
        super(type(self), self).__init__(*args, **kwargs)
        self.tag = tag

    samples = []
    for base, args in ((Vector, (1.0, 2.0, 3.0)), (Quaternion, (0.1, 0.2, 0.3, 0.9)),
                       (EulerRotation, (0.1, 0.2, 0.3, "zyx")),
                       (Matrix, (Matrix(translate=(1.0, 2.0, 3.0), scale=(1.0, -2.0, 3.0)),))):
        tagged = _register_user_class("Tagged" + base.__name__, (base,), {"__init__": tagged_init})
        samples.append(tagged("tag", *args))
        slotted = _register_user_class("Slotted" + base.__name__, (base,), {"__slots__": ("tag", "unset")})
        value = slotted(*args)
        value.tag = ["slot"]
        samples.append(value)
    duplicators = [copy.copy, copy.deepcopy]
    duplicators.extend(
        (lambda value, protocol=protocol: pickle.loads(pickle.dumps(value, protocol)))
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1)
    )
    for value in samples:
        for duplicate in duplicators:
            result = duplicate(value)
            assert type(result) is type(value) and result == value and result is not value
            if isinstance(value, om2.MEulerRotation):
                assert result.order == value.order
            assert result.tag == value.tag
            assert not hasattr(result, "unset")
    # 自身を参照する属性も pickle / deepcopy で復元できる。
    user_vector = _register_user_class("SelfReferenceVector", (Vector,), {})
    looped = user_vector(1.0, 2.0, 3.0)
    looped.me = looped
    for duplicate in (copy.deepcopy, lambda value: pickle.loads(pickle.dumps(value, 2))):
        result = duplicate(looped)
        assert result.me is result and tuple(result) == (1.0, 2.0, 3.0)


def test_matrix_copies_keep_signed_zero_and_non_finite_values():
    inf, nan = float("inf"), float("nan")
    source = om2.MMatrix([-0.0, 0.0, inf, nan, -1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, -inf, -0.0])
    for copied in (Matrix(source), Matrix.from_mmatrix(source), copy.copy(Matrix(source)),
                   pickle.loads(pickle.dumps(Matrix(source))), Matrix(source).transpose().transpose()):
        for actual, expected in zip(copied, source):
            if math.isnan(expected):
                assert math.isnan(actual)
            else:
                assert actual == expected and math.copysign(1.0, actual) == math.copysign(1.0, expected)


def _same_float(actual, expected):
    """NaN と符号付きゼロを区別して2つの float が同じ値か判定する。"""
    if math.isnan(expected):
        return math.isnan(actual)
    return actual == expected and math.copysign(1.0, actual) == math.copysign(1.0, expected)


#: guide_maths.rst の「演算結果の型」に記載した例外(系統の違う om2 の値が左辺で、om2 が
#: 処理して om2 の型を返す組み合わせ)。(左辺の om2 の型名, 演算子, 右辺の hlib の型名)。
_DOCUMENTED_OM2_RESULTS = {
    ("MVector", "*", "Matrix"),
    ("MPoint", "*", "Matrix"),
    ("MPoint", "+", "Vector"),
    ("MPoint", "-", "Vector"),
    ("MPoint", "+", "Translation"),
    ("MPoint", "-", "Translation"),
    ("MEulerRotation", "*", "Quaternion"),
}


def test_operator_result_types_follow_the_documented_rule():
    import operator

    hlib_values = [Vector(1.0, 2.0, 3.0), Translation(1.0, 2.0, 3.0), Quaternion(0.1, 0.2, 0.3, 0.9),
                   EulerRotation(0.1, 0.2, 0.3, "zyx"), Matrix(translate=(1.0, 2.0, 3.0), rotate=(0.1, 0.2, 0.3))]
    om2_values = [om2.MVector(4.0, 5.0, 6.0), om2.MPoint(4.0, 5.0, 6.0), om2.MFloatVector(4.0, 5.0, 6.0),
                  om2.MFloatPoint(4.0, 5.0, 6.0), om2.MQuaternion(0.1, 0.1, 0.1, 0.9),
                  om2.MEulerRotation(0.1, 0.1, 0.1), om2.MMatrix(hlib_values[-1]),
                  om2.MFloatMatrix(om2.MMatrix(hlib_values[-1])), 2, 2.0]
    operators = [("+", operator.add), ("-", operator.sub), ("*", operator.mul), ("/", operator.truediv),
                 ("^", operator.xor), ("@", operator.matmul)]
    hlib_types = (Vector, Quaternion, EulerRotation, Matrix)
    om2_results = set()
    for value in hlib_values:
        for other in om2_values:
            for symbol, function in operators:
                for left, right in ((value, other), (other, value)):
                    try:
                        result = function(left, right)
                    except TypeError:
                        continue
                    if isinstance(result, hlib_types) or type(result) is float:
                        continue
                    # hlib が左辺なら常に hlib の型(または内積の float)。
                    assert left is other, (type(left).__name__, symbol, type(right).__name__, type(result))
                    om2_results.add((type(left).__name__, symbol, type(right).__name__))
    assert om2_results == _DOCUMENTED_OM2_RESULTS, om2_results


def test_reflected_and_mixed_vector_matrix_products_return_hlib_types():
    a = Vector(1.0, 2.0, 3.0)
    raw = om2.MVector(-4.0, 5.5, 0.25)
    # om2.MVector ^ Vector も右辺の __rxor__ が先に呼ばれて Vector になる。
    crossed = raw ^ a
    assert type(crossed) is Vector
    assert crossed == om2.MVector.__xor__(raw, a) == -(a ^ raw)
    assert type(raw ^ Translation(1.0, 2.0, 3.0)) is Vector

    # Matrix が左辺なら om2.MVector / om2.MPoint との積も Vector(om2 の列ベクトルとしての積)。
    m = Matrix(translate=(1.0, 2.0, 3.0), rotate=(0.1, 0.2, 0.3), scale=(1.0, 2.0, 3.0))
    raw_matrix = om2.MMatrix(m)
    column = m * raw
    assert type(column) is Vector
    assert column == raw_matrix * raw == m * Vector(raw)
    point = om2.MPoint(4.0, 5.0, 6.0, 2.0)
    expected = raw_matrix * point
    assert expected.w != 1.0
    product = m * point
    assert type(product) is Vector
    # w は捨て、w で割らない(Vector(om2.MPoint) と同じ)。
    assert tuple(product) == (expected.x, expected.y, expected.z)
    assert product == Vector(expected)
    _assert_raises(TypeError, lambda: m * om2.MFloatVector(1.0, 0.0, 0.0))
    _assert_raises(TypeError, lambda: m * om2.MFloatPoint(1.0, 0.0, 0.0))
    _assert_raises(TypeError, lambda: m @ raw)

    # in-place: 左辺が om2 の値なら om2 の型のまま書き換わる。om2 に無い ^= は束ね直しで Vector。
    target = om2.MVector(1.0, 0.0, 0.0)
    alias = target
    target += a
    assert target is alias and type(target) is om2.MVector
    target ^= a
    assert type(target) is Vector
    rebound = Matrix(m)
    rebound *= raw
    assert type(rebound) is Vector and rebound == column


def test_containment_with_raw_om2_values_depends_on_python_version():
    value = Vector(1.0, 2.0, 3.0)
    point = om2.MPoint(1.0, 2.0, 3.0)
    # in: Python 3.9 以降は「要素 == 探す値」、3.7 は「探す値 == 要素」の向きで比べる。
    if sys.version_info >= (3, 9):
        assert (point in [value]) is False
        assert (point in (value,)) is False
        _assert_raises(TypeError, lambda: value in [point])
    else:
        _assert_raises(TypeError, lambda: point in [value])
        _assert_raises(TypeError, lambda: point in (value,))
        assert (value in [point]) is False
    # index / count / remove はどのバージョンでも「要素 == 探す値」。
    assert [value].count(point) == 0
    _assert_raises(TypeError, lambda: [point].count(value))
    _assert_raises(TypeError, lambda: [point, value].index(value))
    assert [value, point].index(point) == 1
    # リスト同士の == は左のリストの要素が左辺。
    assert ([value] == [point]) is False
    _assert_raises(TypeError, lambda: [point] == [value])
    # hlib の型へ変換すれば、どの向きでも例外にならない。
    assert Vector(point) in [value] and value in [Vector(point)]


def test_values_do_not_support_weak_references():
    import weakref

    for value in _samples():
        _assert_raises(TypeError, lambda value=value: weakref.ref(value))


def test_matrix_construction_paths_agree_and_validate_before_writing():
    matrix_module = sys.modules[PACKAGE_NAME + ".maths.matrix"]
    # 列からの設定の経路は Maya の版で選ぶ(2022 は om2 の __init__ の再適用がリークする)。
    assert matrix_module._REINIT == (om2.MGlobal.apiVersion() >= 20240000)
    floats = [float(i) * 0.5 - 3.0 for i in range(16)]
    expected = om2.MMatrix(floats)
    rows = [floats[0:4], floats[4:8], floats[8:12], floats[12:16]]
    for source in (floats, tuple(floats), rows, tuple(tuple(row) for row in rows), iter(floats),
                   (value for value in floats), expected, om2.MFloatMatrix(om2.MMatrix(list(range(16))))):
        result = Matrix(source)
        assert type(result) is Matrix
        reference = expected if not isinstance(source, om2.MFloatMatrix) else om2.MMatrix(source)
        assert list(result) == list(reference), source
    assert list(Matrix(list(range(16)))) == [float(i) for i in range(16)]
    assert list(Matrix([True] * 16)) == [1.0] * 16

    class Row(object):
        def __init__(self, values):
            self.values = values

        def __len__(self):
            return 4

        def __iter__(self):
            return iter(self.values)

    # om2 が受け付けない形でも、数値へ変換できれば hlib の検証経路で受け付ける。
    assert list(Matrix([Row(row) for row in rows])) == list(expected)
    # 数値以外・要素数の違いは ValueError で、再初期化でも値は変わらない。
    target = Matrix(floats)
    for invalid in (["1"] * 16, [None] * 16, [1.0] * 15, [1.0] * 17, rows[:3], rows[:3] + [[1.0, 2.0, 3.0, "x"]],
                    "abcdefghijklmnop", 42):
        _assert_raises(ValueError, lambda invalid=invalid: Matrix(invalid))
        _assert_raises(ValueError, lambda invalid=invalid: target.__init__(invalid))
        assert list(target) == floats, invalid


def test_matrix_values_rows_iteration_and_indexing_read_om2_elements():
    inf, nan = float("inf"), float("nan")
    source = [-0.0, 0.0, inf, nan, -1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, -inf, -0.0]
    matrix = Matrix(source)
    raw = om2.MMatrix(source)
    for sequence in (matrix.values, tuple(matrix), list(matrix), [item for item in matrix],
                     matrix[:], matrix[0:16], tuple(item for row in matrix.rows for item in row)):
        assert len(sequence) == 16
        for actual, expected in zip(sequence, raw):
            assert _same_float(actual, expected), (sequence, list(raw))
    stepped = matrix[3:16:4]
    assert len(stepped) == 4 and all(_same_float(a, b) for a, b in zip(stepped, (nan, 4.0, 8.0, -0.0)))
    assert all(len(row) == 4 for row in matrix.rows)
    # 反復は開始時点の値を返す(Vector などと同じ)。
    iterator = iter(matrix)
    matrix[1] = 100.0
    assert next(iterator) == -0.0 and next(iterator) == 0.0
    matrix[1] = 0.0
    # (行, 列)の添字は負の値や int 派生も含めて om2 の要素と一致し、範囲外は IndexError。
    counting = Matrix(list(range(16)))
    for row in range(-4, 4):
        for column in range(-4, 4):
            assert counting[row, column] == counting.getElement(row % 4, column % 4)
    assert counting[True, 1] == 5.0
    for index in ((4, 0), (0, 4), (-5, 0), (0, -5), (0, 1, 2), (0,)):
        _assert_raises(IndexError, lambda index=index: counting[index])

        def assign(index=index):
            counting[index] = 1.0

        _assert_raises(IndexError, assign)
    _assert_raises(TypeError, lambda: counting[0.0, 1])
    counting[2, 3] = 42.0
    counting[-1, -1] = 43.0
    counting[True, 0] = 44.0
    assert counting.getElement(2, 3) == 42.0 and counting.getElement(3, 3) == 43.0
    assert counting.getElement(1, 0) == 44.0
    # 派生クラスでも同じ値を読む。
    user_matrix = _register_user_class("UserMatrixValues", (Matrix,), {})
    derived = user_matrix(source)
    for actual, expected in zip(derived.values, raw):
        assert _same_float(actual, expected)


def test_class_statements_use_the_om2_bases():
    # Sphinx と _mermaidClasses.py が基底を om2 の型として表示できるよう、クラス文の基底は
    # 私的な別名ではなく om2.MVector などと書く。
    import ast

    expected = {"vector.py": ("Vector", "MVector"), "quaternion.py": ("Quaternion", "MQuaternion"),
                "eulerRotation.py": ("EulerRotation", "MEulerRotation"), "matrix.py": ("Matrix", "MMatrix")}
    for file_name, (class_name, base_name) in expected.items():
        tree = ast.parse((ROOT / "maths" / file_name).read_text(encoding="utf-8"))
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name]
        assert len(classes) == 1, file_name
        bases = classes[0].bases
        assert len(bases) == 1 and isinstance(bases[0], ast.Attribute), file_name
        assert isinstance(bases[0].value, ast.Name) and bases[0].value.id == "om2", file_name
        assert bases[0].attr == base_name, file_name
    assert Vector.__bases__ == (om2.MVector,) and Quaternion.__bases__ == (om2.MQuaternion,)
    assert EulerRotation.__bases__ == (om2.MEulerRotation,) and Matrix.__bases__ == (om2.MMatrix,)


if __name__ == "__main__":
    import unittest

    # Reload only this test's isolated math package to pick up saved edits.
    for _module_name in list(sys.modules):
        if _module_name.startswith(PACKAGE_NAME + "."):
            del sys.modules[_module_name]
    importlib.invalidate_caches()
    module = importlib.import_module(f"{PACKAGE_NAME}.maths")
    for _type_name in (
        "Vector", "Translation", "Quaternion", "EulerRotation",
        "Scale", "Shear", "Matrix",
    ):
        globals()[_type_name] = getattr(module, _type_name)
    ORDER_NAMES = module.eulerRotation.ORDER_NAMES

    _tests = [
        unittest.FunctionTestCase(value, description=name)
        for name, value in list(globals().items())
        if name.startswith("test_") and isinstance(value, types.FunctionType)
    ]
    _result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(_tests))
    if not _result.wasSuccessful():
        raise AssertionError("hlib datatype tests failed; see test output above.")
