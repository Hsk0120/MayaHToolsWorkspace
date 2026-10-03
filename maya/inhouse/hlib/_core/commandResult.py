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
        from ..plugs.plug import Plug as _InputPlug
        from ..nodes.node import Node

        return _InputPlug._resolve_input(name) if "." in name else Node(name)

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
        from ..nodes.node import Node as _InputNode

        result = dict(kwargs)
        for key in keys:
            if key in result:
                result[key] = _InputNode._input_name(result[key])
        return result
