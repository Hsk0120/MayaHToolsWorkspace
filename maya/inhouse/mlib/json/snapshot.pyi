# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""JSONへ保存・復元するデータの共通の流れ(取得・保存・読み込み・検査・適用)を提供する。

``ValidationReport`` は :class:`Snapshot` の検査と適用だけが返す小さな結果クラスなので、同じファイルに置く。
"""

import maya.api.OpenMaya as om2
from .. import logger
from ..decorator import _edit_context
from . import file
from .nameMapping import NameMapping
from typing import Any, Iterable
import os
import pathlib



class ValidationReport:
    """適用前の検査と、適用の結果を保持する。

    ``missing`` は対応するノードが見つからなかったもの、``skipped`` はロック・接続等で書けずに
    飛ばしたもの、``errors`` は適用できない問題(頂点数の違い等)。``errors`` があれば
    :meth:`Snapshot.apply` は何も変えずに例外にする。
    """
    def __init__(self) -> None:
        """空の報告を作る。"""
        ...
    def __repr__(self) -> str:
        """各項目の件数を含む表記を返す。

        Returns:
            str: ``ValidationReport(missing=1, skipped=0, errors=0)`` の形式。
        """
        ...
    @property
    def missing(self) -> list[str]:
        """見つからなかったノード等の名前を返す。

        Returns:
            list[str]: 対応付けを当てた後の名前。新しいlist。
        """
        ...
    @property
    def skipped(self) -> list[str]:
        """書けずに飛ばしたものの説明を返す。

        Returns:
            list[str]: ``"<名前>: <理由>"`` の形の説明。新しいlist。
        """
        ...
    @property
    def errors(self) -> list[str]:
        """適用できない問題の説明を返す。

        Returns:
            list[str]: 説明。新しいlist。
        """
        ...
    @property
    def valid(self) -> bool:
        """適用できる(``errors`` が無い)かを返す。

        Returns:
            bool: errorsが空ならTrue。missing・skippedがあってもTrue。
        """
        ...
    def addMissing(self, name: str):
        """見つからなかったものを記録する。同じ名前は一度だけ記録する。

        Args:
            name (str): 対応付けを当てた後の名前。
        """
        ...
    def addSkipped(self, name: str, reason: str):
        """書けずに飛ばしたものを記録する。

        Args:
            name (str): 飛ばしたものの名前。
            reason (str): 理由(``"locked"`` 等)。
        """
        ...
    def addError(self, message: str):
        """適用できない問題を記録する。

        Args:
            message (str): 問題の説明。
        """
        ...
    def warn(self, label: str):
        """missing・skippedがあれば、まとめて警告を1回出す。

        Args:
            label (str): 警告の先頭に付ける名前(``"PoseSnapshot"`` 等)。
        """
        ...


class Snapshot:
    """シーンのデータを取得し、JSONへ保存・復元するクラスの共通基底。

    各種類は :attr:`FORMAT`・:attr:`VERSION` と、``capture`` (取得)・``_validate`` (検査)・
    ``_apply`` (適用)を実装する。保持するデータは数学型を含む辞書で、:meth:`toData` で取得できる。
    名前の対応付け(``nameMap``・``replace``・``namespaceMap``)は :class:`NameMapping` の規則に従う。
    """
    FORMAT: None
    VERSION: None
    def __init__(self, data: dict, header: file.Header | None = ...) -> None:
        """データを保持する。通常は ``capture`` か :meth:`load` で作る。

        Args:
            data (dict): 各種類の形式のデータ。複製して保持する。
            header (file.Header | None): 読み込んだファイルのヘッダー。取得したばかりならNone。

        Raises:
            TypeError: dataが辞書でない場合。
            ValueError: データの形が種類と合わない場合。
        """
        ...
    def __repr__(self) -> str:
        """クラス名と形式を含む表記を返す。

        Returns:
            str: ``PoseSnapshot('mlib.pose', 1)`` の形式。
        """
        ...
    @classmethod
    def capture(cls, *args, **kwargs):
        """シーンからデータを取得する。各種類が実装する。

        Raises:
            NotImplementedError: 基底クラスで呼んだ場合。
        """
        ...
    @classmethod
    def fromData(cls, data: dict) -> Snapshot:
        """:meth:`toData` の辞書から作る。

        Args:
            data (dict): 種類の形式のデータ。

        Returns:
            Snapshot: 呼び出したクラスの新しいインスタンス。

        Raises:
            TypeError: dataが辞書でない場合。
            ValueError: データの形が種類と合わない場合。
        """
        ...
    @classmethod
    def load(cls, path: str | os.PathLike) -> Snapshot:
        """JSONファイルを読み込んで作る。

        Args:
            path (str | os.PathLike): :meth:`save` で書き出したファイル。

        Returns:
            Snapshot: 呼び出したクラスの新しいインスタンス。:attr:`header` を持つ。

        Raises:
            ValueError: 形式名・版が違う、またはデータの形が種類と合わない場合。
            OSError: 読み込みに失敗した場合。
        """
        ...
    @property
    def header(self) -> file.Header | None:
        """読み込んだファイルのヘッダーを返す。

        Returns:
            file.Header | None: :meth:`load` で作った場合のヘッダー。取得したばかりならNone。
        """
        ...
    def toData(self) -> dict:
        """保持するデータの複製を返す。

        Returns:
            dict: 数学型を含む辞書。変更しても自身には影響しない。
        """
        ...
    def save(self, path: str | os.PathLike) -> pathlib.Path:
        """データをJSONファイルへ書き出す。

        Args:
            path (str | os.PathLike): 書き出し先。

        Returns:
            pathlib.Path: 書き出したファイルの絶対パス。

        Raises:
            OSError: 書き出しに失敗した場合。
        """
        ...
    def validate(self, *, nameMap: dict[str, str] | None = ..., replace: Iterable[tuple[str, str]] | None = ..., namespaceMap: dict[str, str] | None = ...) -> ValidationReport:
        """適用する前に、シーンとの対応を確かめる。シーンは変更しない。

        Args:
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。

        Returns:
            ValidationReport: 見つからないもの・書けないもの・適用できない問題。
        """
        ...
    def _run_apply(self, mapping_args: dict, options: dict, fast: bool = ...) -> ValidationReport:
        """検査してから、1回のUndoで適用する(各種類の ``apply`` の本体)。

        errorsがあれば何も変えずにValueErrorにする。適用中の失敗は通常経路では巻き戻す。
        最後にmissing・skippedをまとめて警告する。

        Args:
            mapping_args (dict): ``nameMap``・``replace``・``namespaceMap``。
            options (dict): 種類ごとの追加の指定。``_validate``・``_apply`` へ渡す。
            fast (bool): TrueはUndoなしのOpenMaya更新(対応する種類だけが渡す)。

        Returns:
            ValidationReport: 適用の結果。

        Raises:
            ValueError: 適用できない問題がある場合。
        """
        ...
    def _convert_time(self, frame: float, timing: str) -> float:
        """保存時のフレームを、現在のシーンのフレームへ換算する。

        Args:
            frame (float): 保存時のフレーム。
            timing (str): ``"frame"`` または ``"second"``。

        Returns:
            float: 現在のシーンのフレーム。取得したばかり(ヘッダー無し)ならそのまま。
        """
        ...
    def _check_data(self, data: dict):
        """データの形を確かめる。各種類が上書きする。

        Args:
            data (dict): 保持する前のデータ。

        Raises:
            ValueError: データの形が種類と合わない場合。
        """
        ...
    def _validate(self, mapping: NameMapping, report: ValidationReport, options: dict):
        """シーンとの対応を確かめ、reportへ記録する。各種類が実装する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 種類ごとの追加の指定。

        Raises:
            NotImplementedError: 基底クラスで呼んだ場合。
        """
        ...
    def _apply(self, mapping: NameMapping, report: ValidationReport, options: dict, fast: bool):
        """シーンへ書き戻し、書けなかったものをreportへ記録する。各種類が実装する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 種類ごとの追加の指定。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Raises:
            NotImplementedError: 基底クラスで呼んだ場合。
        """
        ...

def _copy_data(value: object) -> Any:
    """辞書・listをたどって複製する。数学型は同じ型の新しい値にする。

    om2の値は ``copy.deepcopy`` で複製できないため、自前でたどる。

    Args:
        value (object): 複製する値。

    Returns:
        object: 複製。文字列・数値・Noneはそのまま。
    """
    ...

def _summary(items: list[str], limit: int = ...) -> str:
    """長い一覧を先頭だけの文字列にする。

    Args:
        items (list[str]): 一覧。
        limit (int): 表示する件数。

    Returns:
        str: カンマ区切りの文字列。超えた分は ``"..."``。
    """
    ...
