"""Containerの所属・公開操作とScalarGraphの生成先を検証する。"""

import unittest

import maya.cmds as cmds

from mlib.nodes import Container, Node
from mlib.common.scalarGraph import ScalarGraph


from mlrig.setups.softIK import SoftIK

class ContainerSoftIkTest(unittest.TestCase):
    def setUp(self):
        """専用namespaceと空containerを作る。"""
        self.previous = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.ns = cmds.namespace(add="containerApiTest")
        cmds.namespace(set=self.ns)
        self.owner = Container.create()

    def tearDown(self):
        """テストノードを削除する。"""
        # Mayaのnamespace一括削除へ公開済みcontainerを渡さず、先に標準削除する。
        containers = cmds.ls(self.ns + ":*", type="container") or []
        if containers:
            cmds.delete(containers)
        cmds.namespace(set=self.previous)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_factory_and_soft_ik(self):
        """両生成先で同じ計算結果になり、既存SoftIKも構築できる。"""
        created = []

        def create_node(kind, name=None):
            """生成物をリストに記録する。"""
            node = Node.create(kind, name=name)
            created.append(node)
            return node

        for graph in (ScalarGraph(self.owner), ScalarGraph(create_node=create_node)):
            value = graph.sum("sum", 2, 3)
            result = graph.multiply("mul", value, 4)
            self.assertEqual(graph.condition("choose", result, 10, result, 0).get(), 20)
        self.assertEqual(len(created), 3)
        from mlrig.setups.softIK import SoftIK
        owner = Node(SoftIK.create("soft", 10))
        owner.getPlug("distance").set(9)
        owner.getPlug("softness").set(2)
        self.assertAlmostEqual(owner.getPlug("ratio").get(), SoftIK.distance(9, 10, 2) / 9, places=5)

if __name__ == "__main__":
    unittest.main()
