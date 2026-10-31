# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
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
from typing import Iterable
from mlib.nodes.dagPose import DagPose
from mlib.nodes.node import Node


def createDagPose(members: Node | str | Iterable[Node | str], name: str | None = ..., bindPose: bool = ..., hierarchy: bool = ...) -> DagPose:
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
    ...
