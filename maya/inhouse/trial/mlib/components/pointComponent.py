"""XYZ 座標を持つコンポーネントと要素群の座標操作。"""

import math
from contextlib import nullcontext

from ..core import geometryEdit as geometry_edit
from ..decorator import _pick_alias, _require_bool, undoChunk
from ..util import _world_space
from ..util import _ArgumentError, _UNSET
from .component import Component, Components


class PointComponent(Component):
    """Shape参照と頂点/CV番号を保持し、現在のXYZ座標を照会・編集する。

    座標をキャッシュせず、取得ごとにMayaへ問い合わせる。XYZの距離単位はcmで、
    既定はShapeのobject空間。world空間では保持ShapeのDAGパスを使う。
    CVはAPIの制御点位置を扱い、カーブ上のパラメータ位置を取得する処理ではない。
    """

    def getPosition(self, worldSpace=_UNSET, *, ws=_UNSET):
        """頂点またはカーブCVの現在のXYZ座標をcmで取得する。

        Shapeと番号を検証してOpenMayaへ問い合わせる。UIの距離単位には換算しない。

        Args:
            worldSpace (bool): Trueは保持DAGパスのworld空間、FalseはShapeのobject空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            tuple[float, float, float]: 新しいXYZ値。シーン内座標への書換え可能な参照ではない。

        Raises:
            ValueError: worldSpaceがbool以外の場合。
            IndexError: 番号が現在の要素数の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが座標取得を拒否した場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        ws = _world_space(worldSpace)
        self._validate()
        return geometry_edit.positions(self.shape, [self.index], ws)[0]

    def setPosition(self, value, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
        """頂点/CVへcm単位の絶対XYZ座標を設定する。移動量ではない。

        通常はUI距離単位へ換算してcmds.xformで更新する。fastは入力履歴・周期カーブと、
        Shape/対象点のロック・入力接続を事前検査する。CVのwは保持する。

        Args:
            value (Iterable[float]): 有限なXYZ（cm）。
            worldSpace (bool): Trueは保持DAGパスのworld、既定FalseはShapeのobject空間。短縮名ws。
            fast (bool): TrueはUndoなし。既定FalseはUndo有効時に記録する。Undo設定は変更しない。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            PointComponent: 自身。共有Shapeの編集は全インスタンスへ影響する。

        Raises:
            ValueError: 座標・空間が不正、または必要なworld逆変換が特異な場合。
            TypeError: fastがbool以外、または長短名を同時指定した場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: 対象が無効・書込み不可、またはMayaが更新を拒否した場合。
            NotImplementedError: fastで入力履歴付きShapeまたは周期カーブを編集する場合。

        Note:
            通常Meshのworld更新はcmdsへ委ね、独自の特異マトリクス判定は行わない。
            書込み中の失敗で完了済みの変更は自動で戻さない。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        _require_bool(fast, "fast")
        with nullcontext() if fast else undoChunk("mlibPointComponentSetPosition"):
            ws = _world_space(worldSpace)
            value = self._finite_coordinates(value, 3)
            self._validate()
            geometry_edit.set_positions(self.shape, [self.index], [value], ws, fast=fast)
            return self

    def getPositionX(self, worldSpace=_UNSET, *, ws=_UNSET):
        """X成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            float: 座標値。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        ws = _world_space(worldSpace)
        return self._get_coordinate(0, ws=ws)

    def setPositionX(self, value, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
        """X成分だけを設定し、他の成分を維持する。

        Args:
            value (float): 有限な座標。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            PointComponent: 更新した自身。

        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        return self._set_coordinate(0, value, ws=ws, fast=fast)

    def getPositionY(self, worldSpace=_UNSET, *, ws=_UNSET):
        """Y成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            float: 座標値。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        ws = _world_space(worldSpace)
        return self._get_coordinate(1, ws=ws)

    def setPositionY(self, value, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
        """Y成分だけを設定し、他の成分を維持する。

        Args:
            value (float): 有限な座標。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            PointComponent: 更新した自身。

        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        return self._set_coordinate(1, value, ws=ws, fast=fast)

    def getPositionZ(self, worldSpace=_UNSET, *, ws=_UNSET):
        """Z成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            float: 座標値。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        ws = _world_space(worldSpace)
        return self._get_coordinate(2, ws=ws)

    def setPositionZ(self, value, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
        """Z成分だけを設定し、他の成分を維持する。

        Args:
            value (float): 有限な座標。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            PointComponent: 更新した自身。

        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        return self._set_coordinate(2, value, ws=ws, fast=fast)


