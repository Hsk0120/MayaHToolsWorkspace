# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""時間から単位なしのアニメーションカーブ。"""

from .animCurve import AnimCurve



class AnimCurveTU(AnimCurve):
    """時間から単位なしへ変換する。共通操作はAnimCurveを参照。"""
