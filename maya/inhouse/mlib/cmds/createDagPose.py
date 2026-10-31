"""現在の姿勢を新しいdagPoseに保存する(``cmds.dagPose(save=True)`` 相当)。

選択状態は参照しない。

.. code-block:: python

    import mlib

    pose = mlib.createDagPose(root, name="rest_pose")
    pose.restore()
"""

from typing import Any, Dict

import maya.cmds as cmds

from ..core.object import Object
from ..decorator import undoChunk


@undoChunk("mlibCreateDagPose")
def createDagPose(members, name=None, bindPose=False, hierarchy=True):
    """現在の姿勢を新しいポーズに保存する。

    対象/nameを検証して保存し、指定名は保存後の改名で適用する。改名失敗でも保存は自動で戻さない。

    Args:
        members (Node | str | Iterable[Node | str]): 保存するTransformまたはJoint。
        name (str | None): 作成名。NoneならMayaの自動命名。
        bindPose (bool): バインドポーズとして保存するか。
        hierarchy (bool): TrueならMaya標準の階層保存、Falseなら指定対象のみ。
            Mayaは復元に必要な親の情報も保存する場合がある。

    Returns:
        DagPose: 作成またはMayaが再利用したポーズ。

    Raises:
        ValueError: 空対象、Transform以外、不正な名前の場合。
        RuntimeError: ノード解決・保存をMayaが拒否した場合。
    """
    # nodes はcmdsを参照するため、循環importを避けて関数内で読み込む。
    from ..nodes.node import Node

    names = []
    for item in Object._input_names(members):
        node = Node(item)
        if not node.isValid() or not node.isType("transform"):
            raise ValueError(f"Expected a valid transform or joint: {item}")
        if node.getFullName() not in names:
            names.append(node.getFullName())
    if not names:
        raise ValueError("At least one transform or joint is required")
    if name is not None and (not isinstance(name, str) or not name):
        raise ValueError("name must be a non-empty string or None")
    flags: Dict[str, Any] = {"save": True, "bindPose": bindPose, "selection": not hierarchy}
    # dagPoseのnameフラグはRedo時に名前空間を失うため、renameに任せる。
    result = cmds.dagPose(names, **flags)
    if name is not None:
        result = cmds.rename(result, name)
    return Node(result)
