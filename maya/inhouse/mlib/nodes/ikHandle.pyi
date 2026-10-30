# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の IK ハンドルを Transform として扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import maya.mel as mel
from ..decorator import undoChunk
from .node import Node
from .transform import Transform
from mlib.nodes.joint import Joint

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


class IkHandle(Transform):
    """ポールベクトルコンストレイントの作成を含むTransform操作に対応するIKハンドル。"""
    @classmethod
    def create(cls, startJoint: str | Node, endJoint: str | Node, solver: str = ..., name: str | None = ..., curve: str | Node | None = ..., **kwargs: object) -> IkHandle:
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
        ...
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
