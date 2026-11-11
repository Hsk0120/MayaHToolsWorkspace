# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""ラティスの点と点のコレクション。"""

import maya.api.OpenMaya as om2
from .component import _MultiIndexComponent, _MultiIndexComponents
from .pointComponent import PointComponent, PointComponents
from typing import Any, Iterable, Iterator
from mlib.nodes.node import Node
from typing import overload


def _lattice_divisions(shape: Node) -> tuple[int, int, int]:
    """ラティスのS・T・U方向の分割数(点の数)を照会する。

    Args:
        shape (Node): 型を検査済みのラティスのシェイプ。

    Returns:
        tuple[int, int, int]: (sDivisions, tDivisions, uDivisions)。
    """
    ...


class LatticePoint(_MultiIndexComponent, PointComponent):
    """ラティスのShape参照と点の番号(``pt[s][t][u]``)を保持し、現在のXYZ座標を照会・編集する。

    保持する :attr:`index` は ``s + t * S + u * S * T`` (S・Tは ``sDivisions``・``tDivisions``)の
    平坦な番号で、``om2.MItGeometry`` の並びと同じ。``(s, t, u)`` は :meth:`getMultiIndex` で照会する。
    座標はラティスのシェイプのオブジェクト空間(既定のラティスは各辺1の立方体)またはワールド空間のcm。
    分割数を変えると同じ番号が別の点を指す。座標の照会・書込み・反転は
    :class:`~mlib.components.pointComponent.PointComponent` と同じ(fastは ``MItGeometry.setAllPositions``)。
    """
    shape_type: str
    component_type: str
    index_size: int
    @classmethod
    def _element_count(cls, shape: Node) -> int:
        """ラティスの点の数(``S * T * U``)を返す。

        Args:
            shape (Node): 型を検査済みのラティスのシェイプ。

        Returns:
            int: 点の数。
        """
        ...
    @classmethod
    def _multi_indices(cls, shape: Node, indices: Iterable[int], command: bool = ...) -> list[tuple[int, int, int]]:
        """平坦な番号を ``(s, t, u)`` へ変換する。

        Args:
            shape (Node): 型を検査済みのラティスのシェイプ。
            indices (Iterable[int]): 範囲を検証済みの平坦な番号。
            command (bool): cmds用の番号か。ラティスでは同じ番号になる。

        Returns:
            list[tuple[int, int, int]]: 指定順の ``(s, t, u)``。
        """
        ...
    @classmethod
    def _flat_indices(cls, shape: Node, numbers: Iterable[tuple[int, int, int]]) -> list[int]:
        """``(s, t, u)`` を平坦な番号へ変換する。

        Args:
            shape (Node): 型を検査済みのラティスのシェイプ。
            numbers (Iterable[tuple[int, int, int]]): 0以上の ``(s, t, u)``。

        Returns:
            list[int]: 指定順の平坦な番号。

        Raises:
            IndexError: 分割数の範囲外の場合。
        """
        ...


class LatticePoints(_MultiIndexComponents, PointComponents):
    """同一ラティスの点の番号列を保持し、点の列挙と座標の一括操作を担当する。

    ``LatticePoints(shape)`` で全点を取得できる。番号の指定には平坦な番号と ``(s, t, u)`` を混ぜられる。
    名前は範囲へまとめない。
    """
    def __iter__(self) -> Iterator[LatticePoint]: ...
    @overload
    def __getitem__(self, index: int) -> LatticePoint: ...
    @overload
    def __getitem__(self, index: slice) -> LatticePoints: ...
    component_class: Any
    def getFullName(self) -> list[str]:
        """各要素の :meth:`~mlib.components.component.Component.getFullName` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def asString(self) -> list[str]:
        """各要素の :meth:`~mlib.core.object.Object.asString` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
