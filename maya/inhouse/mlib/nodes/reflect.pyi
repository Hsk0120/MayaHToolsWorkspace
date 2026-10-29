# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mayaのreflectノードを扱う。"""

from .lambert import Lambert



class Reflect(Lambert):
    """Mayaの継承型に対応するReflect。値と接続はPlugで操作する。"""