class PointComponents(Components):
    """同一Shapeの頂点/CV番号列を保持し、保持順にXYZ座標を照会・一括編集する。

    座標値は保持せず、getPositionで現在値を取得する。XYZはcm単位で、
    setPositionは全要素に同じ絶対座標、setPositionsは番号ごとの座標行を設定する。
    """

    def setPositions(self, values, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
        """保持番号に対応するcm絶対XYZ行を設定する。

        件数・有限値・現在の番号範囲を先に検証する。通常はUI単位へ換算してcmds.xformを保持順に呼ぶ。
        fastは対応条件の検査後に点配列を一括設定する。全件の書込み成功や自動復元は保証しない。

        Args:
            values (Iterable[Iterable[float]]): 保持番号と同じ件数のXYZ行（cm）。
            worldSpace (bool): Trueは保持DAGパスのworld、既定FalseはShapeのobject空間。短縮名ws。
            fast (bool): TrueはUndoなし。既定FalseはUndo有効時に同じチャンクへ記録する。Undo設定は変更しない。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            PointComponents: 自身。空集合と空列はShapeを再照会せず何もしない。
                CVのwは保持し、共有Shapeの編集は全インスタンスへ影響する。

        Raises:
            ValueError: 件数・座標・空間が不正、または必要なworld逆変換が特異な場合。
            TypeError: fastがbool以外、または長短名を同時指定した場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: 対象が無効・書込み不可、またはMayaが更新を拒否した場合。
            NotImplementedError: fastで入力履歴付きShapeまたは周期カーブを編集する場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        _require_bool(fast, "fast")
        with nullcontext() if fast else undoChunk("mlibPointComponentsSetPositions"):
            ws = _world_space(worldSpace)
            rows = self._coordinate_rows(values, 3)
            if not self._indices:
                return self
            self._validate()
            geometry_edit.set_positions(self._shape, self._indices, rows, ws, fast=fast)
            return self

    def getPositionX(self, worldSpace=_UNSET, *, ws=_UNSET):
        """X成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            list[float]: 保持順の座標値。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        ws = _world_space(worldSpace)
        return self._get_coordinate(0, ws=ws)

    def setPositionX(self, value, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
        """X成分だけを設定し、他の成分を維持する。

        Args:
            value (float | Iterable[float]): 同値スカラーまたは保持順の値列。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            PointComponents: 更新した自身。

        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        return self._set_coordinate(0, value, ws=ws, fast=fast)

    def getPositionY(self, worldSpace=_UNSET, *, ws=_UNSET):
        """Y成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            list[float]: 保持順の座標値。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        ws = _world_space(worldSpace)
        return self._get_coordinate(1, ws=ws)

    def setPositionY(self, value, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
        """Y成分だけを設定し、他の成分を維持する。

        Args:
            value (float | Iterable[float]): 同値スカラーまたは保持順の値列。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            PointComponents: 更新した自身。

        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        return self._set_coordinate(1, value, ws=ws, fast=fast)

    def getPositionZ(self, worldSpace=_UNSET, *, ws=_UNSET):
        """Z成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            list[float]: 保持順の座標値。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        ws = _world_space(worldSpace)
        return self._get_coordinate(2, ws=ws)

    def setPositionZ(self, value, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
        """Z成分だけを設定し、他の成分を維持する。

        Args:
            value (float | Iterable[float]): 同値スカラーまたは保持順の値列。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            PointComponents: 更新した自身。

        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        return self._set_coordinate(2, value, ws=ws, fast=fast)

    def getPosition(self, worldSpace=_UNSET, *, ws=_UNSET):
        """保持番号の順に、頂点/CVの現在のXYZ座標をcmで取得する。

        UIの距離単位には換算せず、座標の取得に伴うMayaの評価が発生し得る。

        Args:
            worldSpace (bool): Trueは保持DAGパスのworld空間、FalseはShapeのobject空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            list[tuple[float, float, float]]: 新しい座標値のリスト。シーンを変更する参照ではない。
                空集合はShapeを再照会せず空リストを返す。

        Raises:
            ValueError: worldSpaceがbool以外の場合。空集合でも検証する。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが座標取得を拒否した場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        ws = _world_space(worldSpace)
        if not self._indices:
            return []
        self._validate()
        return geometry_edit.positions(self._shape, self._indices, ws)

    def setPosition(self, value, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
        """保持する全頂点/CVを、同じcm絶対座標へ集める。

        移動量を加算する操作ではない。一つのXYZを各保持番号へ対応させ、setPositionsへ委譲する。

        Args:
            value (Iterable[float]): 全要素に共通の有限なXYZ。cm単位。
            worldSpace (bool): Trueは保持DAGパスのworld空間、FalseはShapeのobject空間。短縮名ws。
            fast (bool): TrueはUndoなしの直接更新。setPositionsと同じ制限に従う。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            PointComponents: 自身。要素別に異なる座標を指定する場合はsetPositionsを使う。

        Raises:
            ValueError: XYZ・空間指定が不正、または必要なworld逆変換が特異な場合。空集合でも入力値を検証する。
            TypeError: fastがbool以外の場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: 対象が無効・書込み不可、またはMayaが更新を拒否した場合。
            NotImplementedError: fastで入力履歴付きShapeまたは周期カーブを編集する場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        point = Component._finite_coordinates(value, 3)
        return self.setPositions([point] * len(self), ws=ws, fast=fast)

    def mirror(self, axis="x", worldSpace=_UNSET, pivot=(0.0, 0.0, 0.0), *, fast=False, ws=_UNSET):
        """保持する頂点/CVの指定軸を、cm中心pivotに対して2*pivot-現在座標へ反転する。

        Transform・トポロジー・CVのwは変更しない。共有Shapeの全インスタンスへ影響する。
        複製・結合・法線反転は行わず、周期CVの通常更新はMayaの連動規則に従う。

        Args:
            axis (str): 重複しないx/y/zの組合せ。大文字も可。
            worldSpace (bool): Trueは保持DAGパスのworld、既定FalseはShapeのobject空間。短縮名ws。
            pivot (Iterable[float]): 指定空間の反転中心XYZ（cm）。既定は原点。
            fast (bool): TrueはUndoなし。既定FalseはUndo有効時に同じチャンクへ記録する。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            PointComponents: 自身。

        Raises:
            ValueError: 軸・空間・中心が不正、またはworld変換が数値的にほぼ特異な場合。
            TypeError: fastがbool以外、または長短名を同時指定した場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが取得・更新を拒否した場合。
            NotImplementedError: fastで入力履歴付きShapeまたは周期カーブを編集する場合。

        Note:
            更新制限はsetPositionsと同じ。途中失敗で完了済みの変更は自動で戻さない。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", False)
        _require_bool(fast, "fast")
        with nullcontext() if fast else undoChunk("mlibPointComponentsMirror"):
            ws = _world_space(worldSpace)
            if not isinstance(axis, str) or not axis or any(a not in "xyz" for a in axis.lower()):
                raise ValueError("axis must contain x, y, or z")
            axis = axis.lower()
            if len(set(axis)) != len(axis):
                raise ValueError("axis must not contain duplicates")
            try:
                pivot = tuple(float(value) for value in pivot)
            except (TypeError, ValueError) as error:
                raise ValueError("pivot must contain three finite numbers") from error
            if len(pivot) != 3 or not all(math.isfinite(value) for value in pivot):
                raise ValueError("pivot must contain three finite numbers")
            components = list(self)
            if not components:
                return self
            if ws:
                matrix = self._shape.mpath().inclusiveMatrix()
                # Maya はゼロスケールを微小値へ置換するためマトリクスの大きさも考慮する。
                magnitude = max(1.0, *(sum(abs(matrix[row * 4 + col]) for col in range(3)) for row in range(3)))
                if abs(matrix.det4x4()) <= 1e-12 * magnitude ** 3:
                    raise ValueError("Cannot mirror in world space with a near-singular transform")
            points = self.getPosition(ws)
            mirrored_axes = {"xyz".index(a) for a in axis}
            rows = []
            for point in points:
                row = []
                for component_index, value in enumerate(point):
                    if component_index in mirrored_axes:
                        value = 2.0 * pivot[component_index] - value
                    row.append(value)
                rows.append(row)
            self.setPositions(rows, ws=ws, fast=fast)
            return self
