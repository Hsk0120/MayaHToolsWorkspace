"""XYZ 座標を持つコンポーネントと要素群の座標の照会・編集。"""

import math
import numbers

import maya.api.OpenMaya as om2

from ..core import geometryEdit as geometry_edit
from ..decorator import _edit_context, _require_bool
from ..util import _finite, _world_space, mirrorArguments
from .component import Component, Components


class PointComponent(Component):
    """Shape参照と頂点/CV番号を保持し、現在のXYZ座標を照会・編集する。

    座標をキャッシュせず、取得ごとにMayaへ問い合わせる。XYZの距離単位はcmで、
    既定はShapeのオブジェクト空間。ワールド空間では保持ShapeのDAGパスを使う。
    CVはAPIの制御点位置を扱い、カーブ上のパラメータ位置を取得する処理ではない。
    書込みは通常 ``cmds.xform`` を使って1回のUndoにまとめ、``fast=True`` はOpenMayaで1点を書いて
    Undoに記録しない。共有Shapeの編集は全インスタンスへ影響する。
    """

    def getPosition(self, worldSpace=False):
        """頂点またはカーブCVの現在のXYZ座標をcmで取得する。

        Shapeと番号を検証してOpenMayaへ問い合わせる。UIの距離単位には換算しない。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            Vector: 新しいXYZ値(:class:`~mlib.maths.vector.Vector`)。シーン内座標への書換え可能な参照ではない。

        Raises:
            TypeError: worldSpaceがbool以外の場合。
            IndexError: 番号が現在の要素数の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが座標取得を拒否した場合。
        """
        ws = _world_space(worldSpace)
        self._require_valid()
        return geometry_edit.vectors(self.shape, [self.index], ws)[0]

    def setPosition(self, value, worldSpace=False, *, fast=False):
        """頂点/CVへcm単位の絶対XYZ座標を設定する。移動量ではない。

        UIの距離単位によらずcmで受け取り、通常は ``cmds.xform`` で書き込んで1回のUndoにまとめる。
        ``fast=True`` は ``MFnMesh.setPoint`` / ``MFnNurbsCurve.setCVPosition`` で1点だけを書き、
        Undoに記録しない。CVのウェイト(w)は保持し、周期カーブの末尾の重複CVは先頭の独立CVと同じ位置に揃う。
        多数の点は :meth:`PointComponents.setPositions` で1回にまとめる。

        Args:
            value (Iterable[float] | om2.MPoint | om2.MVector): 有限なXYZ(cm)。MPointはwで割らずにXYZを使う。
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponent: 自身。

        Raises:
            TypeError: worldSpaceがbool以外、または座標の型が不正な場合。
            ValueError: 座標が3成分の有限値でない、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        point = _point_value(value)
        self._require_valid()
        _write_points([(self.shape, [self.index], [point], ws)], fast, "mlibPointComponentSetPosition")
        return self

    def getPositionX(self, worldSpace=False):
        """X成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(0, worldSpace=_world_space(worldSpace))

    def setPositionX(self, value, worldSpace=False, *, fast=False):
        """X成分だけを設定し、他の成分は指定空間の現在値を保つ。

        Args:
            value (float): 有限な座標(cm)。
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponent: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、またはvalueが数値でない場合。
            ValueError: valueが有限でない、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        return self._set_coordinate(0, value, worldSpace, fast, "mlibPointComponentSetPositionX")

    def getPositionY(self, worldSpace=False):
        """Y成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(1, worldSpace=_world_space(worldSpace))

    def setPositionY(self, value, worldSpace=False, *, fast=False):
        """Y成分だけを設定し、他の成分は指定空間の現在値を保つ。

        Args:
            value (float): 有限な座標(cm)。
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponent: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、またはvalueが数値でない場合。
            ValueError: valueが有限でない、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        return self._set_coordinate(1, value, worldSpace, fast, "mlibPointComponentSetPositionY")

    def getPositionZ(self, worldSpace=False):
        """Z成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(2, worldSpace=_world_space(worldSpace))

    def setPositionZ(self, value, worldSpace=False, *, fast=False):
        """Z成分だけを設定し、他の成分は指定空間の現在値を保つ。

        Args:
            value (float): 有限な座標(cm)。
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponent: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、またはvalueが数値でない場合。
            ValueError: valueが有限でない、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        return self._set_coordinate(2, value, worldSpace, fast, "mlibPointComponentSetPositionZ")

    def _set_coordinate(self, axis, value, worldSpace, fast, chunk):
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
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        number = _finite(value, "value")
        self._require_valid()
        point = list(geometry_edit.positions(self.shape, [self.index], ws)[0])
        point[axis] = number
        _write_points([(self.shape, [self.index], [tuple(point)], ws)], fast, chunk)
        return self


class PointComponents(Components):
    """同一Shapeの頂点/CV番号列を保持し、保持順にXYZ座標を照会・一括編集する。

    座標値は保持せず、getPositionで現在値を取得する。XYZはcm単位で、
    setPositionは全要素に同じ絶対座標、setPositionsは番号ごとの座標行を設定する。
    書込みは入力をすべて検証してから行い、通常は ``cmds.xform`` を点ごとに呼んで1回のUndoにまとめる
    (Mayaが途中で拒否した場合は先に書いた点を戻す)。``fast=True`` はOpenMayaで全点を1回で書き込み、
    Undoに記録しない。共有Shapeの編集は全インスタンスへ影響する。
    """

    def getPositionX(self, worldSpace=False):
        """X成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(0, worldSpace=_world_space(worldSpace))

    def setPositionX(self, value, worldSpace=False, *, fast=False):
        """X成分だけを設定し、他の成分は指定空間の現在値を保つ。

        Args:
            value (float | Iterable[float]): 全要素に共通の値、または保持順の値列(cm)。
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponents: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、または値の型が不正な場合。
            ValueError: 値が有限でない、値列の件数が保持数と違う、またはworldSpace=Trueで
                変換マトリクスがほぼ特異な場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        return self._set_coordinates(0, value, worldSpace, fast, "mlibPointComponentsSetPositionX")

    def getPositionY(self, worldSpace=False):
        """Y成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(1, worldSpace=_world_space(worldSpace))

    def setPositionY(self, value, worldSpace=False, *, fast=False):
        """Y成分だけを設定し、他の成分は指定空間の現在値を保つ。

        Args:
            value (float | Iterable[float]): 全要素に共通の値、または保持順の値列(cm)。
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponents: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、または値の型が不正な場合。
            ValueError: 値が有限でない、値列の件数が保持数と違う、またはworldSpace=Trueで
                変換マトリクスがほぼ特異な場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        return self._set_coordinates(1, value, worldSpace, fast, "mlibPointComponentsSetPositionY")

    def getPositionZ(self, worldSpace=False):
        """Z成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(2, worldSpace=_world_space(worldSpace))

    def setPositionZ(self, value, worldSpace=False, *, fast=False):
        """Z成分だけを設定し、他の成分は指定空間の現在値を保つ。

        Args:
            value (float | Iterable[float]): 全要素に共通の値、または保持順の値列(cm)。
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponents: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、または値の型が不正な場合。
            ValueError: 値が有限でない、値列の件数が保持数と違う、またはworldSpace=Trueで
                変換マトリクスがほぼ特異な場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        return self._set_coordinates(2, value, worldSpace, fast, "mlibPointComponentsSetPositionZ")

    def getPosition(self, worldSpace=False):
        """保持番号の順に、頂点/CVの現在のXYZ座標をcmで取得する。

        UIの距離単位には換算せず、座標の取得に伴うMayaの評価が発生し得る。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            list[Vector]: 新しい座標値(:class:`~mlib.maths.vector.Vector`)のリスト。シーンを変更する
                参照ではない。空集合はShapeを再照会せず空リストを返す。

        Raises:
            TypeError: worldSpaceがbool以外の場合。空集合でも検証する。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが座標取得を拒否した場合。
        """
        ws = _world_space(worldSpace)
        if not self._indices:
            return []
        self._require_valid()
        return geometry_edit.vectors(self._shape, self._indices, ws)

    def setPosition(self, value, worldSpace=False, *, fast=False):
        """保持する全頂点/CVを、同じcm絶対座標へ集める。移動量を加算する操作ではない。

        要素ごとに違う座標は :meth:`setPositions` を使う。

        Args:
            value (Iterable[float] | om2.MPoint | om2.MVector): 全要素に共通の有限なXYZ(cm)。
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponents: 自身。空集合は入力だけを検証して何もしない。

        Raises:
            TypeError: worldSpace・fastがbool以外、または座標の型が不正な場合。
            ValueError: 座標が3成分の有限値でない、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        point = _point_value(value)
        return self._write([point] * len(self._indices), ws, fast, "mlibPointComponentsSetPosition")

    def setPositions(self, values, worldSpace=False, *, fast=False):
        """保持番号の順に、cm単位の絶対XYZ座標を設定する。

        件数・有限値・現在の番号範囲を先にすべて検証し、問題があればシーンを変更しない。
        通常は ``cmds.xform`` を点ごとに呼ぶ(目安は1点あたり約0.2ms)。``fast=True`` は
        ``MFnMesh.setPoints`` / ``MFnNurbsCurve.setCVPositions`` で全点を1回で書き込む。

        Args:
            values (Iterable[Iterable[float] | om2.MPoint | om2.MVector]): 保持番号と同じ件数のXYZ(cm)。
                :meth:`getPosition` の結果をそのまま受け付ける。
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponents: 自身。空集合と空列はShapeを再照会せず何もしない。
                CVのウェイト(w)は保持する。

        Raises:
            TypeError: worldSpace・fastがbool以外、または座標の型が不正な場合。
            ValueError: 件数が保持数と違う、座標が3成分の有限値でない、またはworldSpace=Trueで
                変換マトリクスがほぼ特異な場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        rows = geometry_edit.point_list(values)
        if len(rows) != len(self._indices):
            raise ValueError(f"Expected {len(self._indices)} points, got {len(rows)}")
        return self._write(rows, ws, fast, "mlibPointComponentsSetPositions")

    def mirror(self, axis="x", worldSpace=False, pivot=(0.0, 0.0, 0.0), *, fast=False):
        """保持する頂点/CVを、指定空間の中心pivotに対して反転する(``2 * pivot - 現在座標``)。

        Transform・トポロジー・CVのウェイト(w)は変更しない。複製・結合・片側からの対称化・
        法線の反転は行わない。全点の座標を先に読んでから書くため、周期カーブの重複CVも二重に反転しない。

        Args:
            axis (str | int): 反転する軸 ``"x"``・``"y"``・``"z"``、またはミラー面 ``"YZ"``・``"XZ"``・``"XY"``
                (x⇔YZ、y⇔XZ、z⇔XY。文字の順序・大文字小文字は問わない)、または0/1/2。
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            pivot (Iterable[float]): 指定空間の反転中心XYZ(cm)。既定は原点で、Transformのピボットとは独立。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointComponents: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、またはaxisが文字列・int以外の場合。
            ValueError: axis・pivotが不正、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが取得・書込みを拒否した場合。
            NotImplementedError: fast=Trueで、入力履歴のあるShapeの場合。
        """
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        plan = _mirror_plan(self, axis, ws, pivot, fast)
        _write_points([plan], fast, "mlibPointComponentsMirror")
        return self

    def _set_coordinates(self, axis, value, worldSpace, fast, chunk):
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
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        values = _axis_values(value, len(self._indices))
        if not self._indices:
            return self
        self._require_valid()
        rows = []
        for point, number in zip(geometry_edit.positions(self._shape, self._indices, ws), values):
            row = list(point)
            row[axis] = number
            rows.append(tuple(row))
        return self._write(rows, ws, fast, chunk)

    def _write(self, rows, ws, fast, chunk):
        """検証済みの座標行を、番号範囲と編集条件を確かめてから書き込む。

        Args:
            rows (list[tuple[float, float, float]]): 保持順の座標(cm)。
            ws (bool): Trueならワールド空間。
            fast (bool): TrueはUndoなしのOpenMaya更新。
            chunk (str): Undoチャンク名。

        Returns:
            PointComponents: 自身。
        """
        if not self._indices:
            return self
        self._require_valid()
        _write_points([(self._shape, list(self._indices), rows, ws)], fast, chunk)
        return self


def _point_value(value):
    """1点の座標を検証し、XYZのfloat tupleへ変換する。

    Args:
        value (Iterable[float] | om2.MPoint | om2.MVector): 座標。

    Returns:
        tuple[float, float, float]: 変換済みの座標。

    Raises:
        TypeError: 反復できない、または成分が数値でない場合。
        ValueError: 3成分でない、または有限でない場合。
    """
    return geometry_edit.point_list([value])[0]


def _axis_values(value, count):
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
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return [_finite(value, "value")] * count
    if isinstance(value, (str, bytes)):
        raise TypeError("value must be a number or a sequence of numbers")
    try:
        items = list(value)
    except TypeError:
        raise TypeError("value must be a number or a sequence of numbers") from None
    if len(items) != count:
        raise ValueError(f"Expected {count} values, got {len(items)}")
    return [_finite(item, "value") for item in items]


def _require_invertible(shape):
    """ワールド空間の編集のため、Shapeのワールドマトリクスがほぼ特異でないことを確かめる。

    Mayaはゼロスケールを微小値へ置き換えるため、マトリクスの大きさも考慮して判定する
    (:meth:`~mlib.nodes.shape.Shape.scaleGeometry` と同じ基準)。

    Args:
        shape (Shape): MeshまたはNurbsCurve。

    Raises:
        ValueError: ワールドマトリクスがほぼ特異な場合。
    """
    matrix = shape.mpath().inclusiveMatrix()
    magnitude = max(1.0, *(sum(abs(matrix[row * 4 + col]) for col in range(3)) for row in range(3)))
    if abs(matrix.det4x4()) <= 1e-12 * magnitude ** 3:
        raise ValueError(f"Cannot edit points in world space with a near-singular transform: {shape.getFullName()}")


def _mirror_plan(points, axis, ws, pivot, fast):
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
    (flip,), center = mirrorArguments(axis, pivot)
    indices = list(points.indices)
    if not indices:
        return None
    points._require_valid()
    shape = points.shape
    if ws:
        _require_invertible(shape)
    if fast:
        geometry_edit.geometry(shape, indices, edit=True)
    rows = []
    for point in geometry_edit.positions(shape, indices, ws):
        row = list(point)
        row[flip] = 2.0 * center[flip] - row[flip]
        rows.append(tuple(row))
    if not all(math.isfinite(value) for row in rows for value in row):
        raise ValueError("Mirrored positions must be finite")
    return shape, indices, rows, ws


def _write_points(plans, fast, chunk):
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
    plans = [plan for plan in plans if plan and plan[1]]
    if not plans:
        return
    for shape, _, _, ws in plans:
        if ws:
            _require_invertible(shape)
    # 点ごとのcmds.xformの途中でMayaが書込みを拒否した場合に、先に書いた点を戻すためundoTransactionを使う。
    with _edit_context(chunk, fast, transaction=True):
        for shape, indices, rows, ws in plans:
            if fast and len(indices) == 1:
                # 1点は全点の配列を読み書きせず、その点だけを書く(大きなMeshで全点の書込みより速い)。
                _set_point_fast(shape, indices[0], rows[0], ws)
                continue
            geometry_edit.set_positions(shape, indices, rows, ws, fast=fast)


def _set_point_fast(shape, index, row, ws):
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
    path, fn, mesh = geometry_edit.geometry(shape, [index], edit=True)
    inverse = path.inclusiveMatrixInverse() if ws else om2.MMatrix()
    if mesh:
        fn.setPoint(index, om2.MPoint(row[0], row[1], row[2]) * inverse)
        fn.updateSurface()
        return
    independent = fn.numCVs - fn.degree if fn.form == om2.MFnNurbsCurve.kPeriodic else fn.numCVs
    index %= independent
    weight = fn.cvPosition(index).w
    # _set_positions_fastと同じく、CVのwを掛けた点を逆変換してからwを戻す。
    point = om2.MPoint(row[0], row[1], row[2], weight) * inverse
    point.w = weight
    # 周期カーブはsetCVPositionが独立CVの番号だけを受け付け、末尾の重複CVも同じ位置へ揃える。
    fn.setCVPosition(index, point)
    fn.updateCurve()
