"""時間から角度のアニメーションカーブ。"""

from .._core.registry import node_wrapper
from .animCurve import AnimCurve


@node_wrapper("animCurveTA")
class AnimCurveTA(AnimCurve):
    """時間から角度へ変換する。共通操作はAnimCurveを参照。"""
