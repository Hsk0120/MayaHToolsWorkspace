"""XYZ 座標を持つコンポーネントと要素群の座標操作。"""

import math
from contextlib import nullcontext

from ..core import geometryEdit as geometry_edit
from ..decorator import undoChunk
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
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
        self._validate()
        return geometry_edit.positions(self.shape, [self.index], ws)[0]

    def setPosition(self, value, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
        """頂点またはカーブCVのXYZを、cmの絶対座標で設定する。

        通常経路は現在のUI距離単位へ換算してcmds.xformへ渡す。fastは入力履歴・周期カーブ・
        Shape/対象点のロックや入力接続を検査してからOpenMayaで更新する。
        CVのwは維持する。共有Shapeの編集は他のインスタンスにも影響する。

        Args:
            value (Iterable[float]): cm単位の有限なXYZ。移動量ではない。
            worldSpace (bool): Trueは保持DAGパスのworld空間、FalseはShapeのobject空間。短縮名ws。
            fast (bool): TrueはUndoなしの直接更新。Undo設定は変更しない。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            PointComponent: 自身。通常経路はUndoが有効なら変更を記録する。

        Raises:
            ValueError: 座標・空間指定が不正、または逆変換が必要な経路でworld行列が特異な場合。
            TypeError: fastがbool以外の場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: 対象が無効・書込み不可、またはMayaが更新を拒否した場合。
            NotImplementedError: fastで入力履歴付きShapeまたは周期カーブを編集する場合。

        Note:
            通常Meshのworld更新はMayaコマンドへ委譲し、独自の特異行列判定は行わない。
            APIの書込み・更新中の失敗で、完了済み変更を自動ロールバックする保証はない。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibComponentPosition"):
            ws = _world_space(worldSpace)
            value = self._finite_coordinates(value, 3)
            self._validate()
            geometry_edit.setPositions(self.shape, [self.index], [value], ws, fast=fast)
            return self

    def getPositionX(self, worldSpace=_UNSET, *, ws=_UNSET):
        """X成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            float: 座標値。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
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
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
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
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
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
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
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
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
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
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        ws = _world_space(worldSpace)
        return self._set_coordinate(2, value, ws=ws, fast=fast)


class PointComponents(Components):
    """同一Shapeの頂点/CV番号列を保持し、保持順にXYZ座標を照会・一括編集する。

    座標値は保持せず、getPositionで現在値を取得する。XYZはcm単位で、
    setPositionは全要素に同じ絶対座標、setPositionsは番号ごとの座標行を設定する。
    """

    def setPositions(self, values, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
        """保持番号ごとのXYZ座標を、cmの絶対座標で設定する。

        座標の件数・有限値と現在の番号範囲を、書込み前に検証する。通常経路は
        cmds.xformで保持順に更新し、全点の書込み可否まで事前に保証するものではない。
        fastは対応条件を検査し、点配列を作ってOpenMayaへ一括設定する。

        Args:
            values (Iterable[Iterable[float]]): 保持番号と同じ件数のXYZ行。各値はcm単位。
            worldSpace (bool): Trueは保持DAGパスのworld空間、FalseはShapeのobject空間。短縮名ws。
            fast (bool): TrueはUndoなしの直接更新。入力履歴付きShapeと周期カーブは未対応。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            PointComponents: 自身。空集合と空列はShapeを再照会せず何もしない。
                通常経路はUndoが有効なら同じチャンクへ記録する。fastはUndo設定を変更しない。

        Raises:
            ValueError: 件数・座標・空間指定が不正、または必要なworld逆変換が特異な場合。
            TypeError: fastがbool以外の場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: 対象が無効・書込み不可、またはMayaが更新を拒否した場合。
            NotImplementedError: fastで入力履歴付きShapeまたは周期カーブを編集する場合。

        Note:
            検証を通っても、通常経路の後半やAPI更新中の失敗に対する原子性は保証しない。
            完了済み変更は自動で戻さない。共有Shapeの編集は全インスタンスへ影響する。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibComponentsSetPositions"):
            ws = _world_space(worldSpace)
            rows = self._coordinate_rows(values, 3)
            if not self._indices:
                return self
            self._validate()
            geometry_edit.setPositions(self._shape, self._indices, rows, ws, fast=fast)
            return self

    def getPositionX(self, worldSpace=_UNSET, *, ws=_UNSET):
        """X成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            list[float]: 保持順の座標値。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
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
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
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
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
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
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
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
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
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
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
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
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
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
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        ws = _world_space(worldSpace)
        point = Component._finite_coordinates(value, 3)
        return self.setPositions([point] * len(self), ws=ws, fast=fast)

    def mirror(self, axis="x", worldSpace=_UNSET, pivot=(0.0, 0.0, 0.0), *, fast=False, ws=_UNSET):
        """保持する頂点/CVのXYZを、指定空間の中心に対して軸ごとに反転する。

        現在座標を全件取得し、指定軸で2*pivot-座標を計算してからsetPositionsへ渡す。
        Transformのピボットや行列は変更しない。共有Shapeの変更は全インスタンスへ影響する。

        Args:
            axis (str): x、y、zの重複しない組合せ。大文字も使用可能。
            worldSpace (bool): Trueは保持DAGパスのworld空間、FalseはShapeのobject空間。短縮名ws。
            pivot (Iterable[float]): 指定空間での反転中心XYZ。cm単位。既定は原点。
            fast (bool): TrueはUndoなしの直接更新。setPositionsと同じ編集制限に従う。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            PointComponents: 自身。通常経路はUndoが有効なら同じチャンクへ記録する。

        Raises:
            ValueError: 軸・空間・中心が不正、またはworld行列が数値的にほぼ特異な場合。
            TypeError: fastがbool以外の場合。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが取得・更新を拒否した場合。
            NotImplementedError: fastで入力履歴付きShapeまたは周期カーブを編集する場合。

        Note:
            複製・結合・法線反転は行わない。周期CVの通常更新はMayaの連動規則に従う。
            途中の書込み失敗時に、完了済み変更は自動で戻さない。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibComponentsMirror"):
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
                # Maya はゼロスケールを微小値へ置換するため行列の大きさも考慮する。
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
