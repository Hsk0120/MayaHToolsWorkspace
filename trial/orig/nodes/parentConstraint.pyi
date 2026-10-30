# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の parentConstraint を扱う。"""

from .constraint import Constraint



class ParentConstraint(Constraint):
    """位置と回転をコンストレイントする parentConstraint ラッパー。"""
