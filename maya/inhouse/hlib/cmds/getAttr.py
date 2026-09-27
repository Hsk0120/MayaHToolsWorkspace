"""属性値または状態を照会する。"""

from maya import cmds
from .._core.flags import flag_aliases


@flag_aliases("getAttr")
def getAttr(target, **kwargs):
    """属性値または状態を照会する。

    Args:
        target (str | Node | Plug): 操作対象。
        **kwargs: Mayaの長名・短名フラグ。重複指定は拒否する。

    Returns:
        Matrix | Vector | object: 行列と3成分は数学型、その他は数値/文字列/列。

    Raises:
        TypeError: 入力型やフラグの重複が不正な場合。
        RuntimeError: Mayaが操作を拒否した場合。

    距離・角度は現在のUI単位。Plug.getの固定単位とは区別する。
    """
    from .._core.coerce import to_plug
    from ..maths import Matrix, Vector

    plug = to_plug(target)
    value = cmds.getAttr(plug.full_name(), **kwargs)
    if any(
        kwargs.get(k)
        for k in (
            "type",
            "size",
            "lock",
            "keyable",
            "settable",
            "channelBox",
            "multiIndices",
            "asString",
            "caching",
        )
    ):
        return value
    kind = plug.data_type()
    if kind == "matrix":
        return Matrix(value)
    if kind in ("double3", "float3", "long3", "short3"):
        return Vector(value[0])
    return value
