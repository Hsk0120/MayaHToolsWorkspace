"""Bifrostの入出力・演算・Undoを実機で検証する。"""

import unittest
from maya import cmds
from hlib_bifrost import Graph, ensure_available


class GraphTest(unittest.TestCase):
    """隔離した空シーンで実行するグラフ操作テスト。"""

    @classmethod
    def setUpClass(cls):
        """プラグインを先にロードする。"""
        ensure_available()

    def setUp(self):
        """グラフを作成する。"""
        cmds.file(new=True,force=True)
        cmds.undoInfo(state=True)
        self.graph=Graph.create()

    def test_value_connection_and_undo(self):
        """乗算の実評価とUndoでの既定値復元を確認する。"""
        root=self.graph.root
        root.add_port('result','float',output=True)
        node=root.add_node('BifrostGraph,Core::Math,multiply')
        a=node.add_port('a','float'); b=node.add_port('b','float')
        a.set_default(2);b.set_default(3)
        node.port('output').connect(root.io_port('result',output=True))
        self.assertEqual(cmds.getAttr(self.graph.name()+'.result'),6)
        a.set_default(5)
        self.assertEqual(cmds.getAttr(self.graph.name()+'.result'),15)
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.graph.name()+'.result'),6)
        with self.assertRaises(ValueError):
            node.add_port('a','float')

    def test_cross_graph_rejected(self):
        """別グラフのポートを誤接続できない。"""
        other=Graph.create()
        with self.assertRaises(ValueError):
            self.graph.root.io_port('a').connect(other.root.io_port('a'))


if __name__=='__main__':
    unittest.main()
