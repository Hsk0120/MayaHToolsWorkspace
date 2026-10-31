"""形状を作る関数(``mlib.createCurve`` 等)が共有する、名前・親・シェイプ名の後処理。"""

import maya.cmds as cmds

from ..decorator import nativeUnits, preservedSelection, undoTransaction
from ..util import _finite


def require_name(name):
    """作成名を検証する。

    Args:
        name (str | None): 作成名。Noneは Maya の既定名。

    Returns:
        str | None: 検証した名前。

    Raises:
        TypeError: nameが文字列・None以外の場合。
        ValueError: nameが空文字列、またはDAGパスの区切り ``|`` を含む場合。
    """
    if name is None:
        return None
    if not isinstance(name, str):
        raise TypeError(f"name must be a str or None, got {type(name).__name__}")
    if not name or "|" in name:
        raise ValueError(f"name must be a non-empty name without '|': {name!r}")
    return name


def resolve_parent(parent):
    """親の入力をTransformへ解決する。

    Args:
        parent (Node | str | None): 親。Noneはワールド直下。

    Returns:
        Node | None: 解決した親。

    Raises:
        TypeError: 親がTransformでない場合。
        RuntimeError: 親が無効な場合。
    """
    if parent is None:
        return None
    # nodes は core を参照するため、循環importを避けて呼出し時に読み込む。
    from ..nodes.node import Node
    from ..nodes.transform import Transform

    node = Node._resolve_input(parent)
    if not node.isValid():
        raise RuntimeError("parent is not a valid node")
    if not isinstance(node, Transform):
        raise TypeError(f"parent must be a transform: {node.getFullName()}")
    return node


def finish_shape(transform, kind, name, parent):
    """作成した Transform を親へ移し、シェイプ名をそろえてシェイプのラッパーを返す。

    Args:
        transform (str): Mayaのコマンドが返したTransformの名前。
        kind (str): 返すシェイプの型(``"nurbsCurve"`` 等)。
        name (str | None): 作成名。指定時はシェイプを ``<Transform名>Shape`` にする。
        parent (Node | None): 解決済みの親。Noneはワールド直下のまま。

    Returns:
        Node: 作成したシェイプのラッパー。
    """
    # nodes は core を参照するため、循環importを避けて呼出し時に読み込む。
    from ..nodes.node import Node

    transform = cmds.ls(transform, long=True)[0]
    if parent is not None:
        transform = cmds.ls(cmds.parent(transform, parent.getFullName(), relative=True)[0], long=True)[0]
    shape = cmds.listRelatives(transform, shapes=True, fullPath=True, type=kind)[0]
    if name:
        expected = transform.rsplit("|", 1)[-1] + "Shape"
        if shape.rsplit("|", 1)[-1] != expected:
            shape = cmds.rename(shape, expected)
            shape = cmds.ls(transform + "|" + shape.rsplit("|", 1)[-1], long=True)[0]
    return Node(shape)


def positive_size(value, name):
    """正の有限な大きさを検証する。

    Args:
        value (float): 大きさ。boolは受け付けない。
        name (str): 例外メッセージに使う引数名。

    Returns:
        float: 検証した値。

    Raises:
        TypeError: 実数以外の場合。
        ValueError: 0以下・無限大・NaNの場合。
    """
    value = _finite(value, name)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def subdivision_counts(value, size, name="subdivisions"):
    """分割数のタプルを検証する。

    Args:
        value (Sequence[int]): 分割数。各要素は1以上のint(boolを除く)。
        size (int): 要素数。
        name (str): 例外メッセージに使う引数名。

    Returns:
        tuple[int, ...]: 検証した分割数。

    Raises:
        TypeError: 反復できない、またはint以外を含む場合。
        ValueError: 要素数が違う、または1未満を含む場合。
    """
    try:
        items = tuple(value)
    except TypeError:
        raise TypeError(f"{name} must be a sequence of {size} ints") from None
    if len(items) != size:
        raise ValueError(f"{name} must have {size} values")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in items):
        raise TypeError(f"{name} must contain ints")
    if any(item < 1 for item in items):
        raise ValueError(f"{name} must be 1 or more")
    return items


def create_poly(command, flags, name, parent):
    """ポリゴンのプリミティブを構築履歴なしで作り、シェイプを返す。

    Args:
        command (callable): ``cmds.polyCube`` 等。
        flags (dict): コマンドへ渡すフラグ(距離はcm)。
        name (str | None): 検証済みの作成名。
        parent (Node | None): 解決済みの親。

    Returns:
        Mesh: 作成したシェイプ。
    """
    flags = dict(flags, constructionHistory=False)
    if name:
        flags["name"] = name
    with undoTransaction("mlibCreate" + command.__name__[0].upper() + command.__name__[1:]), preservedSelection():
        # ポリゴンのコマンドの大きさは現在のUI単位で解釈されるため、内部単位(cm)へ切り替えて渡す。
        with nativeUnits():
            transform = command(**flags)[0]
        return finish_shape(transform, "mesh", name, parent)
