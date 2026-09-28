"""Mayaプラグインのコレクションを扱う。"""

import maya.cmds as cmds

from hlib._core.collection import BulkCollection, bulk_api
from .plugin import Plugin


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
            if plugin.name in seen:
                continue
            seen.add(plugin.name)
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
