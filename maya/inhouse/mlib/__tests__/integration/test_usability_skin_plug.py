"""選択頂点・SkinCluster集合・Plugの現在状態の利用フローを検証する。"""

import unittest

import mlib
import maya.cmds as cmds


class SkinPlugWorkflowTest(unittest.TestCase):
    """既存の番号入力・返却と、新しい参照入力を比較する。"""

    def setUp(self):
        """独立したmeshと二つのinfluenceをバインドする。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        self.base = mlib.getNode(cmds.polyCube(ch=False)[0])
        self.first = mlib.nodes.Joint("first", create=True)
        self.second = mlib.nodes.Joint("second", create=True)
        self.skin = mlib.nodes.SkinCluster.bind(self.base, [self.first, self.second])
        self.skin.setWeights([self.first, self.second], [0.25, 0.75])

    def tearDown(self):
        """一時シーンを破棄する。"""
        cmds.file(new=True, force=True)

    def test_selected_vertices_and_mixed_indices_match_existing_values(self):
        """選択listと番号混在入力の計算・None返却・Undoが既存と一致する。"""
        cmds.select(self.base.getFullName() + ".vtx[0:1]")
        selected = mlib.ls(sl=True, type="vertex")
        before = list(self.skin.getWeights([self.first, self.second]))
        self.assertIsNone(self.skin.redistributeWeights(selected))
        expected = list(self.skin.getWeights([self.first, self.second]))
        cmds.undo()
        self.assertEqual(list(self.skin.getWeights([self.first, self.second])), before)
        self.skin.redistributeWeights([selected[0], 1, selected[0]])
        self.assertEqual(list(self.skin.getWeights([self.first, self.second])), expected)
        self.assertEqual(mlib.ls(sl=True, type="vertex"), selected)

    def test_vertices_collection_single_vertex_and_wrong_owner(self):
        """Verticesと単体Vertexを受理し、他meshの頂点を全件検証で拒否する。"""
        shape = self.base.getShape()
        self.skin.redistributeWeights(shape.getVertices([0, 1]))
        self.skin.redistributeWeights(shape.getVertex(2))
        other = mlib.getNode(cmds.polyCube(ch=False)[0]).getShape()
        before = list(self.skin.getWeights([self.first, self.second]))
        for vertices in (other.getVertices([]), [shape.getVertex(0), other.getVertex(0)]):
            with self.assertRaises(ValueError):
                self.skin.redistributeWeights(vertices)
        self.assertEqual(list(self.skin.getWeights([self.first, self.second])), before)

    def test_legacy_conversion_and_partial_update_are_preserved(self):
        """既存int変換と、途中のゼロ合計失敗前に完了した更新を維持する。"""
        self.skin.redistributeWeights(["0", 1.9])
        self.skin.setWeights([self.first, self.second], [0.25, 0.75])
        cmds.setAttr(self.skin.getFullName() + ".weightList[1].weights[0]", 0)
        cmds.setAttr(self.skin.getFullName() + ".weightList[1].weights[1]", 0)
        before = list(self.skin.getWeights([self.first, self.second]))
        with self.assertRaises(ValueError):
            self.skin.redistributeWeights(self.base.getShape().getVertices([0, 1]))
        after = list(self.skin.getWeights([self.first, self.second]))
        self.assertNotEqual(after[:2], before[:2])
        self.assertEqual(after[2:], before[2:])
        cmds.undo()
        self.assertEqual(list(self.skin.getWeights([self.first, self.second])), before)

    def test_collect_skins_is_typed_deduplicated_and_preserves_getters(self):
        """Shape/Transform/Jointを集約し、従来のnested/Joint返却は変えない。"""
        nodes = mlib.nodes.DagNodes([self.base, self.base.getShape(), self.first])
        self.assertIsInstance(self.base.collectSkinClusters(), mlib.nodes.SkinClusters)
        self.assertEqual(list(nodes.collectSkinClusters()), [self.skin])
        self.assertIsInstance(nodes.getSkinClusters(), list)
        self.assertTrue(all(isinstance(row, list) for row in nodes.getSkinClusters()))
        joints = mlib.nodes.Joints([self.first, self.second])
        self.assertIsInstance(joints.getSkinClusters(), mlib.nodes.SkinClusters)
        self.assertEqual(list(joints.collectSkinClusters()), [self.skin])
        self.assertEqual(len(mlib.nodes.DagNodes().collectSkinClusters()), 0)
        results = nodes.callEach("collectSkinClusters", [()] * len(nodes))
        self.assertTrue(all(isinstance(row, mlib.nodes.SkinClusters) for row in results))

    def test_collect_preserves_first_seen_order_and_does_not_recurse_groups(self):
        """別skinの保持順と直下shape検索の既存境界を保つ。"""
        mesh = mlib.getNode(cmds.polyCube(ch=False)[0])
        other = mlib.nodes.SkinCluster.bind(mesh, [self.first, self.second])
        group = mlib.nodes.Transform("group", create=True)
        mesh.setParent(group)
        self.assertEqual(len(group.collectSkinClusters()), 0)
        nodes = mlib.nodes.DagNodes([mesh, self.base, self.first])
        self.assertEqual(list(nodes.collectSkinClusters()), [other, self.skin])

    def test_settable_matches_maya_current_state_and_keeps_writable_definition(self):
        """定義writableは維持し、ロック・入力・キーのsettableをMayaと比較する。"""
        control = mlib.nodes.Transform("control", create=True)
        plug = control.getPlug("translateX")
        self.assertTrue(plug.isWritable())
        self.assertTrue(plug.isSettable())
        plug.setFlags(locked=True)
        self.assertTrue(plug.isWritable())
        self.assertFalse(plug.isSettable())
        plug.setFlags(locked=False)
        self.first.getPlug("translateX").connectTo(plug)
        self.assertFalse(plug.isSettable())
        plug.disconnectInput()
        plug.setKey()
        candidates = (plug, control.getPlug("translate"), control.getPlug("worldMatrix")[0])
        for candidate in candidates:
            with self.subTest(plug=str(candidate)):
                self.assertEqual(candidate.isSettable(), bool(cmds.getAttr(str(candidate), settable=True)))
                self.assertEqual(candidate.isSettable(), candidate.isSettable())
        extra = self.base.addAttr("deleted")
        extra.delete()
        with self.assertRaises(RuntimeError):
            extra.isSettable()


if __name__ == "__main__":
    unittest.main()
