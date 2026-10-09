"""Mayaに依存しない版番号の値を扱う。"""

import re
from dataclasses import dataclass
from functools import total_ordering

from .._core.getterAlias import _is_alias


@total_ordering
@dataclass(frozen=True, eq=False, repr=False, init=False)
class Version:
    """数値の各桁と末尾情報を保持する不変の版番号。

    比較では末尾のゼロを補い、ビルド情報等の接尾辞は無視する。
    例えば3.0と3.0.0-buildは等しい。SemVerのプレリリース順位は扱わない。
    Mayaへの問い合わせやプラグインの更新は行わない。
    """

    __slots__ = ("_parts", "_suffix")
    _parts: tuple
    _suffix: str

    def __init__(self, value):
        """文字列・整数・整数列から版番号を作る。

        Args:
            value (Version | str | int | tuple | list): 版番号。文字列は先頭の
                数字とドットを版として読み、残りを接尾辞として保持する。
                列の要素には非負整数か数字だけの文字列を指定する。

        Raises:
            TypeError: 未対応の型、bool、整数でない列要素を指定した場合。
            ValueError: 空、負の数、数字で始まらない文字列を指定した場合。
        """
        suffix = ""
        if isinstance(value, type(self)):
            parts, suffix = value.parts, value.suffix
        elif isinstance(value, str):
            match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)*)(.*)", value.strip())
            if match is None:
                raise ValueError("Version must start with a numeric release: {!r}".format(value))
            parts = tuple(int(part) for part in match.group(1).split("."))
            suffix = match.group(2)
        elif isinstance(value, (int, tuple, list)):
            values = (value,) if isinstance(value, int) else value
            parts = tuple(self._component(part) for part in values)
            if not parts:
                raise ValueError("Version needs at least one component")
        else:
            raise TypeError("Expected a Version, string, integer or integer sequence")
        object.__setattr__(self, "_parts", parts)
        object.__setattr__(self, "_suffix", suffix)

    def __eq__(self, other):
        """版番号同士の数値列を比較する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | NotImplementedType: Version以外はNotImplemented。
        """
        if not isinstance(other, type(self)):
            return NotImplemented
        return self._comparison_key() == other._comparison_key()

    def __hash__(self):
        """等しい版番号に同じハッシュを返す。

        Returns:
            int: ゼロ埋めと接尾辞に依存しないハッシュ。
        """
        return hash(self._comparison_key())

    def __lt__(self, other):
        """数値列の大小を比較する。接尾辞は順位に影響しない。

        Args:
            other (Version): 比較対象。

        Returns:
            bool | NotImplementedType: Version以外はNotImplemented。
        """
        if not isinstance(other, type(self)):
            return NotImplemented
        return self._comparison_key() < other._comparison_key()

    def __repr__(self):
        """デバッグ用にクラス名と版番号を表示する。

        Returns:
            str: Versionのコンストラクター形式。
        """
        return "{}({!r})".format(type(self).__name__, str(self))

    def __str__(self):
        """数値列と接尾辞を文字列へ変換する。

        Returns:
            str: 3.0.0.0-buildのような文字列。先頭のゼロ・外側の空白は正規化する。
        """
        return ".".join(str(part) for part in self._parts) + self._suffix

    @classmethod
    def parse(cls, value):
        """版番号を解釈し、未取得・不正な値はNoneにする。

        Args:
            value (object): Mayaなどから取得した版番号。

        Returns:
            Version | None: 解釈できた版番号。Noneや空文字列もNoneになる。
        """
        try:
            return cls(value)
        except (TypeError, ValueError):
            return None

    @property
    def parts(self):
        """tuple[int, ...]: 指定時の桁数を維持した数値列。"""
        return self._parts

    @property
    def suffix(self):
        """str: 数値列より後ろのビルド情報等。指定がなければ空文字列。"""
        return self._suffix

    @property
    def major(self):
        """int: 第1桁のメジャー番号。"""
        return self._parts[0]

    @property
    def minor(self):
        """int: 第2桁のマイナー番号。省略時は0。"""
        return self._parts[1] if len(self._parts) > 1 else 0

    @property
    def patch(self):
        """int: 第3桁のパッチ番号。省略時は0。"""
        return self._parts[2] if len(self._parts) > 2 else 0

    @property
    def build(self):
        """int: 第4桁のビルド番号。省略時は0。接尾辞とは別の値。"""
        return self._parts[3] if len(self._parts) > 3 else 0

    def replace(self, *, major=None, minor=None, patch=None, build=None):
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
        parts = list(self._parts)
        for index, value in enumerate((major, minor, patch, build)):
            if value is None:
                continue
            component = self._component(value)
            parts.extend([0] * max(0, index + 1 - len(parts)))
            parts[index] = component
        result = type(self)(parts)
        object.__setattr__(result, "_suffix", self._suffix)
        return result

    def isAtLeast(self, minimum):
        """必要な版番号以上か判定する。

        Args:
            minimum (Version | str | int | tuple | list): 必要な最小の版番号。

        Returns:
            bool: 数値列を比較し、必要な版以上ならTrue。

        Raises:
            ValueError: 最小の版番号を解釈できない場合。
        """
        required = type(self).parse(minimum)
        if required is None:
            raise ValueError("Invalid minimum version: {!r}".format(minimum))
        return self >= required

    @_is_alias(isAtLeast)
    def atLeast(self, *args, **kwargs):
        """isAtLeastへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isAtLeast(*args, **kwargs)

    @staticmethod
    def _component(value):
        """版番号の一桁を非負整数へ変換する。

        Args:
            value (int | str): 整数または数字だけの文字列。

        Returns:
            int: 検証済みの非負整数。

        Raises:
            TypeError: bool・小数など整数でない場合。
            ValueError: 負の整数の場合。
        """
        if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
            return int(value)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("Version components must be integers")
        if value < 0:
            raise ValueError("Version components must be non-negative")
        return value

    def _comparison_key(self):
        """比較とハッシュ用に、末尾のゼロを除いた数値列を返す。

        Returns:
            tuple[int, ...]: 最低1桁を保持する数値列。
        """
        parts = self._parts
        while len(parts) > 1 and parts[-1] == 0:
            parts = parts[:-1]
        return parts
