# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""形状を作る関数(``mlib.createCurve`` 等)が共有する、名前・親・シェイプ名の後処理。"""

import maya.cmds as cmds
from ..decorator import nativeUnits, preservedSelection, undoTransaction
from ..util import _finite
from typing import Any, Callable, Sequence
from mlib.nodes.mesh import Mesh
from mlib.nodes.node import Node


def require_name(name: str | None) -> str | None:
    """作成名を検証する。

    Args:
        name (str | None): 作成名。Noneは Maya の既定名。

    Returns:
        str | None: 検証した名前。

    Raises:
        TypeError: nameが文字列・None以外の場合。
        ValueError: nameが空文字列、またはDAGパスの区切り ``|`` を含む場合。
    """
    ...

def resolve_parent(parent: Node | str | None) -> Node | None:
    """親の入力をTransformへ解決する。

    Args:
        parent (Node | str | None): 親。Noneはワールド直下。

    Returns:
        Node | None: 解決した親。

    Raises:
        TypeError: 親がTransformでない場合。
        RuntimeError: 親が無効な場合。
    """
    ...

def finish_shape(transform: str, kind: str, name: str | None, parent: Node | None) -> Node:
    """作成した Transform を親へ移し、シェイプ名をそろえてシェイプのラッパーを返す。

    Args:
        transform (str): Mayaのコマンドが返したTransformの名前。
        kind (str): 返すシェイプの型(``"nurbsCurve"`` 等)。
        name (str | None): 作成名。指定時はシェイプを ``<Transform名>Shape`` にする。
        parent (Node | None): 解決済みの親。Noneはワールド直下のまま。

    Returns:
        Node: 作成したシェイプのラッパー。
    """
    ...

def positive_size(value: float, name: str) -> float:
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
    ...

def subdivision_counts(value: Sequence[int], size: int, name: str = ...) -> tuple[int, ...]:
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
    ...

def create_poly(command: Callable[..., Any], flags: dict, name: str | None, parent: Node | None) -> Mesh:
    """ポリゴンのプリミティブを構築履歴なしで作り、シェイプを返す。

    Args:
        command (callable): ``cmds.polyCube`` 等。
        flags (dict): コマンドへ渡すフラグ(距離はcm)。
        name (str | None): 検証済みの作成名。
        parent (Node | None): 解決済みの親。

    Returns:
        Mesh: 作成したシェイプ。
    """
    ...
