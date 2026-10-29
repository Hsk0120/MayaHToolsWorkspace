# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の scaleConstraint を扱う。"""

from .constraint import Constraint



class ScaleConstraint(Constraint):
    """スケールをコンストレイントする scaleConstraint ラッパー。"""
