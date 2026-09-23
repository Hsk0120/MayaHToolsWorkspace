"""NURBS カーブの CV と CV コレクション。"""

from .point_component import PointComponent, PointComponents


class CV(PointComponent):
    """NurbsCurve 上の単一 CV。番号はゼロ始まり。"""

    shape_type = "nurbsCurve"
    component_type = "cv"
    count_attribute = "num_cvs"


class CVs(PointComponents):
    """同一 NurbsCurve の CV 群。座標取得・部分列取得・ミラーに対応する。"""

    component_class = CV
