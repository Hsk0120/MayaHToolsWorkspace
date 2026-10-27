"""Simple Physics: Mayaのボーン揺れ制御。"""

__version__ = "0.1.0"


def show():
    """Simple Physicsの設定画面を開く。"""
    # Maya UIを必要とする入口でのみ読み込む。
    from . import ui

    return ui.show()
