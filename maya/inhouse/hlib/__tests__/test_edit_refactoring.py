"""内部処理の分割後も、利用側overrideと複数形の返却契約を維持する。"""

import sys
import unittest
import uuid
from unittest.mock import patch

import maya.cmds as cmds

import hlib

hlib.reload()


class EditRefactoringTest(unittest.TestCase):
    """専用名前空間のノードで公開入口の契約を確認する。"""

    def setUp(self):
        """他のシーン内容から独立した対象を作る。"""
        self.namespace = "hlibEditRefactor_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        self.names = [cmds.createNode("transform", name=self.namespace + ":node" + str(i))
                      for i in range(2)]

    def tearDown(self):
        """このテストが作ったノードだけを削除する。"""
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def test_compound_creation_reenters_user_override_in_child_order(self):
        """子作成でも公開addAttrのoverrideとgetPlug=False指定を保つ。"""
        calls = []

        original = hlib.nodes.Node.addAttr

        def record_add_attr(node, *args, **kwargs):
            """呼出時に差し替えた公開入口でも子作成の入力を受け取る。"""
            calls.append((args, dict(kwargs)))
            return original(node, *args, **kwargs)

        node = hlib.nodes.Transform(self.names[0])
        with patch.object(hlib.nodes.Node, "addAttr", record_add_attr):
            plug = node.addAttr("customVector", "double3", childNames=["redValue", "greenValue", "blueValue"],
                                childShortNames=["rv", "gv", "bv"], defaultValue=(1, 2, 3), keyable=True)
        self.assertEqual([row[0][0] for row in calls],
                         ["customVector", "redValue", "greenValue", "blueValue"])
        self.assertTrue(all(row[1]["getPlug"] is False for row in calls[1:]))
        self.assertEqual([row[1]["shortName"] for row in calls[1:]], ["rv", "gv", "bv"])
        self.assertEqual(tuple(plug.get()), (1, 2, 3))
        cmds.undo()
        self.assertFalse(node.hasAttr("customVector"))

    def test_base_collection_keeps_named_calculation_policy_and_mixed_results(self):
        """Transform以外の同名setterにも従来のget結果収集を適用する。"""
        calls = []

        class NamedNode(hlib.nodes.Node):
            """シーン更新を行わず、返却方針だけ確認する利用側Node。"""

            def setTranslate(self, value, get=False, *, fast=False):
                """getは計算値、それ以外は自身を返す。"""
                calls.append((self.getName(), value, get, fast))
                return tuple(value) if get else self

        class NamedNodes(hlib.nodes.Nodes):
            """基底のcallEachを利用する明示登録済みコレクション。"""

            item_class = NamedNode
            _bulk_methods = dict(hlib.nodes.Nodes._bulk_methods, setTranslate=NamedNode.setTranslate)
            _bulk_returns = dict(hlib.nodes.Nodes._bulk_returns, setTranslate="self")
            _bulk_undo = False

        with patch.dict(hlib.nodes.Node._registry._classes, {"transform": NamedNode}):
            nodes = NamedNodes(self.names)
        result = nodes.callEach("setTranslate", [((1, 2, 3), True), ((4, 5, 6),)],
                                [{"fast": True}, {"get": False}])
        self.assertEqual(result[0], (1, 2, 3))
        self.assertIs(result[1], nodes[1])
        self.assertEqual([(row[2], row[3]) for row in calls], [(True, True), (False, False)])
        self.assertIs(nodes.callEach("setTranslate", [((0, 0, 0),)] * 2), nodes)
        empty = NamedNodes()
        self.assertIs(empty.callEach("setTranslate", []), empty)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
