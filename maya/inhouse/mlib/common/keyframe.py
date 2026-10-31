"""アニメーションカーブのキーを「カーブ + キーの番号」の参照として扱う。

:class:`Keyframe` は1つのキー、:class:`Keyframes` は複数のキー(複数のカーブにまたがってよい)。
頂点(:class:`~mlib.components.vertex.Vertex`)と同じく作成時の番号を保つ参照で、キーの追加・削除・
入力の入れ替わりの後に同じキーを指すことは保証しない。ドリブンキーのカーブ(入力が時間でない animCurveU*)の
キーも同じクラスで扱い、その場合の「時刻」はカーブの入力値を指す。値・時刻の単位は
:class:`~mlib.nodes.animCurve.AnimCurve` と同じ(角度は度、距離はcm、時間はフレーム)。

.. code-block:: python

    import mlib
    from mlib.common import Selection

    for curve, keys in Selection.getKeyframes().iterCurves():
        print(curve, [key.getValue() for key in keys])
    mlib.getNode("pCube1_translateX").getKeyframe(0).setValue(5)
"""

import maya.cmds as cmds

from ..decorator import _require_bool, undoChunk


class Keyframe:
    """アニメーションカーブの1つのキーの参照。

    Args:
        curve (AnimCurve): キーを持つカーブ。
        index (int): 0始まりのキー番号。

    Raises:
        TypeError: curveがAnimCurveでない場合。
        IndexError: indexが範囲外の場合。
    """

    __slots__ = ("_curve", "_index")

    def __init__(self, curve, index):
        # nodes.animCurve はこのモジュールを読み込むため、循環importを避けて関数内で読み込む。
        from ..nodes.animCurve import AnimCurve

        if not isinstance(curve, AnimCurve):
            raise TypeError(f"curve must be an AnimCurve, not {type(curve).__name__}")
        curve._index(index)
        self._curve = curve
        self._index = index

    def __eq__(self, other):
        """同じカーブの同じ番号を指すか比較する。

        Args:
            other: 比較の相手。
        """
        if not isinstance(other, Keyframe):
            return NotImplemented
        return self._curve == other._curve and self._index == other._index

    def __hash__(self):
        """カーブと番号のハッシュを返す。"""
        return hash((self._curve, self._index))

    def __repr__(self):
        """``Keyframe('pCube1_translateX', 3)`` の形で表示する。"""
        name = self._curve.getName() if self._curve.isValid() else "<deleted>"
        return f"{type(self).__name__}({name!r}, {self._index})"

    def getCurve(self):
        """キーを持つカーブを返す。

        Returns:
            AnimCurve: 保持しているカーブ。
        """
        return self._curve

    def getIndex(self):
        """キーの番号を返す。

        Returns:
            int: 作成時の0始まりのキー番号。
        """
        return self._index

    def isValid(self):
        """カーブが有効で、番号がキー数の範囲内ならTrue。

        Returns:
            bool: 参照できればTrue。番号が同じキーを指し続けているかは確かめない。
        """
        return self._curve.isValid() and self._index < self._curve.getKeyCount()

    def getTime(self, *, timeUnit="frame"):
        """キーの入力(時刻、またはドリブンキーの入力値)を返す。

        Args:
            timeUnit (str): T型入力の単位。``"frame"`` / ``"sec"``。

        Returns:
            float: 入力。

        Raises:
            IndexError: 番号がキー数の範囲外になった場合。
            RuntimeError: カーブが無効(削除済み)の場合。
        """
        self._require_valid()
        return self._curve.getKeyInputs(timeUnit=timeUnit)[self._index]

    def getValue(self, *, unit="deg", timeUnit="frame"):
        """キーの値を返す。

        Args:
            unit (str): 角度出力(A型)の単位。``"deg"`` / ``"rad"``。
            timeUnit (str): 時間出力の単位。``"frame"`` / ``"sec"``。

        Returns:
            float: 値。

        Raises:
            IndexError: 番号がキー数の範囲外になった場合。
            RuntimeError: カーブが無効(削除済み)の場合。
        """
        self._require_valid()
        return self._curve.getKeyValues(unit=unit, timeUnit=timeUnit)[self._index]

    def setValue(self, value, *, unit="deg", timeUnit="frame", fast=False):
        """キーの値を、接線型を保ったまま変える。

        Args:
            value (float): 新しい値(:meth:`getValue` と同じ単位)。
            unit (str): 角度出力(A型)の単位。``"deg"`` / ``"rad"``。
            timeUnit (str): 時間出力の単位。``"frame"`` / ``"sec"``。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Keyframe: 自身。

        Raises:
            TypeError: 数値へ変換できない型、またはfastがbool以外の場合。
            ValueError: 非有限値、または単位名が未対応の場合。
            IndexError: 番号がキー数の範囲外になった場合。
            RuntimeError: カーブが無効(削除済み)の場合。
        """
        self._curve._set_key_values(self._index, value, unit=unit, timeUnit=timeUnit, fast=fast)
        return self

    def getTangent(self, *, unit="deg"):
        """接線の型・角度・ウェイト・ロックを返す(:meth:`AnimCurve.getTangent <mlib.nodes.animCurve.AnimCurve.getTangent>`)。

        Args:
            unit (str): 角度の単位。``"deg"`` / ``"rad"``。

        Returns:
            dict: AnimCurve.getTangent と同じ辞書。
        """
        return self._curve.getTangent(self._index, unit=unit)

    def setTangent(self, *, unit="deg", fast=False, **kwargs):
        """接線を変える(:meth:`AnimCurve.setTangent <mlib.nodes.animCurve.AnimCurve.setTangent>`)。

        Args:
            unit (str): 角度の単位。``"deg"`` / ``"rad"``。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            **kwargs: AnimCurve.setTangent と同じフラグ。

        Returns:
            Keyframe: 自身。
        """
        self._curve.setTangent(self._index, unit=unit, fast=fast, **kwargs)
        return self

    def move(self, *, timeOffset=0, valueOffset=0, unit="deg", timeUnit="frame"):
        """キーの入力と値をずらす(:meth:`AnimCurve.moveKey <mlib.nodes.animCurve.AnimCurve.moveKey>`)。

        入力は隣のキーを越えない(Mayaの ``keyframe -relative`` と同じ)。番号は変わらない。

        Args:
            timeOffset (float): 入力の移動量。
            valueOffset (float): 値の移動量。
            unit (str): 角度出力の単位。
            timeUnit (str): 時間の単位。

        Returns:
            Keyframe: 自身。
        """
        self._curve.moveKey(self._index, timeOffset=timeOffset, valueOffset=valueOffset, unit=unit,
                            timeUnit=timeUnit)
        return self

    def remove(self, *, keepCurve=True, fast=False):
        """キーを削除する。削除後、この参照と同じカーブの後ろの番号の参照は別のキーを指す。

        Args:
            keepCurve (bool): Trueは最後のキーを消してもカーブを残す。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。
        """
        self._curve.removeKey(self._index, keepCurve=keepCurve, fast=fast)

    def select(self, *, add=False):
        """Graph Editor・Dope Sheet でこのキーを選ぶ。

        Args:
            add (bool): Trueは今のキーの選択へ足す。Falseは置き換える。

        Returns:
            Keyframe: 自身。
        """
        Keyframes([self]).select(add=add)
        return self

    def _require_valid(self):
        """カーブが有効で、番号が範囲内であることを確かめる。"""
        self._curve._require_valid("access attributes of")
        self._curve._index(self._index)


