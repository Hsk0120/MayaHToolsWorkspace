"""セット・表示レイヤー・シェーディング所属のAPI経路を検証する。"""

import unittest
from unittest import mock

from maya import cmds
import maya.api.OpenMaya as om2
import mlib


class ConsolidatedSetsLayersTests(unittest.TestCase):
    """Maya標準の所属表現と通常Undo・高速編集を比較する。"""

    def setUp(self):
        """隔離した新規シーンを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def tearDown(self):
        """既定レイヤーへ戻して検証シーンを破棄する。"""
        cmds.editDisplayLayerGlobals(currentDisplayLayer="defaultLayer")
        cmds.file(new=True, force=True)

    def test_object_set_members_and_component_subset(self):
        """圧縮範囲・順序・部分範囲の全件判定を標準setsと一致させる。"""
        cube = cmds.polyCube(name="setCube")[0]
        other = cmds.createNode("transform", name="setOther")
        name = cmds.sets(empty=True, name="querySet")
        cmds.sets(cube + ".vtx[0:2]", cube + ".vtx[5:6]", other, add=name)
        node = mlib.nodes.ObjectSet(name)
        expected = cmds.sets(name, query=True)
        actual = [item if isinstance(item, str) else item.getName() for item in node.getMembers()]
        self.assertEqual(actual, expected)
        for member in (cube + ".vtx[0]", cube + ".vtx[3]", cube + ".vtx[0:3]", other, cube):
            expected = bool(cmds.sets(member, isMember=name))
            with mock.patch.object(cmds, "sets", side_effect=AssertionError("cmds sets used")):
                self.assertEqual(node.isMember(member), expected)
                node.getMembers()

    def test_object_set_fast_and_regular_undo(self):
        """高速セット更新はUndoなし、通常追加はUndo可能にする。"""
        node = mlib.nodes.ObjectSet(cmds.sets(empty=True))
        cube = cmds.polyCube()[0]
        cmds.flushUndo()
        node.addMembers(cube + ".f[0:2]", fast=True)
        self.assertTrue(node.isMember(cube + ".f[0:2]"))
        node.removeMembers(cube + ".f[1]", fast=True)
        self.assertFalse(node.isMember(cube + ".f[1]"))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        node.addMembers(cube + ".f[1]")
        self.assertTrue(node.isMember(cube + ".f[1]"))
        cmds.undo()
        self.assertFalse(node.isMember(cube + ".f[1]"))

    def test_display_layer_exclusion_recursion_default_and_current(self):
        """子Shapeを含む排他移動とdefaultLayer・カレント設定を確認する。"""
        cube = mlib.getNode(cmds.polyCube(name="layerCube")[0])
        first = mlib.nodes.DisplayLayer(cmds.createDisplayLayer(empty=True))
        second = mlib.nodes.DisplayLayer(cmds.createDisplayLayer(empty=True))
        first.addMembers(cube)
        expected = cmds.editDisplayLayerMembers(first.getName(), query=True, fullNames=True)
        self.assertEqual([node.getFullName() for node in first.getMembers()], expected)
        cmds.flushUndo()
        second.addMembers(cube, fast=True)
        self.assertEqual(first.getMembers(), [])
        self.assertEqual(set(node.getFullName() for node in second.getMembers()), set(expected))
        self.assertEqual([node.getFullName() for node in second.getMembers()],
                         cmds.editDisplayLayerMembers(second.getName(), query=True, fullNames=True))
        second.removeMembers(cube, fast=True)
        self.assertEqual(second.getMembers(), [])
        default = mlib.nodes.DisplayLayer("defaultLayer")
        expected_default = cmds.editDisplayLayerMembers("defaultLayer", query=True, fullNames=True)
        self.assertEqual([node.getFullName() for node in default.getMembers()], expected_default)
        second.setCurrent(fast=True)
        self.assertEqual(cmds.editDisplayLayerGlobals(query=True, currentDisplayLayer=True), second.getName())
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        if hasattr(om2, "MFnDisplayLayer"):
            with mock.patch.object(cmds, "editDisplayLayerMembers", side_effect=AssertionError("cmds layer read used")):
                default.getMembers()
                second.getMembers()

    def test_shading_members_and_fast_whole_mesh_assignment(self):
        """既存のフェース別割り当てを全体へ置換し、他のメッシュは保持する。"""
        cube = mlib.getNode(cmds.polyCube(name="shadeCube")[0])
        other = mlib.getNode(cmds.polyCube(name="shadeOther")[0])
        first = mlib.nodes.ShadingEngine(cmds.sets(renderable=True, noSurfaceShader=True, empty=True))
        second = mlib.nodes.ShadingEngine(cmds.sets(renderable=True, noSurfaceShader=True, empty=True))
        first.assign([cube.getName() + ".f[0:2]", other.getName()])
        expected = cmds.ls(cmds.sets(first.getName(), query=True), long=True, flatten=True)
        expected = [name.replace(cube.getFullName() + ".f[", cube.getShape().getFullName() + ".f[")
                    for name in expected]
        self.assertEqual([item.getFullName() for item in first.getMembers()], expected)
        cmds.flushUndo()
        second.assign(cube, fast=True)
        mesh = cube.getShape()
        shaders, indices = om2.MFnMesh(mesh.mpath()).getConnectedShaders(mesh.mpath().instanceNumber())
        self.assertTrue(all(shaders[index] == second.mnode() for index in indices))
        self.assertEqual([item.getFullName() for item in first.getMembers()], [other.getShape().getFullName()])
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        with mock.patch.object(cmds, "sets", side_effect=AssertionError("cmds set read used")):
            second.getMembers()

    def test_shading_fast_face_rejection_and_shader_connection(self):
        """未対応のフェース指定を更新前拒否し、シェーダー接続は高速化する。"""
        cube = cmds.polyCube()[0]
        shading = mlib.nodes.ShadingEngine(cmds.sets(renderable=True, noSurfaceShader=True, empty=True))
        before = list(shading.getMembers())
        with self.assertRaises(NotImplementedError):
            shading.assign(cube + ".f[0]", fast=True)
        self.assertEqual(shading.getMembers(), before)
        material = mlib.createNode("lambert")
        cmds.flushUndo()
        shading.setShader(material, fast=True)
        self.assertEqual(shading.getShader(), material)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))


if __name__ == "__main__":
    unittest.main()
