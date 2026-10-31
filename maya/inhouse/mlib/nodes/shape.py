"""DAG シェイプの共通操作を提供する。"""

import math
import numbers
import operator

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace

from ..core import geometryEdit as geometry_edit
from ..decorator import _edit_context
from ..util import _world_space
from .dagNode import DagNode
from .transform import Transform


class Shape(DagNode):
    """Maya DAG shape ノードの共通ラッパー。"""

    def setParent(self, parent, *, fast=False):
        """このシェイプを別のTransformの下へ移す(``cmds.parent(shape, transform, shape=True, relative=True)``)。

        シェイプは常にローカルの形を保って移る(ワールドの位置は新しい親に従う)。元のTransformは
        シェイプが無くなっても削除しない。:meth:`~mlib.nodes.transform.Transform.addShape` は同じ操作を
        受け側から行う。

        Args:
            parent (Transform | str): 新しい親のTransform(Jointを含む)。
            fast (bool): TrueはUndoなしのOpenMaya更新(MDagModifier.reparentNode)。既定False。

        Returns:
            Shape: 自身。移した後のパスを指す。

        Raises:
            TypeError: parentがTransformでない、またはfastがbool以外の場合。
            RuntimeError: 自身・親が無効、シェイプがインスタンス化されている、fastでロック・参照された
                ノードを含む、またはMayaが親の変更を拒否した場合。
            NotImplementedError: fastで、移す先に同じ名前の子がある場合(Mayaの改名の規則を再現しないため)。
        """
        with _edit_context("mlibShapeSetParent", fast):
            self._require_valid("parent")
            target = parent if isinstance(parent, DagNode) else DagNode._resolve_input(parent)
            if not target.isValid():
                raise RuntimeError("parent is not a valid node")
            if not isinstance(target, Transform):
                raise TypeError(f"parent must be a transform: {target.getFullName()}")
            if self.mpath().isInstanced():
                raise RuntimeError(f"Cannot move an instanced shape: {self.getFullName()}")
            current = self.getParent()
            if current is not None and current.mpath().fullPathName() == target.mpath().fullPathName():
                return self
            if fast:
                self._set_parent_fast(target)
            else:
                cmds.parent(self.getFullName(), target.getFullName(), shape=True, relative=True)
            return self

    def scaleGeometry(self, scale, worldSpace=False, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False):
        """メッシュ頂点・NURBSのCVを指定中心で拡縮する。

        Transformのマトリクス・面の頂点順は変えず、共有形状は全インスタンスに影響する。
        周期CVの連動を考慮して拡縮する。途中失敗の先行変更は戻さない。

        Args:
            scale (float | Iterable[float]): 有限な一様倍率、またはXYZ倍率。負数・0も可。
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            pivot (Iterable[float]): 指定空間の中心。cm。既定は原点で、Transformのピボットは使わない。
            indices (Iterable[int | tuple[int, int]] | None): 頂点/CV番号。サーフェスは(U, V)。
                Noneは全要素。空列は書込みなし。ただしShape型とfastのサーフェス拒否は先に検査する。
            fast (bool): Trueは履歴なしメッシュ・カーブをOM2で更新(Undoなし)。
                FalseはMaya標準コマンドをUndo有効時にまとめる。

        Returns:
            Shape: 自身。

        Raises:
            TypeError: fast・番号の型が不正な場合。
            ValueError: 倍率・中心・空間が不正、world変換がほぼ特異、またはメッシュ・NURBS以外のShapeの場合。
            IndexError: 対象番号が範囲外の場合。
            RuntimeError: Mayaが編集を拒否した場合。
            NotImplementedError: fastでサーフェス・入力履歴付き形状の場合。
        """
        with _edit_context("mlibShapeScaleGeometry", fast):
            ws = _world_space(worldSpace)
            try:
                factors = (float(scale),) * 3 if isinstance(scale, numbers.Real) else tuple(float(v) for v in scale)
                center = tuple(float(v) for v in pivot)
            except (TypeError, ValueError):
                raise ValueError("scale and pivot must contain finite numbers") from None
            if len(factors) != 3 or len(center) != 3 or not all(math.isfinite(v) for v in factors + center):
                raise ValueError("scale and pivot must contain three finite numbers")
            path = self.mpath()
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
                raise ValueError("scaleGeometry supports meshes and NURBS shapes")
            if fast and len(counts) == 2:
                raise NotImplementedError("fast scaleGeometry does not support NURBS surfaces")
            selected = []
            if indices is None:
                components = []
                if len(counts) == 2:
                    # cmds.ls("cv[*][*]", flatten=True) と同じく、周期方向は独立CV(数 - 次数)だけを u 優先で並べる。
                    counts_u, counts_v = (
                        count - degree if form == om2.MFnNurbsSurface.kPeriodic else count
                        for count, degree, form in zip(counts, (fn.degreeInU, fn.degreeInV),
                                                       (fn.formInU, fn.formInV))
                    )
                    components = [(u, v) for u in range(counts_u) for v in range(counts_v)]
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
                        row = (geometry_edit.command_indices(self, row)[0],)
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
                        components.append(row)
            if not selected and (len(counts) == 1 or not components):
                return self
            if ws:
                matrix = path.inclusiveMatrix()
                magnitude = max(1.0, *(sum(abs(matrix[r * 4 + c]) for c in range(3)) for r in range(3)))
                if abs(matrix.det4x4()) <= 1e-12 * magnitude ** 3:
                    raise ValueError("Cannot scale in world space with a near-singular transform")
            if len(counts) == 1:
                # 全座標を先にAPIで読む。周期CVも独立番号にまとめ、二重に拡縮しない。
                positions = geometry_edit.positions(self, selected, ws)
                values = [tuple(center[i] + (point[i] - center[i]) * factors[i] for i in range(3))
                          for point in positions]
                if not all(math.isfinite(v) for row in values for v in row):
                    raise ValueError("Scaled positions must be finite")
                geometry_edit.set_positions(self, selected, values, ws, fast=fast)
                return self
            center = tuple(om2.MDistance(v).asUnits(om2.MDistance.uiUnit()) for v in center)
            # scaleコマンドのpivot解釈に依存せず、同じ空間で読んだ座標を変換する。
            # 全座標を先にMFnNurbsSurfaceで読み(cmds.xform(query=True)と同じUI単位の値)、
            # 周期CVの連動で後続の読取り値が変わるのを防ぐ。書込みはUndoのためcmds.xformを使う。
            space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
            surface = om2.MFnNurbsSurface(path)
            ui_unit = om2.MDistance.uiUnit()
            positions = []
            for u, v in components:
                point = surface.cvPosition(u, v, space)
                positions.append([om2.MDistance(point[i]).asUnits(ui_unit) for i in range(3)])
            name = self.getFullName() + "." + token
            for (u, v), position in zip(components, positions):
                values = [center[i] + (position[i] - center[i]) * factors[i] for i in range(3)]
                cmds.xform(f"{name}[{u}][{v}]", translation=values, worldSpace=ws, objectSpace=not ws)
            return self

    def getTransform(self):
        """このShapeの親Transformを取得する。

        Returns:
            Transform | None: 親Transform。存在しない場合は ``None``。
        """
        return self.getParent()

    def _set_parent_fast(self, target):
        """変更前に編集できるか確かめ、MDagModifierでシェイプの親を変える。

        Args:
            target (Transform): 新しい親。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: シェイプ・元の親・新しい親がロック・参照されている場合。
            NotImplementedError: 新しい親に同じ名前の子がある場合。
        """
        # core は nodes を参照するため、循環importを避けて関数内で読み込む。
        from ..core.nodeEdit import require_editable

        current = self.getParent()
        for node in (self, current, target):
            if node is not None:
                require_editable(node.mnode())
        name = om2.MFnDagNode(self.mnode()).name()
        parent_fn = om2.MFnDagNode(target.mpath())
        if any(om2.MFnDagNode(parent_fn.child(i)).name() == name for i in range(parent_fn.childCount())):
            raise NotImplementedError(f"fast setParent does not rename shapes: {target.getFullName()} has a child named {name}")
        modifier = om2.MDagModifier()
        modifier.reparentNode(self.mnode(), target.mnode())
        modifier.doIt()
