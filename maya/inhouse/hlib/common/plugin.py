"""Maya のロード済み/登録済みプラグインを扱う。"""

import maya.cmds as cmds

from .._core.flags import flag_aliases
from .._core.getterAlias import _getter_alias, _is_alias
from .._core.typeHierarchy import clear_cache
from .version import Version

# 旧構成からreloadした場合も、移動したコレクションクラスを残さない。
globals().pop("Plugins", None)

# Versionへ集約した旧関数参照をreload時に残さない。
for _name in ("parse_version", "is_at_least", "format_version"):
    globals().pop(_name, None)


class Plugin:
    """名前で参照する Maya プラグイン(.mll/.py/.so)。生成時に存在確認しない。"""

    _HIK_NODE_TYPES = frozenset((
        "HIKCharacterNode", "HIKSolverNode", "HIKRetargeterNode",
        "HIKControlSetNode", "HIKSkeletonGeneratorNode",
    ))

    def __init__(self, name):
        """プラグイン名を保持する。

        Args:
            name (str): プラグインファイル名(拡張子を除く。例: ``"matrixNodes"``)。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: name が空文字列または文字列以外の場合。
        """
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")
        self._name = name

    def __eq__(self, other):
        """プラグイン名を基準に同一性を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: Plugin 同士は名前の一致。
                異なる型では NotImplemented。
        """
        if not isinstance(other, Plugin):
            return NotImplemented
        return self._name == other._name

    def __hash__(self):
        """プラグイン名を使ったハッシュ値を返す。

        Returns:
            int: 保持している名前のハッシュ。
        """
        return hash(self._name)

    def __repr__(self):
        """デバッグ用にクラス名とプラグイン名を含む表現を返す。

        Returns:
            str: 型名とプラグイン名を含む文字列表現。
        """
        return f"Plugin({self._name!r})"

    def __str__(self):
        """プラグイン名を返す。

        Returns:
            str: 保持しているプラグイン名。
        """
        return self._name

    @classmethod
    def ensureNodePlugin(cls, node_type):
        """指定ノード型が必要とする標準同梱プラグインをロードする。

        Args:
            node_type (str): 作成するMayaノード型。HumanIK以外は何もしない。

        Raises:
            RuntimeError: Mayaがプラグインのロードを拒否した場合。
        """
        if node_type in cls._HIK_NODE_TYPES:
            cls("mayaHIK").ensureLoaded()

    @classmethod
    def loaded(cls):
        """ロード済みプラグインを取得する。

        Returns:
            list[Plugin]: Mayaが返す順序のプラグイン一覧。
        """
        return [cls(name) for name in (cmds.pluginInfo(query=True, listPlugins=True) or [])]

    @property
    def name(self):
        """保持しているプラグイン名を取得する。

        Returns:
            str: プラグイン名。
        """
        return self._name

    def isRegistered(self):
        """Maya がこのプラグインを認識しているか判定する。

        Returns:
            bool: 登録済み(ロード済み、または未ロードだが検出可能)なら True。
                未知のプラグイン名では False。
        """
        return bool(cmds.pluginInfo(self._name, query=True, registered=True))

    @_is_alias(isRegistered)
    def registered(self, *args, **kwargs):
        """isRegisteredへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isRegistered(*args, **kwargs)

    def isLoaded(self):
        """プラグインが現在ロードされているか判定する。

        Returns:
            bool: ロード済みなら True。未知のプラグイン名でも例外にならず False。
        """
        return bool(cmds.pluginInfo(self._name, query=True, loaded=True))

    def getPath(self):
        """プラグインファイルの絶対パスを取得する。

        Returns:
            str | None: 登録済みプラグインのファイルパス。未登録の場合は None。
        """
        if not self.isRegistered():
            return None
        return cmds.pluginInfo(self._name, query=True, path=True) or None

    def getVersionText(self):
        """Mayaが返すプラグインの版文字列をそのまま取得する。

        Returns:
            str | None: 生の版文字列。未登録・空の場合はNone。
        """
        if not self.isRegistered():
            return None
        return cmds.pluginInfo(self._name, query=True, version=True) or None

    def getVersion(self):
        """プラグインの現在の版を値オブジェクトとして取得する。

        Returns:
            Version | None: 問い合わせ時点の版。未登録・解釈不能ならNone。
                取得した値をreplaceしてもMaya側の版は変更されない。
        """
        return Version.parse(self.getVersionText())

    def isVersionAtLeast(self, minimum):
        """プラグインの版が ``minimum`` 以上か判定する。

        Args:
            minimum (Version | str | int | tuple[int, ...]): 必要な最小の版(``"3.0.0"`` など)。

        Returns:
            bool: 未登録・版が取れない場合は False。

        Raises:
            ValueError: minimum が版として解釈できない場合。
        """
        required = Version.parse(minimum)
        if required is None:
            raise ValueError("Invalid minimum version: {!r}".format(minimum))
        version = self.getVersion()
        return version is not None and version >= required

    @_is_alias(isVersionAtLeast)
    def versionAtLeast(self, *args, **kwargs):
        """isVersionAtLeastへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isVersionAtLeast(*args, **kwargs)

    def load(self, **kwargs):
        """プラグインをロードする。

        正常完了後はhlibのノード型継承キャッシュを消去し、次の型選択で再照会する。
        cmds.loadPluginを直接使う操作の状態変更は、この入口では監視しない。

        Args:
            **kwargs (object): ``cmds.loadPlugin`` に渡す追加のキーワード引数
                (``quiet=True`` など)。

        Returns:
            Plugin: 自身。

        Raises:
            RuntimeError: Mayaがロードを拒否した、または初期化後も未ロードの場合。
        """
        cmds.loadPlugin(self._name, **kwargs)
        # Pythonプラグインの初期化失敗は、例外なしのNoneとして返る場合がある。
        # 戻り値だけでは既にロード済みのquiet呼出しと区別できないため状態を照会する。
        if not self.isLoaded():
            raise RuntimeError("Plugin initialization did not complete: " + self._name)
        clear_cache()
        return self

    @flag_aliases(f="force")
    def unload(self, force=False):
        """プラグインをアンロードする。

        正常完了後はhlibのノード型継承キャッシュを消去する。

        Args:
            force (bool): True の場合、使用中でも強制的にアンロードする。 別名 ``f`` も使用可能。

        Returns:
            Plugin: 自身。

        Raises:
            RuntimeError: Maya がアンロードを拒否した場合。
        """
        cmds.unloadPlugin(self._name, force=force)
        clear_cache()
        return self

    def ensureLoaded(self):
        """未ロードであればロードする(冪等)。

        Args:
            なし。

        Returns:
            Plugin: 自身。

        Raises:
            RuntimeError: Maya がロードを拒否した場合。
        """
        if not self.isLoaded():
            self.load()
        return self

    @_getter_alias(getPath)
    def path(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPath(*args, **kwargs)

    @_getter_alias(getVersionText)
    def versionText(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getVersionText(*args, **kwargs)

    @_getter_alias(getVersion)
    def version(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getVersion(*args, **kwargs)
