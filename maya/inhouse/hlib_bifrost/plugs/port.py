"""Bifrost内部ポートの既定値と接続。"""

from __future__ import annotations

from dataclasses import dataclass
from ..nodes.node import Node
from maya import cmds


@dataclass(frozen=True)
class Port:
    """内部ポートの参照。MayaのDG Plugとは区別する。"""

    node: Node
    name: str

    @property
    def path(self):
        """str: 保持している内部接続パス。"""
        return self.node.path + "." + self.name

    def set_default(self, value):
        """既定値を設定する。複合型はVNN形式の文字列または文字列列で渡す。"""
        if isinstance(value, (tuple, list)):
            value = [str(item) for item in value]
        else:
            value = str(value).lower() if isinstance(value, bool) else str(value)
        cmds.vnnNode(
            self.node.graph.name(), self.node.path, setPortDefaultValues=(self.name, value)
        )

    def get_default(self):
        """VNNが返す既定値を照会する。"""
        return cmds.vnnNode(
            self.node.graph.name(), self.node.path, queryPortDefaultValues=self.name
        )

    def connect(self, target):
        """この出力から同じグラフ内の入力へ接続する。"""
        self._check_graph(target)
        cmds.vnnConnect(self.node.graph.name(), self.path, target.path)

    def disconnect(self, target):
        """指定した接続を切断する。"""
        self._check_graph(target)
        cmds.vnnConnect(self.node.graph.name(), self.path, target.path, disconnect=True)

    def _check_graph(self, target):
        """別グラフ間の誤った接続を拒否する。"""
        if not isinstance(target, Port) or self.node.graph.name() != target.node.graph.name():
            raise ValueError("Ports must belong to the same graph")
