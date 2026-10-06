"""Bifrost内部ポートの既定値と接続。"""

from __future__ import annotations

from dataclasses import dataclass

import maya.cmds as cmds

from ..nodes.node import Node


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
        """VNNポートの既定値を設定する。

        Args:
            value (object): VNN形式へ文字列化する値。複合型は文字列または文字列列。
                boolは小文字のtrue/falseへ変換する。
        """
        if isinstance(value, (tuple, list)):
            value = [str(item) for item in value]
        else:
            value = str(value).lower() if isinstance(value, bool) else str(value)
        cmds.vnnNode(
            self.node.graph.getName(), self.node.path, setPortDefaultValues=(self.name, value)
        )

    def get_default(self):
        """VNNが返す既定値を照会する。"""
        return cmds.vnnNode(
            self.node.graph.getName(), self.node.path, queryPortDefaultValues=self.name
        )

    def connect(self, target):
        """この出力から同じグラフ内の入力へ接続する。

        Args:
            target (Port): 接続先の入力ポート。

        Raises:
            ValueError: Port以外、または異なるグラフのポートを指定した場合。
        """
        self._check_graph(target)
        cmds.vnnConnect(self.node.graph.getName(), self.path, target.path)

    def disconnect(self, target):
        """このポートと指定ポートの接続を切断する。

        Args:
            target (Port): 切断する接続先。

        Raises:
            ValueError: Port以外、または異なるグラフのポートを指定した場合。
        """
        self._check_graph(target)
        cmds.vnnConnect(self.node.graph.getName(), self.path, target.path, disconnect=True)

    def _check_graph(self, target):
        """別グラフ間の誤った接続を拒否する。

        Args:
            target: 接続・変換・探索の元または先となる対象。
        """
        if not isinstance(target, Port) or self.node.graph.getName() != target.node.graph.getName():
            raise ValueError("Ports must belong to the same graph")
