# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mayaに依存しない版番号の値を扱う。"""

import re
from dataclasses import dataclass
from functools import total_ordering
import types



@total_ordering
class Version:
    """数値の各桁と末尾情報を保持する不変の版番号。

    比較では末尾のゼロを補い、ビルド情報等の接尾辞は無視する。
    例えば3.0と3.0.0-buildは等しい。SemVerのプレリリース順位は扱わない。
    Mayaへの問い合わせやプラグインの更新は行わない。
    """
    __slots__: tuple
    _parts: tuple
    _suffix: str
    def __init__(self, value: Version | str | int | tuple | list) -> None:
        """文字列・整数・整数列から版番号を作る。

        Args:
            value (Version | str | int | tuple | list): 版番号。文字列は先頭の
                数字とドットを版として読み、残りを接尾辞として保持する。
                列の要素には非負整数か数字だけの文字列を指定する。

        Raises:
            TypeError: 未対応の型、bool、整数でない列要素を指定した場合。
            ValueError: 空、負の数、数字で始まらない文字列を指定した場合。
        """
        ...
    def __eq__(self, other: object) -> bool | types.NotImplementedType:
        """版番号同士の数値列を比較する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | NotImplementedType: Version以外はNotImplemented。
        """
        ...
    def __hash__(self) -> int:
        """等しい版番号に同じハッシュを返す。

        Returns:
            int: ゼロ埋めと接尾辞に依存しないハッシュ。
        """
        ...
    def __lt__(self, other: Version) -> bool | types.NotImplementedType:
        """数値列の大小を比較する。接尾辞は順位に影響しない。

        Args:
            other (Version): 比較対象。

        Returns:
            bool | NotImplementedType: Version以外はNotImplemented。
        """
        ...
    def __repr__(self) -> str:
        """デバッグ用にクラス名と版番号を表示する。

        Returns:
            str: Versionのコンストラクター形式。
        """
        ...
    def __str__(self) -> str:
        """数値列と接尾辞を文字列へ変換する。

        Returns:
            str: 3.0.0.0-buildのような文字列。先頭のゼロ・外側の空白は正規化する。
        """
        ...
    @classmethod
    def parse(cls, value: object) -> Version | None:
        """版番号を解釈し、未取得・不正な値はNoneにする。

        Args:
            value (object): Mayaなどから取得した版番号。

        Returns:
            Version | None: 解釈できた版番号。Noneや空文字列もNoneになる。
        """
        ...
    @property
    def parts(self) -> tuple[int, ...]:
        """tuple[int, ...]: 指定時の桁数を維持した数値列。"""
        ...
    @property
    def suffix(self) -> str:
        """str: 数値列より後ろのビルド情報等。指定がなければ空文字列。"""
        ...
    @property
    def major(self) -> int:
        """int: 第1桁のメジャー番号。"""
        ...
    @property
    def minor(self) -> int:
        """int: 第2桁のマイナー番号。省略時は0。"""
        ...
    @property
    def patch(self) -> int:
        """int: 第3桁のパッチ番号。省略時は0。"""
        ...
    @property
    def build(self) -> int:
        """int: 第4桁のビルド番号。省略時は0。接尾辞とは別の値。"""
        ...
    def replace(self, *, major: int | None = ..., minor: int | None = ..., patch: int | None = ..., build: int | None = ...) -> Version:
        """指定した桁を変更した新しい版番号を返す。元の値は変更しない。

        Args:
            major (int | None): 第1桁。Noneは現在値を維持する。
            minor (int | None): 第2桁。Noneは現在値を維持する。
            patch (int | None): 第3桁。Noneは現在値を維持する。
            build (int | None): 第4桁。Noneは現在値を維持する。

        Returns:
            Version: 未指定の桁と接尾辞を維持した値。必要な中間桁は0で補う。

        Raises:
            TypeError: 整数でない値を指定した場合。
            ValueError: 負の値を指定した場合。
        """
        ...
    def isAtLeast(self, minimum: Version | str | int | tuple | list) -> bool:
        """必要な版番号以上か判定する。

        Args:
            minimum (Version | str | int | tuple | list): 必要な最小の版番号。

        Returns:
            bool: 数値列を比較し、必要な版以上ならTrue。

        Raises:
            ValueError: 最小の版番号を解釈できない場合。
        """
        ...
    @staticmethod
    def _component(value: int | str) -> int:
        """版番号の一桁を非負整数へ変換する。

        Args:
            value (int | str): 整数または数字だけの文字列。

        Returns:
            int: 検証済みの非負整数。

        Raises:
            TypeError: bool・小数など整数でない場合。
            ValueError: 負の整数の場合。
        """
        ...
    def _comparison_key(self) -> tuple[int, ...]:
        """比較とハッシュ用に、末尾のゼロを除いた数値列を返す。

        Returns:
            tuple[int, ...]: 最低1桁を保持する数値列。
        """
        ...
