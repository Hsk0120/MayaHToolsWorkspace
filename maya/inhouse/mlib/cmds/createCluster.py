"""形状・コンポーネントにclusterを作成し、clusterデフォーマーを返す(``cmds.cluster`` 相当)。

ハンドル(clusterHandleを持つtransform)は :meth:`Cluster.getWeightedNode <mlib.nodes.cluster.Cluster.getWeightedNode>`
で取得する。作成を1回のUndoにまとめ、現在の選択は変更しない。

.. code-block:: python

    import mlib

    cluster = mlib.createCluster("body_geo.vtx[0:20]", name="chest_cluster")
    handle = cluster.getWeightedNode()
"""

import maya.cmds as cmds

from ..core.object import Object
from ..core.shapeBuild import require_name
from ..decorator import _pick_alias, _require_bool, preservedSelection, undoChunk
from ..util import _UNSET


def createCluster(targets, name=_UNSET, relative=_UNSET, *, n=_UNSET, rel=_UNSET):
    """形状またはコンポーネントにclusterを作成する。

    選択状態は参照しない。fast引数は持たない(OpenMayaにデフォーマー作成の同等機能が無い)。
    Undo有効時は1回で戻せる。name・relativeは ``cmds.cluster`` と同じ短縮名 ``n``・``rel`` でも受ける
    (長名と短縮名の同時指定はできない)。

    Args:
        targets (str | Node | Component | Iterable): 変形する形状・そのtransform・コンポーネント
            (``"body_geo.vtx[0:20]"``・:class:`~mlib.components.vertex.Vertices` 等)。
        name (str | None): clusterの作成名。ハンドルは ``<名前>Handle``。NoneはMayaの既定名。既定None。
        relative (bool): Trueはハンドルの親の変換を無視し、ハンドル自身の変換だけで変形する。既定False。
        n (str | None): nameの短縮名。同時指定はできない。
        rel (bool): relativeの短縮名。同時指定はできない。

    Returns:
        Cluster: 作成したcluster。

    Raises:
        TypeError: 長名と短縮名を同時に指定した場合、relativeがbool以外、nameが文字列・None以外、
            または対象が対応しない型の場合。
        ValueError: nameが空文字列・``|`` を含む、または対象が空・無効な場合。
        RuntimeError: 名前を解決できない、またはMayaが作成を拒否した場合。

    Examples:
        .. code-block:: python

            cluster = mlib.createCluster(shape.getVertices([0, 1, 2]), relative=True)
            cluster.getWeightedNode().setTranslation((0, 1, 0))
    """
    # nodes はcmdsを参照するため、循環importを避けて関数内で読み込む。
    from ..nodes.node import Node

    name = require_name(_pick_alias(name, n, "name", "n", default=None))
    relative = _pick_alias(relative, rel, "relative", "rel", default=False)
    _require_bool(relative, "relative")
    target_names = Object._input_names(targets, allow_plugs=False)
    if not target_names:
        raise ValueError("At least one target is required")
    flags = {"relative": relative}
    if name is not None:
        flags["name"] = name
    with undoChunk("mlibCreateCluster"), preservedSelection():
        result = cmds.cluster(*target_names, **flags)
        return Node(result[0])
