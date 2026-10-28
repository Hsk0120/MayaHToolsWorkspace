"""距離アトリビュートを汎用 Plug の読み書き機能で扱う。"""

from .plug import Plug


class DoubleLinearPlug(Plug):
    """距離のPlug。get/setは既定cm、uiUnits=Trueなら現在のUI距離単位。"""
