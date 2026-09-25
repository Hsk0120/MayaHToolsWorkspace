import importlib
import math
from pathlib import Path
import sys
import types


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
    assert isinstance(rotation, Vector)
    assert isinstance(scale, Vector)
    assert isinstance(shear, Vector)
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
            assert round_trip.order == order
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
    import maya.api.OpenMaya as om2

    orders = {
        "xyz": om2.MEulerRotation.kXYZ, "yzx": om2.MEulerRotation.kYZX, "zxy": om2.MEulerRotation.kZXY,
        "xzy": om2.MEulerRotation.kXZY, "yxz": om2.MEulerRotation.kYXZ, "zyx": om2.MEulerRotation.kZYX,
    }
    angles = (0.3, -0.5, 0.9)
    for order, om2_order in orders.items():
        rotation = EulerRotation(*angles, order)
        quaternion = rotation.to_quaternion()
        expected = om2.MEulerRotation(*angles, om2_order).asQuaternion()
        assert _quaternions_represent_the_same_rotation(
            quaternion, Quaternion(expected.x, expected.y, expected.z, expected.w)
        )
        round_trip = quaternion.to_euler(order)
        expected_euler = expected.asEulerRotation()
        expected_euler.reorderIt(om2_order)
        assert math.isclose(round_trip.x, expected_euler.x, abs_tol=1e-9)
        assert math.isclose(round_trip.y, expected_euler.y, abs_tol=1e-9)
        assert math.isclose(round_trip.z, expected_euler.z, abs_tol=1e-9)


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

    # 任意姿勢でも swing * twist が元の回転を再現し、twist は axis 周りのみ。
    mixed = Quaternion.from_axis_angle(Vector(0.3, 0.6, -0.2), math.radians(133.0))
    swing, twist = mixed.to_swing_twist(axis)
    recomposed = swing * twist
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
    assert tuple(a @ Vector(1.0, 1.0, 1.0)) == tuple(a * Vector(1.0, 1.0, 1.0))


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

    _tests = [
        unittest.FunctionTestCase(value, description=name)
        for name, value in list(globals().items())
        if name.startswith("test_") and isinstance(value, types.FunctionType)
    ]
    _result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(_tests))
    if not _result.wasSuccessful():
        raise AssertionError("hlib datatype tests failed; see test output above.")
