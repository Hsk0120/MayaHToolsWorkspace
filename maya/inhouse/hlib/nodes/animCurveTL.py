"""時間から距離のアニメーションカーブ。"""

from .._core.registry import node_wrapper
from .animCurve import AnimCurve


@node_wrapper("animCurveTL")
class AnimCurveTL(AnimCurve):
    """時間から距離へ変換する。共通操作はAnimCurveを参照。"""
