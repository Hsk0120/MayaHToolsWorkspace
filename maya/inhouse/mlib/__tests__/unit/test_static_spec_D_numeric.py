"""mlib.common の CurveFit・DampedSpring の約束を、Mayaなしで固定する仕様テスト(担当D)。

curveFit.py と dampedSpring.py は標準ライブラリの math だけを使う。``mlib`` パッケージ全体
(maya.cmds を読み込む)を経由せず、ファイルを単独のモジュールとして読み込んで検証する。
Maya の NURBS 評価との突き合わせは ``test_spec_D_common.py`` で行う。
"""

import copy
import importlib.util
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load(relative, name):
    """mlib のソースファイルを単独のモジュールとして読み込む。

    Args:
        relative (str): mlib からの相対パス。
        name (str): 読み込むモジュール名。

    Returns:
        module: 読み込んだモジュール。
    """
    spec = importlib.util.spec_from_file_location(name, str(ROOT / relative))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CurveFit = _load("common/curveFit.py", "mlib_spec_d_curvefit").CurveFit
DampedSpring = _load("common/dampedSpring.py", "mlib_spec_d_dampedspring").DampedSpring


def _evaluate(controls, parameter):
    """基底重みでCVを重み付けした点を返す。

    Args:
        controls (list[list[float]]): CV座標。
        parameter (float): 0〜1のパラメータ。

    Returns:
        list[float]: 評価した3次元点。
    """
    weights = CurveFit.basis(len(controls), parameter)
    return [sum(w * c[axis] for w, c in zip(weights, controls)) for axis in range(3)]


