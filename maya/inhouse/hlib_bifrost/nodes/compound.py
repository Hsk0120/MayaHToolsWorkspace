"""Bifrost Compoundの構成と境界ポート。"""

from __future__ import annotations

from dataclasses import dataclass
from maya import cmds
from .node import Node


@dataclass(frozen=True)
class Compound(Node):
    """内部ノードの追加とインターフェース定義を行うCompound参照。"""

    def nodes(self):
        """tuple[str]: 直下のノード名を照会する。"""
        return tuple(cmds.vnnCompound(self.graph.name(), self.path, ls=True) or ())

    def child(self, name):
        """Node: 直下のノードを参照する。"""
        return Node(self.graph, self.path.rstrip("/") + "/" + self.identifier(name))

    def add_node(self, type_name):
        """Node: 登録されたCompound型を追加する。"""
        result = cmds.vnnCompound(self.graph.name(), self.path, addNode=type_name)
        return self.child(result[0])

    def create_compound(self, name):
        """Compound: 未使用の名前で空Compoundを作る。"""
        name = self.identifier(name)
        if name in self.nodes():
            raise ValueError("Node already exists: " + name)
        cmds.vnnCompound(self.graph.name(), self.path, create=name)
        return Compound(self.graph, self.child(name).path)

    def add_port(self, name, data_type, output=False):
        """Port: Compound境界にポートを追加する。内部接続はio_portを使う。"""
        name = self.identifier(name)
        if name in [p.rsplit(".", 1)[-1] for p in self.ports()]:
            raise ValueError("Port already exists: " + name)
        flag = "createOutputPort" if output else "createInputPort"
        cmds.vnnCompound(self.graph.name(), self.path, **{flag: (name, data_type)})
        return self.port(name)

    def io_port(self, name, output=False):
        """Port: 既定input/outputノードの内部接続用ポートを参照する。"""
        return self.child("output" if output else "input").port(name)

    def remove_node(self, name):
        """指定した直下の内部ノードを削除する。"""
        cmds.vnnCompound(self.graph.name(), self.path, removeNode=self.identifier(name))
