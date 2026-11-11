# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""XYZ 座標を持つコンポーネントと要素群の座標の照会・編集。"""

import math
import numbers
import maya.api.OpenMaya as om2
from ..core import geometryEdit as geometry_edit
from ..decorator import _edit_context, _pick_alias, _require_bool
from ..util import _UNSET, _finite, _world_space, mirrorArguments
from .component import Component, Components
from typing import Iterable, Iterator
from mlib.maths.vector import Vector
from mlib.nodes.shape import Shape
from typing import overload



class PointComponent(Component):
    """Shape参照と頂点/CV番号を保持し、現在のXYZ座標を照会・編集する。

    座標をキャッシュせず、取得ごとにMayaへ問い合わせる。XYZの距離単位はcmで、
    既定はShapeのオブジェクト空間。ワールド空間では保持ShapeのDAGパスを使う。
    CVはAPIの制御点位置を扱い、カーブ上のパラメータ位置を取得する処理ではない。
    書込みは通常 ``cmds.xform`` を使って1回のUndoにまとめ、``fast=True`` はOpenMayaで1点を書いて
    Undoに記録しない。共有Shapeの編集は全インスタンスへ影響する。
    """
    def getPosition(self, worldSpace: bool = ..., *, ws: bool = ...) -> Vector:
        """頂点またはカーブCVの現在のXYZ座標をcmで取得する。

        Shapeと番号を検証してOpenMayaへ問い合わせる。UIの距離単位には換算しない。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 新しいXYZ値(:class:`~mlib.maths.vector.Vector`)。シーン内座標への書換え可能な参照ではない。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            IndexError: 番号が現在の要素数の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが座標取得を拒否した場合。
        """
        ...
    def setPosition(self, value: Iterable[float] | om2.MPoint | om2.MVector, worldSpace: bool = ..., *, fast: bool = ..., ws: bool = ...) -> PointComponent:
        """頂点/CVへcm単位の絶対XYZ座標を設定する。移動量ではない。

        UIの距離単位によらずcmで受け取り、通常は ``cmds.xform`` で書き込んで1回のUndoにまとめる。
        ``fast=True`` は ``MFnMesh.setPoint`` / ``MFnNurbsCurve.setCVPosition`` で1点だけを書き、
        Undoに記録しない。CVのウェイト(w)は保持し、周期カーブの末尾の重複CVは先頭の独立CVと同じ位置に揃う。
        多数の点は :meth:`PointComponents.setPositions` で1回にまとめる。

        Args:
            value (Iterable[float] | om2.MPoint | om2.MVector): 有限なXYZ(cm)。MPointはwで割らずにXYZを使う。
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponent: 自身。

        Raises:
            TypeError: worldSpaceがbool以外、座標の型が不正な場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 座標が3成分の有限値でない、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        ...
    def getPositionX(self, worldSpace: bool = ..., *, ws: bool = ...) -> float:
        """X成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            float: 座標値。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
        """
        ...
    def setPositionX(self, value: float, worldSpace: bool = ..., *, fast: bool = ..., ws: bool = ...) -> PointComponent:
        """X成分だけを設定し、他の成分は指定空間の現在値を保つ。

        Args:
            value (float): 有限な座標(cm)。
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponent: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、valueが数値でない場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: valueが有限でない、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        ...
    def getPositionY(self, worldSpace: bool = ..., *, ws: bool = ...) -> float:
        """Y成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            float: 座標値。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
        """
        ...
    def setPositionY(self, value: float, worldSpace: bool = ..., *, fast: bool = ..., ws: bool = ...) -> PointComponent:
        """Y成分だけを設定し、他の成分は指定空間の現在値を保つ。

        Args:
            value (float): 有限な座標(cm)。
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponent: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、valueが数値でない場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: valueが有限でない、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        ...
    def getPositionZ(self, worldSpace: bool = ..., *, ws: bool = ...) -> float:
        """Z成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            float: 座標値。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
        """
        ...
    def setPositionZ(self, value: float, worldSpace: bool = ..., *, fast: bool = ..., ws: bool = ...) -> PointComponent:
        """Z成分だけを設定し、他の成分は指定空間の現在値を保つ。

        Args:
            value (float): 有限な座標(cm)。
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponent: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、valueが数値でない場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: valueが有限でない、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        ...
    def moveBy(self, offset: Iterable[float] | om2.MPoint | om2.MVector, worldSpace: bool = ..., *, fast: bool = ..., ws: bool = ...) -> PointComponent:
        """頂点/CVを、現在の位置から offset だけ相対的に動かす。

        指定空間で現在の位置を読み、offset を足した絶対座標を :meth:`setPosition` と同じ経路で書き込む。

        Args:
            offset (Iterable[float] | om2.MPoint | om2.MVector): 移動量の有限なXYZ(cm)。
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponent: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、移動量の型が不正な場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 移動量が3成分の有限値でない、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        ...
    def _set_coordinate(self, axis: int, value: float, worldSpace: bool, fast: bool, chunk: str) -> PointComponent:
        """1成分だけを書き換えた座標を、同じ空間で書き込む。

        Args:
            axis (int): 成分番号(0=X、1=Y、2=Z)。
            value (float): 設定する座標(cm)。
            worldSpace (bool): 空間指定。
            fast (bool): TrueはUndoなしのOpenMaya更新。
            chunk (str): Undoチャンク名。

        Returns:
            PointComponent: 自身。
        """
        ...


class PointComponents(Components):
    """同一Shapeの頂点/CV番号列を保持し、保持順にXYZ座標を照会・一括編集する。

    座標値は保持せず、getPositionで現在値を取得する。XYZはcm単位で、
    setPositionは全要素に同じ絶対座標、setPositionsは番号ごとの座標行を設定する。
    書込みは入力をすべて検証してから行い、通常は ``cmds.xform`` を点ごとに呼んで1回のUndoにまとめる
    (Mayaが途中で拒否した場合は先に書いた点を戻す)。``fast=True`` はOpenMayaで全点を1回で書き込み、
    Undoに記録しない。共有Shapeの編集は全インスタンスへ影響する。
    """
    def __iter__(self) -> Iterator[PointComponent]: ...
    @overload
    def __getitem__(self, index: int) -> PointComponent: ...
    @overload
    def __getitem__(self, index: slice) -> PointComponents: ...
    def getPositionX(self, worldSpace: bool = ..., *, ws: bool = ...) -> list[float]:
        """X成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[float]: 保持順の座標値。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
        """
        ...
    def setPositionX(self, value: float | Iterable[float], worldSpace: bool = ..., *, fast: bool = ..., ws: bool = ...) -> PointComponents:
        """X成分だけを設定し、他の成分は指定空間の現在値を保つ。

        Args:
            value (float | Iterable[float]): 全要素に共通の値、または保持順の値列(cm)。
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponents: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、値の型が不正な場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 値が有限でない、値列の件数が保持数と違う、またはworldSpace=Trueで
                変換マトリクスがほぼ特異な場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        ...
    def getPositionY(self, worldSpace: bool = ..., *, ws: bool = ...) -> list[float]:
        """Y成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[float]: 保持順の座標値。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
        """
        ...
    def setPositionY(self, value: float | Iterable[float], worldSpace: bool = ..., *, fast: bool = ..., ws: bool = ...) -> PointComponents:
        """Y成分だけを設定し、他の成分は指定空間の現在値を保つ。

        Args:
            value (float | Iterable[float]): 全要素に共通の値、または保持順の値列(cm)。
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponents: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、値の型が不正な場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 値が有限でない、値列の件数が保持数と違う、またはworldSpace=Trueで
                変換マトリクスがほぼ特異な場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        ...
    def getPositionZ(self, worldSpace: bool = ..., *, ws: bool = ...) -> list[float]:
        """Z成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[float]: 保持順の座標値。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
        """
        ...
    def setPositionZ(self, value: float | Iterable[float], worldSpace: bool = ..., *, fast: bool = ..., ws: bool = ...) -> PointComponents:
        """Z成分だけを設定し、他の成分は指定空間の現在値を保つ。

        Args:
            value (float | Iterable[float]): 全要素に共通の値、または保持順の値列(cm)。
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponents: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、値の型が不正な場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 値が有限でない、値列の件数が保持数と違う、またはworldSpace=Trueで
                変換マトリクスがほぼ特異な場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        ...
    def getPosition(self, worldSpace: bool = ..., *, ws: bool = ...) -> list[Vector]:
        """保持番号の順に、頂点/CVの現在のXYZ座標をcmで取得する。

        UIの距離単位には換算せず、座標の取得に伴うMayaの評価が発生し得る。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[Vector]: 新しい座標値(:class:`~mlib.maths.vector.Vector`)のリスト。シーンを変更する
                参照ではない。空集合はShapeを再照会せず空リストを返す。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。空集合でも検証する。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが座標取得を拒否した場合。
        """
        ...
    def setPosition(self, value: Iterable[float] | om2.MPoint | om2.MVector, worldSpace: bool = ..., *, fast: bool = ..., ws: bool = ...) -> PointComponents:
        """保持する全頂点/CVを、同じcm絶対座標へ集める。移動量を加算する操作ではない。

        要素ごとに違う座標は :meth:`setPositions` を使う。

        Args:
            value (Iterable[float] | om2.MPoint | om2.MVector): 全要素に共通の有限なXYZ(cm)。
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponents: 自身。空集合は入力だけを検証して何もしない。

        Raises:
            TypeError: worldSpace・fastがbool以外、座標の型が不正な場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 座標が3成分の有限値でない、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        ...
    def setPositions(self, values: Iterable[Iterable[float] | om2.MPoint | om2.MVector], worldSpace: bool = ..., *, fast: bool = ..., ws: bool = ...) -> PointComponents:
        """保持番号の順に、cm単位の絶対XYZ座標を設定する。

        件数・有限値・現在の番号範囲を先にすべて検証し、問題があればシーンを変更しない。
        通常は ``cmds.xform`` を点ごとに呼ぶ(目安は1点あたり約0.2ms)。``fast=True`` は
        ``MFnMesh.setPoints`` / ``MFnNurbsCurve.setCVPositions`` で全点を1回で書き込む。

        Args:
            values (Iterable[Iterable[float] | om2.MPoint | om2.MVector]): 保持番号と同じ件数のXYZ(cm)。
                :meth:`getPosition` の結果をそのまま受け付ける。
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponents: 自身。空集合と空列はShapeを再照会せず何もしない。
                CVのウェイト(w)は保持する。

        Raises:
            TypeError: worldSpace・fastがbool以外、座標の型が不正な場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 件数が保持数と違う、座標が3成分の有限値でない、またはworldSpace=Trueで
                変換マトリクスがほぼ特異な場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        ...
    def mirror(self, axis: str | int = ..., worldSpace: bool = ..., pivot: Iterable[float] = ..., *, fast: bool = ..., ws: bool = ...) -> PointComponents:
        """保持する頂点/CVを、指定空間の中心pivotに対して反転する(``2 * pivot - 現在座標``)。

        Transform・トポロジー・CVのウェイト(w)は変更しない。複製・結合・片側からの対称化・
        法線の反転は行わない。全点の座標を先に読んでから書くため、周期カーブの重複CVも二重に反転しない。

        Args:
            axis (str | int): 反転する軸 ``"x"``・``"y"``・``"z"``、またはミラー面 ``"YZ"``・``"XZ"``・``"XY"``
                (x⇔YZ、y⇔XZ、z⇔XY。文字の順序・大文字小文字は問わない)、または0/1/2。
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            pivot (Iterable[float]): 指定空間の反転中心XYZ(cm)。既定は原点で、Transformのピボットとは独立。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponents: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、axisが文字列・int以外の場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: axis・pivotが不正、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが取得・書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        ...
    def getCenter(self, worldSpace: bool = ..., *, ws: bool = ...) -> Vector:
        """保持する頂点/CVの位置の平均(重心)を取得する。

        選んだ頂点やエッジループの中心にジョイント・コントローラーを置くときに使う。外接箱の中心ではない。
        面・エッジは ``getVertices().getCenter()`` で、構成する頂点の重心を求められる。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 平均の位置(cm)。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 空の集まりの場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが座標取得を拒否した場合。
        """
        ...
    def moveBy(self, offset: Iterable[float] | om2.MPoint | om2.MVector, worldSpace: bool = ..., *, fast: bool = ..., ws: bool = ...) -> PointComponents:
        """保持する全頂点/CVを、現在の位置から同じ offset だけ相対的に動かす。

        指定空間で現在の位置を読み、offset を足した絶対座標を :meth:`setPositions` と同じ経路で1回に書き込む
        (通常は1回のUndoで戻る)。

        Args:
            offset (Iterable[float] | om2.MPoint | om2.MVector): 移動量の有限なXYZ(cm)。
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponents: 自身。空集合は入力だけを検証して何もしない。

        Raises:
            TypeError: worldSpace・fastがbool以外、移動量の型が不正な場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 移動量が3成分の有限値でない、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        ...
    def _set_coordinates(self, axis: int, value: float | Iterable[float], worldSpace: bool, fast: bool, chunk: str) -> PointComponents:
        """保持順の1成分だけを書き換えた座標を、同じ空間で書き込む。

        Args:
            axis (int): 成分番号(0=X、1=Y、2=Z)。
            value (float | Iterable[float]): 共通の値または保持順の値列。
            worldSpace (bool): 空間指定。
            fast (bool): TrueはUndoなしのOpenMaya更新。
            chunk (str): Undoチャンク名。

        Returns:
            PointComponents: 自身。
        """
        ...
    def _write(self, rows: list[tuple[float, float, float]], ws: bool, fast: bool, chunk: str) -> PointComponents:
        """検証済みの座標行を、番号範囲と編集条件を確かめてから書き込む。

        Args:
            rows (list[tuple[float, float, float]]): 保持順の座標(cm)。
            ws (bool): Trueならワールド空間。
            fast (bool): TrueはUndoなしのOpenMaya更新。
            chunk (str): Undoチャンク名。

        Returns:
            PointComponents: 自身。
        """
        ...
    def getFullName(self) -> list[str]:
        """各要素の :meth:`~mlib.components.component.Component.getFullName` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def asString(self) -> list[str]:
        """各要素の :meth:`~mlib.core.object.Object.asString` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...

