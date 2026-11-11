"""Maya のカメラシェイプを扱う。"""

import maya.api.OpenMaya as om2

from ..decorator import _pick_alias
from ..maths.matrix import Matrix
from ..maths.vector import Vector, _vectors_of_points
from ..util import _UNSET, _angle_unit, _from_radians, _world_space
from .shape import Shape


class Camera(Shape):
    """Maya camera shape ノードのラッパー。"""

    def mfn(self):
        """この camera で最も具体的な om2 function set を取得する。

        呼び出すたびに新しい ``om2.MFnCamera`` を保持する DAG パスから作る。

        Returns:
            om2.MFnCamera: この camera の function set。
        """
        return om2.MFnCamera(self.mpath())

    def getFocalLength(self):
        """焦点距離を取得する。

        Returns:
            float: Maya の焦点距離。
        """
        return self.mfn().focalLength

    def getFieldOfView(self, *, unit="deg"):
        """水平・垂直の画角(``MFnCamera.horizontalFieldOfView``・``verticalFieldOfView``)を取得する。

        焦点距離とフィルムバック(``horizontalFilmAperture``・``verticalFilmAperture``)から求めた値。式は
        ``2 * atan(フィルムバック(インチ) / 0.03937 / 2 / 焦点距離(mm))`` で、Mayaの換算は1mm=0.03937インチ。
        Film Fit・解像度の縦横比による切り抜きは含まない。

        Args:
            unit (str): 戻り値の角度の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
                (``"degree"`` 等の別名も可)。

        Returns:
            tuple[float, float]: (水平の画角, 垂直の画角)。

        Raises:
            TypeError: unitが文字列・None以外の場合。
            ValueError: unitが未対応の単位名の場合。
            RuntimeError: ノードが削除済みの場合。
        """
        angle_unit = _angle_unit(unit)
        fn = self.mfn()
        return (_from_radians(fn.horizontalFieldOfView(), angle_unit),
                _from_radians(fn.verticalFieldOfView(), angle_unit))

    def getEyePoint(self, worldSpace=_UNSET, *, ws=_UNSET):
        """カメラの位置(``MFnCamera.eyePoint``)を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間(既定)、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 位置(cm)。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            RuntimeError: ノードが削除済みの場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=True)
        return _vectors_of_points([self.mfn().eyePoint(self._space(worldSpace))])[0]

    def getViewDirection(self, worldSpace=_UNSET, *, ws=_UNSET):
        """カメラの視線の向き(``MFnCamera.viewDirection``。ローカル空間の -Z)を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間(既定)、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 長さ1の向き。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            RuntimeError: ノードが削除済みの場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=True)
        return Vector(self.mfn().viewDirection(self._space(worldSpace))).normal()

    def getUpDirection(self, worldSpace=_UNSET, *, ws=_UNSET):
        """カメラの上の向き(``MFnCamera.upDirection``。ローカル空間の +Y)を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間(既定)、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 長さ1の向き。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            RuntimeError: ノードが削除済みの場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=True)
        return Vector(self.mfn().upDirection(self._space(worldSpace))).normal()

    def getProjectionMatrix(self):
        """カメラ空間からクリップ空間への投影マトリクス(``MFnCamera.projectionMatrix``)を取得する。

        ワールドの点を画面へ写すには、カメラのTransformの逆マトリクス(``worldInverseMatrix``)を掛けてから
        このマトリクスを掛け、w で割る(行ベクトルの規約)。焦点距離・フィルムバック・クリップ面に基づく。

        Returns:
            Matrix: 投影マトリクス(``om2.MFloatMatrix`` の値を倍精度にしたもの)。

        Raises:
            RuntimeError: ノードが削除済みの場合。
        """
        matrix = self.mfn().projectionMatrix()
        return Matrix([matrix.getElement(row, column) for row in range(4) for column in range(4)])

    def isOrtho(self):
        """正投影のカメラかを取得する(``orthographic`` アトリビュート)。

        Returns:
            bool: 正投影ならTrue、透視投影ならFalse。

        Raises:
            RuntimeError: ノードが削除済みの場合。
        """
        return bool(self.mfn().isOrtho())

    @staticmethod
    def _space(worldSpace):
        """worldSpaceを検証し、om2の空間を返す。

        Args:
            worldSpace (bool): Trueはワールド空間。

        Returns:
            int: ``om2.MSpace.kWorld`` または ``om2.MSpace.kObject``。

        Raises:
            TypeError: worldSpaceがbool以外の場合。
        """
        return om2.MSpace.kWorld if _world_space(worldSpace) else om2.MSpace.kObject
