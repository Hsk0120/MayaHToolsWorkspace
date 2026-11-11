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
from ..decorator import _pick_alias, undoChunk
from ..util import _UNSET
from typing import Iterable
from mlib.nodes.dagPose import DagPose
from mlib.nodes.node import Node


def createDagPose(members: Node | str | Iterable[Node | str], name: str | None = ..., bindPose: bool = ..., hierarchy: bool = ..., *, n: str | None = ..., bp: bool = ...) -> DagPose:
    """現在の姿勢を新しいポーズに保存する。

    対象/nameを検証して保存し、指定名は保存後の改名で適用する。改名失敗でも保存は自動で戻さない。
    name・bindPoseは ``cmds.dagPose`` と同じ短縮名 ``n``・``bp`` でも受ける(長名と短縮名の同時指定はできない)。

    Args:
        members (Node | str | Iterable[Node | str]): 保存するTransformまたはJoint。
        name (str | None): 作成名。NoneならMayaの自動命名。既定None。
        bindPose (bool): バインドポーズとして保存するか。既定False。
        hierarchy (bool): TrueならMaya標準の階層保存、Falseなら指定対象のみ。
            Mayaは復元に必要な親の情報も保存する場合がある。
        n (str | None): nameの短縮名。同時指定はできない。
        bp (bool): bindPoseの短縮名。同時指定はできない。

    Returns:
        DagPose: 作成またはMayaが再利用したポーズ。

    Raises:
        TypeError: 長名と短縮名を同時に指定した場合。
        ValueError: 空対象、Transform以外、不正な名前の場合。
        RuntimeError: ノード解決・保存をMayaが拒否した場合。
    """
    ...
