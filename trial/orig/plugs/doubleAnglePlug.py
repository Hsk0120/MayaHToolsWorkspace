"""角度アトリビュートを扱う。"""

from .plug import Plug


class DoubleAnglePlug(Plug):
    """角度のPlug。get/setの数値は既定で度、unit="rad"ならラジアン、uiUnits=Trueなら現在のUI角度単位。"""
