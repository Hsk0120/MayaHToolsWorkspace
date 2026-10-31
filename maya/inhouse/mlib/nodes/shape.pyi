# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
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
from typing import Iterable



class Shape(DagNode):
    """Maya DAG shape ノードの共通ラッパー。"""
    def setParent(self, parent: Transform | str, *, fast: bool = ...) -> Shape:
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
        ...
    def _set_parent_fast(self, target: Transform) -> None:
        """変更前に編集できるか確かめ、MDagModifierでシェイプの親を変える。

        Args:
            target (Transform): 新しい親。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: シェイプ・元の親・新しい親がロック・参照されている場合。
            NotImplementedError: 新しい親に同じ名前の子がある場合。
        """
        ...
    def scaleGeometry(self, scale: float | Iterable[float], worldSpace: bool = ..., pivot: Iterable[float] = ..., indices: Iterable[int | tuple[int, int]] | None = ..., *, fast: bool = ...) -> Shape:
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
        ...
    def getTransform(self) -> Transform | None:
        """このShapeの親Transformを取得する。

        Returns:
            Transform | None: 親Transform。存在しない場合は ``None``。
        """
        ...
