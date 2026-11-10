"""保存時のノード名を、読み込み先のシーンの名前へ変換する規則をまとめる。"""


class NameMapping:
    """名前の対応表・文字列の置き換え・名前空間の入れ替えをまとめ、ノード名を変換する。

    3つを同時に指定した場合は次の順に当てはめる。

    1. ``nameMap``: 名前空間を除いた名前で引く。該当すれば置き換えた名前を使い、``replace`` は当てない。
    2. ``replace``: `` (旧, 新)`` の組を順に文字列置換する。
    3. ``namespaceMap``: 名前空間を入れ替える。キー ``""`` は名前空間の無いノードを表す。

    ``NameMapping()`` は名前を変えない。
    """

    def __init__(self, nameMap=None, replace=None, namespaceMap=None):
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
        self._name_map = _string_dict(nameMap, "nameMap")
        self._namespace_map = {_strip(key): _strip(value)
                               for key, value in _string_dict(namespaceMap, "namespaceMap").items()}
        pairs = []
        if replace is not None:
            if isinstance(replace, (str, bytes)):
                raise TypeError("replace must be a sequence of (old, new) pairs")
            for pair in replace:
                if isinstance(pair, (str, bytes)) or len(pair) != 2:
                    raise ValueError("replace must contain (old, new) pairs")
                old, new = pair
                if not isinstance(old, str) or not isinstance(new, str):
                    raise TypeError("replace pairs must be strings")
                if not old:
                    raise ValueError("replace old text must not be empty")
                pairs.append((old, new))
        self._replace = tuple(pairs)

    def __repr__(self):
        """指定した規則を含む表記を返す。

        Returns:
            str: ``NameMapping(nameMap=..., replace=..., namespaceMap=...)`` の形式。
        """
        return (f"NameMapping(nameMap={self._name_map!r}, replace={list(self._replace)!r}, "
                f"namespaceMap={self._namespace_map!r})")

    def isIdentity(self):
        """名前を変えない規則かを返す。

        Returns:
            bool: どの規則も指定していなければTrue。
        """
        return not (self._name_map or self._replace or self._namespace_map)

    def apply(self, name):
        """ノード名(DAGパスの1要素)を変換する。

        Args:
            name (str): ``"chrA:arm_L_jnt"`` のような名前空間付きの名前。``"|"`` を含めない。

        Returns:
            str: 変換後の名前。

        Raises:
            TypeError: nameが文字列でない場合。
        """
        if not isinstance(name, str):
            raise TypeError("name must be a string")
        namespace, _separator, short = name.rpartition(":")
        namespace = _strip(namespace)
        if short in self._name_map:
            short = self._name_map[short]
        else:
            for old, new in self._replace:
                short = short.replace(old, new)
        namespace = self._map_namespace(namespace)
        return f"{namespace}:{short}" if namespace else short

    def applyPath(self, path):
        """DAGパスの各要素を :meth:`apply` で変換する。

        Args:
            path (str): ``"|chrA:root|chrA:arm_L_jnt"`` のようなパス。DGノード名もそのまま渡せる。

        Returns:
            str: 変換後のパス。先頭の ``"|"`` は保つ。
        """
        if not isinstance(path, str):
            raise TypeError("path must be a string")
        return "|".join(self.apply(part) if part else part for part in path.split("|"))

    def _map_namespace(self, namespace):
        """名前空間を ``namespaceMap`` で入れ替える。

        Args:
            namespace (str): 先頭の ``":"`` を除いた名前空間。ルートは空文字列。

        Returns:
            str: 入れ替えた名前空間。該当が無ければそのまま。
        """
        if namespace in self._namespace_map:
            return self._namespace_map[namespace]
        parts = namespace.split(":") if namespace else []
        for size in range(len(parts) - 1, 0, -1):
            parent = ":".join(parts[:size])
            if parent in self._namespace_map:
                mapped = self._namespace_map[parent]
                rest = ":".join(parts[size:])
                return f"{mapped}:{rest}" if mapped else rest
        return namespace


def _strip(namespace):
    """名前空間の先頭と末尾の ``":"`` を除く。

    Args:
        namespace (str): 名前空間。

    Returns:
        str: ``":"`` を除いた名前空間。
    """
    return namespace.strip(":")


def _string_dict(value, name):
    """文字列から文字列への辞書を検証して複製する。

    Args:
        value (dict[str, str] | None): 検証する辞書。
        name (str): エラーメッセージに使う引数名。

    Returns:
        dict[str, str]: 新しい辞書。Noneは空の辞書。

    Raises:
        TypeError: 辞書でない、またはキー・値が文字列でない場合。
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be a dict")
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise TypeError(f"{name} keys and values must be strings")
    return dict(value)
