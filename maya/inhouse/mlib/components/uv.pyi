# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mesh の現在の UV セットを参照する UV 型。"""

from .component import Component, Components
from typing import Any, Iterator
from typing import overload



class UV(Component):
    """Mesh参照とUV番号を保持し、現在のUVセットのU/V座標を照会する。

    UVセット名は固定して保持しない。切替後は同じ番号で切替先のセットを参照する。
    U/Vは無次元で、0〜1に制限しない。
    """
    shape_type: str
    component_type: str
    count_attribute: str
    def getPosition(self) -> tuple[float, float]:
        """現在のUVセットから、保持番号のU/V座標を取得する。

        Returns:
            tuple[float, float]: 新しい無次元の(U, V)値。UI距離単位やobject/ワールド空間とは無関係。

        Raises:
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshまたは現在のUVセットを参照できない場合。
        """
        ...
    def getU(self) -> float:
        """U成分の現在値を取得する。

        Returns:
            float: 座標値。
        """
        ...
    def getV(self) -> float:
        """V成分の現在値を取得する。

        Returns:
            float: 座標値。
        """
        ...
_UV_GET_POSITION: Any


class UVs(Components):
    """同一MeshのUV番号列を保持し、現在のUVセットの座標を保持順に扱う。

    セット名や座標値は保持せず、セット切替後は切替先の同じ番号を使う。
    """
    def __iter__(self) -> Iterator[UV]: ...
    @overload
    def __getitem__(self, index: int) -> UV: ...
    @overload
    def __getitem__(self, index: slice) -> UVs: ...
    component_class: Any
    def getU(self) -> list[float]:
        """U成分の現在値を取得する。

        Returns:
            list[float]: 保持順の座標値。
        """
        ...
    def getV(self) -> list[float]:
        """V成分の現在値を取得する。

        Returns:
            list[float]: 保持順の座標値。
        """
        ...
    def getPosition(self) -> list[tuple[float, float]]:
        """現在のUVセットのU/V座標を、保持番号の順に取得する。

        標準実装は同じMFnMeshと現在UVセット名を使って各番号を問い合わせる。
        単数参照や反復が拡張されている場合は、各要素のgetPositionへ委譲する。

        Returns:
            list[tuple[float, float]]: 新しい無次元のU/V値リスト。座標への書換え可能な参照ではない。
                標準実装の空集合は、Shapeを再照会せず空リストを返す。

        Raises:
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshまたは現在のUVセットを参照できない場合。
        """
        ...
