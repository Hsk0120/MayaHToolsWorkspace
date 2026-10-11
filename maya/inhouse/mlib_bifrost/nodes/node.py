"""Bifrost内部ノードの参照。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import maya.cmds as cmds

if TYPE_CHECKING:
    from .graph import Graph


@dataclass(frozen=True)
class Node:
    """グラフ内パスを保持する参照。内部ノード改名後は再取得する。"""

    graph: Graph
    path: str

    @staticmethod
    def identifier(value):
        """VNN内部パスの単一識別子を検証する。

        Args:
            value (str): ポートまたはノード名。

        Returns:
            str: 検証した識別子。
        """
        import re

        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError("Expected a simple identifier: {!r}".format(value))
        return value

    def ports(self):
        """VNNが返すポート名を照会する。

        Returns:
            tuple[str]: VNNが返すポート名を照会する。
        """
        return tuple(cmds.vnnNode(self.graph.getName(), self.path, listPorts=True) or ())

    def port(self, name):
        """指定ポートを参照する。存在確認や作成は行わない。

        Args:
            name (str): 内部ノードのポート名。

        Returns:
            Port: 指定名のポート参照。
        """
        from ..plugs.port import Port

        return Port(self, self.identifier(name))

    def add_port(self, name, dataType, output=False):
        """内部ノードへ動的ポートを追加する。

        Args:
            name (str): 未使用のポート名。
            dataType (str): Bifrost型名。
            output (bool): 出力ポートならTrue。
        Returns:
            Port: 追加したポート。
        """
        name, flag = self._port_creation(name, output)
        cmds.vnnNode(self.graph.getName(), self.path, **{flag: (name, dataType)})
        return self.port(name)

    def _port_creation(self, name, output):
        """追加ポートの名前と方向を検証する。VNNへの書込みは行わない。

        Args:
            name (str): 未使用のポート名。
            output (bool): 出力ポートならTrue。

        Returns:
            tuple[str, str]: 検証した名前とnative VNNの作成フラグ。

        Raises:
            ValueError: 名前が不正、または同名ポートが存在する場合。
        """
        name = self.identifier(name)
        if name in [p.rsplit(".", 1)[-1] for p in self.ports()]:
            raise ValueError("Port already exists: " + name)
        return name, "createOutputPort" if output else "createInputPort"
