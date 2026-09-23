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
Translate = module.Translate
Rotate = module.Rotate
Quaternion = module.Quaternion
EulerRotation = module.EulerRotation
Scale = module.Scale
Shear = module.Shear
Matrix = module.Matrix


def test_translation_is_vector_like():
    t = Translate(1.0, 2.0, 3.0)
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
    a = Translate(0.0, 0.0, 0.0)
    b = Translate(3.0, 4.0, 0.0)
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
    rotation = Rotate(0.0, 90.0, 0.0)
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


def test_matrix_exposes_translation_scale_and_shear_values():
    m = Matrix(
        translate=(1.0, 2.0, 3.0),
        scale=(2.0, 3.0, 4.0),
        shear=(0.1, 0.2, 0.3),
    )
    assert isinstance(m.translate, Translate)
    assert isinstance(m.rotation, EulerRotation)
    assert isinstance(m.rotation, Rotate)
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
        "Vector", "Translate", "Rotate", "Quaternion", "EulerRotation",
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
