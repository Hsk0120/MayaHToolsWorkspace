"""単位なしから角度のアニメーションカーブ。"""

from .._core.registry import node_wrapper
from .animCurve import AnimCurve


@node_wrapper("animCurveUA")
class AnimCurveUA(AnimCurve):
    """単位なしから角度へ変換する。共通操作はAnimCurveを参照。"""
