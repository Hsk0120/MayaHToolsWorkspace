"""MayaのNURBS曲面シェイプを扱う。"""

from .shape import Shape


class NurbsSurface(Shape):
    """NURBS曲面の型付き参照。アトリビュート・親Transform操作はShapeから継承する。"""
