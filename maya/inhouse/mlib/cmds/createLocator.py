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


def createLocator(name=None, parent=None, localPosition=(0, 0, 0), localScale=(1, 1, 1)):
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
    name = require_name(name)
    position = _finite_vector(localPosition, 3, "localPosition")
    scale = _finite_vector(localScale, 3, "localScale")
    parent_node = resolve_parent(parent)
    with undoTransaction("mlibCreateLocator"), preservedSelection():
        transform = cmds.spaceLocator(**({"name": name} if name else {}))[0]
        shape = finish_shape(transform, "locator", name, parent_node)
        if any(position):
            shape.getPlug("localPosition").set(position)
        if scale != (1.0, 1.0, 1.0):
            shape.getPlug("localScale").set(scale)
        return shape
