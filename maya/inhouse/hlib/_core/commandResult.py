"""Mayaコマンドの名前戻り値を公開hlib参照へ変換する。"""


class CommandResult:
    """名前を返すコマンドの結果と入力フラグを型付けする。"""

    @staticmethod
    def reference(name):
        """ノード名またはアトリビュート名をNode/Plugへ解決する。

        Args:
            name (str): 一意なノード・アトリビュート名。コンポーネントは対象外。
        Returns:
            Node | Plug: 改名に追従する参照。
        """
        from .._core.coerce import to_plug
        from ..nodes.node import Node

        return to_plug(name) if "." in name else Node(name)

    @classmethod
    def references(cls, names):
        """名前列を型付き参照へ変換する。

        Args:
            names (Sequence[str] | None): Mayaの結果。
        Returns:
            list[Node | Plug]: 未検出時は空リスト。
        """
        return [cls.reference(name) for name in (names or [])]

    @staticmethod
    def node_flags(kwargs, keys):
        """ノードを受けるフラグだけを一意な名前へ変換する。

        Args:
            kwargs (dict): フラグ辞書。元の辞書は変更しない。
            keys (Sequence[str]): ノード指定フラグの長名。
        Returns:
            dict: 変換済みコピー。
        """
        from .._core.coerce import to_node_name

        result = dict(kwargs)
        for key in keys:
            if key in result:
                result[key] = to_node_name(result[key])
        return result
