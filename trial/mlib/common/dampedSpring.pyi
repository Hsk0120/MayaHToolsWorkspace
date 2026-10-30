# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""固定刻みでサンプル列を計算する減衰ばね。"""

import math
from typing import Sequence



class DampedSpring:
    """再生履歴に依存しない、ベイク用の数値ソルバー。"""
    @staticmethod
    def solve(samples: Sequence[Sequence[float]], secondsPerSample: float, frequency: float = ..., damping: float = ..., limit: float = ...) -> list[tuple[float]]:
        """目標値の列へ追従するばねを先頭から計算する。

        Args:
            samples (Sequence[Sequence[float]]): 等時間隔の目標値。各成分を独立計算する。
            secondsPerSample (float): サンプル間隔、秒。
            frequency (float): 固有振動数、Hz。0より大きく30以下。
            damping (float): 減衰比。0〜2。1が臨界減衰。
            limit (float): 目標からの最大差分。正の値。

        Returns:
            list[tuple[float]]: 各目標へ遅れて追従する結果。

        Note:
            初期値は先頭目標、初速ゼロ。内部刻みを細分化する半陰的Euler法。
            回転に使う場合は角度のラップを呼出側で処理する。
        """
        ...
