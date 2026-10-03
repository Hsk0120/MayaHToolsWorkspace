"""Mayaのreflectノードを扱う。"""

from .._core.registry import node_wrapper
from .lambert import Lambert


@node_wrapper("reflect")
class Reflect(Lambert):
    """Mayaの継承型に対応するReflect。値と接続はPlugで操作する。"""
