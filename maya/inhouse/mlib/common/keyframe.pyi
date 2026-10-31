# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
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
from typing import Iterator
from mlib.nodes.animCurve import AnimCurve



class Keyframe:
    """アニメーションカーブの1つのキーの参照。

    Args:
        curve (AnimCurve): キーを持つカーブ。
        index (int): 0始まりのキー番号。

    Raises:
        TypeError: curveがAnimCurveでない場合。
        IndexError: indexが範囲外の場合。
    """
    __slots__: tuple
    def __init__(self, curve, index) -> None: ...
    def __eq__(self, other):
        """同じカーブの同じ番号を指すか比較する。

        Args:
            other: 比較の相手。
        """
        ...
    def __hash__(self):
        """カーブと番号のハッシュを返す。"""
        ...
    def __repr__(self):
        """``Keyframe('pCube1_translateX', 3)`` の形で表示する。"""
        ...
    def getCurve(self) -> AnimCurve:
        """キーを持つカーブを返す。

        Returns:
            AnimCurve: 保持しているカーブ。
        """
        ...
    def getIndex(self) -> int:
        """キーの番号を返す。

        Returns:
            int: 作成時の0始まりのキー番号。
        """
        ...
    def isValid(self) -> bool:
        """カーブが有効で、番号がキー数の範囲内ならTrue。

        Returns:
            bool: 参照できればTrue。番号が同じキーを指し続けているかは確かめない。
        """
        ...
    def getTime(self, *, timeUnit: str = ...) -> float:
        """キーの入力(時刻、またはドリブンキーの入力値)を返す。

        Args:
            timeUnit (str): T型入力の単位。``"frame"`` / ``"sec"``。

        Returns:
            float: 入力。

        Raises:
            IndexError: 番号がキー数の範囲外になった場合。
            RuntimeError: カーブが無効(削除済み)の場合。
        """
        ...
    def getValue(self, *, unit: str = ..., timeUnit: str = ...) -> float:
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
        ...
    def setValue(self, value: float, *, unit: str = ..., timeUnit: str = ..., fast: bool = ...) -> Keyframe:
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
        ...
    def getTangent(self, *, unit: str = ...) -> dict:
        """接線の型・角度・ウェイト・ロックを返す(:meth:`AnimCurve.getTangent <mlib.nodes.animCurve.AnimCurve.getTangent>`)。

        Args:
            unit (str): 角度の単位。``"deg"`` / ``"rad"``。

        Returns:
            dict: AnimCurve.getTangent と同じ辞書。
        """
        ...
    def setTangent(self, *, unit: str = ..., fast: bool = ..., **kwargs) -> Keyframe:
        """接線を変える(:meth:`AnimCurve.setTangent <mlib.nodes.animCurve.AnimCurve.setTangent>`)。

        Args:
            unit (str): 角度の単位。``"deg"`` / ``"rad"``。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            **kwargs: AnimCurve.setTangent と同じフラグ。

        Returns:
            Keyframe: 自身。
        """
        ...
    def move(self, *, timeOffset: float = ..., valueOffset: float = ..., unit: str = ..., timeUnit: str = ...) -> Keyframe:
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
        ...
    def remove(self, *, keepCurve: bool = ..., fast: bool = ...) -> None:
        """キーを削除する。削除後、この参照と同じカーブの後ろの番号の参照は別のキーを指す。

        Args:
            keepCurve (bool): Trueは最後のキーを消してもカーブを残す。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。
        """
        ...
    def select(self, *, add: bool = ...) -> Keyframe:
        """Graph Editor・Dope Sheet でこのキーを選ぶ。

        Args:
            add (bool): Trueは今のキーの選択へ足す。Falseは置き換える。

        Returns:
            Keyframe: 自身。
        """
        ...
    def _require_valid(self):
        """カーブが有効で、番号が範囲内であることを確かめる。"""
        ...


