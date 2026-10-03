"""Mayaのblinnノードを扱う。"""

from .._core.registry import node_wrapper
from .reflect import Reflect


@node_wrapper("blinn")
class Blinn(Reflect):
    """Mayaの継承型に対応するBlinn。値と接続はPlugで操作する。"""
