# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""MayaのNURBS曲面シェイプを扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..components.surfaceCV import SurfaceCV, SurfaceCVs
from ..core import geometryEdit as geometry_edit
from ..core.fastWrite import require_writable
from ..decorator import _edit_context, _pick_alias, _require_bool
from ..maths.vector import Vector, _vectors_of_points
from ..util import _UNSET, _finite, _world_space
from .nurbsCurve import _DEGENERATE, _frame_matrix, _perpendicular, _require_axis
from .shape import Shape
from typing import Iterable, Sequence
from mlib.maths.matrix import Matrix



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
    def getCV(self, u: int, v: int) -> SurfaceCV:
        """``(u, v)`` の番号から CV の単体ラッパーを取得する。

        Args:
            u (int): U方向のCV番号。
            v (int): V方向のCV番号。

        Returns:
            SurfaceCV: シーン上の CV(``cv[u][v]``)を参照するラッパー。

        Raises:
            IndexError: CV 番号が範囲外の場合。
        """
        ...
    def getCVs(self, indices: Iterable[int | tuple[int, int]] | None = ...) -> SurfaceCVs:
        """CV の番号列を保持するコレクションを取得する。

        Args:
            indices (Iterable[int | tuple[int, int]] | None): 平坦な番号か ``(u, v)``。None は現在の全CV。

        Returns:
            SurfaceCVs: 同じ Shape を共有し、重複を除いたコレクション。
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
    def getTangentsAtParam(self, u: float, v: float, worldSpace: bool = ..., *, ws: bool = ...) -> tuple[Vector, Vector]:
        """パラメーター (u, v) の位置の、U方向とV方向の正規化した接線を取得する。

        Args:
            u (float): :meth:`getParamRange` の U の範囲内のパラメーター。
            v (float): :meth:`getParamRange` の V の範囲内のパラメーター。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            tuple[Vector, Vector]: U・Vのパラメーターの増える向きの単位ベクトル。
                ``pointOnSurfaceInfo`` の ``normalizedTangentU``・``normalizedTangentV`` と同じ向き。
                互いに直交するとは限らない。

        Raises:
            TypeError: u・vが数値でない、worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: u・vが有限でない・範囲外、または重なったCV等で接線が0になる位置の場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        ...
    def getMatrixAtParam(self, u: float, v: float, *, aimAxis: str = ..., upAxis: str = ..., worldSpace: bool = ..., ws: bool = ...) -> Matrix:
        """パラメーター (u, v) の位置に、U方向の接線を aimAxis、法線を upAxis へ向けたマトリクスを取得する。

        リボンの上にジョイント等を並べる用途に使う。マトリクスは正規直交の右手系(スケール1)で、
        平行移動は曲面上の位置(cm)。upAxis は法線から接線方向の成分を除いた向きで、残りの軸は
        aimAxis・upAxis から右手系で決まる(既定の x・y では z がおおむね V 方向の逆か同じ向き)。
        :meth:`NurbsCurve.getMatricesAlong <mlib.nodes.nurbsCurve.NurbsCurve.getMatricesAlong>` と同じ軸の指定。

        Args:
            u (float): :meth:`getParamRange` の U の範囲内のパラメーター。
            v (float): :meth:`getParamRange` の V の範囲内のパラメーター。
            aimAxis (str): U方向の接線へ向ける軸。"x"・"y"・"z"・"-x"・"-y"・"-z"。
            upAxis (str): 法線へ向ける軸。aimAxis と別の軸。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Matrix: 行ベクトルの規約(各行が軸、4行目が位置)のマトリクス。

        Raises:
            TypeError: u・vが数値でない、aimAxis・upAxisがstr以外、worldSpaceがbool以外、
                またはworldSpaceとwsを同時に指定した場合。
            ValueError: u・vが有限でない・範囲外、軸名が未対応・aimAxisとupAxisが同じ軸、
                またはU方向の接線・法線が0か互いに平行で向きを決められない場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        ...
    def getArea(self, worldSpace: bool = ..., *, ws: bool = ...) -> float:
        """曲面の面積(``MFnNurbsSurface.area``)を取得する。シーンに計算ノードを作成しない。

        Args:
            worldSpace (bool): Trueはワールド空間(親のスケールを含む)、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            float: 面積(cm²)。トリムされた曲面はトリム後の面積。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
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
    def _tangents(self, fn: om2.MFnNurbsSurface, u: float, v: float, world: bool) -> tuple[om2.MVector | None, om2.MVector | None]:
        """U・V方向の正規化した接線を返す。

        ``MFnNurbsSurface.tangents`` はローカル空間では正規化せず、ワールド空間では版により正規化して返すため、
        ローカル空間の微分ベクトルをマトリクスで変換してから正規化する(非均等スケールでも向きが正しい)。

        Args:
            fn (om2.MFnNurbsSurface): 照会する曲面。
            u (float): 検証済みのUのパラメーター。
            v (float): 検証済みのVのパラメーター。
            world (bool): Trueならワールド空間。

        Returns:
            tuple[om2.MVector | None, om2.MVector | None]: U・Vの単位接線。0になる向きは None。
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