class Keyframes:
    """キーの参照の集まり。複数のカーブにまたがってよく、カーブの初出順・カーブ内は番号の昇順で保持する。

    Args:
        keyframes (Iterable[Keyframe]): キーの参照。同じキーは1つにまとめる。

    Raises:
        TypeError: Keyframe以外を含む場合。
    """
    __hash__: None
    def __init__(self, keyframes=...) -> None: ...
    def __len__(self):
        """キーの数を返す。"""
        ...
    def __iter__(self):
        """カーブごと・番号の昇順に :class:`Keyframe` を返す。"""
        ...
    def __getitem__(self, index: int) -> Keyframe:
        """位置で :class:`Keyframe` を返す。

        Args:
            index (int): 並びの位置。負値は末尾から。

        Returns:
            Keyframe: その位置のキー。
        """
        ...
    def __contains__(self, item):
        """同じカーブの同じ番号を含むか返す。"""
        ...
    def __eq__(self, other):
        """同じカーブ・番号の組を同じ順で持つか比較する。"""
        ...
    def __repr__(self):
        """``Keyframes(count=4, curves=2)`` の形で表示する。"""
        ...
    def getCurves(self) -> list[AnimCurve]:
        """キーを持つカーブを返す。

        Returns:
            list[AnimCurve]: カーブ(初出順、重複なし)。
        """
        ...
    def iterCurves(self) -> Iterator[tuple[AnimCurve, Keyframes]]:
        """カーブごとに、そのカーブのキーの集まりを返す。

        Yields:
            tuple[AnimCurve, Keyframes]: カーブと、そのカーブのキー(番号の昇順)。
        """
        ...
    def getIndices(self, curve: AnimCurve) -> list[int]:
        """指定カーブのキーの番号を返す。

        Args:
            curve (AnimCurve): カーブ。

        Returns:
            list[int]: 番号の昇順。このカーブのキーが無ければ空。
        """
        ...
    def getTimes(self, *, timeUnit: str = ...) -> list[float]:
        """各キーの入力を返す(並びは反復と同じ)。

        Args:
            timeUnit (str): T型入力の単位。

        Returns:
            list[float]: 入力。
        """
        ...
    def getValues(self, *, unit: str = ..., timeUnit: str = ...) -> list[float]:
        """各キーの値を返す(並びは反復と同じ)。

        Args:
            unit (str): 角度出力の単位。
            timeUnit (str): 時間出力の単位。

        Returns:
            list[float]: 値。
        """
        ...
    def setValue(self, value: float, *, unit: str = ..., timeUnit: str = ..., fast: bool = ...) -> Keyframes:
        """全てのキーへ同じ値を書く(1回のUndo)。

        Args:
            value (float): 新しい値。
            unit (str): 角度出力の単位。
            timeUnit (str): 時間出力の単位。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            Keyframes: 自身。
        """
        ...
    def setTangent(self, *, unit=..., fast=..., **kwargs) -> Keyframes:
        """全てのキーの接線を変える(1回のUndo)。引数は :meth:`Keyframe.setTangent` と同じ。

        Returns:
            Keyframes: 自身。
        """
        ...
    def move(self, *, timeOffset: float = ..., valueOffset: float = ..., unit: str = ..., timeUnit: str = ...) -> Keyframes:
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
        ...
    def remove(self, *, keepCurve: bool = ..., fast: bool = ...) -> None:
        """全てのキーを削除する(1回のUndo)。削除後、この集まりの参照は別のキーを指しうる。

        Args:
            keepCurve (bool): Trueは全キーを消してもカーブを残す。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            None: 値を返さない。
        """
        ...
    def select(self, *, add: bool = ...) -> Keyframes:
        """Graph Editor・Dope Sheet でこれらのキーを選ぶ。空の集まりで add=False ならキーの選択を外す。

        Args:
            add (bool): Trueは今のキーの選択へ足す。Falseは置き換える。

        Returns:
            Keyframes: 自身。

        Raises:
            TypeError: addがbool以外の場合。
            RuntimeError: カーブが無効(削除済み)の場合。
        """
        ...

def _keyframe(curve, index):
    """検査を省いて :class:`Keyframe` を作る(番号を検査済みの集まりの反復用)。"""
    ...
