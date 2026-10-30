# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の tangentConstraint を扱う。"""

from .constraint import Constraint



class TangentConstraint(Constraint):
    """NURBS カーブの接線方向へ向けるラッパー。"""
