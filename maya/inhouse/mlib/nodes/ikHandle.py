"""Maya の IK ハンドルを Transform として扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import maya.mel as mel

from ..decorator import undoChunk
from .node import Node
from .transform import Transform

#: :meth:`IkHandle.create` が受け付けるMaya標準のIKソルバー名。
_SOLVERS = ("ikRPsolver", "ikSCsolver", "ikSplineSolver", "ikSpringSolver")

#: :meth:`IkHandle.create` が専用の引数で扱い、``**kwargs`` では受け付けないフラグ。
_MANAGED_FLAGS = frozenset((
    "startJoint", "sj", "endEffector", "ee", "solver", "sol", "name", "n", "curve", "c",
    "createCurve", "ccv", "query", "q", "edit", "e",
))


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


class IkHandle(Transform):
    """ポールベクトルコンストレイントの作成を含むTransform操作に対応するIKハンドル。"""

    @classmethod
    def create(cls, startJoint, endJoint, solver="ikRPsolver", name=None, curve=None, **kwargs):
        """start jointからend jointまでのIKハンドルとエフェクターを作成する(``cmds.ikHandle`` 相当)。

        ``cmds.ikHandle`` 専用の特化ビルダー。エフェクター(ikEffector)はMayaの規則どおり
        end jointの1つ上のjointの子に作られ、:meth:`getEffector` で取得できる。
        ``ikSplineSolver`` で ``curve`` を省略した場合はMayaがカーブを自動作成し、
        :meth:`getCurve` で取得できる。``ikSpringSolver`` はソルバーノードが無ければMaya標準の
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
        from .joint import Joint

        managed = sorted(_MANAGED_FLAGS.intersection(kwargs))
        if managed:
            raise TypeError(f"Use the dedicated arguments instead of: {', '.join(managed)}")
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
        with undoChunk("mlibIkHandleCreate"):
            if solver == "ikSpringSolver" and not cmds.ls(type="ikSpringSolver"):
                # ikSpringSolverはソルバーノードの登録が要るため、Maya標準の手続きで用意する。
                mel.eval("ikSpringSolver")
            _record_chain_angles(start.getFullName(), end.getFullName())
            result = cmds.ikHandle(**flags)
            return cls(result[0])

    def getEffector(self):
        """IKハンドルのエフェクター(``endEffector`` の接続元)を取得する。

        Returns:
            Node | None: ikEffectorノード。未接続ならNone。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        self._require_valid("query the effector of")
        source = self._dependency_fn().findPlug("endEffector", False).source()
        return None if source.isNull else Node(source.node())

    def getCurve(self):
        """ikSplineSolverのカーブ(``inCurve`` の接続元形状の親transform)を取得する。

        Returns:
            Transform | None: カーブのtransform。inCurveが未接続(スプライン以外のソルバー等)ならNone。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        self._require_valid("query the curve of")
        source = self._dependency_fn().findPlug("inCurve", False).source()
        if source.isNull:
            return None
        shape = Node(source.node())
        parent = shape.getParent() if shape.mnode().hasFn(om2.MFn.kShape) else None
        return shape if parent is None else parent

    def getEndJoint(self):
        """IK チェーンの末端 joint を取得する。

        ikEffector ノードの translate 接続元を辿って end joint を特定する
        (``cmds.ikHandle(query=True, jointList=True)`` は end joint を含まない
        ため、別経路で解決する)。

        Returns:
            Joint | None: end joint。接続が見つからない場合は ``None``。
        """
        from .joint import Joint

        effector_plug = self.getPlug("endEffector").getSource(skipConversionNodes=False)
        if effector_plug is None:
            return None
        source = effector_plug.getNode().getPlug("translateX").getSource(skipConversionNodes=False)
        if source is None:
            return None
        return Joint(source.getNode().getFullName())

    def getJoints(self, includeTip=False):
        """IK チェーンを構成する joint を start joint から順に取得する。

        ``cmds.ikHandle(query=True, jointList=True)`` と同じ joint を、``startJoint`` の接続元から
        ``endEffector`` の接続元(ikEffector)の DAG 親を辿って OpenMaya で求める
        (ikEffector は末端 joint の1つ上の joint の子に置かれる)。

        Args:
            includeTip (bool): True の場合、末端 joint(``getEndJoint()``)も
                末尾に含める。``cmds.ikHandle(query=True, jointList=True)`` は
                既定では末端 joint を含まない。

        Returns:
            list[Joint]: start joint から順に並んだ joint。startJoint・endEffector が未接続、
                または ikEffector が start joint の子孫でない場合は空リスト。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        self._require_valid("query the joint list of")
        fn = self._dependency_fn()
        start = fn.findPlug("startJoint", False).source()
        effector = fn.findPlug("endEffector", False).source()
        joints = []
        if not start.isNull and not effector.isNull:
            start_node = start.node()
            path = om2.MDagPath.getAPathTo(effector.node())
            paths = []
            while path.length() > 1:
                path.pop()
                paths.append(om2.MDagPath(path))
                if path.node() == start_node:
                    joints = [Node(item) for item in reversed(paths)]
                    break
        if includeTip:
            tip = self.getEndJoint()
            if tip is not None:
                joints.append(tip)
        return joints
