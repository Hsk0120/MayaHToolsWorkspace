"""追加命名整理の戻り値・継承・読み取り非更新を検証する。"""
import json
import tempfile
from pathlib import Path
import unittest
import maya.cmds as cmds
import hlib
hlib.reload()
from hlib.nodes import Node, DagPose, Container

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

    def test_sparse_getters_do_not_create_elements(self):
        """未設定入力の照会で疎配列を変更しない。"""
        for kind, value in [('blendWeighted', 3.0), ('multMatrix', hlib.maths.Matrix())]:
            node = Node(cmds.createNode(kind))
            node.set_input(4, value)
            attr = 'input' if kind == 'blendWeighted' else 'matrixIn'
            before = cmds.getAttr(node.full_name()+'.'+attr, multiIndices=True)
            self.assertIsNotNone(node.get_input(4))
            with self.assertRaises(IndexError):
                node.get_input(2)
            self.assertEqual(before, cmds.getAttr(node.full_name()+'.'+attr, multiIndices=True))
            if kind == 'blendWeighted':
                weight_before = cmds.getAttr(node.full_name()+'.weight', multiIndices=True)
                self.assertEqual(node.get_weight(4), 1.0)
                self.assertEqual(weight_before, cmds.getAttr(node.full_name()+'.weight', multiIndices=True))
                node.set_weight(4, .25)
                self.assertEqual(node.get_weight(4), .25)
        decompose = Node(cmds.createNode('decomposeMatrix'))
        decompose.set_rotate_order('zyx')
        self.assertEqual(decompose.get_rotate_order(), 5)
        self.assertIsInstance(decompose.get_input(), hlib.maths.Matrix)

    def test_members_and_constraint_weight(self):
        """リスト入力と可変長入力のメンバー追加を検証する。"""
        a, b, c = [Node(cmds.createNode('transform')) for _ in range(3)]
        container = Container.create()
        container.add_members([a, b])
        self.assertEqual({n.uuid() for n in container.members()}, {a.uuid(), b.uuid()})
        made = container.create_node(type='multiplyDivide')
        self.assertEqual(made.type(), 'multiplyDivide')
        # 所有containerと他のテスト用関係を分離し、Mayaの一括削除へ二重所有を渡さない。
        cmds.delete(container.full_name())
        a, b, c = [Node(cmds.createNode('transform')) for _ in range(3)]
        pose = DagPose.create([a], hierarchy=False)
        pose.add_members(b, c)
        self.assertEqual(len(pose.members()), 3)
        pose.remove_members([b, c])
        self.assertEqual(len(pose.members()), 1)
        constraint = c.add_constraint([a, b], type='point')
        constraint.set_weight(.25, a)
        self.assertAlmostEqual(constraint.get_weight(a), .25)
        with self.assertRaises(ValueError):
            constraint.get_weight(c)

    def test_axis_flags_return_and_undo(self):
        """単数・複数の軸更新は空間とfastを受け自身を返す。"""
        transform = cmds.polyCube(constructionHistory=False)[0]
        cmds.setAttr(transform+'.translateX', 10)
        mesh = Node(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])
        vertex = mesh.vertex(0)
        before = vertex.get_position(ws=True)
        self.assertIs(vertex.set_x(12, ws=True), vertex)
        self.assertAlmostEqual(vertex.get_x(ws=True), 12)
        self.assertAlmostEqual(vertex.get_y(ws=True), before[1])
        cmds.undo()
        self.assertEqual(vertex.get_position(ws=True), before)
        vertices = mesh.vertices()[:2]
        self.assertIs(vertices.set_x([13,14], ws=True, fast=True), vertices)
        self.assertEqual(vertices.get_x(ws=True), [13,14])
        uv = mesh.uv(0)
        self.assertIs(uv.set_u(.25), uv)
        uvs = mesh.uvs()[:2]
        self.assertIs(uvs.set_v([.2,.3], fast=True), uvs)
        for actual, expected in zip(uvs.get_v(), [.2,.3]):
            self.assertAlmostEqual(actual,expected,places=6)
        transform = mesh.transform()
        transform.set_visibility(False)
        self.assertFalse(transform.get_visibility())

    def test_influences_and_json_roundtrip(self):
        """influenceはNodeを返すが保存ファイルの名前は文字列のまま。"""
        cmds.select(clear=True)
        joint = cmds.joint()
        mesh = cmds.polyCube(constructionHistory=False)[0]
        skin = Node(cmds.skinCluster(joint, mesh, toSelectedBones=True)[0])
        self.assertTrue(all(isinstance(n, Node) for n in skin.influences()))
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/'weights.json')
            skin.dump_weights(path)
            payload = json.loads(Path(path).read_text())
            self.assertTrue(all(isinstance(n,str) for n in payload['influences']))
            before = list(skin.get_weights(skin.influences()))
            skin.load_weights(path)
            self.assertEqual(list(skin.get_weights(skin.influences())), before)


if __name__ == "__main__":
    unittest.main(argv=[__file__])
