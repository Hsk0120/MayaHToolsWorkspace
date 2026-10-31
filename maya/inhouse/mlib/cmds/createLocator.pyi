# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""ロケーターを作成し、シェイプを返す(``cmds.spaceLocator`` 相当)。

localPosition・localScale はシェイプのアトリビュートの値で、単位はMaya APIの内部単位(cm)。
作成・親子付けを1回のUndoにまとめ、現在の選択は変更しない。

.. code-block:: python

    import mlib

    shape = mlib.createLocator(name="pole", localScale=(2, 2, 2))
    shape.getTransform().setTranslation((0, 5, -10))
"""

import maya.cmds as cmds
from ..core.shapeBuild import finish_shape, require_name, resolve_parent
from ..decorator import preservedSelection, undoTransaction
from ..util import _finite_vector
from typing import Sequence
from mlib.nodes.locator import Locator
from mlib.nodes.node import Node


def createLocator(name: str | None = ..., parent: Node | str | None = ..., localPosition: Sequence[float] = ..., localScale: Sequence[float] = ...) -> Locator:
    """Transformとlocatorシェイプを作成し、シェイプを返す。

    位置はTransformで動かす。localPosition はシェイプの表示だけをずらす(``spaceLocator`` の
    ``position`` と同じアトリビュート)。fast引数は持たない(OpenMayaで作っても約1.2倍で、効果がほぼ無いため)。

    Args:
        name (str | None): Transformの希望名。シェイプは ``<名前>Shape``。NoneはMayaの既定名(``locator1`` 等)。
        parent (Node | str | None): Transformの親。Noneはワールド直下。親のローカル空間に単位マトリクスで置く。
        localPosition (Sequence[float]): シェイプの localPosition(cm)。既定(0, 0, 0)。
        localScale (Sequence[float]): シェイプの localScale。既定(1, 1, 1)。

    Returns:
        Locator: 作成したロケーターのシェイプ。Transformは ``getTransform()`` で取得する。

    Raises:
        TypeError: 引数の型が不正な場合。
        ValueError: localPosition・localScaleの成分数が3でない、または有限でない場合。
        RuntimeError: 親が無効な場合、またはMayaが作成を拒否した場合。
    """
    ...
