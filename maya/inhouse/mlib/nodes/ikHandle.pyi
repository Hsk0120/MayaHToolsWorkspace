# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の IK ハンドルを Transform として扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import maya.mel as mel
from ..decorator import undoChunk
from .node import Node
from .transform import Transform
from mlib.nodes.joint import Joint

_SWITCHABLE_SOLVERS: tuple


class IkHandle(Transform):
    """ポールベクトルコンストレイントの作成を含むTransform操作に対応するIKハンドル。"""
    def getEffector(self) -> Node | None:
        """IKハンドルのエフェクター(``endEffector`` の接続元)を取得する。

        Returns:
            Node | None: ikEffectorノード。未接続ならNone。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        ...
    def getCurve(self) -> Transform | None:
        """ikSplineSolverのカーブ(``inCurve`` の接続元形状の親transform)を取得する。

        Returns:
            Transform | None: カーブのtransform。inCurveが未接続(スプライン以外のソルバー等)ならNone。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        ...
    def getEndJoint(self) -> Joint | None:
        """IK チェーンの末端 joint を取得する。

        ikEffector ノードの translate 接続元を辿って end joint を特定する
        (``cmds.ikHandle(query=True, jointList=True)`` は end joint を含まない
        ため、別経路で解決する)。

        Returns:
            Joint | None: end joint。接続が見つからない場合は ``None``。
        """
        ...
    def getJoints(self, includeTip: bool = ...) -> list[Joint]:
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
        ...
    def getSolver(self) -> str | None:
        """ハンドルが使うIKソルバーの種類(``ikSolver`` の接続元ノードの型名)を取得する。

        Returns:
            str | None: ``"ikRPsolver"``・``"ikSCsolver"``・``"ikSplineSolver"``・``"ikSpringSolver"`` 等。
                ソルバーが未接続ならNone。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        ...
    def setSolver(self, solver: str) -> IkHandle:
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
        ...
    def snapToEffector(self) -> IkHandle:
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
        ...
