# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""子を入れたグループ(空のtransform)を作り、Transformを返す(``cmds.group`` 相当)。

子はワールドの姿勢を保ってグループの下へ移す。グループのピボットはMayaと同じく子のバウンディングボックスの
中心に置く。作成・親子付けを1回のUndoにまとめ、現在の選択は変更しない。

.. code-block:: python

    import mlib

    offset = mlib.createGroup(["arm_CTRL"], name="arm_CTRL_offset")
    empty = mlib.createGroup(name="rig_GRP")

    # cmds.group と同じ短縮名でも指定できる。
    world_group = mlib.createGroup(["hand_JNT"], n="hand_GRP", w=True)
"""

import maya.cmds as cmds
from ..core.shapeBuild import require_name, resolve_parent
from ..decorator import _pick_alias, _require_bool, preservedSelection, undoTransaction
from ..util import _UNSET
from typing import Iterable
from mlib.nodes.node import Node
from mlib.nodes.transform import Transform


def createGroup(children: Iterable[Node | str] | Node | str = ..., name: str | None = ..., parent: Node | str | None = ..., *, world: bool = ..., n: str | None = ..., w: bool = ...) -> Transform:
    """子を入れたグループを作り、グループのTransformを返す。

    children を省略するとワールド(または parent)の直下に空のグループを作る(``cmds.group(empty=True)``)。
    children を渡した場合、parent も world も指定しなければMayaと同じく子の共通の親の下に作る。
    子はワールドの姿勢を保って移し、グループのピボットは子のバウンディングボックスの中心に置く。
    fast引数は持たない(OpenMayaで作っても効果がほぼ無いため)。Undo有効時は1回で戻せる。
    name・world は ``cmds.group`` と同じ短縮名 ``n``・``w`` でも受ける(長名と短縮名の同時指定はできない)。
    parentの短縮名は無い。

    Args:
        children (Iterable[Node | str] | Node | str): グループに入れるtransform。1つならそのまま渡せる。既定は空。
        name (str | None): グループの希望名。NoneはMayaの既定名(``group1`` 等)。既定None。
        parent (Node | str | None): グループの親のtransform。Noneは指定しない。
        world (bool): Trueはワールド直下に作る。parentとは同時に指定できない。既定False。
        n (str | None): nameの短縮名。同時指定はできない。
        w (bool): worldの短縮名。同時指定はできない。

    Returns:
        Transform: 作成したグループ。

    Raises:
        TypeError: 長名と短縮名を同時に指定した、nameが文字列・None以外、worldがbool以外、childrenの要素・parentが
            transformでない、または対応しない型の場合。
        ValueError: nameが空文字列・``|`` を含む、parentとworld=Trueを同時に指定した、
            または同じ子を重ねて渡した場合。
        RuntimeError: 子・親の名前を解決できない・無効な場合、親が子の子孫の場合など、Mayaが作成を拒否した場合。

    Examples:
        >>> offset = mlib.createGroup(ctrl, name=ctrl.getName() + "_offset")
        >>> offset.getChildren()[0] == ctrl
        True
    """
    ...
