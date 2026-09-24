"""時間から単位なしのアニメーションカーブ。"""

from .._core.registry import node_wrapper
from .animCurve import AnimCurve


@node_wrapper("animCurveTU")
class AnimCurveTU(AnimCurve):
    """時間から単位なしへ変換する。共通操作はAnimCurveを参照。"""
