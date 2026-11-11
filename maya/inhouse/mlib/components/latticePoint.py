"""ラティスの点と点のコレクション。"""

import maya.api.OpenMaya as om2

from .component import _MultiIndexComponent, _MultiIndexComponents
from .pointComponent import PointComponent, PointComponents


def _lattice_divisions(shape):
    """ラティスのS・T・U方向の分割数(点の数)を照会する。

    Args:
        shape (Node): 型を検査済みのラティスのシェイプ。

    Returns:
        tuple[int, int, int]: (sDivisions, tDivisions, uDivisions)。
    """
    dependency = om2.MFnDependencyNode(shape.mnode())
    return tuple(dependency.findPlug(name, False).asInt() for name in ("sDivisions", "tDivisions", "uDivisions"))


class LatticePoint(_MultiIndexComponent, PointComponent):
    """ラティスのShape参照と点の番号(``pt[s][t][u]``)を保持し、現在のXYZ座標を照会・編集する。

    保持する :attr:`index` は ``s + t * S + u * S * T`` (S・Tは ``sDivisions``・``tDivisions``)の
    平坦な番号で、``om2.MItGeometry`` の並びと同じ。``(s, t, u)`` は :meth:`getMultiIndex` で照会する。
    座標はラティスのシェイプのオブジェクト空間(既定のラティスは各辺1の立方体)またはワールド空間のcm。
    分割数を変えると同じ番号が別の点を指す。座標の照会・書込み・反転は
    :class:`~mlib.components.pointComponent.PointComponent` と同じ(fastは ``MItGeometry.setAllPositions``)。
    """

    shape_type = "lattice"
    component_type = "pt"
    index_size = 3

    @classmethod
    def _element_count(cls, shape):
        """ラティスの点の数(``S * T * U``)を返す。

        Args:
            shape (Node): 型を検査済みのラティスのシェイプ。

        Returns:
            int: 点の数。
        """
        s, t, u = _lattice_divisions(shape)
        return s * t * u

    @classmethod
    def _multi_indices(cls, shape, indices, command=False):
        """平坦な番号を ``(s, t, u)`` へ変換する。

        Args:
            shape (Node): 型を検査済みのラティスのシェイプ。
            indices (Iterable[int]): 範囲を検証済みの平坦な番号。
            command (bool): cmds用の番号か。ラティスでは同じ番号になる。

        Returns:
            list[tuple[int, int, int]]: 指定順の ``(s, t, u)``。
        """
        count_s, count_t, _ = _lattice_divisions(shape)
        result = []
        for index in indices:
            rest, s = divmod(index, count_s)
            u, t = divmod(rest, count_t)
            result.append((s, t, u))
        return result

    @classmethod
    def _flat_indices(cls, shape, numbers):
        """``(s, t, u)`` を平坦な番号へ変換する。

        Args:
            shape (Node): 型を検査済みのラティスのシェイプ。
            numbers (Iterable[tuple[int, int, int]]): 0以上の ``(s, t, u)``。

        Returns:
            list[int]: 指定順の平坦な番号。

        Raises:
            IndexError: 分割数の範囲外の場合。
        """
        count_s, count_t, count_u = _lattice_divisions(shape)
        result = []
        for s, t, u in numbers:
            if s >= count_s or t >= count_t or u >= count_u:
                raise IndexError(f"Component index out of range: {(s, t, u)}")
            result.append(s + (t + u * count_t) * count_s)
        return result


class LatticePoints(_MultiIndexComponents, PointComponents):
    """同一ラティスの点の番号列を保持し、点の列挙と座標の一括操作を担当する。

    ``LatticePoints(shape)`` で全点を取得できる。番号の指定には平坦な番号と ``(s, t, u)`` を混ぜられる。
    名前は範囲へまとめない。
    """

    component_class = LatticePoint
