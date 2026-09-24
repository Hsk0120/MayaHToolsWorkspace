"""単位なしから単位なしのアニメーションカーブ。"""

from .._core.registry import node_wrapper
from .animCurve import AnimCurve


@node_wrapper("animCurveUU")
class AnimCurveUU(AnimCurve):
    """単位なしから単位なしへ変換する。共通操作はAnimCurveを参照。"""
