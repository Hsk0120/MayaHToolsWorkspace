"""MayaのphongEノードを扱う。"""

from .._core.registry import node_wrapper
from .reflect import Reflect


@node_wrapper("phongE")
class PhongE(Reflect):
    """Mayaの継承型に対応するPhongE。値と接続はPlugで操作する。"""
