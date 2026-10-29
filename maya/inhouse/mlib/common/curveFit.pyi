# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""外部数値ライブラリなしで3次B-splineの制御点を近似する。"""

import math
from typing import Sequence



class CurveFit:
    """等間隔clamped knotを持つ3次カーブの正則化最小二乗フィット。"""
    @staticmethod
    def basis(count: int, parameter: float) -> list[float]:
        """0〜1のパラメータで基底ウェイトを計算する。

        Args:
            count (int): 4以上のCV数。
            parameter (float): 正規化カーブパラメータ。

        Returns:
            list[float]: CVごとのウェイト。
        """
        ...
    @classmethod
    def fit(cls, points: Sequence[Sequence[float]], count: int) -> list[list[float]]:
        """折れ線の弦長をパラメータとしてCVを近似する。

        Args:
            points (Sequence[Sequence[float]]): 同一空間・単位の3次元点、2点以上。
            count (int): CV数、4〜32。

        Returns:
            list[list[float]]: 同じ空間・単位のCV座標。

        Note:
            少ないサンプルでは直線配置へ弱く正則化する。折れ角や弧長の完全一致は保証しない。
        """
        ...
