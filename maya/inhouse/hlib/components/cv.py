"""NURBS カーブの CV と CV コレクション。"""

from .pointComponent import PointComponent, PointComponents
import maya.api.OpenMaya as om2


class CV(PointComponent):
    """NurbsCurve 上の単一 CV。番号はゼロ始まり。"""

    shape_type = "nurbsCurve"
    component_type = "cv"
    count_attribute = "numCVs"

    def fullName(self):
        """cmds用のCV名を返す。周期末尾の重複CVは先頭の対応番号へ写す。

        Returns:
            str: 同じ位置を編集するMayaコンポーネント名。indexはAPI番号を保持する。
        """
        self._validate()
        fn = self.shape.curveFn()
        index = self.index
        if fn.form == om2.MFnNurbsCurve.kPeriodic:
            index %= fn.numCVs - fn.degree
        return "{}.cv[{}]".format(self.shape.fullName(), index)


class CVs(PointComponents):
    """同一 NurbsCurve の CV 群。座標取得・部分列取得・ミラーに対応する。"""

    component_class = CV

    def fullNames(self):
        """保持順のcmds用CV名を返す。周期末尾は対応する独立CVの名前となる。"""
        return [cv.fullName() for cv in self]

    def compactNames(self):
        """cmds用CV名を返す。周期CVの対応を保つため範囲へ圧縮しない。"""
        return self.fullNames()