def _point_value(value: Iterable[float] | om2.MPoint | om2.MVector) -> tuple[float, float, float]:
    """1点の座標を検証し、XYZのfloat tupleへ変換する。

    Args:
        value (Iterable[float] | om2.MPoint | om2.MVector): 座標。

    Returns:
        tuple[float, float, float]: 変換済みの座標。

    Raises:
        TypeError: 反復できない、または成分が数値でない場合。
        ValueError: 3成分でない、または有限でない場合。
    """
    ...

def _axis_values(value: float | Iterable[float], count: int) -> list[float]:
    """1成分の値を、共通のスカラーまたは保持順の値列として検証する。

    Args:
        value (float | Iterable[float]): 共通の値、または件数countの値列。
        count (int): 保持している要素数。

    Returns:
        list[float]: 件数countの有限な値。

    Raises:
        TypeError: 数値・数値の列でない場合(文字列を含む)。
        ValueError: 有限でない、または値列の件数がcountと違う場合。
    """
    ...

def _require_invertible(shape: Shape):
    """ワールド空間の編集のため、Shapeのワールドマトリクスがほぼ特異でないことを確かめる。

    Mayaはゼロスケールを微小値へ置き換えるため、マトリクスの大きさも考慮して判定する
    (:meth:`~mlib.nodes.shape.Shape.scaleGeometry` と同じ基準)。

    Args:
        shape (Shape): MeshまたはNurbsCurve。

    Raises:
        ValueError: ワールドマトリクスがほぼ特異な場合。
    """
    ...

