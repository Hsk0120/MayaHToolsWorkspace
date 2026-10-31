# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""start jointからend jointまでのIKハンドルとエフェクターを作成する(``cmds.ikHandle`` 相当)。

.. code-block:: python

    import mlib

    handle = mlib.createIkHandle(shoulder, wrist, solver="ikRPsolver", name="arm_ikh")
    effector = handle.getEffector()
"""

import maya.cmds as cmds
import maya.mel as mel
from ..decorator import undoChunk
from mlib.nodes.ikHandle import IkHandle
from mlib.nodes.node import Node

_SOLVERS: tuple
_MANAGED_FLAGS: frozenset

def _record_chain_angles(start: str, end: str) -> None:
    """IKチェーンのjointの角度アトリビュートを現在値で書き直し、Undoで戻せるようにする。

    ``cmds.ikHandle`` はpreferredAngle等をUndoに記録せずに書き換えるため、作成前に同じ値を
    cmds.setAttrで書いて元の値をUndoへ記録する。ロック・入力接続のあるアトリビュートは対象外。

    Args:
        start (str): 開始jointの完全パス。
        end (str): 末端jointの完全パス。

    Returns:
        None: 値を返さない。
    """
    ...

def createIkHandle(startJoint: str | Node, endJoint: str | Node, solver: str = ..., name: str | None = ..., curve: str | Node | None = ..., **kwargs: object) -> IkHandle:
    """start jointからend jointまでのIKハンドルとエフェクターを作成する。

    エフェクター(ikEffector)はMayaの規則どおりend jointの1つ上のjointの子に作られ、:meth:`~mlib.nodes.IkHandle.getEffector` で取得できる。
    ``ikSplineSolver`` で ``curve`` を省略した場合はMayaがカーブを自動作成し、
    :meth:`~mlib.nodes.IkHandle.getCurve` で取得できる。``ikSpringSolver`` はソルバーノードが無ければMaya標準の
    ``ikSpringSolver`` で用意する。Mayaの規則どおり作成したハンドルが選択される。
    Mayaがチェーンのjointへ自動で設定するpreferredAngleも、Undoで作成前の値に戻す
    (``cmds.ikHandle`` 単体のUndoでは戻らない)。
    fast引数は持たない(OpenMayaにIKハンドル作成の同等機能が無い)。Undo有効時は1回で戻せる。
    ``mlib.createNode("ikHandle")`` は従来どおり未接続のノードだけを作る。

    Args:
        startJoint (str | Node): チェーンの開始joint。
        endJoint (str | Node): チェーンの末端joint。startJointの子孫であること。
        solver (str): ``"ikRPsolver"``・``"ikSCsolver"``・``"ikSplineSolver"``・``"ikSpringSolver"``。
        name (str | None): ハンドルの作成名。NoneならMayaの自動命名。
        curve (str | Node | None): ikSplineSolverで使う既存カーブ(transformまたはnurbsCurve)。
            Noneなら自動作成する。ikSplineSolver以外では指定できない。
        **kwargs (object): ``cmds.ikHandle`` のその他のフラグ(``priority``・``numSpans``・
            ``parentCurve`` 等)。そのままMayaへ渡す。

    Returns:
        IkHandle: 作成したIKハンドル。

    Raises:
        TypeError: 専用引数で扱うフラグを ``**kwargs`` に渡した場合、nameが文字列・None以外、
            または対象が対応しない型の場合。
        ValueError: solverが対応外、ikSplineSolver以外でcurveを指定した、start/endがjointでない、
            endJointがstartJointの子孫でない、またはnameが空文字列の場合。
        RuntimeError: 名前を解決できない、またはMayaが作成を拒否した場合。

    Note:
        シーンで最初のIKハンドル作成時にMayaが作るソルバーノード(ikRPsolver等)は、
        ``cmds.ikHandle`` と同じくUndoしても残る。
    """
    ...
