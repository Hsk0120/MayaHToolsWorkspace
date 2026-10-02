"""共通基底と入力振り分けが参照・シーンを変更しないことを確認する。"""
import sys
import unittest

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import hlib


class ObjectTest(unittest.TestCase):
    """専用シーンで具象型、同一性、入力の境界を検証する。"""

    def setUp(self):
        """テスト用メッシュを作る。"""
        cmds.file(new=True, force=True)
        self.name = cmds.polyCube()[0]

    def tearDown(self):
        """作成したシーンを破棄する。"""
        cmds.file(new=True, force=True)

    def test_factory_and_identity(self):
        """型を選択しても、既存参照の再初期化やハッシュ変更は行わない。"""
        node = hlib.Object(self.name)
        plug = hlib.Object(self.name + '.tx')
        vertex = hlib.Object(self.name + '.vtx[0]')
        self.assertIsInstance(node, hlib.nodes.Transform)
        self.assertIsInstance(plug, hlib.plugs.Plug)
        self.assertIsInstance(vertex, hlib.components.Vertex)
        for item in (node, plug, vertex):
            with self.subTest(item=type(item).__name__):
                self.assertIsInstance(item, hlib.Object)
                self.assertIs(hlib.Object(item), item)
                resolved = hlib.Object(item.full_name())
                self.assertEqual(resolved, item)
                self.assertEqual(hash(resolved), hash(item))
        self.assertNotIsInstance(hlib.nodes.Nodes([node]), hlib.Object)
        self.assertNotIsInstance(hlib.maths.Matrix(), hlib.Object)

    def test_api_inputs(self):
        """Maya APIの参照から同じ対象へ解決する。"""
        selection = om2.MSelectionList()
        selection.add(self.name)
        self.assertEqual(hlib.Object(selection.getDependNode(0)), hlib.Object(self.name))
        self.assertEqual(hlib.Object(selection.getDagPath(0)), hlib.Object(self.name))
        selection.add(self.name + '.tx')
        self.assertEqual(hlib.Object(selection.getPlug(1)), hlib.Object(self.name + '.tx'))
        selection.add(self.name + '.vtx[1]')
        self.assertEqual(hlib.Object(selection.getComponent(2)), hlib.Object(self.name + '.vtx[1]'))

    def test_invalid_and_multiple_inputs(self):
        """単数の入口では範囲・リスト・未対応型を受け付けない。"""
        with self.assertRaises(ValueError):
            hlib.Object('')
        with self.assertRaises(ValueError):
            hlib.Object(self.name + '.vtx[0:2]')
        for value in (None, 12, [self.name]):
            with self.subTest(value=value), self.assertRaises(TypeError):
                hlib.Object(value)
        with self.assertRaises(RuntimeError):
            hlib.Object('missing_object_reference')

    def test_complete_components_and_mixed_nodes(self):
        """全要素選択と、従来の文字列・Node混在拒否を維持する。"""
        from hlib.scene import Selection
        self.assertEqual(len(Selection(self.name + '.vtx[*]').items), 8)
        with self.assertRaises(TypeError):
            hlib.nodes.Nodes([self.name, hlib.Object(self.name)])


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
