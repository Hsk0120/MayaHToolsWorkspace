# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""単位なしから時間のアニメーションカーブ。"""

from .animCurve import AnimCurve



class AnimCurveUT(AnimCurve):
    """単位なしから時間へ変換する。共通操作はAnimCurveを参照。"""
