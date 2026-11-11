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


def createGroup(children=(), name=_UNSET, parent=None, *, world=_UNSET, n=_UNSET, w=_UNSET):
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
    # nodes はcmdsを参照するため、循環importを避けて関数内で読み込む。
    from ..nodes.node import Node
    from ..nodes.transform import Transform

    name = require_name(_pick_alias(name, n, "name", "n", default=None))
    world = _pick_alias(world, w, "world", "w", default=False)
    _require_bool(world, "world")
    if world and parent is not None:
        raise ValueError("Specify either parent or world=True, not both")
    if isinstance(children, (str, Node)):
        children = [children]
    nodes = []
    for child in children:
        node = Node._resolve_input(child)
        if not node.isValid():
            raise RuntimeError("child is not a valid node")
        if not isinstance(node, Transform):
            raise TypeError(f"child must be a transform: {node.getFullName()}")
        nodes.append(node)
    paths = [node.getFullName() for node in nodes]
    if len(set(paths)) != len(paths):
        raise ValueError("children must not contain the same node twice")
    parent_node = resolve_parent(parent)
    flags = {}
    if name:
        flags["name"] = name
    if parent_node is not None:
        flags["parent"] = parent_node.getFullName()
    elif world:
        flags["world"] = True
    with undoTransaction("mlibCreateGroup"), preservedSelection():
        if paths:
            group = cmds.group(paths, **flags)
        else:
            group = cmds.group(empty=True, **flags)
        # cmds.group は短い名前を返すため、選択(作成直後のグループ)から一意な名前を得る。
        selected = cmds.ls(selection=True, long=True)
        return Node(selected[0] if selected else group)
