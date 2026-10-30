# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の pointConstraint を扱う。"""

from .constraint import Constraint



class PointConstraint(Constraint):
    """位置をコンストレイントする pointConstraint ラッパー。"""
