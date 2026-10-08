"""getOutlinerへ委譲するget省略入口。"""

from .._core.getterAlias import _getter_alias
from .getOutliner import getOutliner as _get_outliner


@_getter_alias(_get_outliner)
def outliner(*args, **kwargs):
    """正式getterへ委譲し、引数・戻り値・例外の仕様を維持する。

    Args:
        *args: 正式getterへ渡す位置引数。
        **kwargs: 正式getterへ渡すキーワード引数。

    Returns:
        object: 正式getterと同じ戻り値。
    """
    from .getOutliner import getOutliner

    return getOutliner(*args, **kwargs)
