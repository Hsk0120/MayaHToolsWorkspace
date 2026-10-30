# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の geometryConstraint を扱う。"""

from .constraint import Constraint



class GeometryConstraint(Constraint):
    """ターゲット表面上の位置へコンストレイントするラッパー。"""
