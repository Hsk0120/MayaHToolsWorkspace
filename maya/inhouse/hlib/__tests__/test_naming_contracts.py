"""取得値・Plug・保持名の命名契約をMaya内で検証する。"""
import unittest
from unittest.mock import patch
import maya.cmds as cmds
import hlib
hlib.reload()
from hlib.nodes import Node, Joints, SkinClusters
from hlib.scene import Namespace
from hlib.ui import UiElement

class NamingContractsTest(unittest.TestCase):
    """改名後の戻り値と複数形への展開を検証する。"""

    def test_stored_names_do_not_query_maya(self):
        """保持名は照会を必要とせず、Namespace入力も受け取る。"""
        namespace = Namespace(':namingContract')
        element = UiElement('namingContractUi', 'menu')
        with patch.object(cmds, 'namespace', side_effect=AssertionError('query')):
            self.assertEqual(namespace.name, ':namingContract')
            self.assertEqual(Namespace(namespace).name, namespace.name)
            self.assertEqual(element.name, 'namingContractUi')

    def test_blender_value_and_plug(self):
        """係数値と接続用参照を区別できる。"""
        node = Node(cmds.createNode('blendColors'))
        try:
            node.setBlender(.25)
            self.assertAlmostEqual(node.getBlender(), .25)
            self.assertEqual(node.blenderPlug().attributeName(), 'blender')
            self.assertEqual(node.outputPlug().attributeName(), 'output')
        finally:
            cmds.delete(node.fullName())

    def test_bulk_getters_are_exposed(self):
        """単数形から新しい取得名が複数形へ展開される。"""
        self.assertTrue(callable(Joints.getJointOrient))
        self.assertTrue(callable(Joints.getInverseScale))
        self.assertTrue(callable(SkinClusters.getMaxInfluences))
        self.assertNotIn('joint_orient', Joints.__dict__)
