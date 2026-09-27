"""Maya DGコンテナとBifrost内部ノードを区別したVNN操作。"""

import re
from dataclasses import dataclass
from maya import cmds


def _identifier(value):
    """ポート・内部ノード用の単一識別子を検証する。"""
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value):
        raise ValueError('Expected a simple identifier: {!r}'.format(value))
    return value


class Graph:
    """DGノードをhlib参照で保持し、名前変更に追従するグラフ。"""

    def __init__(self, node):
        """既存のbifrostGraphShapeを取得する。

        Args:
            node: hlibで解決可能なDGノード。
        """
        from hlib.nodes import Node as MayaNode
        self.node = MayaNode(node)
        if self.node.type() != 'bifrostGraphShape':
            raise TypeError('Expected bifrostGraphShape')

    @classmethod
    def create(cls, name='bifrostGraphShape'):
        """必要なプラグインをロードしてグラフを生成する。"""
        from . import ensure_available
        ensure_available()
        parent = cmds.createNode('transform',name=name+'Transform',skipSelect=True)
        try:
            return cls(cmds.createNode('bifrostGraphShape', name=name,
                                       parent=parent, skipSelect=True))
        except Exception:
            cmds.delete(parent)
            raise

    @property
    def root(self):
        """Compound: ルートへの参照。照会やシーン変更は行わない。"""
        return Compound(self, '/')

    def name(self):
        """str: 現在のDG完全名を取得する。"""
        return self.node.full_name()


@dataclass(frozen=True)
class Node:
    """グラフ内パスを保持する参照。内部ノード改名後は再取得する。"""

    graph: Graph
    path: str

    def ports(self):
        """tuple[str]: VNNが返すポート名を照会する。"""
        return tuple(cmds.vnnNode(self.graph.name(), self.path, listPorts=True) or ())

    def port(self, name):
        """Port: 指定ポートを参照する。存在確認や作成は行わない。"""
        return Port(self, _identifier(name))

    def add_port(self, name, data_type, output=False):
        """内部ノードへ動的ポートを追加する。

        Args:
            name (str): 未使用のポート名。
            data_type (str): Bifrost型名。
            output (bool): 出力ポートならTrue。
        Returns:
            Port: 追加したポート。
        """
        name = _identifier(name)
        if name in [p.rsplit('.', 1)[-1] for p in self.ports()]:
            raise ValueError('Port already exists: ' + name)
        flag = 'createOutputPort' if output else 'createInputPort'
        cmds.vnnNode(self.graph.name(), self.path, **{flag: (name, data_type)})
        return self.port(name)


@dataclass(frozen=True)
class Compound(Node):
    """内部ノードの追加とインターフェース定義を行うCompound参照。"""

    def nodes(self):
        """tuple[str]: 直下のノード名を照会する。"""
        return tuple(cmds.vnnCompound(self.graph.name(), self.path, listNodes=True) or ())

    def child(self, name):
        """Node: 直下のノードを参照する。"""
        return Node(self.graph, self.path.rstrip('/') + '/' + _identifier(name))

    def add_node(self, type_name):
        """Node: 登録されたCompound型を追加する。"""
        result = cmds.vnnCompound(self.graph.name(), self.path, addNode=type_name)
        return self.child(result[0])

    def create_compound(self, name):
        """Compound: 未使用の名前で空Compoundを作る。"""
        name = _identifier(name)
        if name in self.nodes():
            raise ValueError('Node already exists: ' + name)
        cmds.vnnCompound(self.graph.name(), self.path, create=name)
        return Compound(self.graph, self.child(name).path)

    def add_port(self, name, data_type, output=False):
        """Port: Compound境界にポートを追加する。内部接続はio_portを使う。"""
        name = _identifier(name)
        if name in [p.rsplit('.', 1)[-1] for p in self.ports()]:
            raise ValueError('Port already exists: ' + name)
        flag = 'createOutputPort' if output else 'createInputPort'
        cmds.vnnCompound(self.graph.name(), self.path, **{flag: (name, data_type)})
        return self.port(name)

    def io_port(self, name, output=False):
        """Port: 既定input/outputノードの内部接続用ポートを参照する。"""
        return self.child('output' if output else 'input').port(name)

    def remove_node(self, name):
        """指定した直下の内部ノードを削除する。"""
        cmds.vnnCompound(self.graph.name(), self.path, removeNode=_identifier(name))


@dataclass(frozen=True)
class Port:
    """内部ポートの参照。MayaのDG Plugとは区別する。"""

    node: Node
    name: str

    @property
    def path(self):
        """str: 保持している内部接続パス。"""
        return self.node.path + '.' + self.name

    def set_default(self, value):
        """既定値を設定する。複合型はVNN形式の文字列または文字列列で渡す。"""
        if isinstance(value, (tuple, list)):
            value = [str(item) for item in value]
        else:
            value = str(value).lower() if isinstance(value, bool) else str(value)
        cmds.vnnNode(self.node.graph.name(), self.node.path,
                     setPortDefaultValues=(self.name, value))

    def get_default(self):
        """VNNが返す既定値を照会する。"""
        return cmds.vnnNode(self.node.graph.name(), self.node.path,
                            queryPortDefaultValues=self.name)

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
            raise ValueError('Ports must belong to the same graph')
