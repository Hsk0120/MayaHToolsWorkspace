# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya に登録されているモジュール(``.mod`` で定義したもの)を扱う。"""

import maya.cmds as cmds
from .version import Version
import types



class Module:
    """名前で参照する Maya モジュール。生成時に存在確認しない。

    Autodesk 製品(Bifrost・MayaUSD・Arnold など)や ``maya/modules/*.mod`` は、
    プラグインとは別に「モジュール」として登録され、版と場所を持つ。
    """
    def __init__(self, name: str) -> None:
        """モジュール名を保持する。

        Args:
            name (str): モジュール名(``.mod`` の ``+`` 行に書いた名前。例: ``"Bifrost"``)。

        Raises:
            TypeError: name が文字列以外の場合。
            ValueError: name が空文字列の場合。
        """
        ...
    def __eq__(self, other: object) -> bool | types.NotImplementedType:
        """モジュール名を基準に同一性を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: Module 同士は名前の一致。異なる型では NotImplemented。
        """
        ...
    def __hash__(self) -> int:
        """モジュール名を使ったハッシュ値を返す。

        Returns:
            int: 保持している名前のハッシュ。
        """
        ...
    def __repr__(self) -> str:
        """デバッグ用にクラス名とモジュール名を含む表現を返す。

        Returns:
            str: 型名とモジュール名を含む文字列表現。
        """
        ...
    def __str__(self) -> str:
        """モジュール名を返す。

        Returns:
            str: 保持しているモジュール名。
        """
        ...
    @property
    def name(self) -> str:
        """保持しているモジュール名を取得する。

        Returns:
            str: モジュール名。
        """
        ...
    def isRegistered(self) -> bool:
        """Maya がこのモジュールを認識しているか判定する。

        Returns:
            bool: 登録済みなら True。未登録の名前でも例外にならず False。
        """
        ...
    def getVersionText(self) -> str | None:
        """Mayaが返すモジュールの版文字列をそのまま取得する。

        Returns:
            str | None: 生の版文字列。未登録・空の場合はNone。
        """
        ...
    def getVersion(self) -> Version | None:
        """モジュールの現在の版を値オブジェクトとして取得する。

        Returns:
            Version | None: 問い合わせ時点の版。未登録・解釈不能ならNone。
                取得した値をreplaceしてもMaya側の版は変更されない。
        """
        ...
    def isVersionAtLeast(self, minimum: Version | str | int | tuple[int, ...]) -> bool:
        """モジュールの版が ``minimum`` 以上か判定する。

        Args:
            minimum (Version | str | int | tuple[int, ...]): 必要な最小の版(``"3.0.0"`` など)。

        Returns:
            bool: 未登録なら False。

        Raises:
            ValueError: minimum が版として解釈できない場合。
        """
        ...
    def getPath(self) -> str | None:
        """モジュールのフォルダーを取得する。

        Returns:
            str | None: モジュールの場所。未登録の場合は None。
        """
        ...
