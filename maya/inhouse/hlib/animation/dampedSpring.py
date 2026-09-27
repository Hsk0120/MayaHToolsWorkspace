"""固定刻みでサンプル列を計算する減衰ばね。"""

import math


class DampedSpring:
    """再生履歴に依存しない、ベイク用の数値ソルバー。"""

    @staticmethod
    def solve(samples, seconds_per_sample, frequency=3.0, damping=0.5, limit=45.0):
        """目標値の列へ追従するばねを先頭から計算する。

        Args:
            samples (Sequence[Sequence[float]]): 等時間隔の目標値。各成分を独立計算する。
            seconds_per_sample (float): サンプル間隔、秒。
            frequency (float): 固有振動数、Hz。0より大きく30以下。
            damping (float): 減衰比。0〜2。1が臨界減衰。
            limit (float): 目標からの最大差分。正の値。

        Returns:
            list[tuple[float]]: 各目標へ遅れて追従する結果。

        Note:
            初期値は先頭目標、初速ゼロ。内部刻みを細分化する半陰的Euler法。
            回転に使う場合は角度のラップを呼出側で処理する。
        """
        rows = [tuple(float(v) for v in row) for row in samples]
        if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
            raise ValueError("Expected equally sized nonempty samples")
        if not all(math.isfinite(v) for row in rows for v in row):
            raise ValueError("Samples must be finite")
        if not all(math.isfinite(v) for v in (seconds_per_sample, frequency, damping, limit)):
            raise ValueError("Settings must be finite")
        if not (seconds_per_sample > 0 and 0 < frequency <= 30 and 0 <= damping <= 2 and limit > 0):
            raise ValueError("Invalid spring settings")
        omega = 2 * math.pi * frequency
        count = max(1, int(math.ceil(seconds_per_sample * omega * 20)))
        if count > 10000:
            raise ValueError("Sample interval is too large")
        dt = seconds_per_sample / count
        position, velocity = list(rows[0]), [0.0] * len(rows[0])
        result = [tuple(position)]
        for before, after in zip(rows, rows[1:]):
            for step in range(1, count + 1):
                alpha = step / count
                for axis in range(len(position)):
                    goal = before[axis] + (after[axis] - before[axis]) * alpha
                    acceleration = (
                        omega * omega * (goal - position[axis])
                        - 2 * damping * omega * velocity[axis]
                    )
                    velocity[axis] += acceleration * dt
                    position[axis] += velocity[axis] * dt
                    bounded = max(goal - limit, min(goal + limit, position[axis]))
                    if bounded != position[axis]:
                        position[axis], velocity[axis] = bounded, 0.0
            result.append(tuple(position))
        return result
