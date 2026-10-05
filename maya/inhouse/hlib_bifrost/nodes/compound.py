"""Bifrost Compoundの構成と境界ポート。"""

from __future__ import annotations

from dataclasses import dataclass

import maya.cmds as cmds

from .node import Node


@dataclass(frozen=True)
class Compound(Node):
    """内部ノードの追加とインターフェース定義を行うCompound参照。"""

    def nodes(self):
        """直下のノード名を照会する。

        Returns:
            tuple[str]: 直下のノード名を照会する。
        """
        return tuple(cmds.vnnCompound(self.graph.name(), self.path, ls=True) or ())

    def child(self, name):
        """直下のノードを参照する。

        Args:
            name (str): 直下のノード名。パス区切りは含めない。

        Returns:
            Node: 内部パスの参照。ノードの存在確認や作成は行わない。
        """
        return Node(self.graph, self.path.rstrip("/") + "/" + self.identifier(name))

    def add_node(self, type_name):
        """登録されたCompound型を追加する。

        Args:
            type_name (str): VNNに登録されたCompound型名。

        Returns:
            Node: 作成された内部ノード。
        """
        result = cmds.vnnCompound(self.graph.name(), self.path, addNode=type_name)
        return self.child(result[0])

    def create_compound(self, name):
        """未使用の名前で空Compoundを作る。

        Args:
            name (str): 直下で未使用のCompound名。

        Returns:
            Compound: 作成されたCompoundへの参照。

        Raises:
            ValueError: 名前が不正、または同名ノードが存在する場合。
        """
        name = self.identifier(name)
        if name in self.nodes():
            raise ValueError("Node already exists: " + name)
        cmds.vnnCompound(self.graph.name(), self.path, create=name)
        return Compound(self.graph, self.child(name).path)

    def add_port(self, name, dataType, output=False):
        """Compound境界にポートを追加する。内部接続はio_portを使う。

        Args:
            name (str): 未使用のポート名。
            dataType (str): Bifrostの型名。
            output (bool): Trueは出力、Falseは入力ポート。

        Returns:
            Port: 追加した境界ポートへの参照。

        Raises:
            ValueError: 名前が不正、または同名ポートが存在する場合。
        """
        name = self.identifier(name)
        if name in [p.rsplit(".", 1)[-1] for p in self.ports()]:
            raise ValueError("Port already exists: " + name)
        flag = "createOutputPort" if output else "createInputPort"
        cmds.vnnCompound(self.graph.name(), self.path, **{flag: (name, dataType)})
        return self.port(name)

    def io_port(self, name, output=False):
        """既定input/outputノードの内部接続用ポートを参照する。

        Args:
            name (str): 境界に定義されたポート名。
            output (bool): Trueはoutputノード、Falseはinputノードを参照する。

        Returns:
            Port: Compound内部から接続するためのポート参照。
        """
        return self.child("output" if output else "input").port(name)

    def remove_node(self, name):
        """指定した直下の内部ノードを削除する。

        Args:
            name (str): 削除する内部ノード名。
        """
        cmds.vnnCompound(self.graph.name(), self.path, removeNode=self.identifier(name))
