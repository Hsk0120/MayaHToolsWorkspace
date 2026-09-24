"""時間から時間のアニメーションカーブ。"""

from .._core.registry import node_wrapper
from .animCurve import AnimCurve


@node_wrapper("animCurveTT")
class AnimCurveTT(AnimCurve):
    """時間から時間へ変換する。共通操作はAnimCurveを参照。"""
