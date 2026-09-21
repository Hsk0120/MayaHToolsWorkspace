"""Transform node wrapper."""

import math

import maya.cmds as cmds
import maya.api.OpenMaya as om2

from ..decorators.undo import undoable
from ..core.registry import node_wrapper
from ..maths import Matrix
from .node import Node


@node_wrapper("transform")
class Transform(Node):
    """Maya transform ノードを matrix-first API で扱うラッパー。

    評価済み値を取得する ``get_*`` 系メソッドは cymel の ``getMatrix(ws=...)`` に
    倣い、``ws=False``（既定）でローカル空間、``ws=True`` でワールド空間の値を返す。
    """

    def dag_path(self):
        """Transform の MDagPath を取得する。

        Returns:
            om2.MDagPath | None: 有効な DAG パス。取得できない場合は ``None``。
        """
        if self._dag_path is None and self.is_valid():
            self._dag_path = om2.MFnDagNode(self.mobject()).getPath()
        return self._dag_path

    def dag_node(self):
        """Transform 用の MFnDagNode を取得する。

        Returns:
            om2.MFnDagNode: この Transform の function set。
        """
        return om2.MFnDagNode(self.dag_path())

    def parent_path(self):
        """親ノードの DAG パスを取得する。

        Returns:
            om2.MDagPath | None: 親のパス。親がない場合は ``None``。
        """
        if not self.is_valid() or self.dag_node().parentCount() == 0:
            return None
        parent_path = om2.MDagPath(self.dag_path())
        parent_path.pop()
        return parent_path

    def parent_node(self):
        """親ノードを汎用 Node として取得する。

        Returns:
            Node | None: 親ノード。親がない場合は ``None``。
        """
        parent_path = self.parent_path()
        return Node(parent_path) if parent_path is not None else None

    def child_nodes(self):
        """直接の子ノードを汎用 Node のリストとして取得する。

        Returns:
            list[Node]: 直接の子ノード。
        """
        if not self.is_valid():
            return []
        dag_path = self.dag_path()
        dag_fn = self.dag_node()
        children = []
        for index in range(dag_fn.childCount()):
            child_path = om2.MDagPath(dag_path)
            child_path.push(dag_fn.child(index))
            children.append(Node(child_path))
        return children

    def get_matrix(self, ws=False):
        """変換行列を取得する。

        Maya が評価・キャッシュ済みの ``matrix``/``worldMatrix`` 属性値をそのまま
        使うため、``jnt.plug("matrix")``/``jnt.plug("worldMatrix")`` と常に一致する。

        Args:
            ws (bool): ``True`` でワールド空間（``worldMatrix``）、``False``（既定）で
                ローカル空間（``matrix``）の値を取得する。

        Returns:
            Matrix: Translate、Rotate、Scale、Shear を含む Hlib 行列。
        """
        if not self.is_valid():
            return Matrix()
        if ws:
            return self.plug("worldMatrix").element(0, create=True).get()
        return self.plug("matrix").get()

    def get_translate(self, ws=False):
        """Translate を取得する。

        Args:
            ws (bool): ``True`` でワールド空間、``False``（既定）でローカル空間の値を取得する。

        Returns:
            Translate: 評価済みの位置。
        """
        return self.get_matrix(ws=ws).translate

    def get_rotate(self, ws=False):
        """Euler 回転値を取得する。

        Args:
            ws (bool): ``True`` でワールド空間、``False``（既定）でローカル空間の値を取得する。

        Returns:
            EulerRotation: 評価済みの回転値（radian）。
        """
        return self.get_matrix(ws=ws).rotation

    def get_scale(self, ws=False):
        """Scale を取得する。

        Args:
            ws (bool): ``True`` でワールド空間、``False``（既定）でローカル空間の値を取得する。

        Returns:
            Scale: 評価済みのスケール値。
        """
        return self.get_matrix(ws=ws).scale

    def get_shear(self, ws=False):
        """Shear を取得する。

        Args:
            ws (bool): ``True`` でワールド空間、``False``（既定）でローカル空間の値を取得する。

        Returns:
            Shear: 評価済みの shear 値。
        """
        return self.get_matrix(ws=ws).shear

    def get_quaternion(self, ws=False):
        """Quaternion を取得する。

        Args:
            ws (bool): ``True`` でワールド空間、``False``（既定）でローカル空間の値を取得する。

        Returns:
            Quaternion: 評価済みの回転値。
        """
        return self.get_matrix(ws=ws).quaternion

    def get_euler(self, ws=False):
        """EulerRotation を取得する。

        Args:
            ws (bool): ``True`` でワールド空間、``False``（既定）でローカル空間の値を取得する。

        Returns:
            EulerRotation: 評価済みの回転値（radian）。
        """
        return self.get_matrix(ws=ws).euler

    def decompose(self, ws=True):
        """変換行列を TRS/shear 成分として取得する。

        Args:
            ws (bool): ``True``（既定）でワールド空間、``False`` でローカル空間の値を取得する。

        Returns:
            Matrix: 評価済みの Matrix。
        """
        return self.get_matrix(ws=ws)

    def _parent_world_matrix(self):
        parent = self.parent_node()
        if parent is None or not hasattr(parent, "get_matrix"):
            return Matrix()
        return parent.get_matrix(ws=True)

    def _apply_local_matrix(self, matrix):
        name = self.full_name
        cmds.setAttr(f"{name}.translate", *matrix.translate)
        cmds.setAttr(f"{name}.rotate", *(math.degrees(component) for component in matrix.euler))
        cmds.setAttr(f"{name}.scale", *matrix.scale)
        cmds.setAttr(f"{name}.shear", *matrix.shear)

    @undoable("HlibTransformSetMatrix")
    def set_matrix(self, matrix, ws=False):
        """行列をローカルまたはワールド空間で設定する。"""
        if not isinstance(matrix, Matrix):
            matrix = Matrix(matrix)
        if not self.is_valid():
            raise RuntimeError("Cannot set an invalid transform")
        local_matrix = matrix if not ws else matrix * self._parent_world_matrix().inverse()
        self._apply_local_matrix(local_matrix)
        return self

    @undoable("HlibTransformSetTranslate")
    def set_translate(self, value, ws=False):
        """平行移動をローカルまたはワールド空間で設定する。"""
        matrix = self.get_matrix(ws=ws)
        matrix.translate = value
        return self.set_matrix(matrix, ws=ws)

    @undoable("HlibTransformSetRotate")
    def set_rotate(self, value, unit="rad", ws=False):
        """Euler 回転を設定する。入力単位は rad または deg。"""
        if unit not in ("rad", "deg"):
            raise ValueError("unit must be 'rad' or 'deg'")
        if unit == "deg":
            value = tuple(math.radians(component) for component in value)
        matrix = self.get_matrix(ws=ws)
        matrix.rotation = value
        return self.set_matrix(matrix, ws=ws)

    @undoable("HlibTransformSetScale")
    def set_scale(self, value, ws=False):
        """スケールをローカルまたはワールド空間で設定する。"""
        matrix = self.get_matrix(ws=ws)
        matrix.scale = value
        return self.set_matrix(matrix, ws=ws)

    @undoable("HlibTransformSetShear")
    def set_shear(self, value, ws=False):
        """Shear をローカルまたはワールド空間で設定する。"""
        matrix = self.get_matrix(ws=ws)
        matrix.shear = value
        return self.set_matrix(matrix, ws=ws)

    @undoable("HlibTransformCompose")
    def compose(self, matrix, ws=False):
        """Matrix の TRS/shear 成分をローカルまたはワールド空間へ適用する。

        Args:
            matrix (Matrix): 適用する Hlib Matrix。回転値は radian として扱う。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: matrix が Hlib Matrix でない場合。
            RuntimeError: Transform が無効な場合。
        """
        if not isinstance(matrix, Matrix):
            raise TypeError("matrix must be an Hlib Matrix")
        if not self.is_valid():
            raise RuntimeError("Cannot compose an invalid transform")
        local_matrix = matrix if not ws else matrix * self._parent_world_matrix().inverse()
        self._apply_local_matrix(local_matrix)
        return self