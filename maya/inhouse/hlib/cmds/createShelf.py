"""Maya標準シェルフにタブを作成する。"""


def createShelf(name):
    """Maya標準シェルフにタブを作成する。

    Args:
        name (str): シェルフのUI識別名。

    Returns:
        Shelf: シェルフの操作オブジェクト。
    """
    from hlib.ui import Shelf

    return Shelf.create(name)
