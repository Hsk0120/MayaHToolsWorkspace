# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の NURBS カーブシェイプを扱う。"""

import math
import maya.api.OpenMaya as om2
from maya.api.OpenMaya import MSpace
from ..components.cv import CV, CVs
from ..core import geometryEdit as geometry_edit
from ..decorator import _edit_context, _require_bool
from ..maths.vector import _vectors_of_points
from ..util import _world_space
from .shape import Shape
from typing import Iterable, Sequence
from mlib.maths.vector import Vector



class NurbsCurve(Shape):
    """NURBS カーブの形状情報を提供するシェイプラッパー。

    点列からの作成は :func:`mlib.createCurve <mlib.cmds.createCurve.createCurve>`、CV位置の一括書込みは :meth:`setCvPositions` を使う。
    CV(:class:`~mlib.components.cv.CV`)の参照は読み取り専用。
    """
    def getCV(self, index: int) -> CV:
        """CV 番号から単体ラッパーを取得する。

        Args:
            index (int): ゼロ始まりの CV 番号。

        Returns:
            CV: シーン上の CV を参照するラッパー。

        Raises:
            IndexError: CV 番号が範囲外の場合。
        """
        ...
    def getCVs(self, indices: Iterable[int] | None = ...) -> CVs:
        """OpenMayaのCV番号を入力の初出順に保持するコレクションを取得する。

        Args:
            indices (Iterable[int] | None): APIのCV番号。Noneは現在の全CVを昇順で取得し、空列は空集合。
                負数とboolは拒否する。

        Returns:
            CVs: 同じShapeを共有し、重複を除いた新しいコレクション。
                周期末尾の重複CVもAPI番号で保持するが、cmds用の名前では対応する独立CVへ写す。
        """
        ...
    def mfn(self) -> om2.MFnNurbsCurve | om2.MFnDagNode:
        """このカーブで最も具体的な om2 function set を、呼び出すたびに新しく作って返す。

        形状データを持つ場合は ``om2.MFnNurbsCurve``。``mlib.createNode("nurbsCurve")`` 直後のように形状データを
        持たない空のシェイプは ``om2.MFnNurbsCurve`` が使えない(Maya 2027 では作成時に ValueError、
        版により作成後の照会で RuntimeError)ため、``om2.MFnDagNode`` を返す。DagNode 共通の照会
        (中間オブジェクト判定・親の列挙等)は空のシェイプでも使える。

        Returns:
            om2.MFnNurbsCurve | om2.MFnDagNode: このカーブの function set。空のシェイプでは MFnDagNode。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        ...
    def getNumCVs(self) -> int:
        """CV 数を取得する。

        Returns:
            int: カーブの CV 数。
        """
        ...
    def getNumSpans(self) -> int:
        """スパン数を取得する。

        Returns:
            int: カーブのスパン数。
        """
        ...
    def getDegree(self) -> int:
        """カーブの次数を取得する。

        Returns:
            int: NURBS カーブの次数。
        """
        ...
    def getForm(self) -> int:
        """カーブの開閉形式を取得する。

        Returns:
            int: MFnNurbsCurve の kOpen、kClosed、kPeriodic のいずれか。
        """
        ...
    def getLength(self, tolerance: float = ..., *, worldSpace: bool = ..., unit: str | None = ...) -> float:
        """指定空間のカーブ長を取得する。シーンに計算ノードを作成しない。

        Args:
            tolerance (float): 弧長計算の許容誤差。内部距離単位で正の有限値。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            unit (str | None): 出力単位。既定はcm。Noneは現在の距離UI単位。
                mm/cm/m/km/in/ft/yd/mi、またはMayaの長名。

        Returns:
            float: 指定単位での弧長。単位省略時はcm。
                worldSpace=Trueは親の非均等スケール・シアーとインスタンスの変換を含む。

        Raises:
            TypeError: 単位の型が不正な場合。
            ValueError: toleranceが正の有限値でない、worldSpaceがboolでない、または単位名が未対応の場合。
            RuntimeError: 無効なカーブ、またはMayaが評価を拒否した場合。
        """
        ...
    def getCvPositions(self, worldSpace: bool = ...) -> list[Vector]:
        """CV の位置を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。

        Returns:
            list[Vector]: CV 順の位置(:class:`~mlib.maths.vector.Vector`)。距離は Maya API の
                内部単位(cm)。有理カーブのウェイト(w)は含まず、wで割らないXYZを返す。
                そのまま :meth:`setCvPositions` へ渡せる。
        """
        ...
    def setCvPositions(self, points: Iterable[Sequence[float] | om2.MPoint | om2.MVector], worldSpace: bool = ..., *, fast: bool = ...) -> NurbsCurve:
        """全CVの位置を一度に書き込み、自身を返す。

        :meth:`getCvPositions` と同じ並び・単位(内部単位cm)の点列を受け付け、通常は ``cmds.xform`` で
        書き込んで1回のUndoにまとめる。``fast=True`` は ``MFnNurbsCurve.setCVPositions`` で全CVを1回で
        書き込み、Undoに記録しない。CVの数・次数・ノット・ウェイトは変更しない。
        周期カーブは、独立CV数(``getNumCVs() - getDegree()``)の点列か、末尾の重複CVを含む
        ``getNumCVs()`` 個の点列(重複CVは先頭の対応CVと同じ位置であること)を受け付ける。

        Args:
            points (Iterable[Sequence[float] | om2.MPoint | om2.MVector]): CV順の位置。各点は3個の
                有限な数値。MPointはwで割らずにXYZを使う。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            NurbsCurve: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、または点の型・成分が不正な場合。
            ValueError: 点の数がCV数と合わない、成分が有限でない、周期カーブの重複CVが先頭の
                CVと一致しない、またはworldSpace=Trueで変換マトリクスが特異な場合。
            RuntimeError: 形状データが無い・無効なシェイプ、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、createへの入力(コンストラクションヒストリ)がある場合。
        """
        ...
    def getCollocatedCVGroups(self, tolerance: float = ..., worldSpace: bool = ...) -> list[list[int]]:
        """ほぼ同じ位置にある CV をグループ化して取得する。

        周期カーブの重複 CV や、クリーンアップ前のカーブの検証などに使う。

        Args:
            tolerance (float): 同一位置とみなす距離の許容誤差(Maya API の
                内部距離単位)。正の値を指定する。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。

        Returns:
            list[list[int]]: 2個以上の CV が重なっているグループのみを、
                各グループ内は番号昇順、グループ間は先頭番号の昇順で返す。
                重なりのない単独の CV は含まない。

        Raises:
            ValueError: tolerance が正の値でない場合。
        """
        ...
    def _geometry_fn(self) -> om2.MFnNurbsCurve:
        """形状データを要する照会用に ``om2.MFnNurbsCurve`` を返す。

        Returns:
            om2.MFnNurbsCurve: このカーブの function set。

        Raises:
            RuntimeError: 保持する DAG パスが無効、または形状データを持たない空のシェイプの場合。
        """
        ...
