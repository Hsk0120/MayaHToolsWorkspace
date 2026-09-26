"""任意の文字列から Maya のノード名に使える文字列を組み立てる。Maya非依存。

Maya のノード名と名前空間名は、いずれも ASCII 英字・数字・アンダースコア
だけで構成し、数字で始めてはならない。名前空間はコロン ``:`` で区切って
連結する。本モジュールはこの規則を区間(コロン区切りの1要素)単位で満たす
文字列を返す関数を提供する。
"""

import string

#: 名前空間の区切り文字。区切りとして残し、区間ごとに検査する。
_SEPARATOR = ":"

#: 使えない文字の代わりに入れる文字。
_FILLER = "_"

#: 区間内で使ってよい文字。``str.isalnum`` は非ASCII文字も真になるため使わない。
_PERMITTED = frozenset(string.ascii_letters + string.digits + _FILLER)

#: 区間の先頭に置けない文字。``str.isdigit`` は上付き数字なども真になるため使わない。
_NOT_AT_HEAD = frozenset(string.digits)


def _clean_segment(segment):
    """コロンで区切られた1区間を、単独で有効な識別子へ整える。

    前後の空白を落とし、使えない文字が連続する箇所は1文字の ``_`` に
    まとめる。入力にもともと含まれる ``_`` はそのまま残す。整えた結果が
    数字で始まる場合は先頭に ``_`` を足す。

    Args:
        segment (str): コロンを含まない1区間。

    Returns:
        str: 整えた区間。空白だけ、または空の区間なら空文字。
    """
    out = []
    in_bad_run = False
    for char in segment.strip():
        if char in _PERMITTED:
            out.append(char)
            in_bad_run = False
            continue
        if not in_bad_run:
            out.append(_FILLER)
            in_bad_run = True
    cleaned = "".join(out)
    if cleaned[:1] in _NOT_AT_HEAD:
        cleaned = _FILLER + cleaned
    return cleaned


def legalize_name(name):
    """文字列を Maya のノード名として受け付けられる形へ変換する。

    コロン ``:`` を名前空間の区切りとして残し、区切られた各区間(名前空間名と
    末尾のノード名)に同じ規則を当てる。

    - 各区間の前後の空白は取り除く。
    - ASCII 英字・数字・``_`` 以外の文字(途中の空白、記号、``|``、``.``、
      非ASCII文字など)は、連続している範囲ごとに1つの ``_`` へ置き換える。
    - 数字で始まる区間には先頭に ``_`` を足す(``"ns:1abc"`` は ``"ns:_1abc"``)。
    - 空になった区間は捨てる(``"a::b"`` は ``"a:b"``、``"ns:"`` は ``"ns"``)。
    - 先頭のコロンはルート名前空間からの指定とみなし、1つだけ残す。
    - 有効な区間が1つも残らない場合は ``"_"`` を返す。

    Args:
        name (str): 変換したい文字列。

    Returns:
        str: Maya のノード名として有効な文字列。

    Raises:
        TypeError: name が str でない場合。

    Examples:
        >>> legalize_name("  arm L.001 ")
        'arm_L_001'
        >>> legalize_name("rig:2nd joint")
        'rig:_2nd_joint'
    """
    if not isinstance(name, str):
        raise TypeError(
            f"name には str を指定してください(受け取った型: {type(name).__name__})"
        )
    text = name.strip()
    segments = []
    for part in text.split(_SEPARATOR):
        cleaned = _clean_segment(part)
        if cleaned:
            segments.append(cleaned)
    if not segments:
        return _FILLER
    joined = _SEPARATOR.join(segments)
    if text.startswith(_SEPARATOR):
        return _SEPARATOR + joined
    return joined
