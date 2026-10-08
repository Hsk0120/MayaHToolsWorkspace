"""ベース形状へblendShapeを接続し、BlendShapeオブジェクトを返す。

Examples
--------
.. code-block:: python

    bs = hlib.createBlendShape("faceMesh", name="faceBlendShape")
    bs.addTarget("smileMesh")
    bs = hlib.createBlendShape("faceMesh", targets=["smileMesh", "blinkMesh"])
"""

import maya.cmds as cmds

from .._core.flags import flag_aliases
from ..decorator import undoChunk


@flag_aliases("blendShape")
@undoChunk("hlibCreateBlendShape")
def createBlendShape(base, targets=None, **kwargs):
    """明示したベースに新しいblendShapeを作成する。

    Args:
        base (Node | str | om2.MObject | om2.MDagPath): 単一のベース形状またはTransform。
        targets (Node | str | Iterable | None): 初期ターゲット。各列は名前だけ/Nodeだけ。
            Noneまたは空列はターゲットなし。指定順がターゲット番号になる。
        **kwargs (object): Maya標準の作成フラグ。name(n)、origin(o)、
            frontOfChain(foc)、before(bf)、after(af)、topologyCheck(tc)等。
            既定値はMayaに従う。照会・編集フラグは不可。

    Returns:
        BlendShape: ベースへ接続された新しいblendShape。

    Raises:
        ValueError: 空ベース、または作成以外の操作を指定した場合。
        TypeError: 入力型や長短フラグの重複が不正な場合。
        RuntimeError: Mayaが作成を拒否した場合。

    ベースを先頭に指定する。内部のMayaコマンドではターゲット・ベースの順に並べる。
    選択から対象を推測しない。通常のUndoに対応し、fastフラグは持たない。
    """
    from ..nodes.node import Node, Nodes
    from ..nodes.blendShape import BlendShape

    operations = {"query", "edit", "geometry", "remove", "target", "inBetween",
                  "resetTargetDelta", "copyDelta", "copyInBetweenDelta", "flipTarget",
                  "mirrorTarget", "prune", "renameTarget", "removeEmptyTarget",
                  "export", "import"}
    if operations.intersection(kwargs):
        raise ValueError("createBlendShape accepts creation flags only")
    if base is None:
        raise ValueError("A base geometry is required")
    base_name = Node._input_name(base)
    target_nodes = [] if targets is None else [
        Node._resolve_input(value) for value in Nodes._resolve_inputs(targets)]
    names = [node.getFullName() for node in target_nodes]
    created = cmds.blendShape(*(names + [base_name]), **kwargs)
    return BlendShape(created[0])
