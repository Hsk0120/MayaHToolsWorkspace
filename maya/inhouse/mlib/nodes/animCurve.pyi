# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""アニメーションカーブの共通操作。通常編集はUndo、fastはAPI直接更新。"""

import math
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
from ..common.units import angleToUi
from ..core.attributeType import _convert_units, _from_seconds, _to_seconds
from ..decorator import _edit_context, _require_bool
from ..util import _angle_unit, _from_radians, _time_unit, _to_radians
from .node import Node

_TANGENT_TYPES: dict
_TANGENT_NAMES: dict


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
    def setKey(self, input: float, value: float, inTangentType: str = ..., outTangentType: str = ..., *, unit: str = ..., timeUnit: str = ..., fast: bool = ...) -> AnimCurve:
        """キーを追加する。同じ入力位置にキーがあれば値と接線型を更新する。

        通常はUI単位へ換算してsetKeyframeを呼ぶ。fastの既存キーは値→入力接線型→出力接線型の
        順に更新する。新規キーは両接線型を指定し、時間出力の値は追加後に設定する。
        後続の失敗で先行の変更を自動復元しない。

        Args:
            input (float): T型入力はtimeUnitの単位(既定はフレーム)、U型入力は無次元。
            value (float): 出力型に従う度(unit)/cm/フレーム(timeUnit)、または無次元。inputと共に有限値へ変換する。
            inTangentType (str): Mayaの入力接線型。fastのstepはautoへ補正する。
            outTangentType (str): Mayaの出力接線型。
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
    def removeKey(self, index: int, *, fast: bool = ...) -> AnimCurve:
        """指定番号のキーを削除する。キークリップボードは変更しない。

        Args:
            index (int): 0始まりのキー番号。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AnimCurve: 自身。
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
    def shiftKeys(self, inputOffset: float = ..., valueOffset: float = ..., *, unit: str = ..., timeUnit: str = ..., fast: bool = ...) -> AnimCurve:
        """全キーを移動する。

        Args:
            inputOffset (float): 横軸の移動量。T型入力はtimeUnitの単位(既定はフレーム)、U型は無次元。
            valueOffset (float): 縦軸の移動量。角度はunitの単位(既定は度)、距離cm、時間はtimeUnitの単位。
            unit (str): 角度出力(A型)のvalueOffsetの単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力のinputOffsetと、時間出力のvalueOffsetの単位。``"frame"`` / ``"sec"``。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AnimCurve: 自身。空カーブは変更しない。

        Raises:
            TypeError: unit・timeUnitが文字列以外、または数値へ変換できない型の場合。
            ValueError: 非有限値、またはunit・timeUnitが未対応の単位名の場合。
        """
        ...
    def scaleKeys(self, inputScale: float = ..., valueScale: float = ..., inputPivot: float = ..., valuePivot: float = ..., *, unit: str = ..., timeUnit: str = ..., fast: bool = ...) -> AnimCurve:
        """全キーを基準値のまわりで拡縮する。接線処理はMayaのscaleKeyに従う。

        Args:
            inputScale (float): 横軸倍率(単位なし)。0はキーが重なるためValueError。
            valueScale (float): 縦軸倍率(単位なし)。
            inputPivot (float): 横軸の基準値。T型入力はtimeUnitの単位(既定はフレーム)、U型は無次元。
            valuePivot (float): 縦軸の基準値。角度出力(A型)はunitの単位(既定は度)、時間出力はtimeUnitの単位。
            unit (str): 角度出力のvaluePivotの単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力のinputPivotと、時間出力のvaluePivotの単位。``"frame"`` / ``"sec"``。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。負の入力倍率は更新前に未対応として拒否。

        Returns:
            AnimCurve: 自身。

        Raises:
            TypeError: unit・timeUnitが文字列以外、または数値へ変換できない型の場合。
            ValueError: inputScaleが0、非有限値、またはunit・timeUnitが未対応の単位名の場合。
            NotImplementedError: fastで負の入力倍率を指定した場合。
        """
        ...
    def mirror(self, input: bool = ..., value: bool = ..., inputPivot: float = ..., valuePivot: float = ..., *, unit: str = ..., timeUnit: str = ..., fast: bool = ...) -> AnimCurve:
        """入力軸・出力軸を反転する。内部のscaleKeysでUndoをまとめる。

        Args:
            input (bool): 横軸を反転するか。
            value (bool): 縦軸を反転するか。
            inputPivot (float): 横軸の反転中心。T型入力はtimeUnitの単位(既定はフレーム)、U型は無次元。
            valuePivot (float): 縦軸の反転中心。角度出力(A型)はunitの単位(既定は度)、時間出力はtimeUnitの単位。
            unit (str): 角度出力のvaluePivotの単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力のinputPivotと、時間出力のvaluePivotの単位。``"frame"`` / ``"sec"``。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。input=Trueとの併用は未対応。

        Returns:
            AnimCurve: 自身。
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
    def _transform_keys(self, x_scale: float, y_scale: float, x_offset: float, y_offset: float) -> None:
        """キー順を保つ移動・拡縮をAPIで実行し固定接線を追従させる。

        Args:
            x_scale (float): 正の入力倍率。
            y_scale (float): 出力倍率。
            x_offset (float): 内部単位の入力オフセット。
            y_offset (float): 内部単位の出力オフセット。

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
        """直接編集前にカーブとキー格納先のロックを検査する。"""
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
