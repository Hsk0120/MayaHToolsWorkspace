"""Node wrapper type registry for Hlib."""


class NodeRegistry:
    """Maya ノード型と Hlib ラッパークラスの対応を管理する。

    Args:
        fallback_class (type): 未登録の Maya ノード型に使用するラッパークラス。
    """

    def __init__(self, fallback_class):
        """フォールバッククラスと空のノード型対応表を初期化する。"""
        self._fallback_class = fallback_class
        self._classes = {}

    def register(self, node_type, wrapper_class):
        """Maya ノード型へラッパークラスを登録する。

        Args:
            node_type (str): Maya の nodeType 名。
            wrapper_class (type): ノードをラップする Hlib クラス。

        Raises:
            ValueError: node_type が空文字列または文字列以外の場合。
            TypeError: wrapper_class がクラスでない場合。
        """
        if not isinstance(node_type, str) or not node_type:
            raise ValueError("node_type must be a non-empty string")
        if not isinstance(wrapper_class, type):
            raise TypeError("wrapper_class must be a class")
        self._classes[node_type] = wrapper_class

    def wrapper_class(self, node_type):
        """ノード型に対応するクラス、またはフォールバッククラスを返す。

        Args:
            node_type (str): Maya の nodeType 名。

        Returns:
            type: 登録済みまたはフォールバックのラッパークラス。
        """
        return self._classes.get(node_type, self._fallback_class)

    def get(self, node_type):
        """ノード型に対応するラッパークラスを返す。

        Args:
            node_type (str): Maya の nodeType 名。

        Returns:
            type: 登録済みまたはフォールバックのラッパークラス。
        """
        return self.wrapper_class(node_type)

    def resolve(self, node, node_type=None):
        """入力ノードに対応する最適な Hlib ラッパーを生成する。

        Args:
            node (str | object): ノード名、または wrapper_class が受け入れる入力値。
            node_type (str | None): 明示する Maya nodeType。省略時は node が文字列の
                場合に Maya から取得する。

        Returns:
            Node: 解決したラッパーインスタンス。

        Raises:
            TypeError: node_type を推論できない入力を指定した場合。
        """
        if node_type is None:
            if not isinstance(node, str):
                raise TypeError("node_type is required unless node is a Maya node name")
            import maya.cmds as cmds

            node_type = cmds.nodeType(node)
        return self.wrap(node, node_type)

    def wrap(self, node, node_type):
        """解決済みのノード型を使ってラッパーを生成する。

        Args:
            node (object): ラッパークラスへ渡すノード入力。
            node_type (str): 解決済みの Maya nodeType 名。

        Returns:
            Node: 対応する Hlib ラッパー。
        """
        return self.wrapper_class(node_type)(node)


__all__ = ["NodeRegistry"]