"""Transform node wrapper."""

import math

import maya.cmds as cmds
import maya.api.OpenMaya as om2

from ..decorator.undo import undoable
from ..math import Matrix
from .node import Node


class Transform(Node):
    """Maya transform ノードを matrix-first API で扱うラッパー。

    ``matrix`` は評価済みのワールド空間値を、``local_matrix`` は
    ノード自身のローカル変換値を返す。
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

    @property
    def matrix(self):
        """評価済みのワールド空間変換行列を取得する。

        Returns:
            Matrix: Translation、Rotation、Scale、Shear を含む Hlib 行列。
        """
        if not self.is_valid():
            return Matrix()
        path = self.dag_path()
        if path is None:
            return Matrix()
        return self._matrix_from_transformation(
            om2.MTransformationMatrix(path.inclusiveMatrix()), om2.MSpace.kWorld
        )

    def _matrix_from_transformation(self, transformation, space):
        """MTransformationMatrix を指定空間の Hlib Matrix へ変換する。"""
        translation = transformation.translation(space)
        rotation = transformation.rotation(asQuaternion=False)
        scale = transformation.scale(space)
        shear = transformation.shear(space)
        return Matrix(
            translate=(translation.x, translation.y, translation.z),
            rotate=(rotation.x, rotation.y, rotation.z),
            scale=(scale[0], scale[1], scale[2]),
            shear=(shear[0], shear[1], shear[2]),
        )

    @property
    def translation(self):
        """ワールド空間の Translation を取得する。

        Returns:
            Translation: 評価済みの位置。
        """
        return self.matrix.translate

    @property
    def rotation(self):
        """ワールド空間の Euler 回転値を取得する。

        Returns:
            Rotation: 評価済みの回転値（radian）。
        """
        return self.matrix.rotation

    @property
    def scale(self):
        """ワールド空間の Scale を取得する。

        Returns:
            Scale: 評価済みのスケール値。
        """
        return self.matrix.scale

    @property
    def shear(self):
        """ワールド空間の Shear を取得する。

        Returns:
            Shear: 評価済みの shear 値。
        """
        return self.matrix.shear

    @property
    def quaternion(self):
        """ワールド空間の Quaternion を取得する。

        Returns:
            Quaternion: 評価済みの回転値。
        """
        return self.matrix.quaternion

    @property
    def euler(self):
        """ワールド空間の EulerRotation を取得する。

        Returns:
            EulerRotation: 評価済みの回転値（radian）。
        """
        return self.matrix.euler

    @property
    def world_matrix(self):
        """評価済みのワールド空間 Matrix を取得する。

        Returns:
            Matrix: ``matrix`` と同じワールド空間行列。
        """
        return self.matrix

    @property
    def local_matrix(self):
        """ローカル空間の変換行列を取得する。

        Returns:
            Matrix: 親の影響を含まないローカル変換値。
        """
        if not self.is_valid():
            return Matrix()
        transformation = om2.MFnTransform(self.mobject()).transformation()
        return self._matrix_from_transformation(transformation, om2.MSpace.kTransform)

    def decompose(self):
        """ワールド空間行列を TRS/shear 成分として取得する。

        Returns:
            Matrix: 評価済みのワールド空間 Matrix。
        """
        return self.matrix

    @undoable("HlibTransformCompose")
    def compose(self, matrix):
        """Matrix の TRS/shear 成分をローカル属性へ適用する。

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
        name = self.full_name
        cmds.setAttr(f"{name}.translate", *matrix.translate)
        cmds.setAttr(f"{name}.rotate", *(math.degrees(component) for component in matrix.euler))
        cmds.setAttr(f"{name}.scale", *matrix.scale)
        cmds.setAttr(f"{name}.shear", *matrix.shear)
        return self