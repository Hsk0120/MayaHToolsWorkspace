"""Node/文字列が混在する入力を正規化する共通ヘルパー。"""


def to_name(value):
    """Node または文字列から Maya の完全修飾名を取得する。

    渡された文字列自体は解決しない（Maya へ問い合わせない）。解決済みの
    Node が必要な場合は to_node を使う。

    Args:
        value (Node | str): 変換対象。

    Returns:
        str: value が Node なら full_name、str ならそのまま。

    Raises:
        TypeError: value が Node/str 以外の場合。
        ValueError: 変換結果が空文字列の場合。
    """
    from ..nodes.node import Node

    name = value.full_name if isinstance(value, Node) else value
    if not isinstance(name, str):
        raise TypeError("Node または文字列を指定してください")
    if not name:
        raise ValueError("空でない名前を指定してください")
    return name


def to_names(values):
    """Node/文字列が混在するイテラブルを名前のリストへ正規化する。

    単一の Node/str が渡された場合も1要素のリストとして扱う。

    Args:
        values (Node | str | Iterable[Node | str]): 変換対象。

    Returns:
        list[str]: 正規化した名前のリスト。

    Raises:
        TypeError: いずれかの要素が Node/str 以外の場合。
        ValueError: いずれかの要素が空文字列の場合。
    """
    from ..nodes.node import Node

    if isinstance(values, (Node, str)):
        values = [values]
    return [to_name(value) for value in values]


def to_node(value):
    """Node または文字列から Node インスタンスを取得する。

    Args:
        value (Node | str): 変換対象。

    Returns:
        Node: value が Node ならそのまま、str なら Node(value)（Maya へ解決する）。

    Raises:
        TypeError: value が Node/str 以外の場合。
    """
    from ..nodes.node import Node

    if isinstance(value, Node):
        return value
    if isinstance(value, str):
        return Node(value)
    raise TypeError("Node または文字列を指定してください")
