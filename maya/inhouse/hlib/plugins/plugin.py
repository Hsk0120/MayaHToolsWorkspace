"""Maya のロード済み/登録済みプラグインを扱う。"""

# 旧構成からreloadした場合も、移動したコレクションクラスを残さない。
globals().pop("Plugins", None)

# Versionへ集約した旧関数参照をreload時に残さない。
for _name in ("parse_version", "is_at_least", "format_version"):
    globals().pop(_name, None)

import maya.cmds as cmds
from ..utils.version import Version


class Plugin:
    """名前で参照する Maya プラグイン(.mll/.py/.so)。生成時に存在確認しない。"""

    _HIK_NODE_TYPES = frozenset((
        "HIKCharacterNode", "HIKSolverNode", "HIKRetargeterNode",
        "HIKControlSetNode", "HIKSkeletonGeneratorNode",
    ))

    @classmethod
    def ensure_node_plugin(cls, node_type):
        """指定ノード型が必要とする標準同梱プラグインをロードする。

        Args:
            node_type (str): 作成するMayaノード型。HumanIK以外は何もしない。

        Raises:
            RuntimeError: Mayaがプラグインのロードを拒否した場合。
        """
        if node_type in cls._HIK_NODE_TYPES:
            cls("mayaHIK").ensure_loaded()

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

    def name(self):
        """保持しているプラグイン名を取得する。

        Returns:
            str: プラグイン名。
        """
        return self._name

    def is_registered(self):
        """Maya がこのプラグインを認識しているか判定する。

        Returns:
            bool: 登録済み(ロード済み、または未ロードだが検出可能)なら True。
                未知のプラグイン名では False。
        """
        return bool(cmds.pluginInfo(self._name, query=True, registered=True))

    def is_loaded(self):
        """プラグインが現在ロードされているか判定する。

        Returns:
            bool: ロード済みなら True。未知のプラグイン名でも例外にならず False。
        """
        return bool(cmds.pluginInfo(self._name, query=True, loaded=True))

    def path(self):
        """プラグインファイルの絶対パスを取得する。

        Returns:
            str | None: 登録済みプラグインのファイルパス。未登録の場合は None。
        """
        if not self.is_registered():
            return None
        return cmds.pluginInfo(self._name, query=True, path=True) or None

    def version_text(self):
        """Mayaが返すプラグインの版文字列をそのまま取得する。

        Returns:
            str | None: 生の版文字列。未登録・空の場合はNone。
        """
        if not self.is_registered():
            return None
        return cmds.pluginInfo(self._name, query=True, version=True) or None

    def version(self):
        """プラグインの現在の版を値オブジェクトとして取得する。

        Returns:
            Version | None: 問い合わせ時点の版。未登録・解釈不能ならNone。
                取得した値をreplaceしてもMaya側の版は変更されない。
        """
        return Version.parse(self.version_text())

    def version_tuple(self):
        """数値列だけが必要な既存コード向けに版のタプルを取得する。

        Returns:
            tuple[int, ...] | None: 接尾辞を除いた版。未登録・解釈不能ならNone。
        """
        version = self.version()
        return version.parts if version is not None else None

    def is_version_at_least(self, minimum):
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
        version = self.version()
        return version is not None and version >= required

    def load(self, **kwargs):
        """プラグインをロードする。

        Args:
            **kwargs (object): ``cmds.loadPlugin`` に渡す追加のキーワード引数
                (``quiet=True`` など)。

        Returns:
            Plugin: 自身。

        Raises:
            RuntimeError: Maya がロードを拒否した場合。
        """
        cmds.loadPlugin(self._name, **kwargs)
        return self

    def unload(self, force=False):
        """プラグインをアンロードする。

        Args:
            force (bool): True の場合、使用中でも強制的にアンロードする。

        Returns:
            Plugin: 自身。

        Raises:
            RuntimeError: Maya がアンロードを拒否した場合。
        """
        cmds.unloadPlugin(self._name, force=force)
        return self

    def ensure_loaded(self):
        """未ロードであればロードする(冪等)。

        Args:
            なし。

        Returns:
            Plugin: 自身。

        Raises:
            RuntimeError: Maya がロードを拒否した場合。
        """
        if not self.is_loaded():
            self.load()
        return self

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

    def __str__(self):
        """プラグイン名を返す。

        Returns:
            str: 保持しているプラグイン名。
        """
        return self._name

    def __repr__(self):
        """デバッグ用にクラス名とプラグイン名を含む表現を返す。

        Returns:
            str: 型名とプラグイン名を含む文字列表現。
        """
        return f"Plugin({self._name!r})"
