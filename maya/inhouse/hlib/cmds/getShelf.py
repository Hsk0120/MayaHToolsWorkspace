"""既存シェルフを取得する。省略時は現在のタブ。"""


def getShelf(name=None):
    """既存シェルフを取得する。省略時は現在のタブ。

    Args:
        name (str): シェルフのUI識別名。

    Returns:
        Shelf: シェルフの操作オブジェクト。
    """
    from hlib.ui import Shelf

    return Shelf(name)
