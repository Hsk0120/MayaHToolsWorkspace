"""MayaのNURBS曲面シェイプを扱う。"""

from .._core.registry import node_wrapper
from .shape import Shape


@node_wrapper("nurbsSurface")
class NurbsSurface(Shape):
    """NURBS曲面の型付き参照。属性・親Transform操作はShapeから継承する。"""
