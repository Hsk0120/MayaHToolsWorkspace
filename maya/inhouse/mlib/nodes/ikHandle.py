"""Maya の IK ハンドルを Transform として扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import maya.mel as mel

from ..decorator import undoChunk
from .node import Node
from .transform import Transform

#: :meth:`IkHandle.setSolver` で切り替えられるソルバー(ikSplineSolver はカーブが要るため対象外)。
_SWITCHABLE_SOLVERS = ("ikRPsolver", "ikSCsolver", "ikSpringSolver")


class IkHandle(Transform):
    """ポールベクトルコンストレイントの作成を含むTransform操作に対応するIKハンドル。"""

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
        source_node = source.node()
        shape = Node(source_node)
        parent = shape.getParent() if source_node.hasFn(om2.MFn.kShape) else None
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

        effector_plug = self.getPlug("endEffector").getSource()
        if effector_plug is None:
            return None
        source = effector_plug.getNode().getPlug("translateX").getSource()
        if source is None:
            return None
        return Joint(source.getNode().getFullName())

    def getJoints(self, includeTip=False):
        """IK チェーンを構成する joint を start joint から順に取得する。

        ``cmds.ikHandle(query=True, jointList=True)`` と同じ joint を、``startJoint`` の接続元から
        ``endEffector`` の接続元(ikEffector)の DAG 親を辿って OpenMaya で求める
        (ikEffector は末端 joint の1つ上の joint の子に置かれる)。

        既定(``includeTip=False``)は末端 joint を含まない。末端まで含めたチェーン全体は
        ``getJoints(includeTip=True)`` で取得する。

        Args:
            includeTip (bool): True の場合、末端 joint(``getEndJoint()``)も
                末尾に含める。既定 False は ``cmds.ikHandle(query=True, jointList=True)`` と同じく
                末端 joint を含まない。

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

    def getSolver(self):
        """ハンドルが使うIKソルバーの種類(``ikSolver`` の接続元ノードの型名)を取得する。

        Returns:
            str | None: ``"ikRPsolver"``・``"ikSCsolver"``・``"ikSplineSolver"``・``"ikSpringSolver"`` 等。
                ソルバーが未接続ならNone。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        self._require_valid("query the solver of")
        source = self._dependency_fn().findPlug("ikSolver", False).source()
        return None if source.isNull else om2.MFnDependencyNode(source.node()).typeName

    def setSolver(self, solver):
        """ハンドルのIKソルバーを切り替える(``cmds.ikHandle(edit=True, solver=...)`` 相当)。

        ``ikSpringSolver`` はソルバーノードが無ければMaya標準の手続きで用意する(:func:`~mlib.cmds.createIkHandle`
        と同じ)。ikSplineSolverへの切替え・ikSplineSolverからの切替えはカーブの扱いが変わるため受け付けない。
        Undo有効時に1回のUndoで戻る(Mayaが新しく作ったソルバーノードはUndoしても残る)。

        Args:
            solver (str): ``"ikRPsolver"``・``"ikSCsolver"``・``"ikSpringSolver"`` のいずれか。

        Returns:
            IkHandle: 自身。

        Raises:
            TypeError: solverが文字列でない場合。
            ValueError: solverが対応外、またはハンドルがikSplineSolverを使っている場合。
            RuntimeError: ノードが無効、またはMayaが切替えを拒否した場合。
        """
        if not isinstance(solver, str):
            raise TypeError(f"solver must be a string: {solver!r}")
        if solver not in _SWITCHABLE_SOLVERS:
            raise ValueError(f"solver must be one of {', '.join(_SWITCHABLE_SOLVERS)}: {solver!r}")
        if self.getSolver() == "ikSplineSolver":
            raise ValueError(f"Cannot switch the solver of a spline IK handle: {self.getFullName()}")
        with undoChunk("mlibIkHandleSetSolver"):
            if solver == "ikSpringSolver" and not cmds.ls(type="ikSpringSolver"):
                # ikSpringSolverはソルバーノードの登録が要るため、Maya標準の手続きで用意する。
                mel.eval("ikSpringSolver")
            cmds.ikHandle(self.getFullName(), edit=True, solver=solver)
        return self

    def snapToEffector(self):
        """ハンドルをエフェクターの位置へ移す(IK Handle の Snap Handle to Effector と同じ操作)。

        エフェクターの回転ピボットのワールド位置へ、ハンドルの回転ピボットが重なるようtranslateを書き換える
        (:meth:`~mlib.nodes.transform.Transform.setTranslation` の ``worldSpace=True``)。
        IKとFKを切り替えるときに、FKで動かしたチェーンの先端へハンドルを合わせる用途に使う。
        ``cmds.ikHandle(edit=True, snapHandleToEffector=True)`` は ``snapEnable`` が無効のハンドルを動かさないため使わない。
        Undo有効時に1回のUndoで戻る。fast引数は持たない。

        Returns:
            IkHandle: 自身。

        Raises:
            RuntimeError: ノードが無効、エフェクターが未接続、またはtranslateがロック・入力接続で書き込めない場合。
        """
        self._require_valid("snap")
        effector = self.getEffector()
        if effector is None:
            raise RuntimeError(f"IK handle has no end effector: {self.getFullName()}")
        with undoChunk("mlibIkHandleSnapToEffector"):
            self.setTranslation(effector.getTranslation(worldSpace=True), worldSpace=True)
        return self
