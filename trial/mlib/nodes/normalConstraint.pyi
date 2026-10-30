# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の normalConstraint を扱う。"""

from .constraint import Constraint



class NormalConstraint(Constraint):
    """ターゲット表面の法線方向へ向けるラッパー。"""
