"""単位なしから距離のアニメーションカーブ。"""

from .._core.registry import node_wrapper
from .animCurve import AnimCurve


@node_wrapper("animCurveUL")
class AnimCurveUL(AnimCurve):
    """単位なしから距離へ変換する。共通操作はAnimCurveを参照。"""
