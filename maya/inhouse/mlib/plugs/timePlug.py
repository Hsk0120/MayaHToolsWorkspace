"""時間アトリビュートを扱う。"""

from .plug import Plug


class TimePlug(Plug):
    """時間のPlug。get/setの数値は既定で現在のUI時間単位のフレーム、timeUnit="sec"なら秒。"""
