"""単位なしから時間のアニメーションカーブ。"""

from .._core.registry import node_wrapper
from .animCurve import AnimCurve


@node_wrapper("animCurveUT")
class AnimCurveUT(AnimCurve):
    """単位なしから時間へ変換する。共通操作はAnimCurveを参照。"""
