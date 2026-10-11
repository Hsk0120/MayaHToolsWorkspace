"""getWorkspaceLayoutへ委譲するget省略入口。"""

from .._core.getterAlias import _getter_alias
from .getWorkspaceLayout import getWorkspaceLayout as _get_workspaceLayout


@_getter_alias(_get_workspaceLayout)
def workspaceLayout(*args, **kwargs):
    """正式getterへ委譲し、引数・戻り値・例外の仕様を維持する。

    Args:
        *args: 正式getterへ渡す位置引数。
        **kwargs: 正式getterへ渡すキーワード引数。

    Returns:
        object: 正式getterと同じ戻り値。
    """
    from .getWorkspaceLayout import getWorkspaceLayout

    return getWorkspaceLayout(*args, **kwargs)
