# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""MayaのNURBS曲面シェイプを扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..core import geometryEdit as geometry_edit
from ..core.fastWrite import require_writable
from ..decorator import _edit_context, _pick_alias, _require_bool
from ..maths.vector import Vector, _vectors_of_points
from ..util import _UNSET, _finite, _world_space
from .shape import Shape
from typing import Iterable, Sequence



class NurbsSurface(Shape):
    """NURBS曲面の型付き参照。アトリビュート・親Transform操作はShapeから継承する。

    CVの番号は ``cv[u][v]`` の (u, v) で、:meth:`getCvPositions` 等の並びは U を外側・V を内側にした
    ``u * numCVsInV + v`` の順(``om2.MFnNurbsSurface.cvPositions`` と同じ)。距離はMayaの内部単位(cm)。
    """
    def mfn(self) -> om2.MFnNurbsSurface | om2.MFnDagNode:
        """この曲面の om2 function set を、呼び出すたびに新しく作って返す。

        形状データを持たない空のシェイプ(``mlib.createNode("nurbsSurface")`` 直後等)は
        ``om2.MFnNurbsSurface`` が使えないため ``om2.MFnDagNode`` を返す。

        Returns:
            om2.MFnNurbsSurface | om2.MFnDagNode: この曲面の function set。空のシェイプでは MFnDagNode。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        ...
    def getNumCVs(self) -> tuple[int, int]:
        """U・V方向のCV数を取得する(周期曲面は重複CVを含む)。

        Returns:
            tuple[int, int]: (U方向のCV数, V方向のCV数)。

        Raises:
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        ...
    def getNumSpans(self) -> tuple[int, int]:
        """U・V方向のスパン数を取得する。

        Returns:
            tuple[int, int]: (U方向のスパン数, V方向のスパン数)。

        Raises:
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        ...
    def getDegree(self) -> tuple[int, int]:
        """U・V方向の次数を取得する。

        Returns:
            tuple[int, int]: (U方向の次数, V方向の次数)。

        Raises:
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        ...
    def getForm(self) -> tuple[int, int]:
        """U・V方向の開閉形式を取得する。

        Returns:
            tuple[int, int]: ``om2.MFnNurbsSurface`` の kOpen・kClosed・kPeriodic のいずれかを U・V の順に。

        Raises:
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        ...
    def getParamRange(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """U・Vのパラメーターの範囲(``MFnNurbsSurface.knotDomainInU/V``)を取得する。

        Returns:
            tuple[tuple[float, float], tuple[float, float]]: ((U の最小, U の最大), (V の最小, V の最大))。
                ``minMaxRangeU``・``minMaxRangeV`` アトリビュートと同じ値。

        Raises:
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        ...
    def getCvPositions(self, worldSpace: bool = ..., *, ws: bool = ...) -> list[Vector]:
        """全CVの位置を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[Vector]: ``u * numCVsInV + v`` の順の位置(cm)。有理曲面のウェイト(w)では割らない。
                そのまま :meth:`setCvPositions` へ渡せる。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        ...
    def setCvPositions(self, points: Iterable[Sequence[float] | om2.MPoint | om2.MVector], worldSpace: bool = ..., *, fast: bool = ..., ws: bool = ...) -> NurbsSurface:
        """全CVの位置を一度に書き込み、自身を返す。

        :meth:`getCvPositions` と同じ並び・単位(cm)の点列を受け付け、通常は ``cmds.xform`` で書き込んで
        1回のUndoにまとめる。``fast=True`` は ``MFnNurbsSurface.setCVPositions`` で1回で書き込み、Undoに
        記録しない。CVの数・次数・ノット・ウェイトは変更しない。周期曲面の重複CVは、対応する先頭のCVと
        同じ位置を渡す(違う場合は後に書いた値になる)。

        Args:
            points (Iterable[Sequence[float] | om2.MPoint | om2.MVector]): CV順の位置。各点は3個の有限な数値。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            NurbsSurface: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、点の型・成分が不正な場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 点の数がCV数と合わない、成分が有限でない、またはworldSpace=Trueで変換マトリクスが
                特異な場合。
            RuntimeError: 形状データが無い・無効なシェイプ、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、createへの入力(コンストラクションヒストリ)がある場合。
        """
        ...
    def getClosestPoint(self, point: Sequence[float] | om2.MPoint | om2.MVector, worldSpace: bool = ..., *, ws: bool = ...) -> tuple[Vector, float, float]:
        """指定した位置に最も近い曲面上の点と、そのパラメーター (u, v) を取得する。

        ``closestPointOnSurface`` ノードの ``result.position``・``parameterU``・``parameterV`` に相当する。
        シーンに計算ノードを作成しない。follicle・uvPin の配置に使える。

        Args:
            point (Sequence[float] | om2.MPoint | om2.MVector): 位置(cm)。worldSpaceと同じ空間で指定する。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            tuple[Vector, float, float]: 最も近い点(cm)と u・v のパラメーター。

        Raises:
            TypeError: 点の型・成分が不正、worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 成分が有限でない場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        ...
    def getPointAtParam(self, u: float, v: float, worldSpace: bool = ..., *, ws: bool = ...) -> Vector:
        """パラメーター (u, v) の位置を取得する。

        Args:
            u (float): :meth:`getParamRange` の U の範囲内のパラメーター。
            v (float): :meth:`getParamRange` の V の範囲内のパラメーター。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 位置(cm)。``pointOnSurfaceInfo`` の ``position`` と同じ。

        Raises:
            TypeError: u・vが数値でない、worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: u・vが有限でない、または範囲外の場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        ...
    def getNormalAtParam(self, u: float, v: float, worldSpace: bool = ..., *, ws: bool = ...) -> Vector:
        """パラメーター (u, v) の位置の、正規化した法線を取得する。

        Args:
            u (float): :meth:`getParamRange` の U の範囲内のパラメーター。
            v (float): :meth:`getParamRange` の V の範囲内のパラメーター。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 長さ1の法線。``pointOnSurfaceInfo`` の ``normalizedNormal`` と同じ向き。

        Raises:
            TypeError: u・vが数値でない、worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: u・vが有限でない・範囲外、または退化した位置で法線が0になる場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        ...
    @staticmethod
    def _require_params(fn: om2.MFnNurbsSurface, u: float, v: float) -> tuple[float, float]:
        """パラメーターを検証し、範囲の端へ丸め込んだ (u, v) を返す。

        Args:
            fn (om2.MFnNurbsSurface): 照会する曲面。
            u (float): Uのパラメーター。範囲外は端からの相対1e-9までを許す。
            v (float): Vのパラメーター。

        Returns:
            tuple[float, float]: 検証済みのパラメーター。

        Raises:
            TypeError: 数値でない場合。
            ValueError: 有限でない、または範囲外の場合。
        """
        ...
    def _require_fast_editable(self):
        """fast で直接書き込めることを検証する。

        Raises:
            NotImplementedError: createへの入力(コンストラクションヒストリ)がある場合。
            RuntimeError: シェイプのロック、またはCVのアトリビュートがロック・入力接続されている場合。
        """
        ...
    def _geometry_fn(self) -> om2.MFnNurbsSurface:
        """形状データを要する照会用に ``om2.MFnNurbsSurface`` を返す。

        Returns:
            om2.MFnNurbsSurface: この曲面の function set。

        Raises:
            RuntimeError: 保持する DAG パスが無効、または形状データを持たない空のシェイプの場合。
        """
        ...
