# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""保存時のノード名を、読み込み先のシーンの名前へ変換する規則をまとめる。"""

from typing import Iterable



class NameMapping:
    """名前の対応表・文字列の置き換え・名前空間の入れ替えをまとめ、ノード名を変換する。

    3つを同時に指定した場合は次の順に当てはめる。

    1. ``nameMap``: 名前空間を除いた名前で引く。該当すれば置き換えた名前を使い、``replace`` は当てない。
    2. ``replace``: `` (旧, 新)`` の組を順に文字列置換する。
    3. ``namespaceMap``: 名前空間を入れ替える。キー ``""`` は名前空間の無いノードを表す。

    ``NameMapping()`` は名前を変えない。
    """
    def __init__(self, nameMap: dict[str, str] | None = ..., replace: Iterable[tuple[str, str]] | None = ..., namespaceMap: dict[str, str] | None = ...) -> None:
        """対応付けの規則を保持する。

        Args:
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表(``{"arm_L_jnt": "leftArm_jnt"}``)。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換(``[("_L_", "_R_")]``)。
            namespaceMap (dict[str, str] | None): 名前空間の対応(``{"chrA": "chrB"}``)。
                先頭の ``":"`` は無視する。入れ子の名前空間は、一致する最も長い親を入れ替える。

        Raises:
            TypeError: 各引数の型が不正な場合。
            ValueError: 置換の組が2要素でない、または置換元が空文字列の場合。
        """
        ...
    def __repr__(self) -> str:
        """指定した規則を含む表記を返す。

        Returns:
            str: ``NameMapping(nameMap=..., replace=..., namespaceMap=...)`` の形式。
        """
        ...
    def isIdentity(self) -> bool:
        """名前を変えない規則かを返す。

        Returns:
            bool: どの規則も指定していなければTrue。
        """
        ...
    def apply(self, name: str) -> str:
        """ノード名(DAGパスの1要素)を変換する。

        Args:
            name (str): ``"chrA:arm_L_jnt"`` のような名前空間付きの名前。``"|"`` を含めない。

        Returns:
            str: 変換後の名前。

        Raises:
            TypeError: nameが文字列でない場合。
        """
        ...
    def applyPath(self, path: str) -> str:
        """DAGパスの各要素を :meth:`apply` で変換する。

        Args:
            path (str): ``"|chrA:root|chrA:arm_L_jnt"`` のようなパス。DGノード名もそのまま渡せる。

        Returns:
            str: 変換後のパス。先頭の ``"|"`` は保つ。

        Raises:
            TypeError: pathが文字列でない場合。
        """
        ...
    def _map_namespace(self, namespace: str) -> str:
        """名前空間を ``namespaceMap`` で入れ替える。

        Args:
            namespace (str): 先頭の ``":"`` を除いた名前空間。ルートは空文字列。

        Returns:
            str: 入れ替えた名前空間。該当が無ければそのまま。
        """
        ...

def _strip(namespace: str) -> str:
    """名前空間の先頭と末尾の ``":"`` を除く。

    Args:
        namespace (str): 名前空間。

    Returns:
        str: ``":"`` を除いた名前空間。
    """
    ...

def _string_dict(value: dict[str, str] | None, name: str) -> dict[str, str]:
    """文字列から文字列への辞書を検証して複製する。

    Args:
        value (dict[str, str] | None): 検証する辞書。
        name (str): エラーメッセージに使う引数名。

    Returns:
        dict[str, str]: 新しい辞書。Noneは空の辞書。

    Raises:
        TypeError: 辞書でない、またはキー・値が文字列でない場合。
    """
    ...
