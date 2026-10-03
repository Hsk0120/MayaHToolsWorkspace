"""Mayaのphongノードを扱う。"""

from .._core.registry import node_wrapper
from .reflect import Reflect


@node_wrapper("phong")
class Phong(Reflect):
    """Mayaの継承型に対応するPhong。値と接続はPlugで操作する。"""
