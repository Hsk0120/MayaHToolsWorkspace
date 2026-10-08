"""Containerの所属・公開操作とScalarGraphの生成先を検証する。"""

import unittest

import maya.cmds as cmds

from hlib.nodes import Container, Node
from hlib.common.scalarGraph import ScalarGraph


class ContainerTest(unittest.TestCase):
    """専用namespaceでMaya標準のcontainerを操作する。"""

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

    def test_publish_lifecycle(self):
        """公開名作成・Bind・編集・改名・解除とUndoを検証する。"""
        node = self.owner.createNode("multiplyDivide")
        self.assertEqual(self.owner.publishName("Gain"), "Gain")
        self.assertEqual(self.owner.getPublishedAttrs(), {"Gain": None})
        plug = self.owner.bindAttr("Gain", node.getPlug("input2X"))
        self.owner.getPublishedAttrs()["Gain"].set(3)
        self.assertEqual(plug.get(), 3)
        node.rename("renamedMultiply")
        self.assertEqual(self.owner.getPublishedAttrs()["Gain"], plug)
        with self.assertRaises(ValueError):
            self.owner.unpublishName("Gain")
        self.owner.unbindAttr("Gain")
        self.owner.unpublishName("Gain")
        self.assertFalse(self.owner.getPublishedAttrs())
        self.owner.publishAndBind("Input", node.getPlug("input1X"))
        cmds.undo()
        self.assertFalse(self.owner.getPublishedAttrs())

    def test_publish_failure(self):
        """外部ノードの公開を拒否し、作成途中の公開名を残さない。"""
        foreign = Node.create("multiplyDivide")
        with self.assertRaises(ValueError):
            self.owner.publishAndBind("External", foreign.getPlug("input1X"))
        self.assertFalse(self.owner.getPublishedAttrs())
        node = self.owner.createNode("multiplyDivide")
        self.owner.publishAndBind("Gain", node.getPlug("input2X"))
        with self.assertRaises(ValueError):
            self.owner.publishName("Gain")
        self.assertEqual(self.owner.getPublishedAttrs()["Gain"], node.getPlug("input2X"))

    def test_remove_and_delete(self):
        """所属解除・箱だけ解除・通常削除の違いを検証する。"""
        node = self.owner.createNode("multiplyDivide")
        self.owner.removeMembers(node)
        self.assertTrue(node.isValid())
        self.assertFalse(self.owner.getMembers())
        self.owner.addMembers(node)
        self.owner.publishAndBind("Gain", node.getPlug("input2X"))
        self.owner.removeContainer()
        self.assertTrue(node.isValid())
        cmds.undo()
        restored = Container(cmds.container(query=True, findContainer=node.getFullName()))
        self.assertIn(node, restored.getMembers())
        self.assertEqual(restored.getPublishedAttrs()["Gain"], node.getPlug("input2X"))
        restored.delete()
        self.assertFalse(node.isValid())

    def test_nested_remove(self):
        """ネストからの解除は親へ移り、forceでは全所属を外す。"""
        inner = Container.create(name="inner")
        self.owner.addMembers(inner)
        node = inner.createNode("multiplyDivide")
        inner.removeMembers(node)
        self.assertEqual(cmds.container(query=True, findContainer=node.getFullName()), self.owner.getFullName())
        self.owner.removeMembers(node)
        inner.addMembers(node)
        inner.removeMembers(node, force=True)
        self.assertFalse(cmds.container(query=True, findContainer=node.getFullName()))

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
        from hrig.setups.softIK import SoftIK
        owner = Node(SoftIK.create("soft", 10))
        owner.getPlug("distance").set(9)
        owner.getPlug("softness").set(2)
        self.assertAlmostEqual(owner.getPlug("ratio").get(), SoftIK.distance(9, 10, 2) / 9, places=5)


if __name__ == "__main__":
    unittest.main()
