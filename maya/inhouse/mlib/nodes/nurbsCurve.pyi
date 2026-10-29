# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の NURBS カーブシェイプを扱う。"""

import math
import maya.api.OpenMaya as om2
from maya.api.OpenMaya import MSpace
from ..components.cv import CV, CVs
from ..decorator import _require_bool
from ..util import _world_space
from .shape import Shape
from typing import Iterable



class NurbsCurve(Shape):
    """NURBS カーブの形状情報を提供するシェイプラッパー。"""
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
    def getCvPositions(self, worldSpace: bool = ...) -> om2.MPointArray:
        """CV の位置を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。

        Returns:
            om2.MPointArray: CV 順の位置。距離は Maya API の内部単位。
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