class CurveFitBasisSpecTest(unittest.TestCase):
    """CurveFit.basis の範囲検査・端点・1の分割を固定する。"""

    def test_rejects_count_below_four_and_parameter_out_of_range(self):
        """countが4未満、parameterが0〜1の外ならValueError。"""
        for count, parameter in ((3, 0.5), (0, 0.0), (4, -1e-9), (4, 1.0 + 1e-9), (8, 2.0)):
            with self.assertRaises(ValueError):
                CurveFit.basis(count, parameter)

    def test_length_matches_count_and_values_are_float(self):
        """重みはCV数と同じ長さのfloatのlist。"""
        for count in (4, 5, 7, 12, 32):
            for parameter in (0.0, 0.13, 0.5, 0.99, 1.0):
                weights = CurveFit.basis(count, parameter)
                self.assertIsInstance(weights, list)
                self.assertEqual(len(weights), count)
                self.assertTrue(all(isinstance(w, float) for w in weights))

    def test_partition_of_unity_and_non_negative(self):
        """全パラメータで重みの和は1、各重みは0以上。"""
        for count in (4, 6, 9):
            for step in range(0, 101):
                weights = CurveFit.basis(count, step / 100.0)
                self.assertAlmostEqual(sum(weights), 1.0, places=12)
                self.assertTrue(all(w >= -1e-15 for w in weights))

    def test_clamped_end_points(self):
        """clamped knotのため、0は先頭CV、1は末尾CVだけの重みになる。"""
        self.assertEqual(CurveFit.basis(6, 0.0), [1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        self.assertEqual(CurveFit.basis(6, 1), [0.0, 0.0, 0.0, 0.0, 0.0, 1.0])
        # int の 0 も受け付ける。
        self.assertEqual(CurveFit.basis(4, 0)[0], 1.0)

    def test_four_controls_are_bernstein_polynomials(self):
        """CV数4(1スパン)では3次のBernstein基底と一致する。"""
        for step in range(11):
            t = step / 10.0
            expected = [(1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3]
            for actual, wanted in zip(CurveFit.basis(4, t), expected):
                self.assertAlmostEqual(actual, wanted, places=12)

    def test_local_support(self):
        """各パラメータで0でない重みは連続する高々4個(3次のため)。"""
        for step in range(1, 100):
            weights = CurveFit.basis(10, step / 100.0)
            nonzero = [i for i, w in enumerate(weights) if abs(w) > 1e-15]
            self.assertLessEqual(len(nonzero), 4)
            self.assertEqual(nonzero, list(range(nonzero[0], nonzero[-1] + 1)))


class CurveFitFitSpecTest(unittest.TestCase):
    """CurveFit.fit の入力検証・端点・直線の再現を固定する。"""

    def test_rejects_invalid_count(self):
        """countは4〜32のint。boolやfloatもValueError。"""
        points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]
        for count in (3, 33, 4.0, True, "4", None):
            with self.assertRaises(ValueError):
                CurveFit.fit(points, count)

    def test_rejects_too_few_points(self):
        """点が2個未満ならValueError。"""
        with self.assertRaises(ValueError):
            CurveFit.fit([(0.0, 0.0, 0.0)], 4)
        with self.assertRaises(ValueError):
            CurveFit.fit([], 4)

    def test_rejects_non_3d_and_non_finite_points(self):
        """3成分以外・NaN・無限大はValueError。"""
        for bad in ([(0, 0), (1, 1)], [(0, 0, 0, 0), (1, 0, 0, 0)],
                    [(0, 0, 0), (float("nan"), 0, 0)], [(0, 0, 0), (float("inf"), 0, 0)]):
            with self.assertRaises(ValueError):
                CurveFit.fit(bad, 4)

    def test_rejects_zero_length_chain(self):
        """全点が同じ位置なら長さ0としてValueError。"""
        with self.assertRaises(ValueError):
            CurveFit.fit([(1.0, 2.0, 3.0)] * 5, 4)

    def test_result_shape_and_exact_end_points(self):
        """CV数ぶんの3成分listを返し、両端CVは入力の両端と完全に一致する独立したlist。"""
        points = [(math.cos(i * 0.3), math.sin(i * 0.3), i * 0.1) for i in range(12)]
        original = copy.deepcopy(points)
        result = CurveFit.fit(points, 7)
        self.assertEqual(len(result), 7)
        self.assertTrue(all(isinstance(row, list) and len(row) == 3 for row in result))
        self.assertEqual(result[0], list(points[0]))
        self.assertEqual(result[-1], list(points[-1]))
        self.assertIsNot(result[0], points[0])
        self.assertEqual(points, original)
        self.assertTrue(all(math.isfinite(v) for row in result for v in row))

    def test_two_points_regularize_to_straight_line(self):
        """2点だけでも、両端の直線上へ等間隔に近いCVを返す。"""
        result = CurveFit.fit([(0.0, 0.0, 0.0), (9.0, 0.0, 0.0)], 4)
        for row in result:
            self.assertAlmostEqual(row[1], 0.0, places=6)
            self.assertAlmostEqual(row[2], 0.0, places=6)
        xs = [row[0] for row in result]
        self.assertEqual(xs, sorted(xs))

    def test_reproduces_uniform_straight_line(self):
        """等間隔の直線上の点は、フィットしたカーブ上で同じ位置に再現される。"""
        points = [(i * 0.5, i * 0.25, -i * 0.1) for i in range(21)]
        controls = CurveFit.fit(points, 6)
        total = math.sqrt(10.0 ** 2 + 5.0 ** 2 + 2.0 ** 2)
        for index, point in enumerate(points):
            length = math.sqrt(sum(v * v for v in point))
            evaluated = _evaluate(controls, length / total)
            for axis in range(3):
                self.assertAlmostEqual(evaluated[axis], point[axis], places=4)

    def test_deterministic(self):
        """同じ入力には同じ結果を返す。"""
        points = [(i, math.sin(i), 0.0) for i in range(8)]
        self.assertEqual(CurveFit.fit(points, 5), CurveFit.fit(points, 5))


class DampedSpringSpecTest(unittest.TestCase):
    """DampedSpring.solve の入力検証・初期条件・減衰・制限を固定する。"""

    def test_result_shape_and_initial_value(self):
        """入力と同数のtupleを返し、先頭は先頭目標そのもの。"""
        samples = [(0, 1), (1, 1), (2, 1)]
        result = DampedSpring.solve(samples, 1 / 24.0)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(isinstance(row, tuple) and len(row) == 2 for row in result))
        self.assertEqual(result[0], (0.0, 1.0))
        self.assertTrue(all(isinstance(v, float) for v in result[0]))

    def test_single_sample_returns_itself(self):
        """1サンプルでは計算せず先頭目標だけを返す。"""
        self.assertEqual(DampedSpring.solve([(3, 4, 5)], 0.1), [(3.0, 4.0, 5.0)])

    def test_constant_target_stays_constant(self):
        """初速ゼロなので、目標が一定なら値は変わらない。"""
        result = DampedSpring.solve([(2.5,)] * 20, 1 / 30.0)
        self.assertEqual(result, [(2.5,)] * 20)

    def test_axes_are_independent(self):
        """各成分は独立して計算する。一定の成分は他の成分の動きに影響されない。"""
        samples = [(0.0 if i == 0 else 1.0, 7.0) for i in range(30)]
        result = DampedSpring.solve(samples, 1 / 24.0)
        self.assertTrue(all(row[1] == 7.0 for row in result))
        alone = DampedSpring.solve([(row[0],) for row in samples], 1 / 24.0)
        self.assertEqual([row[0] for row in result], [row[0] for row in alone])

    def test_underdamped_overshoots_and_critical_converges(self):
        """減衰比0.1は目標を超え、減衰比1はほぼ超えずに目標へ収束する。"""
        samples = [(0.0,)] + [(1.0,)] * 120
        under = [row[0] for row in DampedSpring.solve(samples, 1 / 24.0, frequency=2.0, damping=0.1)]
        self.assertGreater(max(under), 1.2)
        critical = [row[0] for row in DampedSpring.solve(samples, 1 / 24.0, frequency=2.0, damping=1.0)]
        self.assertLess(max(critical), 1.0 + 1e-3)
        self.assertAlmostEqual(critical[-1], 1.0, places=3)

    def test_zero_damping_keeps_oscillating(self):
        """減衰比0では収束せず振動を続ける。"""
        samples = [(0.0,)] + [(1.0,)] * 200
        values = [row[0] for row in DampedSpring.solve(samples, 1 / 24.0, frequency=1.0, damping=0.0)]
        tail = values[100:]
        self.assertGreater(max(tail) - min(tail), 1.0)

    def test_limit_bounds_the_lag(self):
        """各サンプル時点で目標との差はlimit以内に収まる。"""
        samples = [(0.0,)] + [(10.0,)] * 10
        result = DampedSpring.solve(samples, 1 / 24.0, frequency=0.5, damping=1.0, limit=0.25)
        for target, row in zip(samples, result):
            self.assertLessEqual(abs(row[0] - target[0]), 0.25 + 1e-12)

    def test_rejects_invalid_samples(self):
        """空・空行・長さ不揃い・非有限の目標はValueError。"""
        for samples in ([], [()], [(0, 0), (1,)], [(0,), (float("nan"),)], [(0,), (float("inf"),)]):
            with self.assertRaises(ValueError):
                DampedSpring.solve(samples, 0.04)

    def test_rejects_invalid_settings(self):
        """間隔・振動数・減衰比・制限が範囲外または非有限ならValueError。"""
        cases = [
            dict(seconds_per_sample=0.0), dict(seconds_per_sample=-1.0),
            dict(seconds_per_sample=float("nan")), dict(frequency=0.0), dict(frequency=30.0001),
            dict(damping=-0.01), dict(damping=2.01), dict(limit=0.0), dict(limit=float("inf")),
        ]
        for overrides in cases:
            options = dict(seconds_per_sample=0.04)
            options.update(overrides)
            with self.assertRaises(ValueError, msg=repr(overrides)):
                DampedSpring.solve([(0.0,), (1.0,)], **options)

    def test_boundary_settings_are_accepted(self):
        """振動数30・減衰比0と2は範囲内として受け付ける。"""
        DampedSpring.solve([(0.0,), (1.0,)], 0.04, frequency=30.0)
        DampedSpring.solve([(0.0,), (1.0,)], 0.04, damping=0.0)
        DampedSpring.solve([(0.0,), (1.0,)], 0.04, damping=2.0)

    def test_rejects_too_large_interval(self):
        """内部刻みが10000を超える間隔はValueError。"""
        with self.assertRaises(ValueError):
            DampedSpring.solve([(0.0,), (1.0,)], 3.0, frequency=30.0)

    def test_deterministic_and_input_not_modified(self):
        """同じ入力には同じ結果を返し、入力の列は変更しない。"""
        samples = [[0.0, 1.0], [0.5, 0.0], [2.0, -1.0]]
        before = copy.deepcopy(samples)
        first = DampedSpring.solve(samples, 1 / 24.0)
        self.assertEqual(first, DampedSpring.solve(samples, 1 / 24.0))
        self.assertEqual(samples, before)


if __name__ == "__main__":
    unittest.main()
