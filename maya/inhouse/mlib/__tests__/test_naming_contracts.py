"""取得値・Plug・保持名の命名契約をMaya内で検証する。"""
import unittest
from unittest.mock import patch
import maya.cmds as cmds
import mlib
mlib.reload()
from mlib.nodes import Node, Joints, SkinClusters
from mlib.common import Namespace

class NamingContractsTest(unittest.TestCase):
    """改名後の戻り値と複数形への展開を検証する。"""

    def test_stored_names_do_not_query_maya(self):
        """保持名は照会を必要とせず、Namespace入力も受け取る。"""
        namespace = Namespace(':namingContract')
        with patch.object(cmds, 'namespace', side_effect=AssertionError('query')):
            self.assertEqual(namespace.name, ':namingContract')
            self.assertEqual(Namespace(namespace).name, namespace.name)

    def test_blender_value_and_plug(self):
        """演算ノードの値と接続用参照はMaya標準名のPlugで扱う。"""
        node = Node(cmds.createNode("blendColors"))
        try:
            blender = node.getPlug("blender")
            blender.set(.25)
            self.assertAlmostEqual(blender.get(), .25)
            self.assertEqual(blender.getLongName(), "blender")
            self.assertEqual(node.getPlug("output").getLongName(), "output")
        finally:
            cmds.delete(node.getFullName())

    def test_bulk_getters_are_exposed(self):
        """複数形へ明示した取得入口が正式名で公開される。"""
        self.assertTrue(callable(Joints.getJointOrient))
        self.assertTrue(callable(Joints.getInverseScale))
        self.assertTrue(callable(SkinClusters.getMaxInfluences))
        self.assertNotIn('joint_orient', Joints.__dict__)
