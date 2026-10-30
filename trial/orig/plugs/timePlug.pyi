# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""時間アトリビュートを扱う。"""

from .plug import Plug



class TimePlug(Plug):
    """時間のPlug。get/setは既定秒、uiUnits=Trueなら現在のUI時間単位。"""
