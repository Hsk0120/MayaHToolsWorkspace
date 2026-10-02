"""部分更新・事前検証・保持値の公開契約をMayaで検証する。"""

import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import maya.cmds as cmds
import hlib

hlib.reload()


class ApiRefinementsTest(unittest.TestCase):
    """シーンをnamespace内に限定して追加APIの契約を確認する。"""

    def setUp(self):
        """検証用namespaceと復元用の単位を準備する。"""
        self.ns = "hlibRefine_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.unit = cmds.currentUnit(query=True, linear=True)

    def tearDown(self):
        """作成物を削除して単位を戻す。"""
        cmds.currentUnit(linear=self.unit)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def create(self, type):
        """検証用namespace内に指定型を作成する。"""
        return hlib.createNode(type, name=self.ns + ":" + type)

    def skin(self):
        """3本の骨と既知のウェイトを持つスキンを用意する。"""
        joints = [self.create("joint") for _ in range(3)]
        cmds.parent(joints[1], joints[0])
        mesh = cmds.polyCube(name=self.ns + ":mesh", constructionHistory=False)[0]
        skin = hlib.nodes.SkinCluster.bind(mesh, joints)
        pose = skin.bind_pose()
        if pose:
            pose.rename(self.ns + ":pose")
        skin.plug("normalizeWeights").set(0)
        skin.set_weights(joints, [.2, .5, .3])
        return skin, joints

    def test_infinity_partial_update_and_undo(self):
        """省略側を維持し、不正な後半指定で前半も変更しない。"""
        for kind in ("animCurveUU", "animCurveTL"):
            curve = self.create(kind)
            curve.set_infinity(pre="cycle", post="linear")
            curve.set_infinity(pre="oscillate")
            self.assertEqual(curve.get_infinity(), dict(pre="oscillate", post="linear"))
            cmds.undo()
            self.assertEqual(curve.get_infinity(), dict(pre="cycle", post="linear"))
            cmds.redo()
            before = curve.get_infinity()
            curve.set_infinity()
            self.assertEqual(curve.get_infinity(), before)
            for invalid in ("invalid", [], True):
                with self.assertRaises(ValueError):
                    curve.set_infinity(pre="constant", post=invalid)
                self.assertEqual(curve.get_infinity(), before)
            curve.set_infinity(pre="constant", post="constant")
            self.assertEqual(curve.get_infinity(), dict(pre="constant", post="constant"))

    def test_pivot_kinds_preserve_matrix_and_units(self):
        """別々のピボット、親・負scale・Joint・単位変換とUndoを確認する。"""
        parent = self.create("transform")
        parent.set_translate((4, 6, 8))
        parent.set_scale((-2, 3, 1))
        for type in ("transform", "joint"):
            node = self.create(type)
            node.set_parent(parent)
            node.set_rotate((.3, .4, .5))
            node.set_scale((1.2, .7, 2))
            if type == "joint":
                before = node.get_matrix(ws=True)
                for kind in ("rotate", "scale", "both"):
                    with self.assertRaises(TypeError):
                        node.set_pivot((1, 2, 3), kind=kind)
                    self.assertTrue(node.get_matrix(ws=True).is_equivalent(before))
                continue
            if type == "joint":
                before = node.get_matrix(ws=True)
                for kind in ("rotate", "scale", "both"):
                    with self.assertRaises(TypeError):
                        node.set_pivot((1, 2, 3), kind=kind)
                    self.assertTrue(node.get_matrix(ws=True).is_equivalent(before))
                continue
            node.set_pivot((1, 2, 3), kind="rotate")
            node.set_pivot((-2, 1, 4), kind="scale")
            for unit in ("cm", "m"):
                cmds.currentUnit(linear=unit)
                for ws in (False, True):
                    for kind in ("rotate", "scale", "both"):
                        before = node.get_matrix(ws=True)
                        old = {k: tuple(node.get_pivot(ws=ws, kind=k)) for k in ("rotate", "scale")}
                        node.set_pivot((12, 15, 18), ws=ws, kind=kind)
                        self.assertTrue(node.get_matrix(ws=True).is_equivalent(before, 1e-8))
                        for k in ("rotate", "scale"):
                            expected = (12, 15, 18) if kind in (k, "both") else old[k]
                            for a, b in zip(node.get_pivot(ws=ws, kind=k), expected):
                                self.assertAlmostEqual(a, b, places=7, msg=(type, unit, ws, kind, k))
                        cmds.undo()
                        for k in old:
                            for a, b in zip(node.get_pivot(ws=ws, kind=k), old[k]):
                                self.assertAlmostEqual(a, b, places=7, msg=(type, unit, ws, kind, k))
                        cmds.redo()
                        self.assertTrue(node.get_matrix(ws=True).is_equivalent(before, 1e-8))
                        cmds.undo()

    def test_pivot_validation_and_default_target(self):
        """既定は回転のみ。不正入力は更新せず、補償なしも選べる。"""
        node = self.create("transform")
        node.set_rotate((.2, .4, .1))
        before = node.get_matrix()
        scale = node.get_pivot(kind="scale")
        node.set_pivot((1, 2, 3))
        self.assertEqual(node.get_pivot(kind="scale"), scale)
        self.assertTrue(node.get_matrix().is_equivalent(before))
        for kwargs in (dict(kind="bad"), dict(preserve="False")):
            with self.assertRaises((TypeError, ValueError)):
                node.set_pivot((9, 9, 9), **kwargs)
        for value in ((1, 2), (float("nan"), 0, 0)):
            with self.assertRaises(ValueError):
                node.set_pivot(value)
        for a, b in zip(node.get_pivot(), (1, 2, 3)):
            self.assertAlmostEqual(a, b)
        node.set_pivot((5, 6, 7), preserve=False)
        self.assertFalse(node.get_matrix().is_equivalent(before))
        self.assertFalse(hasattr(type(node), "pivot"))

    def test_removal_flag_validation_across_entries(self):
        """単体・複数・Jointとも文字列のFalseを更新前に拒否する。"""
        skin, joints = self.skin()
        before = list(skin.get_weights(joints))
        actions = (
            lambda value: skin.remove_influence(joints[1], transfer_to_parent=value),
            lambda value: joints[1].remove_influence(skin, transfer_to_parent=value),
            lambda value: hlib.nodes.SkinClusters([skin]).remove_influences(joints[1], transfer_to_parent=value),
        )
        for action in actions:
            for value in ("False", 0, None):
                with self.assertRaises(TypeError):
                    action(value)
                self.assertEqual(list(skin.get_weights(joints)), before)
                self.assertTrue(skin.has_influence(joints[1]))

    def test_transfer_validates_every_pair_before_editing(self):
        """後続の未登録・欠損ペアを検証してから移送し、選択も維持する。"""
        skin, joints = self.skin()
        outside = self.create("joint")
        cmds.select(joints[2])
        before = list(skin.get_weights(joints))
        for bad in ((joints[0], outside), (joints[0],), "bad"):
            with self.assertRaises(ValueError):
                skin.transfer_weights([(joints[0], joints[1]), bad])
            self.assertEqual(list(skin.get_weights(joints)), before)
            self.assertEqual(cmds.ls(selection=True, long=True), [joints[2].full_name()])

    def test_transfer_generator_order_self_pair_and_undo(self):
        """Maya API参照とgeneratorを受け付け、連鎖移送の順序を保つ。"""
        skin, joints = self.skin()
        before = list(skin.get_weights(joints))
        skin.transfer_weights([(joints[0], joints[0])])
        self.assertEqual(list(skin.get_weights(joints)), before)
        # 元の移送はskinPercentの正規化規則を使う。同じ標準操作の結果と比較する。
        cmds.undoInfo(openChunk=True)
        try:
            for source, target in ((joints[0], joints[1]), (joints[1], joints[2])):
                cmds.skinCluster(skin, edit=True, selectInfluenceVerts=source)
                cmds.skinPercent(skin, transformMoveWeights=[source, target])
        finally:
            cmds.undoInfo(closeChunk=True)
        expected = list(skin.get_weights(joints))
        cmds.undo()
        skin.transfer_weights(pair for pair in ((joints[0].mobject(), joints[1]), (joints[1], joints[2].dag_path())))
        values = list(skin.get_weights(joints))
        for a, b in zip(values, expected):
            self.assertAlmostEqual(a, b)
        cmds.undo()
        self.assertEqual(list(skin.get_weights(joints)), before)
        cmds.redo()
        self.assertEqual(list(skin.get_weights(joints)), values)

    def test_stored_properties_do_not_query_maya(self):
        """保持値の参照はMaya照会をせず、Selectionの返却リストはコピー。"""
        scene = hlib.scene.Scene(Path("stored.ma"))
        plugin = hlib.environment.Plugin("example")
        module = hlib.environment.Module("example")
        selection = hlib.scene.Selection([self.create("transform")])
        view = object.__new__(hlib.ui.Viewport)
        view._name, view._panel = "editor", "panel"
        with patch.object(cmds, "file", side_effect=AssertionError("Unexpected query")), patch.object(
            cmds, "pluginInfo", side_effect=AssertionError("Unexpected query")
        ), patch.object(cmds, "modelEditor", side_effect=AssertionError("Unexpected query")):
            self.assertEqual(scene.path.name, "stored.ma")
            self.assertEqual(scene.name, "stored.ma")
            self.assertEqual(plugin.name, "example")
            self.assertEqual(module.name, "example")
            self.assertEqual(view.name, "editor")
            self.assertEqual(view.panel, "panel")
            selection.items.clear()
            self.assertEqual(len(selection.items), 1)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
