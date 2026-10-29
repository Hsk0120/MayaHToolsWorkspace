# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""距離アトリビュートを汎用 Plug の読み書き機能で扱う。"""

from .plug import Plug



class DoubleLinearPlug(Plug):
    """距離のPlug。get/setは既定cm、uiUnits=Trueなら現在のUI距離単位。"""
