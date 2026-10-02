"""既存のWindowを取得する。UI生成や保存は行わない。"""


def getWindow(name):
    """既存対象への操作オブジェクトを取得する。

    Args:
        name (str): Mayaに登録された名前。

    Returns:
        Window: 対象への参照。
    """
    from hlib.ui import Window

    return Window(name)
