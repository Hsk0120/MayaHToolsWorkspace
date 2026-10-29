"""モジュールとプラグインの組で導入される製品(Bifrost など)の導入確認とロード。"""

import maya.cmds as cmds

from .. import logger
from .module import Module
from .plugin import Plugin
from .version import Version

# クラスメソッドへ移した旧モジュール関数をreload時に除去する。
globals().pop("_maya_year", None)

# Versionへ集約した旧関数参照をreload時に残さない。
for _name in ("parse_version", "is_at_least", "format_version"):
    globals().pop(_name, None)

SKIPPED = "skipped"
"""str: 対象外の Maya バージョンのため何もしなかった。"""
LOADED = "loaded"
"""str: ロード失敗がなく、版の検査も通過した。"""
MISSING = "missing"
"""str: 最小版を満たさない、または未検出製品の全プラグインがロードに失敗した。"""
OUTDATED = "outdated"
"""str: 導入済みだが、既にロードされているプラグインが古い版だった。"""
LOAD_FAILED = "load-failed"
"""str: 1個以上のプラグインのロードに失敗した。"""


class PluginPackage:
    """モジュール・プラグイン群と必要版を保持し、導入確認とロードを担当する。

    生成時は照会・ロードせず、tryLoadでMayaの対象版、導入版、ロード結果を順に判定する。
    ロード済みのプラグインを自動アンロードする責務は持たない。
    """

    def __init__(self, name, plugins=(), module=None, versionPlugin=None,
                 minimumVersion=None, minimumMaya=None, installHint=None):
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
        if not isinstance(name, str):
            raise TypeError("name must be a str")
        if not name:
            raise ValueError("name must be a non-empty string")
        self._name = name
        self._plugins = tuple(item if isinstance(item, Plugin) else Plugin(item) for item in plugins)
        self._module = module if isinstance(module, Module) or module is None else Module(module)
        if not self._plugins and self._module is None:
            raise ValueError("plugins or module is required")
        if versionPlugin is None:
            self._version_plugin = self._plugins[0] if self._plugins else None
        else:
            self._version_plugin = versionPlugin if isinstance(versionPlugin, Plugin) else Plugin(versionPlugin)
        if minimumVersion is None:
            self._minimum_version = None
        else:
            self._minimum_version = Version.parse(minimumVersion)
            if self._minimum_version is None:
                raise ValueError(f"minimumVersion must be a version such as '3.0.0': {minimumVersion!r}")
        self._minimum_maya = None if minimumMaya is None else int(minimumMaya)
        self._install_hint = installHint

    def __repr__(self):
        """デバッグ用に製品名と最小の版を含む表現を返す。

        Returns:
            str: 型名・製品名・最小の版を含む文字列表現。
        """
        minimum = str(self._minimum_version) if self._minimum_version is not None else "なし"
        return f"PluginPackage({self._name!r}, minimumVersion={minimum})"

    @staticmethod
    def showDialog(message, title="インストールが必要です"):
        """警告ダイアログを表示する。GUI がないバッチ・スタンドアロンでは何もしない。

        Args:
            message (str): 表示する文章。
            title (str): ダイアログのタイトル。

        Returns:
            None: 値を返さない。
        """
        if cmds.about(batch=True):
            return
        cmds.confirmDialog(title=title, message=message, button=["OK"], defaultButton="OK", icon="warning")

    @property
    def name(self):
        """製品名を取得する。

        Returns:
            str: 製品名。
        """
        return self._name

    @property
    def plugins(self):
        """ロード対象のプラグインを取得する。

        Returns:
            list[Plugin]: ロード順のプラグイン。
        """
        return list(self._plugins)

    @property
    def module(self):
        """版の取得元のモジュールを取得する。

        Returns:
            Module | None: モジュール。指定していない場合は None。
        """
        return self._module

    @property
    def minimumVersion(self):
        """必要な最小の版を取得する。

        Returns:
            Version | None: 最小の版。指定していない場合は None。
        """
        return self._minimum_version

    @property
    def minimumMaya(self):
        """対象とする最小の Maya の年を取得する。

        Returns:
            int | None: 年。指定していない場合は None。
        """
        return self._minimum_maya

    def isMayaSupported(self):
        """現在の Maya が対象のバージョンか判定する。

        Returns:
            bool: ``minimumMaya`` が未指定、または現在の Maya の年がそれ以上なら True。
        """
        return self._minimum_maya is None or self._maya_year() >= self._minimum_maya

    def getInstalledVersion(self):
        """Maya に登録されている製品の版を取得する。

        モジュールが登録されていればその版、無ければ版を調べるプラグインの版を使う。

        Returns:
            Version | None: 版。未導入・版が取れない場合は None。
        """
        version = self._module.getVersion() if self._module is not None else None
        if version is None and self._version_plugin is not None:
            version = self._version_plugin.getVersion()
        return version

    def getLoadedVersion(self):
        """ロード済みの、版を調べるプラグインの版を取得する。

        Returns:
            Version | None: 版。ロードされていない場合は None。
        """
        plugin = self._version_plugin
        if plugin is None or not plugin.isLoaded():
            return None
        return plugin.getVersion()

    def isInstalled(self):
        """必要な版が導入されているか判定する。

        ロード前のプラグインは Maya に登録されていない場合がある。``minimumVersion`` を
        指定しない製品は、この判定が False でも :meth:`tryLoad` がロードを試みる。

        Returns:
            bool: ``minimumVersion`` 以上が導入されていれば True。``minimumVersion`` を指定していない
            場合は、版が取れるか、モジュールまたはプラグインが 1 つでも登録されていれば True。
        """
        version = self.getInstalledVersion()
        if self._minimum_version is not None:
            return version is not None and version >= self._minimum_version
        if version is not None:
            return True
        if self._module is not None and self._module.isRegistered():
            return True
        return any(plugin.isRegistered() for plugin in self._plugins)

    def getMessage(self, found=None):
        """導入が必要なときの警告文を作る。

        Args:
            found (Version | None): 検出した版。省略すると現在の導入状況から求める。

        Returns:
            str: 日本語と英語の警告文。
        """
        if found is None:
            found = self.getInstalledVersion()
        wanted = f"{self._name} {self._minimum_version}" if self._minimum_version else self._name
        year = self._maya_year()
        hint = self._install_hint or (
            f"Autodesk アカウントなどから Maya {year} 用の {wanted} 以降を入手してインストールしてください。")
        found_text = str(found) if found is not None else "なし"
        return (
            f"{wanted} 以降が見つかりません(検出した版: {found_text})。\n\n{hint}\n"
            "インストール後に Maya を再起動すると、自動でロードされます。\n\n"
            f"{wanted} or later was not found for Maya {year}. Please install it."
        )

    def loadPlugins(self):
        """全プラグインをロードする。ロードできない名前があっても続行する。

        Returns:
            list[str]: ロードに失敗したプラグイン名。失敗ごとに警告を出す。
        """
        failed = []
        for plugin in self._plugins:
            try:
                plugin.load(quiet=True)
            except Exception as error:
                failed.append(plugin.name)
                logger.warning("[mlib] Cannot load plugin %s for %s: %s",
                               plugin.name, self._name, error)
        return failed

    def tryLoad(self, dialog=True, warn=True):
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
        if not self.isMayaSupported():
            return SKIPPED
        title = f"{self._name} のインストールが必要です"
        show = (lambda text: self.showDialog(text, title)) if dialog is True else (dialog or None)
        installed = self.isInstalled()
        if not installed and self._minimum_version is not None:
            self._report(show, warn, self.getMessage(self.getInstalledVersion()))
            return MISSING
        failed = self.loadPlugins()
        if not installed and self._plugins and len(failed) == len(self._plugins):
            # 版を指定しない製品は、ロードできるかどうかで導入の有無を判断する。
            self._report(show, warn, self.getMessage())
            return MISSING
        running = self.getLoadedVersion()
        if self._minimum_version is not None and running is not None \
                and running < self._minimum_version:
            self._report(show, warn, self.getMessage(running))
            return OUTDATED
        return LOAD_FAILED if failed else LOADED

    @staticmethod
    def _maya_year():
        """現在のMayaの年版を照会する。

        Returns:
            int: 2025などの年版。
        """
        return int(str(cmds.about(version=True)).split(".")[0])

    def _report(self, show, warn, message):
        """指定した通知先へメッセージを送る。

        Args:
            show (callable | None): メッセージ全体を渡す表示コールバック。
            warn (bool): 最初の行を warning にも渡すか。
            message (str): 通知内容。コールバックの例外は伝播する。

        Returns:
            None: 値を返さない。
        """
        if warn:
            logger.warning("[mlib] %s", message.split("\n")[0])
        if show is not None:
            show(message)
