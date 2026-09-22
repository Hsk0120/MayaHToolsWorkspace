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
        raise AssertionError("Hlib datatype tests failed; see test output above.")
