"""Mayaのreflectノードを扱う。"""

from .lambert import Lambert


class Reflect(Lambert):
    """Mayaの継承型に対応するReflect。値と接続はPlugで操作する。"""
