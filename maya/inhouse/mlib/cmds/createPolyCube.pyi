# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""ポリゴンの立方体を作成し、シェイプを返す(``cmds.polyCube(constructionHistory=False)`` 相当)。

大きさはMaya APIの内部単位(cm)で、現在のUI単位に依存しない。構築履歴は作らない。
作成・親子付けを1回のUndoにまとめ、現在の選択は変更しない。

.. code-block:: python

    import mlib

    shape = mlib.createPolyCube(width=2.0, height=1.0, depth=1.0, subdivisions=(4, 1, 1), name="box")
    transform = shape.getTransform()
"""

import maya.cmds as cmds
from ..core.shapeBuild import create_poly, positive_size, require_name, resolve_parent, subdivision_counts
from typing import Sequence
from mlib.nodes.mesh import Mesh
from mlib.nodes.node import Node


def createPolyCube(width: float = ..., height: float = ..., depth: float = ..., subdivisions: Sequence[int] = ..., name: str | None = ..., parent: Node | str | None = ...) -> Mesh:
    """原点を中心とするポリゴンの直方体を作成し、そのシェイプを返す。

    fast引数は持たない(Mayaのコマンドと同じUV・法線のメッシュをOpenMayaで組み立て直すことになり、同じ結果を保つのが難しいため)。

    Args:
        width (float): X方向の幅(cm)。既定1。
        height (float): Y方向の高さ(cm)。既定1。
        depth (float): Z方向の奥行き(cm)。既定1。
        subdivisions (Sequence[int]): X・Y・Zの分割数(``subdivisionsX/Y/Z``)。既定(1, 1, 1)。
        name (str | None): Transformの希望名。シェイプは ``<名前>Shape``。NoneはMayaの既定名。
        parent (Node | str | None): Transformの親。Noneはワールド直下。親のローカル空間に単位マトリクスで置く。

    Returns:
        Mesh: 作成したメッシュのシェイプ。Transformは ``getTransform()`` で取得する。

    Raises:
        TypeError: 引数の型が不正な場合。
        ValueError: 大きさが0以下・有限でない、分割数・軸が不正な場合。
        RuntimeError: 親が無効な場合、またはMayaが作成を拒否した場合。
    """
    ...