def _mirror_plan(points: PointComponents, axis: str | int, ws: bool, pivot: Iterable[float], fast: bool) -> tuple | None:
    """頂点/CVの集まりを反転した座標を求め、書込みの計画を返す。シーンは変更しない。

    書込みの前に、軸・中心・番号範囲・ワールドマトリクス・fastの編集条件をすべて確かめる。
    :meth:`Transform.mirrorGeometry <mlib.nodes.transform.Transform.mirrorGeometry>` が複数Shapeを
    まとめて検証してから書くために使う。

    Args:
        points (PointComponents): 反転する頂点/CVの集まり。
        axis (str | int): 反転する軸またはミラー面。
        ws (bool): Trueならワールド空間。検証済み。
        pivot (Iterable[float]): 指定空間の反転中心XYZ(cm)。
        fast (bool): TrueならOpenMayaで直接書けるかも確かめる。

    Returns:
        tuple | None: ``(shape, indices, rows, ws)``。空集合ならNone。

    Raises:
        TypeError: axisが文字列・int以外の場合。
        ValueError: axis・pivotが不正、またはワールドマトリクスがほぼ特異な場合。
        IndexError: 保持番号が現在の範囲外の場合。
        RuntimeError: Shapeが無効、またはfastでロック等により書き込めない場合。
        NotImplementedError: fastで入力履歴のあるShapeの場合。
    """
    ...

