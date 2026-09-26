"""hlib.maths.easing の対称イージング曲線を検証するテスト。

``hlib.maths`` は Maya に依存しないため、``hlib`` パッケージ全体
(maya.cmds を読み込む)を経由せず、maths だけを独立した仮パッケージとして
読み込んで検証する。mayapy で ``maya.standalone`` を初期化せずに実行しても通る。
"""

import decimal
import fractions
import importlib
import math
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "hlib_easing_test"


def _load_easing():
    """保存済みの最新ソースから hlib/maths/easing.py を読み込み直す。

    Returns:
        module: 読み込んだ easing モジュール。
    """
    for module_name in list(sys.modules):
        if module_name == PACKAGE_NAME or module_name.startswith(PACKAGE_NAME + "."):
            del sys.modules[module_name]
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE_NAME] = package
    importlib.invalidate_caches()
    return importlib.import_module(PACKAGE_NAME + ".maths.easing")


easing = _load_easing()

# 単調性・対称性を調べる標本点(両端を含む 0〜1 の等間隔 1001 点)。
SAMPLES = [index / 1000.0 for index in range(1001)]


class CurveCatalogTest(unittest.TestCase):
    """CURVES の内容と既定の曲線を検証する。"""

    def test_curves_is_a_tuple_of_unique_names(self):
        self.assertIsInstance(easing.CURVES, tuple)
        self.assertEqual(len(easing.CURVES), len(set(easing.CURVES)))
        for curve in easing.CURVES:
            self.assertIsInstance(curve, str)

    def test_curves_contains_the_polynomial_family_and_named_shapes(self):
        for curve in (
            "linear", "smoothstep", "sine", "circular",
            "quadratic", "cubic", "quartic", "quintic", "exponential",
        ):
            self.assertIn(curve, easing.CURVES)

    def test_default_curve_is_cubic(self):
        for t in (0.1, 0.3, 0.5, 0.8):
            self.assertEqual(easing.ease(t), easing.ease(t, "cubic"))

    def test_public_names(self):
        self.assertEqual(sorted(easing.__all__), ["CURVES", "ease"])

    def test_reload_drops_functions_left_over_from_the_previous_api(self):
        # importlib.reload はモジュールの辞書を引き継ぐ。旧版の関数が
        # 実行中のセッションに残っている状況を再現して、再読み込みで消えることを確かめる。
        easing.ease_in_out_cubic = lambda value: value
        easing.ease_in_out_legacy_shape = lambda value: value

        reloaded = importlib.reload(easing)

        self.assertIs(reloaded, easing)
        self.assertFalse(hasattr(easing, "ease_in_out_cubic"))
        self.assertFalse(hasattr(easing, "ease_in_out_legacy_shape"))
        self.assertEqual(easing.ease(0.25, "cubic"), 0.0625)
        self.assertEqual(sorted(easing.__all__), ["CURVES", "ease"])


class CurvePropertyTest(unittest.TestCase):
    """全曲線に共通する性質(端点・中央・対称・単調・値域)を検証する。"""

    def test_endpoints_are_exact(self):
        for curve in easing.CURVES:
            with self.subTest(curve=curve):
                self.assertEqual(easing.ease(0.0, curve), 0.0)
                self.assertEqual(easing.ease(1.0, curve), 1.0)
                self.assertEqual(easing.ease(0, curve), 0.0)
                self.assertEqual(easing.ease(1, curve), 1.0)
                self.assertIsInstance(easing.ease(0, curve), float)
                self.assertIsInstance(easing.ease(1, curve), float)

    def test_midpoint_is_exactly_one_half(self):
        for curve in easing.CURVES:
            with self.subTest(curve=curve):
                self.assertEqual(easing.ease(0.5, curve), 0.5)

    def test_point_symmetric_about_the_center(self):
        for curve in easing.CURVES:
            with self.subTest(curve=curve):
                for t in SAMPLES:
                    self.assertAlmostEqual(
                        easing.ease(t, curve) + easing.ease(1.0 - t, curve), 1.0, places=12
                    )

    def test_monotonic_and_within_unit_range(self):
        for curve in easing.CURVES:
            with self.subTest(curve=curve):
                values = [easing.ease(t, curve) for t in SAMPLES]
                for value in values:
                    self.assertGreaterEqual(value, 0.0)
                    self.assertLessEqual(value, 1.0)
                for previous, current in zip(values, values[1:]):
                    self.assertGreater(current, previous)

    def test_non_linear_curves_start_slow_and_finish_slow(self):
        for curve in easing.CURVES:
            if curve == "linear":
                continue
            with self.subTest(curve=curve):
                for t in (0.05, 0.25, 0.45):
                    self.assertLess(easing.ease(t, curve), t)
                for t in (0.55, 0.75, 0.95):
                    self.assertGreater(easing.ease(t, curve), t)


