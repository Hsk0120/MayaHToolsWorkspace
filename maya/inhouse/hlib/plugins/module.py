"""Maya に登録されているモジュール(``.mod`` で定義したもの)を扱う。"""

import maya.cmds as cmds

from .versions import is_at_least, parse_version


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

    def name(self):
        """保持しているモジュール名を取得する。

        Returns:
            str: モジュール名。
        """
        return self._name

    def is_registered(self):
        """Maya がこのモジュールを認識しているか判定する。

        Returns:
            bool: 登録済みなら True。未登録の名前でも例外にならず False。
        """
        return self._name in (cmds.moduleInfo(listModules=True) or [])

    def version(self):
        """モジュールの版の文字列を取得する。

        Returns:
            str | None: 版の文字列(例: ``"3.0.0.0"``)。未登録・版が空の場合は None。
        """
        if not self.is_registered():
            return None
        return cmds.moduleInfo(version=True, moduleName=self._name) or None

    def version_tuple(self):
        """モジュールの版を数値のタプルで取得する。

        Returns:
            tuple[int, ...] | None: 版。未登録・解釈できない場合は None。
        """
        return parse_version(self.version())

    def is_version_at_least(self, minimum):
        """モジュールの版が ``minimum`` 以上か判定する。

        Args:
            minimum (str | int | tuple[int, ...]): 必要な最小の版(``"3.0.0"`` など)。

        Returns:
            bool: 未登録なら False。

        Raises:
            ValueError: minimum が版として解釈できない場合。
        """
        return is_at_least(self.version_tuple(), minimum)

    def path(self):
        """モジュールのフォルダーを取得する。

        Returns:
            str | None: モジュールの場所。未登録の場合は None。
        """
        if not self.is_registered():
            return None
        return cmds.moduleInfo(path=True, moduleName=self._name) or None

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

    def __str__(self):
        """モジュール名を返す。

        Returns:
            str: 保持しているモジュール名。
        """
        return self._name

    def __repr__(self):
        """デバッグ用にクラス名とモジュール名を含む表現を返す。

        Returns:
            str: 型名とモジュール名を含む文字列表現。
        """
        return "Module({!r})".format(self._name)
