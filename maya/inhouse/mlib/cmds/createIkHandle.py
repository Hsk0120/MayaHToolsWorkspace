"""start jointからend jointまでのIKハンドルとエフェクターを作成する(``cmds.ikHandle`` 相当)。

.. code-block:: python

    import mlib

    handle = mlib.createIkHandle(shoulder, wrist, solver="ikRPsolver", name="arm_ikh")
    effector = handle.getEffector()

    # cmds.ikHandle と同じ短縮名でも指定できる。
    handle = mlib.createIkHandle(sj=shoulder, ee=wrist, sol="ikSCsolver", n="arm_sc_ikh")
"""

import maya.cmds as cmds
import maya.mel as mel

from ..decorator import _pick_alias, undoChunk
from ..util import _UNSET

#: ``createIkHandle`` が受け付けるMaya標準のIKソルバー名。
_SOLVERS = ("ikRPsolver", "ikSCsolver", "ikSplineSolver", "ikSpringSolver")

#: ``**kwargs`` では受け付けないフラグ。``endEffector`` は ``endJoint``(短縮名 ``ee``)、
#: ``createCurve`` は ``curve`` の有無で決め、query・editは作成専用のため受け付けない。
_REJECTED_FLAGS = frozenset(("endEffector", "createCurve", "ccv", "query", "q", "edit", "e"))


def _record_chain_angles(start, end):
    """IKチェーンのjointの角度アトリビュートを現在値で書き直し、Undoで戻せるようにする。

    ``cmds.ikHandle`` はpreferredAngle等をUndoに記録せずに書き換えるため、作成前に同じ値を
    cmds.setAttrで書いて元の値をUndoへ記録する。ロック・入力接続のあるアトリビュートは対象外。

    Args:
        start (str): 開始jointの完全パス。
        end (str): 末端jointの完全パス。

    Returns:
        None: 値を返さない。
    """
    joint = end
    while joint:
        for attribute in ("preferredAngle", "fkRotate", "ikRotate"):
            plug = joint + "." + attribute
            if cmds.getAttr(plug, settable=True):
                cmds.setAttr(plug, *cmds.getAttr(plug)[0])
        if joint == start:
            break
        parents = cmds.listRelatives(joint, parent=True, fullPath=True)
        joint = parents[0] if parents else None


