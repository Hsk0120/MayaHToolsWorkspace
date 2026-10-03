"""DAG シェイプの共通操作を提供する。"""
from maya.api.OpenMaya import MSpace
from .._core.space import world_space
from .._core import fastGeometry
from ..decorators._fast import fast_edit, is_fast

from .dagNode import DagNode
from .transform import Transform
from ..decorators.undo import undo_chunk
import math
import operator
import numbers
import maya.cmds as cmds
import maya.api.OpenMaya as om2


class Shape(DagNode):
    """Maya DAG shape ノードの共通ラッパー。"""

    @fast_edit
    @undo_chunk("hlibShapeScaleGeometry")
    def scaleGeometry(self, scale, space=MSpace.kObject, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False):
        """メッシュ頂点・NURBSカーブ/サーフェスのCVを指定中心で拡縮する。

        Args:
            scale (float | Iterable[float]): 一様倍率、またはXYZの倍率。負数・0も可。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            pivot (Iterable[float]): 指定空間の中心。内部距離単位cm。
                既定は原点。Transformのピボットは使わない。
            indices (Iterable[int | tuple[int, int]] | None): 頂点/CV番号。
                サーフェスは(U, V)の組。Noneは全要素、空列は変更なし。
            fast (bool): Trueは履歴なしメッシュ・非周期カーブをom2で直接更新し、Undoなし。

        Returns:
            Shape: 自身。Transformの行列・トポロジーは変更しない。

        Raises:
            ValueError: 倍率・中心・空間が不正、またはワールド変換がほぼ特異な場合。
            IndexError: 対象番号が範囲外の場合。
            TypeError: 番号が整数でない場合。
            NotImplementedError: 未対応Shape、またはfastでサーフェス・周期カーブ・入力履歴付き形状の場合。
            RuntimeError: Mayaが編集を拒否した場合。

        通常モードはMaya標準コマンドを使いUndoできる。周期CVはMayaの連動規則に従う。
        負の倍率でも面の頂点順は変えない。共有形状は全インスタンスに影響する。
        """
        ws = world_space(space)
        try:
            factors = (float(scale),) * 3 if isinstance(scale, numbers.Real) else tuple(float(v) for v in scale)
            center = tuple(float(v) for v in pivot)
        except (TypeError, ValueError):
            raise ValueError("scale and pivot must contain finite numbers") from None
        if len(factors) != 3 or len(center) != 3 or not all(math.isfinite(v) for v in factors + center):
            raise ValueError("scale and pivot must contain three finite numbers")
        path = self.dagPath()
        if path.node().hasFn(om2.MFn.kMesh):
            counts = (om2.MFnMesh(path).numVertices,)
            token = "vtx"
        elif path.node().hasFn(om2.MFn.kNurbsCurve):
            fn = om2.MFnNurbsCurve(path)
            counts = (fn.numCVs,)
            token = "cv"
        elif path.node().hasFn(om2.MFn.kNurbsSurface):
            fn = om2.MFnNurbsSurface(path)
            counts = (fn.numCVsInU, fn.numCVsInV)
            token = "cv"
        else:
            raise NotImplementedError("scaleGeometry supports meshes and NURBS shapes")
        if is_fast() and len(counts) == 2:
            raise NotImplementedError("fast scaling of NURBS surfaces is not supported")
        selected = []
        if indices is None:
            components = [self.fullName() + "." + token + "[*]" * len(counts)]
            if len(counts) == 1:
                count = counts[0]
                if token == "cv" and fn.form == om2.MFnNurbsCurve.kPeriodic:
                    count -= fn.degree
                selected = list(range(count))
        else:
            components = []
            seen = set()
            for value in indices:
                row = (value,) if len(counts) == 1 else tuple(value)
                if len(row) != len(counts) or any(isinstance(v, bool) for v in row):
                    raise TypeError("Invalid component index")
                row = tuple(operator.index(v) for v in row)
                if any(v < 0 or v >= count for v, count in zip(row, counts)):
                    raise IndexError("Component index out of range")
                if path.node().hasFn(om2.MFn.kNurbsCurve):
                    fn = om2.MFnNurbsCurve(path)
                    if fn.form == om2.MFnNurbsCurve.kPeriodic:
                        row = (row[0] % (fn.numCVs - fn.degree),)
                elif path.node().hasFn(om2.MFn.kNurbsSurface):
                    fn = om2.MFnNurbsSurface(path)
                    row = tuple(
                        value % (count - degree) if form == om2.MFnNurbsSurface.kPeriodic else value
                        for value, count, degree, form in zip(
                            row, counts, (fn.degreeInU, fn.degreeInV), (fn.formInU, fn.formInV)
                        )
                    )
                if row in seen:
                    continue
                seen.add(row)
                if len(counts) == 1:
                    selected.append(row[0])
                else:
                    components.append(self.fullName() + "." + token + "".join("[{}]".format(v) for v in row))
        if not selected and (len(counts) == 1 or not components):
            return self
        if ws:
            matrix = path.inclusiveMatrix()
            magnitude = max(1.0, *(sum(abs(matrix[r * 4 + c]) for c in range(3)) for r in range(3)))
            if abs(matrix.det4x4()) <= 1e-12 * magnitude ** 3:
                raise ValueError("Cannot scale in world space with a near-singular transform")
        if len(counts) == 1:
            # 全座標を先にAPIで読む。周期CVも独立番号にまとめ、二重に拡縮しない。
            positions = fastGeometry.positions(self, selected, ws)
            values = [tuple(center[i] + (point[i] - center[i]) * factors[i] for i in range(3))
                      for point in positions]
            if not all(math.isfinite(v) for row in values for v in row):
                raise ValueError("Scaled positions must be finite")
            if is_fast():
                fastGeometry.setPositions(self, selected, values, ws)
            else:
                name = self.fullName()
                if ws and token == "cv":
                    values = fastGeometry.object_positions(self, selected, values)
                    ws = False
                for index, row in zip(selected, values):
                    ui_values = [om2.MDistance(v).asUnits(om2.MDistance.uiUnit()) for v in row]
                    cmds.xform("{}.{}[{}]".format(name, token, index), translation=ui_values,
                               worldSpace=ws, objectSpace=not ws)
            return self
        center = tuple(om2.MDistance(v).asUnits(om2.MDistance.uiUnit()) for v in center)
        # scaleコマンドのpivot解釈に依存せず、同じ空間で読んだ座標を変換する。
        # 全座標を先に保持し、周期CVの連動で後続の読取り値が変わるのを防ぐ。
        components = cmds.ls(components, flatten=True) or []
        positions = [cmds.xform(component, query=True, translation=True,
                                worldSpace=ws, objectSpace=not ws) for component in components]
        for component, position in zip(components, positions):
            values = [center[i] + (position[i] - center[i]) * factors[i] for i in range(3)]
            cmds.xform(component, translation=values, worldSpace=ws, objectSpace=not ws)
        return self

    def parentNode(self):
        """親 Transform を取得する。

        Returns:
            Transform | None: 親 Transform。存在しない場合は ``None``。
        """
        parent = super().parentNode()
        return parent if isinstance(parent, Transform) else None

    def transform(self):
        """このShapeの親Transformを返す。

        Returns:
            Transform | None: 親Transform。存在しない場合は ``None``。
        """
        return self.parentNode()

    def isIntermediateObject(self):
        """中間オブジェクト（履歴用の非表示Shape）か判定する。

        Returns:
            bool: 中間オブジェクトの場合は True。
        """
        return self.dagFn().isIntermediateObject
