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
from ..decorator import _pick_alias
from ..util import _UNSET


def createPolyCube(width=_UNSET, height=_UNSET, depth=_UNSET, subdivisions=(1, 1, 1), name=_UNSET, parent=None, *,
        w=_UNSET, h=_UNSET, d=_UNSET, n=_UNSET):
    """原点を中心とするポリゴンの直方体を作成し、そのシェイプを返す。

    fast引数は持たない(Mayaのコマンドと同じUV・法線のメッシュをOpenMayaで組み立て直すことになり、同じ結果を保つのが難しいため)。
    width・height・depth・nameは ``cmds.polyCube`` と同じ短縮名でも受ける(長名と短縮名の同時指定はできない)。
    subdivisionsは ``subdivisionsX/Y/Z`` をまとめた独自の引数のため短縮名は無い。

    Args:
        width (float): X方向の幅(cm)。既定1。
        height (float): Y方向の高さ(cm)。既定1。
        depth (float): Z方向の奥行き(cm)。既定1。
        subdivisions (Sequence[int]): X・Y・Zの分割数(``subdivisionsX/Y/Z``)。既定(1, 1, 1)。
        name (str | None): Transformの希望名。シェイプは ``<名前>Shape``。NoneはMayaの既定名。既定None。
        parent (Node | str | None): Transformの親。Noneはワールド直下。親のローカル空間に単位マトリクスで置く。
        w (float): widthの短縮名。同時指定はできない。
        h (float): heightの短縮名。同時指定はできない。
        d (float): depthの短縮名。同時指定はできない。
        n (str | None): nameの短縮名。同時指定はできない。

    Returns:
        Mesh: 作成したメッシュのシェイプ。Transformは ``getTransform()`` で取得する。

    Raises:
        TypeError: 長名と短縮名を同時に指定した場合、または引数の型が不正な場合。
        ValueError: 大きさが0以下・有限でない、分割数・軸が不正な場合。
        RuntimeError: 親が無効な場合、またはMayaが作成を拒否した場合。
    """
    width = _pick_alias(width, w, "width", "w", default=1.0)
    height = _pick_alias(height, h, "height", "h", default=1.0)
    depth = _pick_alias(depth, d, "depth", "d", default=1.0)
    name = _pick_alias(name, n, "name", "n", default=None)
    sx, sy, sz = subdivision_counts(subdivisions, 3)
    flags = {"width": positive_size(width, "width"), "height": positive_size(height, "height"),
             "depth": positive_size(depth, "depth"), "subdivisionsX": sx, "subdivisionsY": sy, "subdivisionsZ": sz}
    return create_poly(cmds.polyCube, flags, require_name(name), resolve_parent(parent))
