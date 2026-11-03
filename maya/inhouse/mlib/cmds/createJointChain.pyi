# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""点を順につないだjointのチェーンを作り、各jointを次の点へ向けたjointのlistを返す。

各jointの aimAxis を次の点へ、upAxis を up の向きへ向ける(最後のjointは1つ前と同じ向き)。
向きは jointOrient に入れ、rotate は0にする。``cmds.joint`` で1つずつ作って ``orientJoint`` で揃える手順を
1回で行う。

.. code-block:: python

    import mlib
    from mlib.cmds.createJointChain import createJointChain

    joints = createJointChain([(0, 10, 0), (5, 10, -1), (10, 10, 0)], aimAxis="x", upAxis="y",
                              up=(0, 0, -1), names=["arm_JNT", "elbow_JNT", "wrist_JNT"])
"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..core.object import Object
from ..decorator import undoChunk
from ..maths.matrix import Matrix
from ..util import _finite_vector
from typing import Iterable, Sequence
from mlib.nodes.joint import Joint
from mlib.nodes.node import Node

_AXES: dict

def _axis(value: str, label: str) -> tuple[int, float]:
    """軸の名前を検証し、(軸の番号, 符号) を返す。

    Args:
        value (str): ``"x"``・``"y"``・``"z"``・``"-x"``・``"-y"``・``"-z"``。
        label (str): 例外メッセージに使う引数名。

    Returns:
        tuple[int, float]: 軸の番号(0〜2)と符号。

    Raises:
        TypeError: 文字列でない場合。
        ValueError: 対応しない名前の場合。
    """
    ...

def createJointChain(points: Iterable[Sequence[float]], *, aimAxis: str = ..., upAxis: str = ..., up: Sequence[float] = ..., names: Sequence[str] | None = ..., parent: str | Node | None = ...) -> list[Joint]:
    """点を順につないだjointのチェーンを作る。

    1つ目のjointを parent の子に、以降を1つ前のjointの子に作る。各jointの aimAxis を次の点へ向け、
    upAxis を up を aim に垂直にした向きへ向ける(最後のjointは1つ前のjointと同じ向き)。向きは
    jointOrient に入れ、rotate・rotateAxis は0のまま。inverseScale は親がjointならその scale へ接続する。
    選択は変更しない。fast引数は持たない。Undo有効時は1回で戻せる。

    Args:
        points (Iterable[Sequence[float]]): ワールド空間の位置(cm)の列。2点以上で、隣り合う点は別の位置。
        aimAxis (str): 次の点へ向ける軸。``"x"`` (既定)・``"y"``・``"z"``・``"-x"``・``"-y"``・``"-z"``。
        upAxis (str): up の向きへ向ける軸。aimAxis と別の軸。既定 ``"y"``。
        up (Sequence[float]): ワールド空間の上方向の目安。既定 ``(0, 1, 0)``。
        names (Sequence[str] | None): jointの名前。points と同じ数。Noneは ``joint#`` (Mayaの連番)。
        parent (str | Node | None): 1つ目のjointの親のtransform。Noneはワールド。

    Returns:
        list[Joint]: 作ったjoint。points の順。

    Raises:
        TypeError: points・up の成分が数値でない、aimAxis・upAxis が文字列でない、names が文字列の列・None以外、
            または parent がtransformでない場合。
        ValueError: 点が2つ未満、隣り合う点が同じ位置、軸の名前が不正・同じ軸、names の数が points と違う・空の名前を含む、
            up が0、または up が向ける方向とほぼ平行な場合。
        RuntimeError: parent の名前が存在しない、またはMayaが作成を拒否した場合。

    Note:
        parent のスケールが1でない場合も位置と向きは parent のワールドのマトリクスで換算するが、
        segmentScaleCompensate による補正は考慮しない。
    """
    ...
