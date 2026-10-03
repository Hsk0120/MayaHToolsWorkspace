"""既存のWorkspaceLayoutを取得する。UI生成や保存は行わない。"""


def getWorkspaceLayout(name=None):
    """既存対象への操作オブジェクトを取得する。

    Args:
        name (str): Mayaに登録された名前。

    Returns:
        WorkspaceLayout: 対象への参照。
    """
    from ..ui import WorkspaceLayout

    return WorkspaceLayout(name)
