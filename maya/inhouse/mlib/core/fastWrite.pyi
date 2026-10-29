# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""対応する値更新のcmds/OpenMayaバックエンド。独自プラグインは使わない。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..decorator import _require_bool
from .attributeType import NUMERIC_WRITERS, _convert_units, _require_number, _round_integer
from typing import Any, Iterator

_TYPED_DATA_FACTORIES: dict

def require_supported_type(plug: om2.MPlug) -> None:
    """fastで書ける型か全子の定義から確認する。値や書込み可否は検査しない。

    safeの部分更新前に呼び、ロックや不正な値によって後続の未対応型が隠れるのを防ぐ。
    対応するtyped配列の型表は、実データを構築するprepare_dataと共有する。

    Args:
        plug (om2.MPlug): 有効性を確認済みの更新対象。

    Returns:
        None: 値を返さない。

    Raises:
        NotImplementedError: 子を含め、fastで扱えない型がある場合。
    """
    ...

def _ancestor_plugs(mplug: om2.MPlug) -> Iterator[om2.MPlug]:
    """プラグ自身から、コンパウンドアトリビュートの親・マルチアトリビュートを順に遡って列挙する。

    ロック・入力接続は親(コンパウンドアトリビュート)やマルチアトリビュートにも設定できるため、書込み可否の検査で使う。

    Args:
        mplug (om2.MPlug): 起点のプラグ。

    Yields:
        om2.MPlug: mplug自身、次に親またはマルチアトリビュート、最上位に達するまで。
    """
    ...

def require_writable(plug: om2.MPlug, _fn: om2.MFnAttribute | None = ...) -> None:
    """ロック・入力接続・書込み不能アトリビュートをAPIで検査する。

    Args:
        plug (om2.MPlug): 検査するプラグ。
        _fn (om2.MFnAttribute | None): 同じ更新内で生成したアトリビュートの
            function set。省略時は新しく生成する。値や検査結果はキャッシュしない。

    Returns:
        None: 値を返さない。

    Raises:
        RuntimeError: ロック・入力接続・書込み禁止がある場合。
    """
    ...

def writable_compound(mplug: om2.MPlug) -> None:
    """プラグ自身と、コンパウンドアトリビュートなら全ての子の書込み可否を検査する。

    Args:
        mplug (om2.MPlug): 検査するプラグ。

    Returns:
        None: 値を返さない。

    Raises:
        RuntimeError: 自身または子にロック・入力接続・書込み禁止がある場合。
    """
    ...

def require_range(plug: om2.MPlug, value: float, _fn: om2.MFnNumericAttribute | om2.MFnUnitAttribute | None = ...) -> None:
    """cmds.setAttrと同様、アトリビュートに設定されたハード範囲を検査する。

    Args:
        plug (om2.MPlug): 検査するプラグ。
        value (float): 設定予定の値。単位型ではcm/rad/秒。
        _fn (om2.MFnNumericAttribute | om2.MFnUnitAttribute | None): 同じ更新内で
            生成したfunction set。範囲と単位定義は呼出しごとに照会する。

    Returns:
        None: 値を返さない。

    Raises:
        RuntimeError: 値が設定されたハード範囲外の場合。
    """
    ...

def _prepared_writes(plug: om2.MPlug, value: object, _writable_checked: bool = ...) -> list[tuple]:
    """全成分の型・制限を更新前に検査し、直接書込みの列を組み立てる。

    Args:
        plug (om2.MPlug): 書込み先。
        value (object): 内部単位の入力値。
        _writable_checked (bool): Trueなら、呼出し元が同じ更新の直前に自身と全子へ
            :func:`require_writable` を適用済みとして、ここでは書込み可否を調べ直さない。
            型・値・範囲の検査は省かない。

    Returns:
        list[tuple]: setter・プラグ・変換済み値・書込み終了まで保持するfunction setの列。

    Raises:
        TypeError: 数値型への数値以外、または文字列型への文字列以外の入力の場合。
        ValueError: コンパウンドアトリビュートの値の成分数が子数と異なる場合。
        RuntimeError: 書込み不能、またはハード範囲外(enumはフィールドの最小〜最大の外)の場合。
        NotImplementedError: API 2.0で値を構築できない型の場合。
    """
    ...

def set_plug(plug: om2.MPlug, value: object, _writable_checked: bool = ...) -> None:
    """全成分を事前検証してMPlugへ設定する。Undoには記録しない。

    最初に全子の型がfastに対応するかを確かめ(未対応ならロック等より先にNotImplementedError)、
    次に書込み可否・入力の型・ハード範囲を確認し、型付きデータを構築してから準備順に書き込む。
    入力の意味は通常経路(cmds.setAttr)と同じにする: 整数型・enum・boolへの小数は四捨五入し、
    数値型への文字列や文字列型への数値は変換せずTypeErrorにする。
    function setはデータの受渡しが終わるまで保持する。Undo設定は変更しない。
    事前検証後のAPI書込みで失敗した場合、先に書いた成分の自動復元は行わない。

    Args:
        plug (om2.MPlug): 更新対象。
        value (object): 角度rad、距離cm、時間秒の値。
        _writable_checked (bool): 内部用。呼出し元が直前に自身と全子の書込み可否を
            :func:`require_writable` で検査済みならTrue。その検査だけを重ねて行わない。

    Returns:
        None: 値を返さない。

    Raises:
        TypeError: 入力の型の不一致(数値型への数値以外・文字列型への文字列以外)の場合。
        ValueError: コンパウンドアトリビュートの値の成分数が子数と異なる場合。
        RuntimeError: 書込み不能、またはハード範囲外の場合。
        NotImplementedError: API 2.0で未対応の型の場合。書込み可否より先に、更新前に拒否する。
    """
    ...

def set_attr(name: str, *values, fast: bool = ..., **kwargs) -> Any:
    """既存のsetAttrと同じ値入力を、明示fast時だけMPlugへ渡す。

    Args:
        name (str): アトリビュート名。
        *values: cmds.setAttr と同じ形・現在の Maya 単位の値。
        fast (bool): TrueはOpenMaya直接更新。呼出元が明示的に指定する。
        **kwargs: setAttr のフラグ。fast 時の対応フラグは限定される。

    Returns:
        object | None: 通常経路は ``cmds.setAttr`` の戻り値。fastはNone。

    Raises:
        TypeError: fastがbool以外、またはfastで入力の型が一致しない場合。
        NotImplementedError: fastで ``type`` と状態フラグ以外のフラグを指定した場合。
    """
    ...

def prepare_data(attribute: om2.MObject, value: object, *, name: str | None = ...) -> tuple:
    """MPlugを必要とせず、マトリクス・typed dataの型と値を検査する。

    Args:
        attribute (MObject): 登録前でもよいアトリビュート定義。
        value (object): 設定予定の値。
        name (str | None): エラー表示用の名前。

    Returns:
        tuple: setter、変換済み値、書込み終了まで保持するfunction set。

    Raises:
        TypeError: 文字列型へ文字列以外を渡した場合。
        NotImplementedError: fastで構築できない型の場合。
    """
    ...
