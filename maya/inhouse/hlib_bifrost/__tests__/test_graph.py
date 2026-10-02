"""Bifrostの入出力・演算・Undoを実機で検証する。"""

import unittest
from maya import cmds
from hlib_bifrost.nodes import Graph
from hlib_bifrost.environment import Bifrost


class GraphTest(unittest.TestCase):
    """隔離した空シーンで実行するグラフ操作テスト。"""

    @classmethod
    def setUpClass(cls):
        """プラグインを先にロードする。"""
        Bifrost.ensure_available()

    def setUp(self):
        """グラフを作成する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        self.graph = Graph.create()

    def test_package_layout(self):
        """実装をhlibと同じ責務別パッケージに一つずつ配置する。"""
        import hlib_bifrost as package
        from pathlib import Path

        for folder, names in (
            ("nodes", ("Graph", "Node", "Compound")),
            ("plugs", ("Port",)),
            ("environment", ("Bifrost",)),
            ("utils", ("MathBuilder",)),
        ):
            for name in names:
                cls = getattr(getattr(package, folder), name)
                self.assertTrue(cls.__module__.startswith("hlib_bifrost." + folder + "."))
        for name in ("graph", "node", "compound", "port", "mathBuilder", "softIK"):
            self.assertFalse((Path(package.__file__).parent / (name + ".py")).exists())
        self.assertTrue(Bifrost.is_available())

    def test_value_connection_and_undo(self):
        """乗算の実評価とUndoでの既定値復元を確認する。"""
        root = self.graph.root
        root.add_port("result", "float", output=True)
        node = root.add_node("BifrostGraph,Core::Math,multiply")
        a = node.add_port("a", "float")
        b = node.add_port("b", "float")
        a.set_default(2)
        b.set_default(3)
        node.port("output").connect(root.io_port("result", output=True))
        self.assertEqual(cmds.getAttr(self.graph.name() + ".result"), 6)
        a.set_default(5)
        self.assertEqual(cmds.getAttr(self.graph.name() + ".result"), 15)
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.graph.name() + ".result"), 6)
        with self.assertRaises(ValueError):
            node.add_port("a", "float")

    def test_cross_graph_rejected(self):
        """別グラフのポートを誤接続できない。"""
        other = Graph.create()
        with self.assertRaises(ValueError):
            self.graph.root.io_port("a").connect(other.root.io_port("a"))

    def test_math_builder_and_ownership(self):
        """基本演算、clamp、名前変更と親削除を確認する。"""
        from hlib_bifrost.utils import MathBuilder

        root = self.graph.root
        root.add_port("result", "float", output=True)
        builder = MathBuilder(root)
        total = builder.operation("add", (2, 3))
        builder.clamp(total, 0, 4).connect(root.io_port("result", output=True))
        self.assertAlmostEqual(cmds.getAttr(self.graph.name() + ".result"), 4)
        self.graph.parent().rename("renamedParent")
        self.assertIn("renamedParent", self.graph.name())
        self.graph.delete()
        self.assertFalse(cmds.objExists("renamedParent"))
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(self.graph.name() + ".result"), 4)

    def test_soft_ik_library(self):
        """Bifrost版をhlibの参照値と比較し、新配置のAPIで構築する。"""
        from hrig.setups.bifrostSoftIK import SoftIK
        from hrig.setups import SoftIK as Reference

        graph = SoftIK.create("soft", 8)
        for softness in (0, 1, 4):
            for distance in (2, 7, 8, 12):
                cmds.setAttr(graph.name() + ".distance", distance)
                cmds.setAttr(graph.name() + ".softness", softness)
                self.assertAlmostEqual(
                    cmds.getAttr(graph.name() + ".ratio") * distance,
                    Reference.distance(distance, 8, softness),
                    places=4,
                )


if __name__ == "__main__":
    unittest.main()
