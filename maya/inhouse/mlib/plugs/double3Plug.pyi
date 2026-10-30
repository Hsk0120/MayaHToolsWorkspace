# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""double3アトリビュートを意味付きの3成分値として読み書きする。"""

import math
import maya.api.OpenMaya as om2
from ..core.attributeType import _convert_angles, _convert_units, _plain_angle_unit, _plain_time_unit
from ..core.fastWrite import set_plug
from ..decorator import _require_bool
from ..maths import EulerRotate, Scale, Shear, Translate, Vector
from .compoundPlug import CompoundPlug
from typing import Iterable
from mlib.maths.quaternion import Quaternion



class Double3Plug(CompoundPlug):
    """3成分アトリビュートを参照し、チャンネル値を読み書きする。マトリクス変換は行わない。"""
    _value_types: dict
    def get(self, *, unit: str | None = ..., timeUnit: str | None = ..., uiUnits: bool = ...) -> Vector | Translate | EulerRotate | Scale | Shear | tuple[float, float, float]:
        """3成分のチャンネル値を取得する。jointOrientなどは合成しない。

        Args:
            unit (str | None): 角度の子の数値の単位。None(既定)は度(rotateはEulerRotate)。
                rotateにunitを明示すると、EulerRotateではなく指定単位の数値tupleを返す。
                ``"deg"`` / ``"rad"`` と ``"degree"`` 等の別名を受け付け、uiUnits=Trueとは同時に指定できない。
            timeUnit (str | None): Plug共通の時間の単位指定。3成分の子は時間を持たないため検証だけ行う。
            uiUnits (bool): Trueは現在のUI単位の数値tuple。既定Falseは数学値。

        Returns:
            Vector | Translate | EulerRotate | Scale | Shear | tuple[float, float, float]:
                translateはTranslate、rotateはノードのrotateOrderを持つEulerRotate(内部はrad)、
                scaleはScale、shearはShear、その他はVector。距離はcm、jointOrient・rotateAxis等の
                角度の子は度(unit="rad"ならrad)の独立した値。
                uiUnits=Trueと、rotateへのunit指定では数値のtupleを返す。

        Raises:
            TypeError: uiUnitsがbool以外、またはunit・timeUnitが文字列・None以外の場合。
            ValueError: unit・timeUnitが未対応の単位名、またはuiUnits=Trueと同時に指定した場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効な場合。
        """
        ...
    def set(self, value: Iterable[float] | EulerRotate | Quaternion, safe: bool = ..., *, unit: str | None = ..., timeUnit: str | None = ..., uiUnits: bool = ..., fast: bool = ...) -> Double3Plug | int:
        """このアトリビュートの3成分だけを書き込む。マトリクス経由の姿勢変更は行わない。

        3成分の入力と書込み可否を確認してCompoundPlug.setへ渡す。
        safeの再試行では成功した子の更新を残す。通常処理はUndo有効時に記録し、fastは記録しない。

        Args:
            value (Iterable[float] | EulerRotate | Quaternion): 3成分の値。
                rotateではOpenMaya基底型の回転も受理し、ノードのrotateOrderへ揃える。
                数値列はノードのrotateOrderで解釈する。角度の子の数値は既定で度。
                EulerRotate・Quaternionは自身の単位(rad)を持つため、unitに関係なく換算しない。
            safe (bool): Trueは対応する書込み失敗を数える。
            unit (str | None): 角度の子(rotate・jointOrient・rotateAxis等)の数値の単位。
                None(既定)は度、``"rad"`` はラジアン(``"degree"`` 等の別名も可)。角度以外の子では使わない。
            timeUnit (str | None): Plug共通の時間の単位指定。3成分の子は時間を持たないため検証だけ行う。
            uiUnits (bool): TrueはUI単位の数値列を指定する。数学型とunitの同時指定は受理しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Double3Plug | int: safe=Falseは自身。safe=Trueは成功0、子の失敗数、または入力変換失敗の1。
                CompoundPlug.setの再試行規則に従い、更新済みの値は自動では戻さない。

        Raises:
            TypeError: fastがbool以外、またはマルチアトリビュート全体への設定。safe=Trueでも抑制しない。
                safe=Falseでは入力型が不正な場合も送出する。
            ValueError: unit・timeUnitが未対応、またはuiUnits=Trueとの同時指定(safe=Trueでは1を返す)。
                safe=Falseで成分数・有限値が不正な場合。
            RuntimeError: safe=Falseで無効参照、ロック・入力接続、またはMayaの編集失敗。
            NotImplementedError: fastで未対応の型の場合。safe=Trueでも抑制しない。
        """
        ...
    def _set_value(self, value: Iterable[float] | EulerRotate | Quaternion, *, uiUnits: bool = ..., fast: bool = ...) -> None:
        """3成分の入力と書込み可否を確認して書き込む。骨格は :meth:`Plug.set`。

        Args:
            value (Iterable[float] | EulerRotate | Quaternion): 3成分の値。角度の数値は
                :meth:`Plug._set_template` でradへ換算済み。
            uiUnits (bool): TrueはUI単位の数値列。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 入力型が不正な場合。
            ValueError: 成分数・有限値が不正な場合。
            RuntimeError: 無効参照、ロック・入力接続、またはMayaの編集失敗。
        """
        ...
    def _set_children_safely(self, value: object, *, uiUnits: bool = ..., fast: bool = ...) -> int:
        """回転順序と入力単位を揃えてから、子のsafe設定を順に試す。

        UI数値への数学型指定など、成分変換そのものの失敗では子を更新しない。

        Args:
            value (object): 最初の設定へ渡した値(角度の数値はrad換算済み)。
            uiUnits (bool): TrueならUI数値を内部単位へ一度変換する。
            fast (bool): 子のsetへ渡す更新経路。

        Returns:
            int: 子の失敗数、または入力変換の失敗を表す1。
        """
        ...
    def _ui_components(self, value: Iterable[float]) -> tuple:
        """UI入力を数値列として変換し、内部単位を持つ数学値を拒否する。

        Args:
            value (Iterable[float]): UI単位の数値3成分。

        Returns:
            tuple: 内部単位の数値3成分。

        Raises:
            TypeError: OpenMayaの数学値をUI数値として指定した場合。
        """
        ...
    def _set_components(self, value: Iterable[float] | om2.MEulerRotation | om2.MQuaternion) -> tuple[float, float, float]:
        """3成分の入力を検証し、rotateでは回転順序をノードへ揃える。

        シーンへの書込みは行わない。角度の数値は呼出元でradへ換算済みのものを受け取る。

        Args:
            value (Iterable[float] | om2.MEulerRotation | om2.MQuaternion): 入力値。

        Returns:
            tuple[float, float, float]: rotateはノードのrotateOrderに従うラジアンの成分。
                それ以外は入力の3成分。

        Raises:
            TypeError: 値を数値列へ変換できない場合。
            ValueError: 成分数・有限値が不正の場合。
        """
        ...