class CurveShapeTest(unittest.TestCase):
    """曲線ごとの形を、定義から直接求めた値と比較して検証する。"""

    def test_linear_is_identity(self):
        for t in SAMPLES:
            self.assertEqual(easing.ease(t, "linear"), t)

    def test_polynomial_values_in_the_first_half(self):
        # 前半 [0, 0.5] は (2t)^n / 2 になる。
        for degree, curve in enumerate(("quadratic", "cubic", "quartic", "quintic"), start=2):
            with self.subTest(curve=curve):
                for t in (0.1, 0.25, 0.4):
                    self.assertAlmostEqual(
                        easing.ease(t, curve), 0.5 * (2.0 * t) ** degree, places=15
                    )
        self.assertEqual(easing.ease(0.25, "quadratic"), 0.125)
        self.assertEqual(easing.ease(0.25, "cubic"), 0.0625)

    def test_higher_degree_is_flatter_near_the_ends(self):
        order = ("quadratic", "cubic", "quartic", "quintic")
        for t in (0.1, 0.25, 0.4):
            values = [easing.ease(t, curve) for curve in order]
            self.assertEqual(values, sorted(values, reverse=True))

    def test_smoothstep_matches_hermite_polynomial(self):
        for t in (0.1, 0.25, 0.6, 0.9):
            self.assertAlmostEqual(easing.ease(t, "smoothstep"), 3 * t ** 2 - 2 * t ** 3, places=15)

    def test_sine_matches_half_cosine_wave(self):
        for t in (0.1, 0.25, 0.6, 0.9):
            self.assertAlmostEqual(
                easing.ease(t, "sine"), (1.0 - math.cos(math.pi * t)) / 2.0, places=15
            )

    def test_circular_first_half_lies_on_a_circle(self):
        # 前半は中心 (0, 0.5)・半径 0.5 の円周上にある。
        for t in (0.1, 0.25, 0.4):
            y = easing.ease(t, "circular")
            self.assertAlmostEqual(t ** 2 + (y - 0.5) ** 2, 0.25, places=12)

    def test_exponential_first_half_is_a_normalized_exponential(self):
        # 前半は (e^(k*2t) - 1) / (e^k - 1) / 2。k は曲線の急さを決める内部定数。
        steepness = easing._EXPONENTIAL_STEEPNESS
        for t in (0.1, 0.25, 0.4):
            expected = 0.5 * math.expm1(steepness * 2.0 * t) / math.expm1(steepness)
            self.assertAlmostEqual(easing.ease(t, "exponential"), expected, places=15)


class InputHandlingTest(unittest.TestCase):
    """範囲外の入力の切り詰めと、不正な引数の例外を検証する。"""

    def test_clamps_values_outside_the_unit_interval(self):
        for curve in easing.CURVES:
            with self.subTest(curve=curve):
                self.assertEqual(easing.ease(-0.25, curve), 0.0)
                self.assertEqual(easing.ease(-1e9, curve), 0.0)
                self.assertEqual(easing.ease(float("-inf"), curve), 0.0)
                self.assertEqual(easing.ease(1.25, curve), 1.0)
                self.assertEqual(easing.ease(1e9, curve), 1.0)
                self.assertEqual(easing.ease(float("inf"), curve), 1.0)

    def test_unknown_curve_name_raises_value_error(self):
        for curve in ("", "Cubic", "sinusoidal", "ease_in_out_cubic", "bounce"):
            with self.subTest(curve=curve):
                with self.assertRaises(ValueError):
                    easing.ease(0.5, curve)

    def test_non_string_curve_raises_type_error(self):
        for curve in (None, 3, ("cubic",)):
            with self.subTest(curve=curve):
                with self.assertRaises(TypeError):
                    easing.ease(0.5, curve)

    def test_nan_input_raises_value_error(self):
        with self.assertRaises(ValueError):
            easing.ease(float("nan"))

    def test_non_numeric_input_raises_type_error(self):
        # 数値化できる内容の文字列や bool も、実数ではないため受け付けない。
        for value in (None, "0.5", "abc", b"0.5", bytearray(b"0.5"), True, False, 0.5j, object()):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    easing.ease(value)

    def test_accepts_real_numbers_other_than_float(self):
        self.assertEqual(easing.ease(fractions.Fraction(1, 4), "quadratic"), 0.125)
        self.assertEqual(easing.ease(decimal.Decimal("0.25"), "cubic"), 0.0625)
        self.assertIsInstance(easing.ease(fractions.Fraction(1, 2), "sine"), float)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
