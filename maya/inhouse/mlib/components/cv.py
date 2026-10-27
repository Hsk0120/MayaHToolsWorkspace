"""NURBS カーブの CV と CV コレクション。"""

from ..core.geometryEdit import command_indices
from .pointComponent import PointComponent, PointComponents


class CV(PointComponent):
    """NurbsCurveのShape参照とOpenMayaのCV番号を保持する。

    NurbsSurfaceの二次元CVは対象外。周期カーブもnumCVs範囲のAPI番号を保持し、
    cmds用の名前では末尾の重複CVを先頭の対応番号へ写す。
    """

    shape_type = "nurbsCurve"
    component_type = "cv"
    count_attribute = "getNumCVs"

    def getFullName(self):
        """cmds用のCV名を返す。周期末尾の重複CVは先頭の対応番号へ写す。

        Returns:
            str: 同じ位置を編集するMayaコンポーネント名。indexはAPI番号を保持する。
        """
        self._require_valid()
        index = command_indices(self.shape, [self.index])[0]
        return "{}.cv[{}]".format(self.shape.getFullName(), index)


class CVs(PointComponents):
    """同一NurbsCurveのCV番号列を保持し、CVの列挙と座標の一括操作を担当する。

    番号列はOpenMayaの番号と保持順を保つ。周期末尾と先頭は別のAPI番号として保持できるが、
    cmds用の名前では同じ独立CV番号へ写る場合がある。名前の取得では範囲圧縮しない。
    """

    component_class = CV

    def getFullNames(self):
        """保持順のcmds用CV名を返す。周期末尾は対応する独立CVの名前となる。

        Returns:
            list[str]: 保持順のMayaコンポーネント名。indicesはAPI番号を保持する。

        Raises:
            TypeError: 所有シェイプの種類がNurbsCurveでない場合。
            IndexError: 保持番号が現在のCV範囲外になった場合。
            RuntimeError: 所有シェイプが無効な場合。
        """
        self._require_valid()
        name = self.shape.getFullName()
        return ["{}.cv[{}]".format(name, index)
                for index in command_indices(self.shape, self.indices)]

    def getCompactNames(self):
        """cmds用CV名を返す。周期CVの対応を保つため範囲へ圧縮しない。

        Returns:
            list[str]: getFullNamesと同じ、保持順のMayaコンポーネント名。

        Raises:
            TypeError: 所有シェイプの種類がNurbsCurveでない場合。
            IndexError: 保持番号が現在のCV範囲外になった場合。
            RuntimeError: 所有シェイプが無効な場合。
        """
        return self.getFullNames()
