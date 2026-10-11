"""アトリビュートのPlugを取得し、フラグ指定時はMayaの値・状態を照会する。"""

import maya.cmds as cmds

from .._core.flags import flag_aliases


@flag_aliases("getAttr")
def getAttr(target, **kwargs):
    """通常はPlugを取得し、フラグを明示した場合は従来の照会を行う。

    Args:
        target (str | Plug | om2.MPlug): アトリビュート名または参照。
        **kwargs: Mayaの長名・短名フラグ。省略時はPlug取得。
            一つでも指定した場合は値・状態の照会。重複指定は拒否する。

    Returns:
        Plug | Matrix | Vector | object: フラグなしはgetPlugと同じ型付きPlug。
            既存Plugはそのまま返す。フラグ指定時は従来の照会値。

    Raises:
        TypeError: 入力型やフラグの重複が不正な場合。
        ValueError: 空のアトリビュート名または空のMPlugを指定した場合。
        RuntimeError: Mayaが操作を拒否した場合。

    値は返したPlugのget()で内部単位、getu()で現在のUI単位として取得する。
    フラグを指定したMaya照会は現在のUI単位を維持する。
    """
    from .getPlug import getPlug as _get_plug
    from ..plugs.plug import Plug as _InputPlug
    from ..maths import Matrix, Vector

    if not kwargs:
        return _get_plug(target)
    plug = _InputPlug._resolve_input(target)
    value = cmds.getAttr(plug.getFullName(), **kwargs)
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
    kind = plug.getDataType()
    if kind == "matrix":
        return Matrix(value)
    if kind in ("double3", "float3", "long3", "short3"):
        return Vector(value[0])
    return value
