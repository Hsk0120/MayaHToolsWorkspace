"""内部処理の分割後も、利用側overrideの契約を維持する。"""

import sys
import unittest
import uuid
from unittest.mock import patch

import maya.cmds as cmds

import mlib

mlib.reload()


class EditRefactoringTest(unittest.TestCase):
    """専用名前空間のノードで公開入口の契約を確認する。"""

    def setUp(self):
        """他のシーン内容から独立した対象を作る。"""
        self.namespace = "mlibEditRefactor_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        self.names = [cmds.createNode("transform", name=self.namespace + ":node" + str(i))
                      for i in range(2)]

    def tearDown(self):
        """このテストが作ったノードだけを削除する。"""
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def test_compound_creation_reenters_user_override_in_child_order(self):
        """子作成でも公開addAttrのoverrideとgetPlug=False指定を保つ。"""
        calls = []

        original = mlib.nodes.Node.addAttr

        def record_add_attr(node, *args, **kwargs):
            """呼出時に差し替えた公開入口でも子作成の入力を受け取る。"""
            calls.append((args, dict(kwargs)))
            return original(node, *args, **kwargs)

        node = mlib.nodes.Transform(self.names[0])
        with patch.object(mlib.nodes.Node, "addAttr", record_add_attr):
            plug = node.addAttr("customVector", "double3", childNames=["redValue", "greenValue", "blueValue"],
                                childShortNames=["rv", "gv", "bv"], defaultValue=(1, 2, 3), keyable=True)
        self.assertEqual([row[0][0] for row in calls],
                         ["customVector", "redValue", "greenValue", "blueValue"])
        self.assertTrue(all(row[1]["getPlug"] is False for row in calls[1:]))
        self.assertEqual([row[1]["shortName"] for row in calls[1:]], ["rv", "gv", "bv"])
        self.assertEqual(tuple(plug.get()), (1, 2, 3))
        cmds.undo()
        self.assertFalse(node.hasAttr("customVector"))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
