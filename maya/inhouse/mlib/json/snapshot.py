"""JSONへ保存・復元するデータの共通の流れ(取得・保存・読み込み・検査・適用)を提供する。

``ValidationReport`` は :class:`Snapshot` の検査と適用だけが返す小さな結果クラスなので、同じファイルに置く。
"""

import maya.api.OpenMaya as om2

from .. import logger
from ..decorator import _edit_context
from . import file
from .nameMapping import NameMapping


class ValidationReport:
    """適用前の検査と、適用の結果を保持する。

    ``missing`` は対応するノードが見つからなかったもの、``skipped`` はロック・接続等で書けずに
    飛ばしたもの、``errors`` は適用できない問題(頂点数の違い等)。``errors`` があれば
    各種類の ``apply`` (:meth:`PoseSnapshot.apply <mlib.json.poseSnapshot.PoseSnapshot.apply>` 等)は
    何も変えずに例外にする。
    """

    def __init__(self):
        """空の報告を作る。"""
        self._missing = []
        self._skipped = []
        self._errors = []

    def __repr__(self):
        """各項目の件数を含む表記を返す。

        Returns:
            str: ``ValidationReport(missing=1, skipped=0, errors=0)`` の形式。
        """
        return (f"ValidationReport(missing={len(self._missing)}, skipped={len(self._skipped)}, "
                f"errors={len(self._errors)})")

    @property
    def missing(self):
        """見つからなかったノード等の名前を返す。

        Returns:
            list[str]: 対応付けを当てた後の名前。新しいlist。
        """
        return list(self._missing)

    @property
    def skipped(self):
        """書けずに飛ばしたものの説明を返す。

        Returns:
            list[str]: ``"<名前>: <理由>"`` の形の説明。新しいlist。
        """
        return list(self._skipped)

    @property
    def errors(self):
        """適用できない問題の説明を返す。

        Returns:
            list[str]: 説明。新しいlist。
        """
        return list(self._errors)

    @property
    def valid(self):
        """適用できる(``errors`` が無い)かを返す。

        Returns:
            bool: errorsが空ならTrue。missing・skippedがあってもTrue。
        """
        return not self._errors

    def addMissing(self, name):
        """見つからなかったものを記録する。同じ名前は一度だけ記録する。

        Args:
            name (str): 対応付けを当てた後の名前。
        """
        if name not in self._missing:
            self._missing.append(name)

    def addSkipped(self, name, reason):
        """書けずに飛ばしたものを記録する。

        Args:
            name (str): 飛ばしたものの名前。
            reason (str): 理由(``"locked"`` 等)。
        """
        self._skipped.append(f"{name}: {reason}")

    def addError(self, message):
        """適用できない問題を記録する。

        Args:
            message (str): 問題の説明。
        """
        self._errors.append(message)

    def warn(self, label):
        """missing・skippedがあれば、まとめて警告を1回出す。

        Args:
            label (str): 警告の先頭に付ける名前(``"PoseSnapshot"`` 等)。
        """
        parts = []
        if self._missing:
            parts.append(f"{len(self._missing)} not found ({_summary(self._missing)})")
        if self._skipped:
            parts.append(f"{len(self._skipped)} skipped ({_summary(self._skipped)})")
        if parts:
            logger.warning("%s: %s", label, "; ".join(parts))


