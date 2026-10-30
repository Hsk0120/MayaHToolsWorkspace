# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mayaのphongノードを扱う。"""

from .reflect import Reflect



class Phong(Reflect):
    """Mayaの継承型に対応するPhong。値と接続はPlugで操作する。"""
