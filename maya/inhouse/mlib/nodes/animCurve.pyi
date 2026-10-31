# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""アニメーションカーブの共通操作。通常編集はUndo、fastはAPI直接更新。"""

import math
from contextlib import contextmanager
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
from ..common.keyframe import Keyframe, Keyframes
from ..common.units import angleToUi
from ..core.attributeType import _convert_units, _from_seconds, _to_seconds
from ..core.fastWrite import require_writable
from ..core.nodeEdit import delete_nodes
from ..decorator import _edit_context, _require_bool, undoChunk
from ..util import _angle_unit, _from_radians, _time_unit, _to_radians
from .node import Node
from typing import Any, Iterable, Sequence
from mlib._stubtypes import GeneratorContextManager
from mlib.plugs.plug import Plug

_TANGENT_TYPES: dict
_TANGENT_NAMES: dict

def _default_tangents() -> tuple[int, int]:
    """Mayaの設定の既定の接線型(``keyTangent -q -g``)を、fastで使えるAPIの定数で返す。

    Returns:
        tuple[int, int]: 入力・出力の接線型。fastで使えない型(fixed・入力のstep/stepnext等)はautoにする。
    """
    ...


class AnimCurve(Node):
    """animCurveノードを参照し、8種類のカーブのキー・接線・外挿を編集する。

    入力T型は既定で現在のUI時間単位のフレーム(各メソッドの ``timeUnit="sec"`` で秒)、U型は無次元。
    出力はA型が度(各メソッドの ``unit="rad"`` でラジアン)、L型がcm、T型がフレーム(``timeUnit="sec"`` で秒)、
    U型が無次元。接線の角度も既定で度。T型とA型の両方を持つカーブ(animCurveTA)ではunitとtimeUnitを
    別々に指定する。
    ドライバーPlugの単位変換はDrivenKeyが担当する。
    通常編集はUI単位へ換算してcmdsへ渡し、Undo有効時に一つのチャンクへまとめる。
    fastはUndo設定を変更せずOpenMayaで直接更新する。失敗時の自動復元は保証しない。
    """
    def isTimeInput(self) -> bool:
        """横軸が時間ならTrue、単位なしならFalse。

        Returns:
            bool: 横軸が時間ならTrue、単位なしならFalse。

        Raises:
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        ...
    def getKeyCount(self) -> int:
        """キー数。

        Returns:
            int: キー数。
        """
        ...
    def getKeyInputs(self, *, timeUnit: str = ...) -> list[float]:
        """カーブのキー入力をキー番号順で取得する。

        入力T型はtimeUnitの単位(既定は現在のUI時間単位のフレーム)、U型は無次元の入力値を返す。
        U型のドライバーPlugのUI表示値へは変換しない。

        Args:
            timeUnit (str): 入力T型の単位。既定 ``"frame"`` はフレーム、``"sec"`` は秒
                (``"frames"`` / ``"seconds"`` 等の別名も可)。U型では使わない。

        Returns:
            list[float]: 新しい入力値リスト。変更してもカーブへ書き戻さない。

        Raises:
            TypeError: timeUnitが文字列以外の場合。
            ValueError: timeUnitが未対応の単位名の場合。
        """
        ...
    def getKeyValues(self, *, unit: str = ..., timeUnit: str = ...) -> list[float]:
        """カーブのキー出力値をキー番号順で取得する。

        角度はunitの単位(既定は度)、距離はcm、時間はtimeUnitの単位(既定はフレーム)、その他は無次元で返す。
        時間出力はMFnAnimCurve.value()の版差を避け、time型のキー値Plugから読む。

        Args:
            unit (str): 角度出力(A型)の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
                (``"degree"`` 等の別名も可)。他の型では使わない。
            timeUnit (str): 時間出力(TT・UT型)の単位。既定 ``"frame"`` は現在のUI時間単位のフレーム、
                ``"sec"`` は秒。他の型では使わない。

        Returns:
            list[float]: 新しい出力値リスト。変更してもカーブへ書き戻さない。

        Raises:
            TypeError: unit・timeUnitが文字列以外の場合。
            ValueError: unit・timeUnitが未対応の単位名の場合。
        """
        ...
    def evaluate(self, input: float, *, unit: str = ..., timeUnit: str = ...) -> float:
        """カーブ単体を指定入力で評価する。現在時刻は変更しない。

        接続先の合成結果ではなく、カーブの補間・外挿値を返す。
        時間出力はMaya 2022/2023のAPI版差を補正してから、timeUnitの単位へ揃える。

        Args:
            input (float): T型入力はtimeUnitの単位(既定はフレーム)、U型入力は無次元。
                float()で変換し有限性を検査する。
            unit (str): 角度出力(A型)の戻り値の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン。
            timeUnit (str): T型入力のinputと、時間出力(TT・UT型)の戻り値の単位。既定 ``"frame"`` は
                現在のUI時間単位のフレーム、``"sec"`` は秒。

        Returns:
            float: 出力型に従う度(unit)/cm/フレーム(timeUnit)、または無次元の値。

        Raises:
            TypeError: float()へ変換できない型、またはunit・timeUnitが文字列以外。
            ValueError: 非有限値、float()変換で受理できない値、またはunit・timeUnitが未対応の単位名。
            RuntimeError: 空カーブ、またはMayaの評価失敗。空カーブは入力変換より先に拒否する。
        """
        ...
    def setKey(self, input: float, value: float, inTangentType: str | None = ..., outTangentType: str | None = ..., *, unit: str = ..., timeUnit: str = ..., fast: bool = ...) -> AnimCurve:
        """キーを追加する。同じ入力位置にキーがあれば値と、指定した接線型を更新する。

        接線型を省略すると ``cmds.setKeyframe`` と同じく、既存のキーは接線型を保ち、新しいキーは
        Mayaの設定(Preferences > Animation の Default tangent、``keyTangent -q -g``)に従う。
        通常はUI単位へ換算してsetKeyframeを呼ぶ。fastの既存キーは値→入力接線型→出力接線型の
        順に更新する。新規キーは両接線型を指定し、時間出力の値は追加後に設定する。
        後続の失敗で先行の変更を自動復元しない。

        Args:
            input (float): T型入力はtimeUnitの単位(既定はフレーム)、U型入力は無次元。
            value (float): 出力型に従う度(unit)/cm/フレーム(timeUnit)、または無次元。inputと共に有限値へ変換する。
            inTangentType (str | None): Mayaの入力接線型。Noneは上記の既定。fastのstepはautoへ補正する。
            outTangentType (str | None): Mayaの出力接線型。Noneは上記の既定。
            unit (str): 角度出力(A型)のvalueの単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
                (``"degree"`` 等の別名も可)。他の型では使わない。
            timeUnit (str): T型入力のinputと、時間出力(TT・UT型)のvalueの単位。既定 ``"frame"`` は
                現在のUI時間単位のフレーム、``"sec"`` は秒(``"seconds"`` 等の別名も可)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AnimCurve: 自身。fixed接線の角度・ウェイト指定にはsetTangentを使う。

        Raises:
            TypeError: fastがbool以外、unit・timeUnitが文字列以外、または数値へ変換できない型。
            ValueError: 非有限値、不正な数値、未対応のunit・timeUnit、またはfastでfixed/global/未知の接線型を指定した場合。
            RuntimeError: ノードが無効(削除済み)の場合。fastも通常と同じ文言で、編集前に拒否する。
            NotImplementedError: fastの入力接線にstepnextを指定した場合。編集前に拒否する。
        """
        ...
    def removeKey(self, index: int | Sequence[int] | None = ..., *, time: float | Sequence[float] | None = ..., timeUnit: str = ..., keepCurve: bool = ..., fast: bool = ...) -> AnimCurve:
        """指定番号、または入力の範囲にあるキーを削除する。キークリップボードは変更しない。

        index と time はどちらか一方を指定する。既定(keepCurve=True)では全キーを削除してもカーブを残す
        (:meth:`Plug.removeKey <mlib.plugs.plug.Plug.removeKey>`・``cmds.cutKey`` は空になったカーブを削除する)。

        Args:
            index (int | Sequence[int] | None): 0始まりのキー番号、またはその並び。
            time (float | Sequence[float] | None): 削除する入力の時刻、または両端を含む範囲 ``(start, end)``。
                T型入力はtimeUnitの単位(既定はフレーム)、U型入力は無次元。範囲内にキーが無ければ何もしない。
            timeUnit (str): T型入力のtimeの単位。``"frame"`` / ``"sec"``。
            keepCurve (bool): Trueは全キーを消してもカーブを残す。FalseはMayaと同じく空のカーブを削除する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AnimCurve: 自身。keepCurve=Falseでカーブを削除した場合、この参照は無効になる。

        Raises:
            TypeError: indexとtimeの両方・どちらも指定しない場合、timeが数値・2つの数値の並び以外、
                またはkeepCurve・fastがbool以外の場合。
            ValueError: timeが有限でない、範囲の開始が終了より大きい、またはtimeUnitが未対応の単位名の場合。
            IndexError: indexが範囲外の場合。
        """
        ...
    def replaceKeys(self, keys: Iterable[Sequence], *, unit: str = ..., timeUnit: str = ...) -> AnimCurve:
        """カーブを残したまま、全キーを指定したキーへ置き換える(1回のUndo)。

        ``keys`` の各要素は ``(入力, 値)`` または ``(入力, 値, 入力接線型, 出力接線型)``。接線型の省略・None・
        空文字列(:meth:`getTangent` が未登録の型に返す値)はMayaの設定(Default tangent)に従う。同じ入力が重なった場合は後の要素で上書きする。空の並びは
        全キーを消して空のカーブを残す。全要素を検査してからカーブを変える。fast引数は持たない。

        Args:
            keys (Iterable[Sequence]): 新しいキーの並び。入力・値の単位は :meth:`setKey` と同じ。
            unit (str): 角度出力(A型)の値の単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力と、時間出力の値の単位。``"frame"`` / ``"sec"``。

        Returns:
            AnimCurve: 自身。

        Raises:
            TypeError: 要素が2つ・4つの並びでない、または数値へ変換できない型の場合。
            ValueError: 非有限値、未知の接線型・fixed(角度・ウェイトは :meth:`setTangent` で書く)、
                またはunit・timeUnitが未対応の単位名の場合。
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        ...
    def getTangent(self, index: int, *, unit: str = ...) -> dict:
        """指定キーの入力/出力接線型、角度、ウェイトとロック状態を取得する。

        角度はMAngleからunitの単位(既定は度)へ変換する。接線ウェイトはgetTangentAngleWeight()の
        返却値をそのまま使い、一律の距離単位などへ追加変換しない(``keyTangent`` の照会と同じく、
        T型入力のウェイトは現在のUI時間単位に依存する)。時間の単位の引数(timeUnit)は持たない。
        lock/weightLockはキー単位、weightedTangentsはカーブ全体の状態である。

        Args:
            index (int): 0始まりの既存キー番号。
            unit (str): inAngle/outAngleの単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
                (``"degree"`` 等の別名も可)。

        Returns:
            dict: inTangentType/outTangentType、inAngle/outAngle、inWeight/outWeight、
                lock、weightLock、weightedTangentsの新しい辞書。型名はMayaコマンド表記で、
                未登録のAPI接線型は空文字列。辞書を変更してもカーブは更新しない。

        Raises:
            IndexError: bool、非int、負値、またはキー数以上の番号の場合。
            TypeError: unitが文字列以外の場合。
            ValueError: unitが未対応の単位名の場合。
        """
        ...
    def setTangent(self, index: int, *, unit: str = ..., fast: bool = ..., **kwargs) -> AnimCurve:
        """指定キーの接線をMayaの接線ロック規則に従って変更する。

        weightedTangentsを指定した場合はカーブ全体のウェイト付き接線モードだけを適用し、
        同時指定したキー別フラグは適用しない。fastでも同時指定値の検証は省略しない。
        通常はkeyTangentへ角度をUI単位に換算して渡す。fastはlock、weightLock、
        入力側、出力側の順に更新し、後半の失敗による先行変更を自動復元しない。

        Args:
            index (int): 0始まりの既存キー番号。
            unit (str): inAngle/outAngleの単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
                (``"degree"`` 等の別名も可)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            **kwargs: getTangent()の辞書と同じ9種類の長名フラグ。角度はunitの単位、
                接線ウェイトはAPIの値を使う。fastでは角度/ウェイトをfloat()で有限性検査し、
                負のウェイトを拒否する。fastの型名は大文字小文字を区別せず、spline表記を使う。
                入力stepはautoへ補正する。ロックは自動解除しない。

        Returns:
            AnimCurve: 自身。

        Raises:
            ValueError: フラグが空/未知、unitが未対応、またはfastで不正値やglobal/未知の接線型を指定した場合。
            TypeError: unitが文字列以外の場合。
            IndexError: キー番号が不正な場合。
            NotImplementedError: fastで入力接線にstepnextを指定した場合。
                ロック・ウェイトを含む更新より前に拒否する。
        """
        ...
    def getInfinity(self) -> dict:
        """pre/postをキーとした外挿方法名。

        Returns:
            dict: pre/postをキーとした外挿方法名。
        """
        ...
    def setInfinity(self, *, pre: str | None = ..., post: str | None = ..., fast: bool = ...) -> AnimCurve:
        """指定した側だけ外挿方法を変更する。省略した側は維持する。

        Args:
            pre (str | None): constant/linear/cycle/cycleRelative/oscillate。
                Noneは変更しない。
            post (str | None): preと同じ選択肢。Noneは変更しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AnimCurve: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 指定した外挿方法が不正な場合。両側を変更前に検証する。
            RuntimeError: ノードが無効、または更新先がロック・接続などで書込み不可の場合。
        """
        ...
    def moveKey(self, index: int | Sequence[int] | None = ..., *, time: float | Sequence[float] | None = ..., timeOffset: float = ..., valueOffset: float = ..., unit: str = ..., timeUnit: str = ...) -> AnimCurve:
        """キーの入力(時刻)と値をずらす。index・timeを両方省略すると全キーを動かす。

        Mayaの ``keyframe -edit -relative`` と同じく、入力をずらしたキーは対象でない隣のキーを越えない
        (越える量は隣のキーの直前で止まる)。fast引数は持たない(範囲を1回で処理するcmds.keyframeの方が、
        キーごとにOpenMayaで書くより速い)。

        Args:
            index (int | Sequence[int] | None): 0始まりのキー番号、またはその並び。
            time (float | Sequence[float] | None): 動かすキーの入力の時刻、または両端を含む範囲
                ``(start, end)``。T型入力はtimeUnitの単位、U型入力は無次元。indexとは同時に指定できない。
            timeOffset (float): 入力の移動量。T型入力はtimeUnitの単位(既定はフレーム)、U型は無次元。
            valueOffset (float): 値の移動量。角度はunitの単位(既定は度)、距離cm、時間はtimeUnitの単位。
            unit (str): 角度出力(A型)のvalueOffsetの単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力のtime・timeOffsetと、時間出力のvalueOffsetの単位。``"frame"`` / ``"sec"``。

        Returns:
            AnimCurve: 自身。対象のキーが無ければ変更しない。

        Raises:
            TypeError: indexとtimeの両方を指定した、unit・timeUnitが文字列以外、または数値へ変換できない型の場合。
            ValueError: 非有限値、範囲の開始が終了より大きい、またはunit・timeUnitが未対応の単位名の場合。
            IndexError: indexが範囲外の場合。
        """
        ...
    def scaleKey(self, inputScale: float = ..., valueScale: float = ..., inputPivot: float = ..., valuePivot: float = ..., *, index: int | Sequence[int] | None = ..., time: float | Sequence[float] | None = ..., unit: str = ..., timeUnit: str = ...) -> AnimCurve:
        """キーを基準値のまわりで拡縮する。index・timeを両方省略すると全キー。接線処理はMayaのscaleKeyに従う。

        fast引数は持たない(:meth:`moveKey` と同じ理由)。

        Args:
            inputScale (float): 横軸倍率(単位なし)。0はキーが重なるためValueError。
            valueScale (float): 縦軸倍率(単位なし)。
            inputPivot (float): 横軸の基準値。T型入力はtimeUnitの単位(既定はフレーム)、U型は無次元。
            valuePivot (float): 縦軸の基準値。角度出力(A型)はunitの単位(既定は度)、時間出力はtimeUnitの単位。
            index (int | Sequence[int] | None): 0始まりのキー番号、またはその並び。
            time (float | Sequence[float] | None): 拡縮するキーの入力の時刻、または両端を含む範囲。
                indexとは同時に指定できない。
            unit (str): 角度出力のvaluePivotの単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力のtime・inputPivotと、時間出力のvaluePivotの単位。``"frame"`` / ``"sec"``。

        Returns:
            AnimCurve: 自身。

        Raises:
            TypeError: indexとtimeの両方を指定した、unit・timeUnitが文字列以外、または数値へ変換できない型の場合。
            ValueError: inputScaleが0、非有限値、またはunit・timeUnitが未対応の単位名の場合。
            IndexError: indexが範囲外の場合。
        """
        ...
    def mirror(self, input: bool = ..., value: bool = ..., inputPivot: float = ..., valuePivot: float = ..., *, index: int | Sequence[int] | None = ..., time: float | Sequence[float] | None = ..., unit: str = ..., timeUnit: str = ...) -> AnimCurve:
        """入力軸・出力軸を反転する。内部のscaleKeyでUndoをまとめる。fast引数は持たない(:meth:`scaleKey` と同じ)。

        Args:
            input (bool): 横軸を反転するか。
            value (bool): 縦軸を反転するか。
            inputPivot (float): 横軸の反転中心。T型入力はtimeUnitの単位(既定はフレーム)、U型は無次元。
            valuePivot (float): 縦軸の反転中心。角度出力(A型)はunitの単位(既定は度)、時間出力はtimeUnitの単位。
            index (int | Sequence[int] | None): 反転するキーの番号。index・timeの両方の省略は全キー。
            time (float | Sequence[float] | None): 反転するキーの入力の時刻、または両端を含む範囲。
            unit (str): 角度出力のvaluePivotの単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力のinputPivotと、時間出力のvaluePivotの単位。``"frame"`` / ``"sec"``。

        Returns:
            AnimCurve: 自身。
        """
        ...
    def getDrivenPlugs(self) -> list[Plug]:
        """このカーブが動かしているアトリビュート(unitConversion等の変換ノードを飛ばした先)を返す。

        Returns:
            list[Plug]: ``output`` の出力先。つながっていなければ空リスト。

        Raises:
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        ...
    def getKeyframe(self, index: int) -> Keyframe:
        """指定番号のキーの参照を返す。

        Args:
            index (int): 0始まりの既存キー番号。

        Returns:
            Keyframe: このカーブと番号を保つ参照。

        Raises:
            IndexError: bool、非int、負値、またはキー数以上の番号の場合。
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        ...
    def getKeyframes(self, indices: Iterable[int] | None = ...) -> Keyframes:
        """キーの参照の集まりを返す。

        Args:
            indices (Iterable[int] | None): 0始まりのキー番号の並び。Noneは全キー。

        Returns:
            Keyframes: このカーブのキーの集まり(番号の昇順、重複なし)。

        Raises:
            IndexError: 範囲外の番号を含む場合。
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        ...
    def _set_key_values(self, indices: int | Sequence[int], value: float, *, unit: str = ..., timeUnit: str = ..., fast: bool = ...) -> AnimCurve:
        """指定番号のキーの値を、接線型を保ったまま変える(:class:`~mlib.common.keyframe.Keyframe` の入口)。

        Args:
            indices (int | Sequence[int]): 0始まりのキー番号。
            value (float): 新しい値。単位は :meth:`setKey` と同じ。
            unit (str): 角度出力(A型)の値の単位。
            timeUnit (str): 時間出力の値の単位。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            AnimCurve: 自身。
        """
        ...
    def _kept_curve(self) -> GeneratorContextManager[Any]:
        """全キーの削除でMayaがカーブを消さないよう、その間だけノードをロックする。

        ``cmds.cutKey`` は空になったカーブ(つながっていないものも)を削除するが、ロックしたノードは
        削除しない。ロックの変更もUndoへ記録され、呼び出し側のチャンクにまとまる。
        """
        ...
    def _set_api_value(self, fn: oma2.MFnAnimCurve, index: int, value: float) -> None:
        """キー値を直接更新し、時間出力の秒をMTimeで保持する。

        Args:
            fn (oma2.MFnAnimCurve): 更新対象カーブ。
            index (int): キー番号。
            value (float): 内部単位の値。

        Returns:
            None: 値を返さない。
        """
        ...
    def _output_angle_unit(self, unit: str) -> str:
        """角度の単位名を検証し、出力が角度(A型)のカーブだけ換算する単位を返す。

        Args:
            unit (str): 角度の単位名。

        Returns:
            str: A型のカーブでは ``"deg"`` / ``"rad"``、それ以外は換算しない ``"rad"``。

        Raises:
            TypeError: unitが文字列以外の場合。
            ValueError: unitが未対応の単位名の場合。
        """
        ...
    def _input_time_unit(self, time_unit: str) -> str:
        """時間の単位名を検証し、入力が時間(T型)のカーブだけ換算する単位を返す。

        Args:
            time_unit (str): 時間の単位名。

        Returns:
            str: T型入力のカーブでは ``"frame"`` / ``"sec"``、U型入力では換算しない ``"sec"``。

        Raises:
            TypeError: time_unitが文字列以外の場合。
            ValueError: time_unitが未対応の単位名の場合。
        """
        ...
    def _output_time_unit(self, time_unit: str) -> str:
        """時間の単位名を検証し、出力が時間(TT・UT型)のカーブだけ換算する単位を返す。

        Args:
            time_unit (str): 時間の単位名。

        Returns:
            str: 時間出力のカーブでは ``"frame"`` / ``"sec"``、それ以外は換算しない ``"sec"``。

        Raises:
            TypeError: time_unitが文字列以外の場合。
            ValueError: time_unitが未対応の単位名の場合。
        """
        ...
    def _curve_fn(self) -> oma2.MFnAnimCurve:
        """保持ノードのAPI 2.0カーブ関数セットを返す。

        削除済みの MObject へ関数セットを作るとMayaが異常終了するため、先に有効性を検査する。

        Returns:
            oma2.MFnAnimCurve: 有効なカーブの関数セット。

        Raises:
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        ...
    def _api_input(self, value):
        """内部単位の入力をAPIが要求する時間値または数値へ変換する。"""
        ...
    @staticmethod
    def _api_number(value):
        """時間値を秒、その他を数値として返す。"""
        ...
    @staticmethod
    def _tangent_type(name: str, *, incoming: bool = ..., key: bool = ...):
        """Mayaの接線名を変換し、直接更新できない組合せを更新前に拒否する。

        Args:
            name (str): Maya標準の接線型名。
            incoming (bool): 入力接線として解釈するか。
            key (bool): setKeyでキーを作成・更新するか。
        """
        ...
    @staticmethod
    def _tangent_name(value):
        """API接線型をMayaのコマンド表記へ変換する。"""
        ...
    def _require_curve_writable(self):
        """直接編集前に、キーを格納するアトリビュート(keyTimeValue)のロック・入力接続を検査する。

        全キーの要素を調べるとキー数に比例して遅くなる(キーを打つたびに全要素を調べる)ため、
        マルチアトリビュート自体だけを調べる。要素ごとのロックはcmds.setKeyframeでもエラーにならない。

        Raises:
            RuntimeError: ノードが無効、またはkeyTimeValueがロック・入力接続されている場合。
        """
        ...
    def _unit_value(self, value: float, output: bool = ..., to_ui: bool = ...) -> float:
        """カーブの入出力アトリビュート定義に従い、コマンド境界で単位を変換する。

        Args:
            value (float): 変換する値。
            output (bool): Trueはoutput、Falseはinputの定義を使う。
            to_ui (bool): Trueは内部単位からUI単位、FalseはUI単位から内部単位へ変換する。

        Returns:
            float: 単位型に応じた値。無次元のアトリビュートでは値をそのまま使う。
        """
        ...
    @staticmethod
    def _finite(value: object) -> float:
        """キーや接線の入力をfloatへ変換し、非有限値を拒否する。

        float()に従うため、変換可能な数値文字列やboolもここでは受理する。
        キー番号などの厳密なint検証とは別の責務とする。

        Args:
            value (object): float()へ渡す値。

        Returns:
            float: 有限な値。

        Raises:
            TypeError: float()が受理しない型の場合。
            ValueError: 変換できない文字列など、またはNaN/正負の無限大の場合。
        """
        ...
    def _time_span(self, time: float | Sequence[float], time_unit: str) -> tuple[int, int] | None:
        """入力の時刻・範囲を、その中にあるキーの番号の範囲へ変換する。

        Args:
            time (float | Sequence[float]): 時刻、または両端を含む範囲。
            time_unit (str): T型入力のtimeの単位。

        Returns:
            tuple[int, int] | None: 最初と最後のキー番号。範囲内にキーが無ければNone。

        Raises:
            TypeError: timeが数値・2つの数値の並び以外の場合。
            ValueError: 有限でない、開始が終了より大きい、またはtime_unitが未対応の単位名の場合。
        """
        ...
    def _key_ranges(self, index: int | Iterable[int] | None, time: float | Sequence[float] | None, time_unit: str) -> list[tuple[int, int]]:
        """index・timeの指定を、``cmds.keyframe`` の ``index`` フラグに渡す番号の範囲の並びへ変換する。

        Args:
            index (int | Iterable[int] | None): キー番号、またはその並び。
            time (float | Sequence[float] | None): 入力の時刻、または両端を含む範囲。
            time_unit (str): T型入力のtimeの単位。

        Returns:
            list[tuple[int, int]]: 昇順で重ならない ``(最初, 最後)`` の並び。両方Noneは全キー、該当なしは空。

        Raises:
            IndexError: 範囲外の番号を含む場合。
        """
        ...
    def _index(self, index: int) -> tuple[int, int]:
        """0始まりの既存キー番号を検証し、cmdsの単一キー範囲へ変換する。

        Args:
            index (int): boolを除くint。負値による末尾参照は受け付けない。

        Returns:
            tuple[int, int]: 同じ番号を両端に持つ範囲。

        Raises:
            IndexError: 非int、bool、負値、または現在のキー数以上の場合。
        """
        ...