def createIkHandle(startJoint=_UNSET, endJoint=_UNSET, solver=_UNSET, name=_UNSET, curve=_UNSET, *,
        sj=_UNSET, ee=_UNSET, sol=_UNSET, n=_UNSET, c=_UNSET, **kwargs):
    """start jointからend jointまでのIKハンドルとエフェクターを作成する。

    エフェクター(ikEffector)はMayaの規則どおりend jointの1つ上のjointの子に作られ、:meth:`~mlib.nodes.IkHandle.getEffector` で取得できる。
    ``ikSplineSolver`` で ``curve`` を省略した場合はMayaがカーブを自動作成し、
    :meth:`~mlib.nodes.IkHandle.getCurve` で取得できる。``ikSpringSolver`` はソルバーノードが無ければMaya標準の
    ``ikSpringSolver`` で用意する。Mayaの規則どおり作成したハンドルが選択される。
    Mayaがチェーンのjointへ自動で設定するpreferredAngleも、Undoで作成前の値に戻す
    (``cmds.ikHandle`` 単体のUndoでは戻らない)。
    fast引数は持たない(OpenMayaにIKハンドル作成の同等機能が無い)。Undo有効時は1回で戻せる。
    ``mlib.createNode("ikHandle")`` は従来どおり未接続のノードだけを作る。
    専用引数は ``cmds.ikHandle`` と同じ短縮名でも受ける(長名と短縮名の同時指定はできない)。

    Args:
        startJoint (str | Node): チェーンの開始joint。必須。
        endJoint (str | Node): チェーンの末端joint(``cmds.ikHandle`` の ``endEffector``)。startJointの子孫であること。必須。
        solver (str): ``"ikRPsolver"``・``"ikSCsolver"``・``"ikSplineSolver"``・``"ikSpringSolver"``。
            既定 ``"ikRPsolver"``。
        name (str | None): ハンドルの作成名。NoneならMayaの自動命名。既定None。
        curve (str | Node | None): ikSplineSolverで使う既存カーブ(transformまたはnurbsCurve)。
            Noneなら自動作成する。ikSplineSolver以外では指定できない。既定None。
        sj (str | Node): startJointの短縮名。同時指定はできない。
        ee (str | Node): endJointの短縮名(Mayaの ``endEffector``)。同時指定はできない。
        sol (str): solverの短縮名。同時指定はできない。
        n (str | None): nameの短縮名。同時指定はできない。
        c (str | Node | None): curveの短縮名。同時指定はできない。
        **kwargs (object): ``cmds.ikHandle`` のその他のフラグ(``priority``・``numSpans``・
            ``parentCurve`` 等)。そのままMayaへ渡す。``endEffector``(``endJoint`` で指定する)・
            ``createCurve``(``curve`` の有無で決まる)・query・editは受け付けない。

    Returns:
        IkHandle: 作成したIKハンドル。

    Raises:
        TypeError: 長名と短縮名を同時に指定した、startJoint・endJointを省略した、``**kwargs`` で受け付けない
            フラグを渡した、nameが文字列・None以外、または対象が対応しない型の場合。
        ValueError: solverが対応外、ikSplineSolver以外でcurveを指定した、start/endがjointでない、
            endJointがstartJointの子孫でない、またはnameが空文字列の場合。
        RuntimeError: 名前を解決できない、またはMayaが作成を拒否した場合。

    Note:
        シーンで最初のIKハンドル作成時にMayaが作るソルバーノード(ikRPsolver等)は、
        ``cmds.ikHandle`` と同じくUndoしても残る。
    """
    # nodes はcmdsを参照するため、循環importを避けて関数内で読み込む。
    from ..nodes.joint import Joint
    from ..nodes.node import Node

    startJoint = _pick_alias(startJoint, sj, "startJoint", "sj")
    endJoint = _pick_alias(endJoint, ee, "endJoint", "ee")
    solver = _pick_alias(solver, sol, "solver", "sol", default="ikRPsolver")
    name = _pick_alias(name, n, "name", "n", default=None)
    curve = _pick_alias(curve, c, "curve", "c", default=None)
    rejected = sorted(_REJECTED_FLAGS.intersection(kwargs))
    if rejected:
        raise TypeError(f"createIkHandle does not accept: {', '.join(rejected)}")
    if solver not in _SOLVERS:
        raise ValueError(f"solver must be one of {', '.join(_SOLVERS)}: {solver!r}")
    if name is not None and not isinstance(name, str):
        raise TypeError("name must be a string or None")
    if name == "":
        raise ValueError("name must be a non-empty string or None")
    if curve is not None and solver != "ikSplineSolver":
        raise ValueError("curve can only be used with ikSplineSolver")
    start = Node._resolve_input(startJoint)
    end = Node._resolve_input(endJoint)
    for role, joint in (("startJoint", start), ("endJoint", end)):
        if not joint.isValid() or not isinstance(joint, Joint):
            raise ValueError(f"{role} must be a valid joint")
    if not start.isAncestorOf(end):
        raise ValueError("endJoint must be a descendant of startJoint")
    flags = dict(kwargs)
    flags.update(startJoint=start.getFullName(), endEffector=end.getFullName(), solver=solver)
    if name is not None:
        flags["name"] = name
    if curve is not None:
        flags["curve"] = Node._input_name(curve)
        flags["createCurve"] = False
    with undoChunk("mlibCreateIkHandle"):
        if solver == "ikSpringSolver" and not cmds.ls(type="ikSpringSolver"):
            # ikSpringSolverはソルバーノードの登録が要るため、Maya標準の手続きで用意する。
            mel.eval("ikSpringSolver")
        _record_chain_angles(start.getFullName(), end.getFullName())
        result = cmds.ikHandle(**flags)
        return Node(result[0])
