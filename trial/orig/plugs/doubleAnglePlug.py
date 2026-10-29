"""角度アトリビュートを扱う。"""

from .plug import Plug


class DoubleAnglePlug(Plug):
    """角度のPlug。get/setは既定rad、uiUnits=Trueなら現在のUI角度単位。"""
