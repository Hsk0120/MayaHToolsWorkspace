# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""時間から距離のアニメーションカーブ。"""

from .animCurve import AnimCurve



class AnimCurveTL(AnimCurve):
    """時間から距離へ変換する。共通操作はAnimCurveを参照。"""
