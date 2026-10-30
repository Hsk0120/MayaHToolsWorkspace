# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""MayaのNURBS曲面シェイプを扱う。"""

from .shape import Shape



class NurbsSurface(Shape):
    """NURBS曲面の型付き参照。アトリビュート・親Transform操作はShapeから継承する。"""