class Snapshot:
    """シーンのデータを取得し、JSONへ保存・復元するクラスの共通基底。

    各種類は :attr:`FORMAT`・:attr:`VERSION` と、``capture`` (取得)・``_validate`` (検査)・
    ``_apply`` (適用)を実装する。保持するデータは数学型を含む辞書で、:meth:`toData` で取得できる。
    名前の対応付け(``nameMap``・``replace``・``namespaceMap``)は :class:`NameMapping` の規則に従う。
    """

    #: 形式名。各種類が ``"mlib.pose"`` 等で上書きする。
    FORMAT = None

    #: 形式の版。データの形を変えたら上げる(古い版のファイルは読まない)。
    VERSION = None

    def __init__(self, data, header=None):
        """データを保持する。通常は ``capture`` か :meth:`load` で作る。

        Args:
            data (dict): 各種類の形式のデータ。複製して保持する。
            header (file.Header | None): 読み込んだファイルのヘッダー。取得したばかりならNone。

        Raises:
            TypeError: dataが辞書でない場合。
            ValueError: データの形が種類と合わない場合。
        """
        if not isinstance(data, dict):
            raise TypeError("snapshot data must be a dict")
        self._check_data(data)
        self._data = _copy_data(data)
        self._header = header

    def __repr__(self):
        """クラス名と形式を含む表記を返す。

        Returns:
            str: ``PoseSnapshot('mlib.pose', 1)`` の形式。
        """
        return f"{type(self).__name__}({self.FORMAT!r}, {self.VERSION})"

    @classmethod
    def capture(cls, *args, **kwargs):
        """シーンからデータを取得する。各種類が実装する。

        Args:
            *args (object): 各種類の ``capture`` の位置引数。
            **kwargs (object): 各種類の ``capture`` のキーワード引数。

        Raises:
            NotImplementedError: 基底クラスで呼んだ場合。
        """
        raise NotImplementedError(f"{cls.__name__} does not implement capture")

    @classmethod
    def fromData(cls, data):
        """:meth:`toData` の辞書から作る。

        Args:
            data (dict): 種類の形式のデータ。

        Returns:
            Snapshot: 呼び出したクラスの新しいインスタンス。

        Raises:
            TypeError: dataが辞書でない場合。
            ValueError: データの形が種類と合わない場合。
        """
        return cls(data)

    @classmethod
    def load(cls, path):
        """JSONファイルを読み込んで作る。

        Args:
            path (str | os.PathLike): :meth:`save` で書き出したファイル。

        Returns:
            Snapshot: 呼び出したクラスの新しいインスタンス。:attr:`header` を持つ。

        Raises:
            ValueError: 形式名・版が違う、またはデータの形が種類と合わない場合。
            OSError: 読み込みに失敗した場合。
        """
        header, data = file.load(path, cls.FORMAT, cls.VERSION)
        return cls(data, header)

    @property
    def header(self):
        """読み込んだファイルのヘッダーを返す。

        Returns:
            file.Header | None: :meth:`load` で作った場合のヘッダー。取得したばかりならNone。
        """
        return self._header

    def toData(self):
        """保持するデータの複製を返す。

        Returns:
            dict: 数学型を含む辞書。変更しても自身には影響しない。
        """
        return _copy_data(self._data)

    def save(self, path):
        """データをJSONファイルへ書き出す。

        Args:
            path (str | os.PathLike): 書き出し先。

        Returns:
            pathlib.Path: 書き出したファイルの絶対パス。

        Raises:
            OSError: 書き出しに失敗した場合。
        """
        return file.dump(self._data, path, self.FORMAT, self.VERSION)

    def validate(self, *, nameMap=None, replace=None, namespaceMap=None):
        """適用する前に、シーンとの対応を確かめる。シーンは変更しない。

        Args:
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。

        Returns:
            ValidationReport: 見つからないもの・書けないもの・適用できない問題。
        """
        report = ValidationReport()
        self._validate(NameMapping(nameMap, replace, namespaceMap), report, {})
        return report

    def _run_apply(self, mapping_args, options, fast=False):
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
        mapping = NameMapping(**mapping_args)
        report = ValidationReport()
        self._validate(mapping, report, options)
        if not report.valid:
            raise ValueError(f"Cannot apply {type(self).__name__}: " + "; ".join(report.errors))
        with _edit_context(f"mlib{type(self).__name__}Apply", fast, transaction=True):
            self._apply(mapping, report, options, fast)
        report.warn(type(self).__name__)
        return report

    def _convert_time(self, frame, timing):
        """保存時のフレームを、現在のシーンのフレームへ換算する。

        Args:
            frame (float): 保存時のフレーム。
            timing (str): ``"frame"`` または ``"second"``。

        Returns:
            float: 現在のシーンのフレーム。取得したばかり(ヘッダー無し)ならそのまま。
        """
        if self._header is None:
            file._require_timing(timing)
            return frame
        return self._header.convertTime(frame, timing)

    def _check_data(self, data):
        """データの形を確かめる。各種類が上書きする。

        Args:
            data (dict): 保持する前のデータ。

        Raises:
            ValueError: データの形が種類と合わない場合。
        """

    def _validate(self, mapping, report, options):
        """シーンとの対応を確かめ、reportへ記録する。各種類が実装する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 種類ごとの追加の指定。

        Raises:
            NotImplementedError: 基底クラスで呼んだ場合。
        """
        raise NotImplementedError(f"{type(self).__name__} does not implement validation")

    def _apply(self, mapping, report, options, fast):
        """シーンへ書き戻し、書けなかったものをreportへ記録する。各種類が実装する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 種類ごとの追加の指定。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Raises:
            NotImplementedError: 基底クラスで呼んだ場合。
        """
        raise NotImplementedError(f"{type(self).__name__} does not implement apply")


def _copy_data(value):
    """辞書・listをたどって複製する。数学型は同じ型の新しい値にする。

    om2の値は ``copy.deepcopy`` で複製できないため、自前でたどる。

    Args:
        value (object): 複製する値。

    Returns:
        object: 複製。文字列・数値・Noneはそのまま。
    """
    if isinstance(value, dict):
        return {key: _copy_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy_data(item) for item in value]
    if isinstance(value, (om2.MVector, om2.MQuaternion, om2.MEulerRotation, om2.MMatrix)):
        return type(value)(value)
    return value


def _summary(items, limit=5):
    """長い一覧を先頭だけの文字列にする。

    Args:
        items (list[str]): 一覧。
        limit (int): 表示する件数。

    Returns:
        str: カンマ区切りの文字列。超えた分は ``"..."``。
    """
    text = ", ".join(items[:limit])
    return text + (", ..." if len(items) > limit else "")
