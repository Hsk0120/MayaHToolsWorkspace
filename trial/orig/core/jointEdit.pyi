# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Jointの再親付けを、回転チャンネルとSSCを保って直接実行する。"""

import maya.api.OpenMaya as om2
from .fastWrite import require_writable
from .nodeEdit import require_editable
from mlib.nodes.joint import Joint
from mlib.nodes.transform import Transform


def reparent_plan(joint: Joint, parent: Transform | None) -> tuple:
    """cmds.parentで中間Transformを必要としないJointの更新計画を作る。

    Args:
        joint (Joint): 移動するJoint。
        parent (Transform | None): 移動先。

    Returns:
        tuple: 対象、親、移動・jointOrient、新しいinverseScale入力。
    """
    ...

def reparent(plan: tuple) -> None:
    """検証済みJointを移動し、inverseScale接続と姿勢を復元する。

    Args:
        plan (tuple): reparent_planが返した計画。

    Returns:
        None: 値を返さない。
    """
    ...
