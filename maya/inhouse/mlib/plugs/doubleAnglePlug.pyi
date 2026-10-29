# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""角度アトリビュートを扱う。"""

from .plug import Plug



class DoubleAnglePlug(Plug):
    """角度のPlug。get/setの数値は既定で度、unit="rad"ならラジアン、uiUnits=Trueなら現在のUI角度単位。"""
