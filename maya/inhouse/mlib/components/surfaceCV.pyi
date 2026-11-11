# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""NURBS 曲面の CV と CV コレクション。"""

import maya.api.OpenMaya as om2
from .component import _MultiIndexComponent, _MultiIndexComponents
from .pointComponent import PointComponent, PointComponents
from typing import Any, Iterable, Iterator
from mlib.nodes.nurbsSurface import NurbsSurface
from typing import overload


def _surface_layout(shape: NurbsSurface) -> tuple[int, int, int, int]:
    """曲面のCVの並びを照会する。

    Args:
        shape (NurbsSurface): 型を検査済みの曲面。

    Returns:
        tuple[int, int, int, int]: (U方向のCV数, V方向のCV数, U方向の独立CV数, V方向の独立CV数)。
            周期方向の独立CV数は ``CV数 - 次数`` (cmds の ``cv[u][v]`` の番号の範囲)。

    Raises:
        RuntimeError: 形状データを持たない空のシェイプの場合。
    """
    ...


class SurfaceCV(_MultiIndexComponent, PointComponent):
    """NurbsSurfaceのShape参照とCVの番号(``cv[u][v]``)を保持し、現在のXYZ座標を照会・編集する。

    保持する :attr:`index` は ``u * V方向のCV数 + v`` の平坦な番号で、
    :meth:`NurbsSurface.getCvPositions <mlib.nodes.nurbsSurface.NurbsSurface.getCvPositions>` の並びと同じ。
    ``(u, v)`` は :meth:`getMultiIndex` で照会する。周期曲面もOpenMayaの番号(重複CVを含む)を保持し、
    cmds用の名前では末尾の重複CVを先頭の対応番号へ写す。座標の書込みでは重複CVも同じ位置に揃う。
    座標の照会・書込み・反転は :class:`~mlib.components.pointComponent.PointComponent` と同じ。
    """
    shape_type: str
    component_type: str
    index_size: int
    @classmethod
    def _element_count(cls, shape: NurbsSurface) -> int:
        """曲面のCV数(``U方向のCV数 * V方向のCV数``)を返す。

        Args:
            shape (NurbsSurface): 型を検査済みの曲面。

        Returns:
            int: 周期曲面の重複CVを含むCV数。
        """
        ...
    @classmethod
    def _multi_indices(cls, shape: NurbsSurface, indices: Iterable[int], command: bool = ...) -> list[tuple[int, int]]:
        """平坦な番号を ``(u, v)`` へ変換する。

        Args:
            shape (NurbsSurface): 型を検査済みの曲面。
            indices (Iterable[int]): 範囲を検証済みの平坦な番号。
            command (bool): Trueならcmds用の番号(周期方向の重複CVを先頭の対応番号へ写す)。

        Returns:
            list[tuple[int, int]]: 指定順の ``(u, v)``。
        """
        ...
    @classmethod
    def _flat_indices(cls, shape: NurbsSurface, numbers: Iterable[tuple[int, int]]) -> list[int]:
        """``(u, v)`` を平坦な番号へ変換する。

        Args:
            shape (NurbsSurface): 型を検査済みの曲面。
            numbers (Iterable[tuple[int, int]]): 0以上の ``(u, v)``。

        Returns:
            list[int]: 指定順の平坦な番号。

        Raises:
            IndexError: U・V方向のCV数の範囲外の場合。
        """
        ...


class SurfaceCVs(_MultiIndexComponents, PointComponents):
    """同一NurbsSurfaceのCVの番号列を保持し、CVの列挙と座標の一括操作を担当する。

    番号の指定には平坦な番号と ``(u, v)`` を混ぜられる。名前は範囲へまとめない。
    """
    def __iter__(self) -> Iterator[SurfaceCV]: ...
    @overload
    def __getitem__(self, index: int) -> SurfaceCV: ...
    @overload
    def __getitem__(self, index: slice) -> SurfaceCVs: ...
    component_class: Any
    def getFullName(self) -> list[str]:
        """各要素の :meth:`~mlib.components.component.Component.getFullName` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def asString(self) -> list[str]:
        """各要素の :meth:`~mlib.core.object.Object.asString` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
