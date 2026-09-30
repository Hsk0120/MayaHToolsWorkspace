"""DAG シェイプの共通操作を提供する。"""

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

    @undo_chunk("hlibShapeScaleGeometry")
    def scale_geometry(self, scale, ws=False, pivot=(0.0, 0.0, 0.0), indices=None):
        """メッシュ頂点・NURBSカーブ/サーフェスのCVを指定中心で拡縮する。

        Args:
            scale (float | Iterable[float]): 一様倍率、またはXYZの倍率。負数・0も可。
            ws (bool): Falseはオブジェクト、Trueはワールド空間。
            pivot (Iterable[float]): 指定空間の中心。現在のMaya距離単位。
                既定は原点。Transformのピボットは使わない。
            indices (Iterable[int | tuple[int, int]] | None): 頂点/CV番号。
                サーフェスは(U, V)の組。Noneは全要素、空列は変更なし。

        Returns:
            Shape: 自身。Transformの行列・トポロジーは変更しない。

        Raises:
            ValueError: 倍率・中心・空間が不正、またはワールド変換がほぼ特異な場合。
            IndexError: 対象番号が範囲外の場合。
            TypeError: 番号が整数でない場合。
            NotImplementedError: メッシュ・NURBS以外のShapeの場合。
            RuntimeError: Mayaが編集を拒否した場合。

        Maya標準コマンドを使いUndoできる。周期CVはMayaの連動規則に従う。
        負の倍率でも面の頂点順は変えない。共有形状は全インスタンスに影響する。
        """
        if not isinstance(ws, bool):
            raise ValueError("ws must be a bool")
        try:
            factors = (float(scale),) * 3 if isinstance(scale, numbers.Real) else tuple(float(v) for v in scale)
            center = tuple(float(v) for v in pivot)
        except (TypeError, ValueError):
            raise ValueError("scale and pivot must contain finite numbers") from None
        if len(factors) != 3 or len(center) != 3 or not all(math.isfinite(v) for v in factors + center):
            raise ValueError("scale and pivot must contain three finite numbers")
        path = self.dag_path()
        if path.node().hasFn(om2.MFn.kMesh):
            counts = (om2.MFnMesh(path).numVertices,)
            token = "vtx"
        elif path.node().hasFn(om2.MFn.kNurbsCurve):
            counts = (om2.MFnNurbsCurve(path).numCVs,)
            token = "cv"
        elif path.node().hasFn(om2.MFn.kNurbsSurface):
            fn = om2.MFnNurbsSurface(path)
            counts = (fn.numCVsInU, fn.numCVsInV)
            token = "cv"
        else:
            raise NotImplementedError("scale_geometry supports meshes and NURBS shapes")
        if indices is None:
            components = [self.full_name() + "." + token + "[*]" * len(counts)]
        else:
            components = []
            for value in indices:
                row = (value,) if len(counts) == 1 else tuple(value)
                if len(row) != len(counts) or any(isinstance(v, bool) for v in row):
                    raise TypeError("Invalid component index")
                row = tuple(operator.index(v) for v in row)
                if any(v < 0 or v >= count for v, count in zip(row, counts)):
                    raise IndexError("Component index out of range")
                component = self.full_name() + "." + token + "".join("[{}]".format(v) for v in row)
                if component not in components:
                    components.append(component)
        if not components:
            return self
        if ws:
            matrix = path.inclusiveMatrix()
            magnitude = max(1.0, *(sum(abs(matrix[r * 4 + c]) for c in range(3)) for r in range(3)))
            if abs(matrix.det4x4()) <= 1e-12 * magnitude ** 3:
                raise ValueError("Cannot scale in world space with a near-singular transform")
        # scaleコマンドのpivot解釈に依存せず、同じ空間で読んだ座標を変換する。
        # 全座標を先に保持し、周期CVの連動で後続の読取り値が変わるのを防ぐ。
        components = cmds.ls(components, flatten=True) or []
        positions = [cmds.xform(component, query=True, translation=True,
                                worldSpace=ws, objectSpace=not ws) for component in components]
        for component, position in zip(components, positions):
            values = [center[i] + (position[i] - center[i]) * factors[i] for i in range(3)]
            cmds.xform(component, translation=values, worldSpace=ws, objectSpace=not ws)
        return self

    def parent_node(self):
        """親 Transform を取得する。

        Returns:
            Transform | None: 親 Transform。存在しない場合は ``None``。
        """
        parent = super().parent_node()
        return parent if isinstance(parent, Transform) else None

    def transform(self):
        """このShapeの親Transformを返す。

        Returns:
            Transform | None: 親Transform。存在しない場合は ``None``。
        """
        return self.parent_node()

    def is_intermediate_object(self):
        """中間オブジェクト（履歴用の非表示Shape）か判定する。

        Returns:
            bool: 中間オブジェクトの場合は True。
        """
        return self.dag_fn().isIntermediateObject
