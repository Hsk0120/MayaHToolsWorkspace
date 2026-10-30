# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""モジュールとプラグインの組で導入される製品(Bifrost など)の導入確認とロード。"""

import maya.cmds as cmds
from .. import logger
from .module import Module
from .plugin import Plugin
from .version import Version
from typing import Any, Callable, Iterable

SKIPPED: str
LOADED: str
MISSING: str
OUTDATED: str
LOAD_FAILED: str


class PluginPackage:
    """モジュール・プラグイン群と必要版を保持し、導入確認とロードを担当する。

    生成時は照会・ロードせず、tryLoadでMayaの対象版、導入版、ロード結果を順に判定する。
    ロード済みのプラグインを自動アンロードする責務は持たない。
    """
    def __init__(self, name: str, plugins: Iterable[str | Plugin] = ..., module: str | Module | None = ..., versionPlugin: str | Plugin | None = ..., minimumVersion: Version | str | int | tuple[int, ...] | None = ..., minimumMaya: int | None = ..., installHint: str | None = ...) -> None:
        """製品名・ロード対象・必要版を保持する。Mayaへは問い合わせない。

        Args:
            name (str): 通知に表示する製品名。
            plugins (Iterable[str | Plugin]): ロード順のプラグイン。
            module (str | Module | None): 版の取得元。未取得ならversionPluginの版を使う。
            versionPlugin (str | Plugin | None): 版を調べるプラグイン。既定はpluginsの先頭。
            minimumVersion (Version | str | int | tuple[int, ...] | None): 最小版。Noneは版を問わない。
            minimumMaya (int | None): 対象Mayaの最小年版。それ未満ではtryLoadを省略する。
            installHint (str | None): 導入不足の通知へ加える説明。

        Raises:
            TypeError: 名前・プラグイン名が文字列以外、pluginsを反復できない、
                またはminimumMayaを整数に変換できない型の場合。
            ValueError: 名前・プラグイン名が空文字列、最小版が不正、またはpluginsもmoduleも指定されない場合。
        """
        ...
    def __repr__(self) -> str:
        """デバッグ用に製品名と最小の版を含む表現を返す。

        Returns:
            str: 型名・製品名・最小の版を含む文字列表現。
        """
        ...
    @staticmethod
    def showDialog(message: str, title: str = ...) -> None:
        """警告ダイアログを表示する。GUI がないバッチ・スタンドアロンでは何もしない。

        Args:
            message (str): 表示する文章。
            title (str): ダイアログのタイトル。

        Returns:
            None: 値を返さない。
        """
        ...
    @property
    def name(self) -> str:
        """製品名を取得する。

        Returns:
            str: 製品名。
        """
        ...
    @property
    def plugins(self) -> list[Plugin]:
        """ロード対象のプラグインを取得する。

        Returns:
            list[Plugin]: ロード順のプラグイン。
        """
        ...
    @property
    def module(self) -> Module | None:
        """版の取得元のモジュールを取得する。

        Returns:
            Module | None: モジュール。指定していない場合は None。
        """
        ...
    @property
    def minimumVersion(self) -> Version | None:
        """必要な最小の版を取得する。

        Returns:
            Version | None: 最小の版。指定していない場合は None。
        """
        ...
    @property
    def minimumMaya(self) -> int | None:
        """対象とする最小の Maya の年を取得する。

        Returns:
            int | None: 年。指定していない場合は None。
        """
        ...
    def isMayaSupported(self) -> bool:
        """現在の Maya が対象のバージョンか判定する。

        Returns:
            bool: ``minimumMaya`` が未指定、または現在の Maya の年がそれ以上なら True。
        """
        ...
    def getInstalledVersion(self) -> Version | None:
        """Maya に登録されている製品の版を取得する。

        モジュールが登録されていればその版、無ければ版を調べるプラグインの版を使う。

        Returns:
            Version | None: 版。未導入・版が取れない場合は None。
        """
        ...
    def getLoadedVersion(self) -> Version | None:
        """ロード済みの、版を調べるプラグインの版を取得する。

        Returns:
            Version | None: 版。ロードされていない場合は None。
        """
        ...
    def isInstalled(self) -> bool:
        """必要な版が導入されているか判定する。

        ロード前のプラグインは Maya に登録されていない場合がある。``minimumVersion`` を
        指定しない製品は、この判定が False でも :meth:`tryLoad` がロードを試みる。

        Returns:
            bool: ``minimumVersion`` 以上が導入されていれば True。``minimumVersion`` を指定していない
            場合は、版が取れるか、モジュールまたはプラグインが 1 つでも登録されていれば True。
        """
        ...
    def getMessage(self, found: Version | None = ...) -> str:
        """導入が必要なときの警告文を作る。

        Args:
            found (Version | None): 検出した版。省略すると現在の導入状況から求める。

        Returns:
            str: 日本語と英語の警告文。
        """
        ...
    def loadPlugins(self) -> list[str]:
        """全プラグインをロードする。ロードできない名前があっても続行する。

        Returns:
            list[str]: ロードに失敗したプラグイン名。失敗ごとに警告を出す。
        """
        ...
    def tryLoad(self, dialog: bool | Callable[[str], None] = ..., warn: bool = ...) -> str:
        """対象Mayaと必要版を確認してロードし、結果の定数を返す。

        minimumMaya未満なら何もしない。最小版指定時は未導入・版不足ならロードしない。
        最小版なしでは未検出でもロードを試し、全プラグインが失敗すればMISSINGとする。
        失敗時も成功済みプラグインを自動ではアンロードしない。

        Args:
            dialog (bool | Callable[[str], None]): TrueはshowDialog、False/Noneは表示なし。
                callableには不足時の通知文を渡す。
            warn (bool): 導入・版不足をlogger.warningへ通知するか。
                個別のロード失敗警告はこのフラグで抑制しない。

        Returns:
            str: SKIPPED(対象外)、LOADED(成功)、MISSING(未導入・版不足)、
                OUTDATED(ロード済み版が古い)、LOAD_FAILED(ロード失敗あり)。
        """
        ...
    @staticmethod
    def _maya_year() -> int:
        """現在のMayaの年版を照会する。

        Returns:
            int: 2025などの年版。
        """
        ...
    def _report(self, show: Callable[..., Any] | None, warn: bool, message: str) -> None:
        """指定した通知先へメッセージを送る。

        Args:
            show (callable | None): メッセージ全体を渡す表示コールバック。
            warn (bool): 最初の行を warning にも渡すか。
            message (str): 通知内容。コールバックの例外は伝播する。

        Returns:
            None: 値を返さない。
        """
        ...
