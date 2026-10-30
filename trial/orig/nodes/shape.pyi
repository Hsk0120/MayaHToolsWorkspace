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
            fast (bool): Trueは履歴なしメッシュ・非周期カーブをOM2で更新(Undoなし)。
                FalseはMaya標準コマンドをUndo有効時にまとめる。

        Returns:
            Shape: 自身。

        Raises:
            TypeError: fast・番号の型が不正な場合。
            ValueError: 倍率・中心・空間が不正、world変換がほぼ特異、またはメッシュ・NURBS以外のShapeの場合。
            IndexError: 対象番号が範囲外の場合。
            RuntimeError: Mayaが編集を拒否した場合。
            NotImplementedError: fastでサーフェス・周期カーブ・入力履歴付き形状の場合。
        """
        ...
    def getTransform(self) -> Transform | None:
        """このShapeの親Transformを取得する。

        Returns:
            Transform | None: 親Transform。存在しない場合は ``None``。
        """
        ...
