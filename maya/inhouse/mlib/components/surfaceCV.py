"""NURBS 曲面の CV と CV コレクション。"""

import maya.api.OpenMaya as om2

from .component import _MultiIndexComponent, _MultiIndexComponents
from .pointComponent import PointComponent, PointComponents


def _surface_layout(shape):
    """曲面のCVの並びを照会する。

    Args:
        shape (NurbsSurface): 型を検査済みの曲面。

    Returns:
        tuple[int, int, int, int]: (U方向のCV数, V方向のCV数, U方向の独立CV数, V方向の独立CV数)。
            周期方向の独立CV数は ``CV数 - 次数`` (cmds の ``cv[u][v]`` の番号の範囲)。

    Raises:
        RuntimeError: 形状データを持たない空のシェイプの場合。
    """
    fn = shape._geometry_fn()
    count_u, count_v = fn.numCVsInU, fn.numCVsInV
    periodic = om2.MFnNurbsSurface.kPeriodic
    independent_u = count_u - fn.degreeInU if fn.formInU == periodic else count_u
    independent_v = count_v - fn.degreeInV if fn.formInV == periodic else count_v
    return count_u, count_v, independent_u, independent_v


class SurfaceCV(_MultiIndexComponent, PointComponent):
    """NurbsSurfaceのShape参照とCVの番号(``cv[u][v]``)を保持し、現在のXYZ座標を照会・編集する。

    保持する :attr:`index` は ``u * V方向のCV数 + v`` の平坦な番号で、
    :meth:`NurbsSurface.getCvPositions <mlib.nodes.nurbsSurface.NurbsSurface.getCvPositions>` の並びと同じ。
    ``(u, v)`` は :meth:`getMultiIndex` で照会する。周期曲面もOpenMayaの番号(重複CVを含む)を保持し、
    cmds用の名前では末尾の重複CVを先頭の対応番号へ写す。座標の書込みでは重複CVも同じ位置に揃う。
    座標の照会・書込み・反転は :class:`~mlib.components.pointComponent.PointComponent` と同じ。
    """

    shape_type = "nurbsSurface"
    component_type = "cv"
    index_size = 2

    @classmethod
    def _element_count(cls, shape):
        """曲面のCV数(``U方向のCV数 * V方向のCV数``)を返す。

        Args:
            shape (NurbsSurface): 型を検査済みの曲面。

        Returns:
            int: 周期曲面の重複CVを含むCV数。
        """
        count_u, count_v, _, _ = _surface_layout(shape)
        return count_u * count_v

    @classmethod
    def _multi_indices(cls, shape, indices, command=False):
        """平坦な番号を ``(u, v)`` へ変換する。

        Args:
            shape (NurbsSurface): 型を検査済みの曲面。
            indices (Iterable[int]): 範囲を検証済みの平坦な番号。
            command (bool): Trueならcmds用の番号(周期方向の重複CVを先頭の対応番号へ写す)。

        Returns:
            list[tuple[int, int]]: 指定順の ``(u, v)``。
        """
        _, count_v, independent_u, independent_v = _surface_layout(shape)
        result = []
        for index in indices:
            u, v = divmod(index, count_v)
            if command:
                u %= independent_u
                v %= independent_v
            result.append((u, v))
        return result

    @classmethod
    def _flat_indices(cls, shape, numbers):
        """``(u, v)`` を平坦な番号へ変換する。

        Args:
            shape (NurbsSurface): 型を検査済みの曲面。
            numbers (Iterable[tuple[int, int]]): 0以上の ``(u, v)``。

        Returns:
            list[int]: 指定順の平坦な番号。

        Raises:
            IndexError: U・V方向のCV数の範囲外の場合。
        """
        count_u, count_v, _, _ = _surface_layout(shape)
        result = []
        for u, v in numbers:
            if u >= count_u or v >= count_v:
                raise IndexError(f"Component index out of range: {(u, v)}")
            result.append(u * count_v + v)
        return result


class SurfaceCVs(_MultiIndexComponents, PointComponents):
    """同一NurbsSurfaceのCVの番号列を保持し、CVの列挙と座標の一括操作を担当する。

    番号の指定には平坦な番号と ``(u, v)`` を混ぜられる。名前は範囲へまとめない。
    """

    component_class = SurfaceCV