def _write_points(plans: list[tuple | None], fast: bool, chunk: str):
    """検証済みの書込みの計画を、1回のUndo(fastはUndoなし)で書き込む。

    Args:
        plans (list[tuple | None]): ``(shape, indices, rows, ws)`` の列。Noneと空の番号は飛ばす。
        fast (bool): TrueはUndoなしのOpenMaya更新。
        chunk (str): 通常経路のUndoチャンク名。

    Raises:
        ValueError: worldSpaceで変換マトリクスがほぼ特異な場合。書込みの前に全計画を確かめる。
        RuntimeError: Mayaが書込みを拒否した場合。通常経路では先に書いた点を戻す。
        NotImplementedError: fastで入力履歴のあるShapeの場合。
    """
    ...

def _set_point_fast(shape: Shape, index: int, row: tuple[float, float, float], ws: bool):
    """1点をOpenMayaで書き込む。CVのウェイト(w)は保持し、周期カーブの重複CVも揃える。

    Args:
        shape (Shape): 入力履歴の無いMeshまたはNurbsCurve。
        index (int): 検証済みのAPI番号。
        row (tuple[float, float, float]): 設定するXYZ(cm)。
        ws (bool): Trueならワールド座標。マトリクスは検証済み。

    Raises:
        RuntimeError: ロック・入力接続・書込み禁止がある場合。
        NotImplementedError: 入力履歴のあるShapeの場合。
    """
    ...
