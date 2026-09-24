"""Maya のノード名として有効な文字列への変換。Maya非依存の純粋関数。"""

import re

_ILLEGAL_CHARACTERS = re.compile(r"[^_a-zA-Z0-9:]+")


def legalize_name(name):
    """任意の文字列を Maya が受け付けるノード名へ変換する。

    前後の空白を除去し、先頭が数字ならアンダースコアを付与し、
    英数字・アンダースコア・コロン(namespace区切り)以外の連続を
    単一のアンダースコアへ置換する。

    Args:
        name (str): 変換対象の文字列。

    Returns:
        str: Maya のノード名として有効な文字列。変換後に空になる場合は ``"_"``。

    Raises:
        TypeError: name が文字列でない場合。
    """
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    name = name.strip()
    if name and name[0].isdigit():
        name = "_" + name
    name = _ILLEGAL_CHARACTERS.sub("_", name)
    return name or "_"
