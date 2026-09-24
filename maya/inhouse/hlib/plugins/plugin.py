"""Maya のロード済み/登録済みプラグインを扱う。"""

import maya.cmds as cmds
from .._core.collection import BulkCollection, bulk_api


class Plugin:
    """名前で参照する Maya プラグイン(.mll/.py/.so)。生成時に存在確認しない。"""

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

    def version(self):
        """プラグインのバージョン文字列を取得する。

        Returns:
            str | None: バージョン文字列。未登録の場合は None。
        """
        if not self.is_registered():
            return None
        return cmds.pluginInfo(self._name, query=True, version=True) or None

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


@bulk_api(Plugin, undo=False)
class Plugins(BulkCollection):
    """プラグイン名または Plugin の列を、名前の重複を除いて保持するコレクション。"""

    def __init__(self, names=()):
        """プラグイン名または Plugin のシーケンスから重複なしコレクションを作成する。

        Args:
            names (Iterable[str | Plugin]): プラグイン名またはラッパー。
                名前で重複を除外する。

        Returns:
            None: 値を返さない。
        """
        self._items = []
        seen = set()
        for item in names:
            plugin = item if isinstance(item, Plugin) else Plugin(item)
            if plugin.name() in seen:
                continue
            seen.add(plugin.name())
            self._items.append(plugin)

    @classmethod
    def loaded(cls):
        """現在ロードされている全プラグインを取得する。

        Returns:
            Plugins: ロード済みプラグインのコレクション。
        """
        names = cmds.pluginInfo(query=True, listPlugins=True) or []
        return cls(names)

    def __iter__(self):
        """保持している Plugin を順に反復する。

        Returns:
            Iterator[Plugin]: 保存順に Plugin を返すイテレータ。
        """
        return iter(self._items)

    def __len__(self):
        """保持しているプラグイン数を取得する。

        Returns:
            int: コレクションの要素数。
        """
        return len(self._items)
