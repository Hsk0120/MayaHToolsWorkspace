"""MayaのNURBS曲面シェイプを扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core import geometryEdit as geometry_edit
from ..core.fastWrite import require_writable
from ..decorator import _edit_context, _pick_alias, _require_bool
from ..maths.vector import Vector, _vectors_of_points
from ..util import _UNSET, _finite, _world_space
from .shape import Shape


class NurbsSurface(Shape):
    """NURBS曲面の型付き参照。アトリビュート・親Transform操作はShapeから継承する。

    CVの番号は ``cv[u][v]`` の (u, v) で、:meth:`getCvPositions` 等の並びは U を外側・V を内側にした
    ``u * numCVsInV + v`` の順(``om2.MFnNurbsSurface.cvPositions`` と同じ)。距離はMayaの内部単位(cm)。
    """

    def mfn(self):
        """この曲面の om2 function set を、呼び出すたびに新しく作って返す。

        形状データを持たない空のシェイプ(``mlib.createNode("nurbsSurface")`` 直後等)は
        ``om2.MFnNurbsSurface`` が使えないため ``om2.MFnDagNode`` を返す。

        Returns:
            om2.MFnNurbsSurface | om2.MFnDagNode: この曲面の function set。空のシェイプでは MFnDagNode。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        path = self.mpath()
        try:
            fn = om2.MFnNurbsSurface(path)
            # 版により作成は通り照会で失敗するため、形状データの有無を作成直後に確かめる。
            fn.numCVsInU
        except (RuntimeError, ValueError):
            return om2.MFnDagNode(path)
        return fn

    def getNumCVs(self):
        """U・V方向のCV数を取得する(周期曲面は重複CVを含む)。

        Returns:
            tuple[int, int]: (U方向のCV数, V方向のCV数)。

        Raises:
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        fn = self._geometry_fn()
        return fn.numCVsInU, fn.numCVsInV

    def getNumSpans(self):
        """U・V方向のスパン数を取得する。

        Returns:
            tuple[int, int]: (U方向のスパン数, V方向のスパン数)。

        Raises:
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        fn = self._geometry_fn()
        return fn.numSpansInU, fn.numSpansInV

    def getDegree(self):
        """U・V方向の次数を取得する。

        Returns:
            tuple[int, int]: (U方向の次数, V方向の次数)。

        Raises:
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        fn = self._geometry_fn()
        return fn.degreeInU, fn.degreeInV

    def getForm(self):
        """U・V方向の開閉形式を取得する。

        Returns:
            tuple[int, int]: ``om2.MFnNurbsSurface`` の kOpen・kClosed・kPeriodic のいずれかを U・V の順に。

        Raises:
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        fn = self._geometry_fn()
        return fn.formInU, fn.formInV

    def getParamRange(self):
        """U・Vのパラメーターの範囲(``MFnNurbsSurface.knotDomainInU/V``)を取得する。

        Returns:
            tuple[tuple[float, float], tuple[float, float]]: ((U の最小, U の最大), (V の最小, V の最大))。
                ``minMaxRangeU``・``minMaxRangeV`` アトリビュートと同じ値。

        Raises:
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        fn = self._geometry_fn()
        u_start, u_end = fn.knotDomainInU
        v_start, v_end = fn.knotDomainInV
        return (u_start, u_end), (v_start, v_end)

    def getCvPositions(self, worldSpace=_UNSET, *, ws=_UNSET):
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
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        space = om2.MSpace.kWorld if _world_space(worldSpace) else om2.MSpace.kObject
        return _vectors_of_points(self._geometry_fn().cvPositions(space))

    def setCvPositions(self, points, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
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
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        _require_bool(fast, "fast")
        world = _world_space(worldSpace)
        values = geometry_edit.point_list(points)
        fn = self._geometry_fn()
        count_v = fn.numCVsInV
        count = fn.numCVsInU * count_v
        if len(values) != count:
            raise ValueError(f"Expected {count} points, got {len(values)}")
        path = self.mpath()
        current = fn.cvPositions()
        inverse = om2.MMatrix()
        if world:
            matrix = path.inclusiveMatrix()
            if abs(matrix.det4x4()) < 1e-12:
                raise ValueError("Cannot edit in world space with a singular transform")
            inverse = matrix.inverse()
        # cvPositions(kWorld)はCVのwもマトリクスの積に使うため、同じwで逆変換してローカルのXYZにする。
        local = []
        for value, old in zip(values, current):
            point = om2.MPoint(value[0], value[1], value[2], old.w) * inverse
            point.w = old.w
            local.append(point)
        with _edit_context("mlibNurbsSurfaceSetCvPositions", fast, transaction=True):
            if fast:
                self._require_fast_editable()
                fn.setCVPositions(om2.MPointArray(local))
                fn.updateSurface()
            else:
                name = self.getFullName()
                unit = om2.MDistance.uiUnit()
                for index, point in enumerate(local):
                    u, v = divmod(index, count_v)
                    coordinates = [om2.MDistance(c).asUnits(unit) for c in (point.x, point.y, point.z)]
                    cmds.xform(f"{name}.cv[{u}][{v}]", absolute=True, translation=coordinates, objectSpace=True)
        return self

    def getClosestPoint(self, point, worldSpace=_UNSET, *, ws=_UNSET):
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
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        space = om2.MSpace.kWorld if _world_space(worldSpace) else om2.MSpace.kObject
        x, y, z = geometry_edit.point_list([point])[0]
        found, u, v = self._geometry_fn().closestPoint(om2.MPoint(x, y, z), tolerance=1e-7, space=space)
        return _vectors_of_points([found])[0], u, v

    def getPointAtParam(self, u, v, worldSpace=_UNSET, *, ws=_UNSET):
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
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        space = om2.MSpace.kWorld if _world_space(worldSpace) else om2.MSpace.kObject
        fn = self._geometry_fn()
        u, v = self._require_params(fn, u, v)
        return _vectors_of_points([fn.getPointAtParam(u, v, space)])[0]

    def getNormalAtParam(self, u, v, worldSpace=_UNSET, *, ws=_UNSET):
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
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        space = om2.MSpace.kWorld if _world_space(worldSpace) else om2.MSpace.kObject
        fn = self._geometry_fn()
        u, v = self._require_params(fn, u, v)
        normal = Vector(fn.normal(u, v, space))
        if normal.length() < 1e-12:
            raise ValueError(f"Normal is undefined at ({u}, {v}): {self.getFullName()}")
        return normal.normal()

    @staticmethod
    def _require_params(fn, u, v):
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
        result = []
        for name, value, (start, end) in (("u", u, fn.knotDomainInU), ("v", v, fn.knotDomainInV)):
            value = _finite(value, name)
            margin = 1e-9 * max(1.0, end - start)
            if value < start - margin or value > end + margin:
                raise ValueError(f"{name} {value} is outside the surface range [{start}, {end}]")
            result.append(min(max(value, start), end))
        return result[0], result[1]

    def _require_fast_editable(self):
        """fast で直接書き込めることを検証する。

        Raises:
            NotImplementedError: createへの入力(コンストラクションヒストリ)がある場合。
            RuntimeError: シェイプのロック、またはCVのアトリビュートがロック・入力接続されている場合。
        """
        dependency = om2.MFnDependencyNode(self.mnode())
        if dependency.findPlug("create", False).isDestination:
            raise NotImplementedError("fast geometry edits require a shape without input history")
        if dependency.isLocked:
            raise RuntimeError("Shape node is locked")
        points = dependency.findPlug("controlPoints", False)
        for index in points.getExistingArrayAttributeIndices():
            point = points.elementByLogicalIndex(index)
            require_writable(point)
            for child in range(point.numChildren()):
                require_writable(point.child(child))

    def _geometry_fn(self):
        """形状データを要する照会用に ``om2.MFnNurbsSurface`` を返す。

        Returns:
            om2.MFnNurbsSurface: この曲面の function set。

        Raises:
            RuntimeError: 保持する DAG パスが無効、または形状データを持たない空のシェイプの場合。
        """
        fn = self.mfn()
        if not isinstance(fn, om2.MFnNurbsSurface):
            raise RuntimeError("nurbsSurface has no geometry data: %s" % self.getFullName())
        return fn
