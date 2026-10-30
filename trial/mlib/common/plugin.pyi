# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya のロード済み/登録済みプラグインを扱う。"""

import maya.cmds as cmds
from ..core.registry import _clear_type_hierarchy_cache
from .version import Version
import types



class Plugin:
    """名前で参照する Maya プラグイン(.mll/.py/.so)。生成時に存在確認しない。"""
    _HIK_NODE_TYPES: frozenset
    def __init__(self, name: str) -> None:
        """プラグイン名を保持する。

        Args:
            name (str): プラグインファイル名(拡張子を除く。例: ``"matrixNodes"``)。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: name が文字列以外の場合。
            ValueError: name が空文字列の場合。
        """
        ...
    def __eq__(self, other: object) -> bool | types.NotImplementedType:
        """プラグイン名を基準に同一性を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: Plugin 同士は名前の一致。
                異なる型では NotImplemented。
        """
        ...
    def __hash__(self) -> int:
        """プラグイン名を使ったハッシュ値を返す。

        Returns:
            int: 保持している名前のハッシュ。
        """
        ...
    def __repr__(self) -> str:
        """デバッグ用にクラス名とプラグイン名を含む表現を返す。

        Returns:
            str: 型名とプラグイン名を含む文字列表現。
        """
        ...
    def __str__(self) -> str:
        """プラグイン名を返す。

        Returns:
            str: 保持しているプラグイン名。
        """
        ...
    @classmethod
    def ensureNodePlugin(cls, nodeType: str) -> None:
        """指定ノード型が必要とする標準同梱プラグインをロードする。

        Args:
            nodeType (str): 作成するMayaノード型。HumanIK以外は何もしない。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: Mayaがプラグインのロードを拒否した場合。
        """
        ...
    @classmethod
    def loaded(cls) -> list[Plugin]:
        """ロード済みプラグインを取得する。

        Returns:
            list[Plugin]: Mayaが返す順序のプラグイン一覧。
        """
        ...
    @property
    def name(self) -> str:
        """保持しているプラグイン名を取得する。

        Returns:
            str: プラグイン名。
        """
        ...
    def isRegistered(self) -> bool:
        """Maya がこのプラグインを認識しているか判定する。

        Returns:
            bool: 登録済み(ロード済み、または未ロードだが検出可能)なら True。
                未知のプラグイン名では False。
        """
        ...
    def isLoaded(self) -> bool:
        """プラグインが現在ロードされているか判定する。

        Returns:
            bool: ロード済みなら True。未知のプラグイン名でも例外にならず False。
        """
        ...
    def getPath(self) -> str | None:
        """プラグインファイルの絶対パスを取得する。

        Returns:
            str | None: 登録済みプラグインのファイルパス。未登録の場合は None。
        """
        ...
    def getVersionText(self) -> str | None:
        """Mayaが返すプラグインの版文字列をそのまま取得する。

        Returns:
            str | None: 生の版文字列。未登録・空の場合はNone。
        """
        ...
    def getVersion(self) -> Version | None:
        """プラグインの現在の版を値オブジェクトとして取得する。

        Returns:
            Version | None: 問い合わせ時点の版。未登録・解釈不能ならNone。
                取得した値をreplaceしてもMaya側の版は変更されない。
        """
        ...
    def isVersionAtLeast(self, minimum: Version | str | int | tuple[int, ...]) -> bool:
        """プラグインの版が ``minimum`` 以上か判定する。

        Args:
            minimum (Version | str | int | tuple[int, ...]): 必要な最小の版(``"3.0.0"`` など)。

        Returns:
            bool: 未登録・版が取れない場合は False。

        Raises:
            ValueError: minimum が版として解釈できない場合。
        """
        ...
    def load(self, **kwargs: object) -> Plugin:
        """プラグインをロードする。

        正常完了後はmlibのノード型継承キャッシュを消去し、次の型選択で再照会する。
        cmds.loadPluginを直接使う操作の状態変更は、この入口では監視しない。

        Args:
            **kwargs (object): ``cmds.loadPlugin`` に渡す追加のキーワード引数
                (``quiet=True`` など)。

        Returns:
            Plugin: 自身。

        Raises:
            RuntimeError: Mayaがロードを拒否した、または初期化後も未ロードの場合。
        """
        ...
    def unload(self, force: bool = ...) -> Plugin:
        """プラグインをアンロードする。

        正常完了後はmlibのノード型継承キャッシュを消去する。

        Args:
            force (bool): True の場合、使用中でも強制的にアンロードする。

        Returns:
            Plugin: 自身。

        Raises:
            TypeError: forceとfを同時に指定した場合。
            RuntimeError: Maya がアンロードを拒否した場合。
        """
        ...
    def ensureLoaded(self) -> Plugin:
        """未ロードであればロードする(冪等)。

        Returns:
            Plugin: 自身。

        Raises:
            RuntimeError: Maya がロードを拒否した場合。
        """
        ...
