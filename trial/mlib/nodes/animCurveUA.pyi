# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""単位なしから角度のアニメーションカーブ。"""

from .animCurve import AnimCurve



class AnimCurveUA(AnimCurve):
    """単位なしから角度へ変換する。共通操作はAnimCurveを参照。"""
