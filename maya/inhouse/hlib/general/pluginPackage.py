"""モジュールとプラグインの組で導入される製品(Bifrost など)の導入確認とロード。"""

# クラスメソッドへ移した旧モジュール関数をreload時に除去する。
globals().pop("_maya_year", None)

# Versionへ集約した旧関数参照をreload時に残さない。
for _name in ("parse_version", "is_at_least", "format_version"):
    globals().pop(_name, None)

import maya.cmds as cmds
from ..utils import logger

from .module import Module
from .plugin import Plugin
from hlib.utils.version import Version

SKIPPED = "skipped"
"""str: 対象外の Maya バージョンのため何もしなかった。"""
LOADED = "loaded"
"""str: 必要な版が導入済みで、全プラグインをロードした。"""
MISSING = "missing"
"""str: 導入されていない、または版が古い。プラグインはロードしていない。"""
OUTDATED = "outdated"
"""str: 導入済みだが、既にロードされているプラグインが古い版だった。"""
LOAD_FAILED = "load-failed"
"""str: 必要な版は導入済みだが、一部のプラグインをロードできなかった。"""


class PluginPackage:
    """モジュール(版の出どころ)とプラグイン群からなる製品の導入状態を扱う。

    ``Bifrost`` は Autodesk のインストーラーが Maya のバージョン別にモジュールとして
    登録し、複数のプラグインで構成される。この型は「必要な版が入っているか」の確認、
    「全プラグインのロード」、「入っていない場合の警告」を 1 つにまとめる。

    Examples:
        >>> bifrost = PluginPackage(
        ...     "Bifrost", plugins=("mayaVnnPlugin", "bifrostGraph", "flowWedging"),
        ...     module="Bifrost", version_plugin="bifrostGraph",
        ...     minimum_version="3.0.0", minimum_maya=2025)
        >>> bifrost.try_load()   # 入っていなければ警告ダイアログを出す
        'loaded'
    """

    def __init__(self, name, plugins=(), module=None, version_plugin=None,
                 minimum_version=None, minimum_maya=None, install_hint=None):
        """製品の定義を保持する。生成時に Maya へ問い合わせない。

        Args:
            name (str): 警告文に出す製品名(例: ``"Bifrost"``)。
            plugins (Iterable[str | Plugin]): ロードするプラグイン。この順にロードする。
            module (str | Module | None): 版の取得元にするモジュール。省略すると
                ``version_plugin`` の版を使う。
            version_plugin (str | Plugin | None): 版を調べるプラグイン。省略すると ``plugins`` の先頭。
            minimum_version (Version | str | int | tuple[int, ...] | None): 必要な最小の版(``"3.0.0"`` など)。
                省略すると版は問わず、導入されていればよい。
            minimum_maya (int | None): この製品を必要とする最小の Maya の年(``2025`` など)。
                それ未満の Maya では何もしない。
            install_hint (str | None): 警告文に加える導入方法の説明。省略すると既定の文章。

        Raises:
            ValueError: name が空、plugins も module も無い、minimum_version が解釈できない場合。
            TypeError: plugins の要素が文字列でも Plugin でもない場合。
        """
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")
        self._name = name
        self._plugins = tuple(item if isinstance(item, Plugin) else Plugin(item) for item in plugins)
        self._module = module if isinstance(module, Module) or module is None else Module(module)
        if not self._plugins and self._module is None:
            raise ValueError("plugins or module is required")
        if version_plugin is None:
            self._version_plugin = self._plugins[0] if self._plugins else None
        else:
            self._version_plugin = version_plugin if isinstance(version_plugin, Plugin) else Plugin(version_plugin)
        if minimum_version is None:
            self._minimum_version = None
        else:
            self._minimum_version = Version.parse(minimum_version)
            if self._minimum_version is None:
                raise ValueError("minimum_version must be a version such as '3.0.0': {!r}".format(minimum_version))
        self._minimum_maya = None if minimum_maya is None else int(minimum_maya)
        self._install_hint = install_hint

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
    def minimum_version(self):
        """必要な最小の版を取得する。

        Returns:
            Version | None: 最小の版。指定していない場合は None。
        """
        return self._minimum_version

    @property
    def minimum_maya(self):
        """対象とする最小の Maya の年を取得する。

        Returns:
            int | None: 年。指定していない場合は None。
        """
        return self._minimum_maya

    @staticmethod
    def _maya_year():
        """現在のMayaの年版を照会する。

        Returns:
            int: 2025などの年版。
        """
        return int(str(cmds.about(version=True)).split(".")[0])

    def is_maya_supported(self):
        """現在の Maya が対象のバージョンか判定する。

        Returns:
            bool: ``minimum_maya`` が未指定、または現在の Maya の年がそれ以上なら True。
        """
        return self._minimum_maya is None or self._maya_year() >= self._minimum_maya

    def installed_version(self):
        """Maya に登録されている製品の版を取得する。

        モジュールが登録されていればその版、無ければ版を調べるプラグインの版を使う。

        Returns:
            Version | None: 版。未導入・版が取れない場合は None。
        """
        version = self._module.version() if self._module is not None else None
        if version is None and self._version_plugin is not None:
            version = self._version_plugin.version()
        return version

    def loaded_version(self):
        """ロード済みの、版を調べるプラグインの版を取得する。

        Returns:
            Version | None: 版。ロードされていない場合は None。
        """
        plugin = self._version_plugin
        if plugin is None or not plugin.is_loaded():
            return None
        return plugin.version()

    def is_installed(self):
        """必要な版が導入されているか判定する。

        ロード前のプラグインは Maya に登録されていない場合がある。``minimum_version`` を
        指定しない製品は、この判定が False でも :meth:`try_load` がロードを試みる。

        Returns:
            bool: ``minimum_version`` 以上が導入されていれば True。``minimum_version`` を指定していない
            場合は、版が取れるか、モジュールまたはプラグインが 1 つでも登録されていれば True。
        """
        version = self.installed_version()
        if self._minimum_version is not None:
            return version is not None and version >= self._minimum_version
        if version is not None:
            return True
        if self._module is not None and self._module.is_registered():
            return True
        return any(plugin.is_registered() for plugin in self._plugins)

    def message(self, found=None):
        """導入が必要なときの警告文を作る。

        Args:
            found (Version | None): 検出した版。省略すると現在の導入状況から求める。

        Returns:
            str: 日本語と英語の警告文。
        """
        if found is None:
            found = self.installed_version()
        wanted = "{} {}".format(self._name, (str(self._minimum_version) if self._minimum_version is not None else "なし")) if self._minimum_version \
            else self._name
        year = self._maya_year()
        hint = self._install_hint or "Autodesk アカウントなどから Maya {} 用の {} 以降を入手してインストールしてください。".format(
            year, wanted)
        return (
            "{wanted} 以降が見つかりません(検出した版: {found})。\n\n{hint}\n"
            "インストール後に Maya を再起動すると、自動でロードされます。\n\n"
            "{wanted} or later was not found for Maya {year}. Please install it."
        ).format(wanted=wanted, found=(str(found) if found is not None else "なし"), hint=hint, year=year)

    @staticmethod
    def show_dialog(message, title="インストールが必要です"):
        """警告ダイアログを表示する。GUI がないバッチ・スタンドアロンでは何もしない。

        Args:
            message (str): 表示する文章。
            title (str): ダイアログのタイトル。
        """
        if cmds.about(batch=True):
            return
        cmds.confirmDialog(title=title, message=message, button=["OK"], defaultButton="OK", icon="warning")

    def load_plugins(self):
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
                logger.warning("[hlib] {} のプラグイン {} をロードできません: {}".format(
                    self._name, plugin.name, error))
        return failed

    def try_load(self, dialog=True, warn=True):
        """必要な版が導入されていれば全プラグインをロードし、無ければ警告する。

        ``minimum_maya`` 未満の Maya では何もしない。導入されていない、または版が古い場合は
        プラグインをロードせず、警告(``warn``)とダイアログ(``dialog``)を出す。

        Args:
            dialog (bool | Callable[[str], None]): True で :meth:`show_dialog` を使う。
                False・None で表示しない。関数を渡すと警告文を受け取って呼ぶ(テストや独自 UI 用)。
            warn (bool): True で ``logger.warning`` にも警告を出す。

        Returns:
            str: ``SKIPPED`` (対象外)/``LOADED`` (ロードした)/``MISSING`` (未導入・古い)/
            ``OUTDATED`` (既に古い版がロード済み)/``LOAD_FAILED`` (一部をロードできない)。
        """
        if not self.is_maya_supported():
            return SKIPPED
        title = "{} のインストールが必要です".format(self._name)
        show = (lambda text: self.show_dialog(text, title)) if dialog is True else (dialog or None)
        installed = self.is_installed()
        if not installed and self._minimum_version is not None:
            self._report(show, warn, self.message(self.installed_version()))
            return MISSING
        failed = self.load_plugins()
        if not installed and self._plugins and len(failed) == len(self._plugins):
            # 版を指定しない製品は、ロードできるかどうかで導入の有無を判断する。
            self._report(show, warn, self.message())
            return MISSING
        running = self.loaded_version()
        if self._minimum_version is not None and running is not None \
                and running < self._minimum_version:
            self._report(show, warn, self.message(running))
            return OUTDATED
        return LOAD_FAILED if failed else LOADED

    def _report(self, show, warn, message):
        if warn:
            logger.warning("[hlib] " + message.split("\n")[0])
        if show is not None:
            show(message)

    def __repr__(self):
        """デバッグ用に製品名と最小の版を含む表現を返す。

        Returns:
            str: 型名・製品名・最小の版を含む文字列表現。
        """
        return "PluginPackage({!r}, minimum_version={})".format(self._name, (str(self._minimum_version) if self._minimum_version is not None else "なし"))