class Keyframes:
    """キーの参照の集まり。複数のカーブにまたがってよく、カーブの初出順・カーブ内は番号の昇順で保持する。

    Args:
        keyframes (Iterable[Keyframe]): キーの参照。同じキーは1つにまとめる。

    Raises:
        TypeError: Keyframe以外を含む場合。
    """

    #: 中身を変えられる集まりなのでハッシュ不可(Components と同じ)。
    __hash__ = None

    def __init__(self, keyframes=()):
        groups = {}
        for keyframe in keyframes:
            if not isinstance(keyframe, Keyframe):
                raise TypeError(f"Expected Keyframe, not {type(keyframe).__name__}")
            groups.setdefault(keyframe._curve, set()).add(keyframe._index)
        self._groups = [(curve, sorted(indices)) for curve, indices in groups.items()]

    def __len__(self):
        """キーの数を返す。"""
        return sum(len(indices) for _, indices in self._groups)

    def __iter__(self):
        """カーブごと・番号の昇順に :class:`Keyframe` を返す。"""
        for curve, indices in self._groups:
            for index in indices:
                yield _keyframe(curve, index)

    def __getitem__(self, index):
        """位置で :class:`Keyframe` を返す。

        Args:
            index (int): 並びの位置。負値は末尾から。

        Returns:
            Keyframe: その位置のキー。
        """
        return list(self)[index]

    def __contains__(self, item):
        """同じカーブの同じ番号を含むか返す。"""
        if not isinstance(item, Keyframe):
            return False
        return any(curve == item._curve and item._index in indices for curve, indices in self._groups)

    def __eq__(self, other):
        """同じカーブ・番号の組を同じ順で持つか比較する。"""
        if not isinstance(other, Keyframes):
            return NotImplemented
        return self._groups == other._groups

    def __repr__(self):
        """``Keyframes(count=4, curves=2)`` の形で表示する。"""
        return f"{type(self).__name__}(count={len(self)}, curves={len(self._groups)})"

    def getCurves(self):
        """キーを持つカーブを返す。

        Returns:
            list[AnimCurve]: カーブ(初出順、重複なし)。
        """
        return [curve for curve, _ in self._groups]

    def iterCurves(self):
        """カーブごとに、そのカーブのキーの集まりを返す。

        Yields:
            tuple[AnimCurve, Keyframes]: カーブと、そのカーブのキー(番号の昇順)。
        """
        for curve, indices in self._groups:
            yield curve, Keyframes(_keyframe(curve, index) for index in indices)

    def getIndices(self, curve):
        """指定カーブのキーの番号を返す。

        Args:
            curve (AnimCurve): カーブ。

        Returns:
            list[int]: 番号の昇順。このカーブのキーが無ければ空。
        """
        for held, indices in self._groups:
            if held == curve:
                return list(indices)
        return []

    def getTimes(self, *, timeUnit="frame"):
        """各キーの入力を返す(並びは反復と同じ)。

        Args:
            timeUnit (str): T型入力の単位。

        Returns:
            list[float]: 入力。
        """
        result = []
        for curve, indices in self._groups:
            inputs = curve.getKeyInputs(timeUnit=timeUnit)
            result.extend(inputs[index] for index in indices)
        return result

    def getValues(self, *, unit="deg", timeUnit="frame"):
        """各キーの値を返す(並びは反復と同じ)。

        Args:
            unit (str): 角度出力の単位。
            timeUnit (str): 時間出力の単位。

        Returns:
            list[float]: 値。
        """
        result = []
        for curve, indices in self._groups:
            values = curve.getKeyValues(unit=unit, timeUnit=timeUnit)
            result.extend(values[index] for index in indices)
        return result

    def setValue(self, value, *, unit="deg", timeUnit="frame", fast=False):
        """全てのキーへ同じ値を書く(1回のUndo)。

        Args:
            value (float): 新しい値。
            unit (str): 角度出力の単位。
            timeUnit (str): 時間出力の単位。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            Keyframes: 自身。
        """
        with undoChunk("mlibKeyframesSetValue"):
            for curve, indices in self._groups:
                curve._set_key_values(indices, value, unit=unit, timeUnit=timeUnit, fast=fast)
        return self

    def setTangent(self, *, unit="deg", fast=False, **kwargs):
        """全てのキーの接線を変える(1回のUndo)。引数は :meth:`Keyframe.setTangent` と同じ。

        Returns:
            Keyframes: 自身。
        """
        with undoChunk("mlibKeyframesSetTangent"):
            for curve, indices in self._groups:
                for index in indices:
                    curve.setTangent(index, unit=unit, fast=fast, **kwargs)
        return self

    def move(self, *, timeOffset=0, valueOffset=0, unit="deg", timeUnit="frame"):
        """全てのキーの入力と値をずらす(カーブごとに1回で動かし、全体で1回のUndo)。

        同じカーブの対象のキー同士は一緒に動くため、互いを越える制限は受けない。

        Args:
            timeOffset (float): 入力の移動量。
            valueOffset (float): 値の移動量。
            unit (str): 角度出力の単位。
            timeUnit (str): 時間の単位。

        Returns:
            Keyframes: 自身。
        """
        with undoChunk("mlibKeyframesMove"):
            for curve, indices in self._groups:
                curve.moveKey(indices, timeOffset=timeOffset, valueOffset=valueOffset, unit=unit,
                              timeUnit=timeUnit)
        return self

    def remove(self, *, keepCurve=True, fast=False):
        """全てのキーを削除する(1回のUndo)。削除後、この集まりの参照は別のキーを指しうる。

        Args:
            keepCurve (bool): Trueは全キーを消してもカーブを残す。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            None: 値を返さない。
        """
        with undoChunk("mlibKeyframesRemove"):
            for curve, indices in self._groups:
                curve.removeKey(indices, keepCurve=keepCurve, fast=fast)

    def select(self, *, add=False):
        """Graph Editor・Dope Sheet でこれらのキーを選ぶ。空の集まりで add=False ならキーの選択を外す。

        Args:
            add (bool): Trueは今のキーの選択へ足す。Falseは置き換える。

        Returns:
            Keyframes: 自身。

        Raises:
            TypeError: addがbool以外の場合。
            RuntimeError: カーブが無効(削除済み)の場合。
        """
        _require_bool(add, "add")
        with undoChunk("mlibKeyframesSelect"):
            if not add:
                # 対象を省いた selectKey -clear は選択ノードが無いと失敗するため、選んでいるカーブを指定して外す。
                selected = cmds.keyframe(query=True, selected=True, name=True) or []
                if selected:
                    cmds.selectKey(selected, clear=True)
            for curve, indices in self._groups:
                ranges = curve._key_ranges(indices, None, "frame")
                cmds.selectKey(curve.getFullName(), index=ranges, add=True, animation="objects")
        return self


def _keyframe(curve, index):
    """検査を省いて :class:`Keyframe` を作る(番号を検査済みの集まりの反復用)。"""
    keyframe = Keyframe.__new__(Keyframe)
    keyframe._curve = curve
    keyframe._index = index
    return keyframe
