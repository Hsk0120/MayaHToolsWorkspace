"""hlib.nodes.cluster の Cluster ラッパーを検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.nodes import Node
from hlib.nodes.cluster import Cluster


class ClusterTest(unittest.TestCase):
    """weightedNode/geometry を検証する。"""

    def setUp(self):
        self.mesh = cmds.polyCube(name="hlibClusterMesh", constructionHistory=False)[0]
        cluster_name, handle_name = cmds.cluster(self.mesh + ".vtx[0:2]")
        self.created = [self.mesh, handle_name]
        self.cluster = Node(cluster_name)
        self.handle_name = handle_name

    def tearDown(self):
        for node in reversed(self.created):
            if cmds.objExists(node):
                cmds.delete(node)

    def test_node_resolves_to_cluster_wrapper(self):
        self.assertIsInstance(self.cluster, Cluster)

    def test_weighted_node_returns_handle_transform(self):
        weightedNode = self.cluster.getWeightedNode()
        self.assertIsInstance(weightedNode, Node)
        self.assertEqual(weightedNode.getName(), self.handle_name)

    def test_geometry_returns_affected_shape(self):
        geometry = self.cluster.getGeometry()
        self.assertEqual(len(geometry), 1)
        self.assertTrue(geometry[0].getName().startswith(self.mesh))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
