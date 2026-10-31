"""追加命名整理の戻り値・継承・読み取り非更新を検証する。"""
from maya.api.OpenMaya import MSpace
import json
import tempfile
from pathlib import Path
import unittest
import maya.cmds as cmds
import mlib
mlib.reload()
from mlib.nodes import Node, Container

class ApiProposalTest(unittest.TestCase):
    """隔離テストシーン上で新しい公開契約を確認する。"""

    def setUp(self):
        """テスト用namespaceへ切り替える。"""
        self.previous = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.ns = cmds.namespace(add='proposalTest')
        cmds.namespace(set=self.ns)

    def tearDown(self):
        """テスト対象を除去し元のnamespaceへ戻す。"""
        cmds.namespace(set=self.previous)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_members_and_constraint_weight(self):
        """リスト入力と可変長入力のメンバー追加を検証する。"""
        a, b, c = [Node(cmds.createNode('transform')) for _ in range(3)]
        container = mlib.createContainer()
        container.addMembers([a, b])
        self.assertEqual({n.getUuid() for n in container.getMembers()}, {a.getUuid(), b.getUuid()})
        made = container.createNode(type='multiplyDivide')
        self.assertEqual(made.getType(), 'multiplyDivide')
        # 所有containerと他のテスト用関係を分離し、Mayaの一括削除へ二重所有を渡さない。
        cmds.delete(container.getFullName())
        a, b, c = [Node(cmds.createNode('transform')) for _ in range(3)]
        constraint = c.addConstraint([a, b], type='point')
        constraint.setWeight(.25, a)
        self.assertAlmostEqual(constraint.getWeight(a), .25)
        with self.assertRaises(ValueError):
            constraint.getWeight(c)

    def test_axis_flags_return_and_undo(self):
        """単数・複数の軸照会は空間を受け、Transformの表示切替は自身の状態を変える。"""
        transform = cmds.polyCube(constructionHistory=False)[0]
        cmds.setAttr(transform+'.translateX', 10)
        mesh = Node(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])
        vertex = mesh.getVertex(0)
        position = vertex.getPosition(worldSpace=True)
        self.assertAlmostEqual(vertex.getPositionX(worldSpace=True), position[0])
        self.assertAlmostEqual(vertex.getPositionX(), position[0] - 10)
        vertices = mesh.getVertices()[:2]
        self.assertEqual(vertices.getPositionX(worldSpace=True), [v.getPositionX(worldSpace=True) for v in vertices])
        uvs = mesh.getUVs()[:2]
        self.assertEqual(uvs.getV(), [uv.getV() for uv in uvs])
        transform = mesh.getTransform()
        transform.setVisibility(False)
        self.assertFalse(transform.getVisibility())

    def test_influences_and_json_roundtrip(self):
        """influenceはNodeを返すが保存ファイルの名前は文字列のまま。"""
        cmds.select(clear=True)
        joint = cmds.joint()
        mesh = cmds.polyCube(constructionHistory=False)[0]
        skin = Node(cmds.skinCluster(joint, mesh, toSelectedBones=True)[0])
        self.assertTrue(all(isinstance(n, Node) for n in skin.getInfluences()))
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/'weights.json')
            skin.dumpWeights(path)
            payload = json.loads(Path(path).read_text())
            self.assertTrue(all(isinstance(n,str) for n in payload['influences']))
            before = list(skin.getWeights(skin.getInfluences()))
            skin.loadWeights(path)
            self.assertEqual(list(skin.getWeights(skin.getInfluences())), before)


if __name__ == "__main__":
    unittest.main(argv=[__file__])
