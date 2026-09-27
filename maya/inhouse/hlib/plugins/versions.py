"""プラグイン・モジュールの版の文字列を数値のタプルとして扱う補助関数。"""

import re


def parse_version(value):
    """版を、先頭の数字の並びからタプルにする。

    Args:
        value (str | int | tuple[int, ...] | list[int] | None): ``"3.0.0.0"`` や
            ``"3.0.0.0-202602040323-9df3db7"`` のような文字列、整数 1 つ(メジャー版)、
            または整数の並び。

    Returns:
        tuple[int, ...] | None: 版の数値。空・数字で始まらない・None の場合は None。

    Examples:
        >>> parse_version("3.0.0.0-202602040323-9df3db7")
        (3, 0, 0, 0)
        >>> parse_version((3, 1))
        (3, 1)
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return (value,)
    if isinstance(value, (tuple, list)):
        try:
            return tuple(int(part) for part in value) or None
        except (TypeError, ValueError):
            return None
    match = re.match(r"\s*(\d+(?:\.\d+)*)", str(value))
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_at_least(version, minimum):
    """``version`` が ``minimum`` 以上かを返す。桁数が違っても比較できる。

    Args:
        version (str | int | tuple[int, ...] | None): 調べる版。None・解釈できない値は未検出として扱う。
        minimum (str | int | tuple[int, ...]): 必要な最小の版。

    Returns:
        bool: 未検出なら False。

    Raises:
        ValueError: minimum が版として解釈できない場合。

    Examples:
        >>> is_at_least("3.1.0.8", "3.0.0")
        True
        >>> is_at_least((2, 15, 0, 0), (3, 0, 0))
        False
    """
    required = parse_version(minimum)
    if required is None:
        raise ValueError("minimum must be a version such as '3.0.0': {!r}".format(minimum))
    found = parse_version(version)
    if found is None:
        return False
    width = max(len(found), len(required))
    return found + (0,) * (width - len(found)) >= required + (0,) * (width - len(required))


def format_version(version):
    """版のタプルを ``3.0.0`` のような文字列にする。

    Args:
        version (tuple[int, ...] | None): 版。

    Returns:
        str: ``"3.0.0"`` のような文字列。None は ``"なし"``。
    """
    parsed = parse_version(version)
    return ".".join(str(part) for part in parsed) if parsed else "なし"
