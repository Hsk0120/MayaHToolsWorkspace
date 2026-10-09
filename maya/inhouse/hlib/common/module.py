"""Maya に登録されているモジュール(``.mod`` で定義したもの)を扱う。"""

import maya.cmds as cmds

from .._core.getterAlias import _getter_alias, _is_alias
from .version import Version

# Versionへ集約した旧関数参照をreload時に残さない。
for _name in ("parse_version", "is_at_least", "format_version"):
    globals().pop(_name, None)


class Module:
    """名前で参照する Maya モジュール。生成時に存在確認しない。

    Autodesk 製品(Bifrost・MayaUSD・Arnold など)や ``maya/modules/*.mod`` は、
    プラグインとは別に「モジュール」として登録され、版と場所を持つ。
    """

    def __init__(self, name):
        """モジュール名を保持する。

        Args:
            name (str): モジュール名(``.mod`` の ``+`` 行に書いた名前。例: ``"Bifrost"``)。

        Raises:
            ValueError: name が空文字列または文字列以外の場合。
        """
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")
        self._name = name

    def __eq__(self, other):
        """モジュール名を基準に同一性を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: Module 同士は名前の一致。異なる型では NotImplemented。
        """
        if not isinstance(other, Module):
            return NotImplemented
        return self._name == other._name

    def __hash__(self):
        """モジュール名を使ったハッシュ値を返す。

        Returns:
            int: 保持している名前のハッシュ。
        """
        return hash(self._name)

    def __repr__(self):
        """デバッグ用にクラス名とモジュール名を含む表現を返す。

        Returns:
            str: 型名とモジュール名を含む文字列表現。
        """
        return "Module({!r})".format(self._name)

    def __str__(self):
        """モジュール名を返す。

        Returns:
            str: 保持しているモジュール名。
        """
        return self._name

    @property
    def name(self):
        """保持しているモジュール名を取得する。

        Returns:
            str: モジュール名。
        """
        return self._name

    def isRegistered(self):
        """Maya がこのモジュールを認識しているか判定する。

        Returns:
            bool: 登録済みなら True。未登録の名前でも例外にならず False。
        """
        return self._name in (cmds.moduleInfo(listModules=True) or [])

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

    def getVersionText(self):
        """Mayaが返すモジュールの版文字列をそのまま取得する。

        Returns:
            str | None: 生の版文字列。未登録・空の場合はNone。
        """
        if not self.isRegistered():
            return None
        return cmds.moduleInfo(version=True, moduleName=self._name) or None

    def getVersion(self):
        """モジュールの現在の版を値オブジェクトとして取得する。

        Returns:
            Version | None: 問い合わせ時点の版。未登録・解釈不能ならNone。
                取得した値をreplaceしてもMaya側の版は変更されない。
        """
        return Version.parse(self.getVersionText())

    def isVersionAtLeast(self, minimum):
        """モジュールの版が ``minimum`` 以上か判定する。

        Args:
            minimum (Version | str | int | tuple[int, ...]): 必要な最小の版(``"3.0.0"`` など)。

        Returns:
            bool: 未登録なら False。

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

    def getPath(self):
        """モジュールのフォルダーを取得する。

        Returns:
            str | None: モジュールの場所。未登録の場合は None。
        """
        if not self.isRegistered():
            return None
        return cmds.moduleInfo(path=True, moduleName=self._name) or None

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
