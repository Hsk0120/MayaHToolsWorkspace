"""Skin Weight Kit の処理(skinWeightKit.core)を mayapy で確かめる。

各テストは新しいシーンで、縦に分割した円柱を3本のジョイントへバインドし、操作の結果を cmds で読んで確かめる。
"""

import os
import tempfile
import unittest

import maya.cmds as cmds

import mlib
from mlib.common import Selection

from skinWeightKit.core import (blend, cleanup, deformers, hold, influences, paint, reduction, sample, selectionTools,
                                shells, skin, smoothing, symmetry, target, transfer, weights)


def _weights(skin_name, vertex):
    """頂点の {インフルエンスの名前: 値} を cmds で読む。"""
    names = cmds.skinCluster(skin_name, query=True, influence=True)
    values = cmds.skinPercent(skin_name, "{}.vtx[{}]".format(_mesh(skin_name), vertex), query=True, value=True)
    return dict(zip(names, values))


def _mesh(skin_name):
    """skinCluster が変形しているメッシュのシェイプ名。"""
    return cmds.skinCluster(skin_name, query=True, geometry=True)[0]


class _Case(unittest.TestCase):
    """新しいシーンに、バインドした円柱を作る。"""

    def setUp(self):
        """円柱(高さ方向に8分割)と3本のジョイントを作ってバインドする。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True, infinity=True)
        self.geo = cmds.polyCylinder(name="swkGeo", height=8, subdivisionsY=8, subdivisionsX=8)[0]
        cmds.move(0, 4, 0, self.geo)
        cmds.makeIdentity(self.geo, apply=True, translate=True)
        cmds.select(clear=True)
        self.joints = [cmds.joint(name="swkJnt{}".format(index), position=(0, index * 4, 0)) for index in range(3)]
        self.skin = cmds.skinCluster(self.joints, self.geo, toSelectedBones=True, maximumInfluences=3)[0]
        self.shape = _mesh(self.skin)

    def select_vertices(self, *indices):
        """頂点を選び、対象を返す。"""
        cmds.select(["{}.vtx[{}]".format(self.geo, index) for index in indices])
        return target.require()

    def assert_normalized(self, vertex):
        """頂点のウェイトの合計が1であることを確かめる。"""
        self.assertAlmostEqual(sum(_weights(self.skin, vertex).values()), 1.0, places=5)


class TargetTest(_Case):
    """選択から対象を決める。"""

    def test_vertices_without_duplicates(self):
        cmds.select("{}.vtx[5]".format(self.geo), "{}.vtx[2]".format(self.geo), "{}.vtx[5]".format(self.geo))
        found = target.require()
        self.assertEqual(sorted(found.vertices), [2, 5])
        self.assertEqual(str(found.skin), self.skin)

    def test_edges_and_faces_become_vertices(self):
        cmds.select("{}.e[0]".format(self.geo))
        self.assertEqual(len(target.require().vertices), 2)
        cmds.select("{}.f[0]".format(self.geo))
        self.assertEqual(len(target.require().vertices), 4)

    def test_object_selection_uses_whole_mesh(self):
        cmds.select(self.geo)
        found = target.require()
        self.assertIsNone(found.vertices)
        self.assertEqual(len(found.editVertices()), cmds.polyEvaluate(self.geo, vertex=True))

    def test_nothing_selected_is_an_error(self):
        cmds.select(clear=True)
        self.assertIsNone(target.resolve())
        with self.assertRaises(ValueError):
            target.require()

    def test_unskinned_mesh_has_no_skin(self):
        other = cmds.polyCube(name="swkCube")[0]
        cmds.select(other)
        found = target.require()
        self.assertIsNone(found.skin)
        with self.assertRaises(ValueError):
            found.requireSkin()


class ValueTest(_Case):
    """値の設定・加算・倍率。"""

    def test_set_value_keeps_sum_one(self):
        found = self.select_vertices(20)
        weights.setValue(found, self.joints[1], 0.25)
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[1]], 0.25, places=5)
        self.assert_normalized(20)

    def test_add_and_scale(self):
        found = self.select_vertices(20)
        weights.setValue(found, self.joints[1], 0.5)
        weights.setValue(found, self.joints[1], 0.1, mode="add")
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[1]], 0.6, places=5)
        weights.setValue(found, self.joints[1], 0.5, mode="scale")
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[1]], 0.3, places=5)
        weights.setValue(found, self.joints[1], -1.0, mode="add")
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[1]], 0.0, places=5)
        self.assert_normalized(20)

    def test_locked_influence_is_kept(self):
        found = self.select_vertices(20)
        weights.setValue(found, self.joints[0], 0.2)
        before = _weights(self.skin, 20)[self.joints[0]]
        influences.setLocked([mlib.getNode(self.joints[0])], True)
        weights.setValue(found, self.joints[1], 0.5)
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[0]], before, places=5)
        with self.assertRaises(ValueError):
            weights.setValue(found, self.joints[0], 0.5)

    def test_one_undo_restores(self):
        found = self.select_vertices(20, 21)
        before = _weights(self.skin, 20)
        weights.setValue(found, self.joints[2], 1.0)
        cmds.undo()
        for name, value in before.items():
            self.assertAlmostEqual(_weights(self.skin, 20)[name], value, places=5)

    def test_bad_mode_is_rejected(self):
        found = self.select_vertices(20)
        with self.assertRaises(ValueError):
            weights.setValue(found, self.joints[1], 0.5, mode="multiply")


class SmoothTest(_Case):
    """ハンマー・スムーズ・平均。"""

    def spike(self, vertex):
        """1つの頂点だけを末端のジョイントに100%にする。"""
        weights.setValue(self.select_vertices(vertex), self.joints[2], 1.0)

    def test_hammer_moves_to_neighbor_average(self):
        self.spike(20)
        weights.hammer(self.select_vertices(20))
        self.assertLess(_weights(self.skin, 20)[self.joints[2]], 0.99)
        self.assert_normalized(20)

    def test_smooth_zero_strength_changes_nothing(self):
        self.spike(20)
        weights.smooth(self.select_vertices(20), strength=0.0)
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[2]], 1.0, places=5)

    def test_smooth_iterations_soften_more(self):
        self.spike(20)
        weights.smooth(self.select_vertices(20, 21, 12), strength=0.5, iterations=1)
        once = _weights(self.skin, 20)[self.joints[2]]
        cmds.undo()
        weights.smooth(self.select_vertices(20, 21, 12), strength=0.5, iterations=4)
        self.assertNotAlmostEqual(once, _weights(self.skin, 20)[self.joints[2]], places=4)
        self.assert_normalized(20)

    def test_smooth_rejects_bad_arguments(self):
        found = self.select_vertices(20)
        with self.assertRaises(ValueError):
            weights.smooth(found, strength=2.0)
        with self.assertRaises(ValueError):
            weights.smooth(found, iterations=0)

    def test_average_makes_rows_equal(self):
        weights.average(self.select_vertices(4, 60))
        first, second = _weights(self.skin, 4), _weights(self.skin, 60)
        for name in first:
            self.assertAlmostEqual(first[name], second[name], places=5)

    def test_copy_and_paste(self):
        copied = weights.copy(self.select_vertices(60))
        self.assertTrue(weights.hasCopy())
        weights.paste(self.select_vertices(4, 5))
        for name, value in copied.items():
            self.assertAlmostEqual(_weights(self.skin, 4)[name], value, places=5)


class InfluenceTest(_Case):
    """インフルエンスの一覧・ロック・選択・追加と削除。"""

    def test_list_shows_average_of_selection(self):
        weights.setValue(self.select_vertices(20, 21), self.joints[1], 0.4)
        listed = {info.name: info for info in influences.listInfluences(target.require())}
        self.assertAlmostEqual(listed[self.joints[1]].value, 0.4, places=5)
        cmds.select(self.geo)
        self.assertIsNone(influences.listInfluences(target.require())[0].value)

    def test_lock_others(self):
        found = self.select_vertices(20)
        keep = mlib.getNode(self.joints[1])
        influences.lockOthers(found, [keep])
        states = {info.name: info.locked for info in influences.listInfluences(found)}
        self.assertEqual(states, {self.joints[0]: True, self.joints[1]: False, self.joints[2]: True})

    def test_select_affected(self):
        cmds.select(self.geo)
        count = influences.selectAffected(target.require(), self.joints[0])
        self.assertGreater(count, 0)
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), count)

    def test_add_and_remove_influence(self):
        cmds.select(clear=True)
        extra = cmds.joint(name="swkExtra", position=(2, 4, 0))
        cmds.select(self.geo)
        found = target.require()
        self.assertEqual(influences.addInfluences(found, [mlib.getNode(extra)]), 1)
        self.assertIn(extra, cmds.skinCluster(self.skin, query=True, influence=True))
        influences.removeInfluence(found, extra)
        self.assertNotIn(extra, cmds.skinCluster(self.skin, query=True, influence=True))


class RemoveJointsTest(_Case):
    """選んだジョイントを外し、ウェイトを親へ移す。"""

    def test_remove_tip_moves_weights_to_parent(self):
        before = _weights(self.skin, 60)
        removed = influences.removeJoints([mlib.getNode(self.joints[2])])
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0][0], self.joints[2])
        self.assertTrue(removed[0][2].endswith(self.joints[1]))
        self.assertNotIn(self.joints[2], cmds.skinCluster(self.skin, query=True, influence=True))
        after = _weights(self.skin, 60)
        self.assertAlmostEqual(after[self.joints[1]], before[self.joints[1]] + before[self.joints[2]], places=5)
        self.assert_normalized(60)

    def test_parent_and_child_collect_into_ancestor(self):
        influences.removeJoints([mlib.getNode(self.joints[1]), mlib.getNode(self.joints[2])])
        self.assertEqual(cmds.skinCluster(self.skin, query=True, influence=True), [self.joints[0]])
        self.assertAlmostEqual(_weights(self.skin, 60)[self.joints[0]], 1.0, places=5)

    def test_one_undo_restores_all(self):
        influences.removeJoints([mlib.getNode(self.joints[1]), mlib.getNode(self.joints[2])])
        cmds.undo()
        self.assertEqual(len(cmds.skinCluster(self.skin, query=True, influence=True)), 3)

    def test_errors(self):
        with self.assertRaises(ValueError):
            influences.removeJoints([])
        cmds.select(clear=True)
        loose = cmds.joint(name="swkLoose")
        with self.assertRaises(ValueError):
            influences.removeJoints([mlib.getNode(loose)])


class CleanupTest(_Case):
    """整理と不正な頂点。"""

    def test_limit_influences(self):
        cmds.select(self.geo)
        cleanup.limitInfluences(target.require(), 1)
        for vertex in (0, 20, 40):
            self.assertEqual(sum(1 for value in _weights(self.skin, vertex).values() if value > 1e-6), 1)
            self.assert_normalized(vertex)

    def test_prune_selection(self):
        found = self.select_vertices(20)
        weights.setValue(found, self.joints[2], 0.05)
        cleanup.prune(found, 0.1)
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[2]], 0.0, places=6)
        self.assert_normalized(20)

    def test_round_keeps_sum(self):
        found = self.select_vertices(20)
        weights.setValue(found, self.joints[1], 0.123456)
        cleanup.roundWeights(found, 2)
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[1]], 0.12, places=6)
        self.assert_normalized(20)

    def test_bad_vertices_and_normalize(self):
        cmds.setAttr(self.skin + ".normalizeWeights", 0)
        cmds.skinPercent(self.skin, "{}.vtx[20]".format(self.geo), transformValue=[(self.joints[0], 0.9)],
                         normalize=False)
        cmds.select(self.geo)
        found = target.require()
        self.assertIn(20, cleanup.badVertices(found)["sum"])
        cleanup.normalize(found)
        self.assertNotIn(20, cleanup.badVertices(found)["sum"])
        self.assertEqual(cleanup.selectBadVertices(found), 0)


class SkinTest(_Case):
    """スキン全体の操作。"""

    def test_bind_skips_skinned_meshes(self):
        other = cmds.polyCube(name="swkCube")[0]
        joints = [mlib.getNode(name) for name in self.joints]
        meshes = [mlib.getNode(other).getShapes()[0], mlib.getNode(self.shape)]
        created = skin.bind(joints, meshes, maxInfluences=2)
        self.assertEqual(len(created), 1)
        with self.assertRaises(ValueError):
            skin.bind(joints, meshes, method="voxel")

    def test_skinned_meshes_in_scene(self):
        cmds.polyCube(name="swkLooseCube")
        meshes = skin.skinnedMeshes()
        self.assertEqual([mesh.getNodeName() for mesh in meshes], [self.shape.split("|")[-1]])

    def test_selected_joints_and_meshes(self):
        cmds.select(self.joints[0], self.geo)
        self.assertEqual([node.getNodeName() for node in skin.selectedJoints()], [self.joints[0]])
        self.assertEqual(len(skin.selectedMeshes()), 1)

    def test_mirror_runs(self):
        cmds.select(self.geo)
        skin.mirror(target.require(), "x")
        with self.assertRaises(ValueError):
            skin.mirror(target.require(), "w")

    def test_copy_skin(self):
        other = cmds.polyCylinder(name="swkCopy", height=8, subdivisionsY=8, subdivisionsX=8)[0]
        cmds.move(0, 4, 0, other)
        cmds.select(self.geo)
        source = target.require()
        self.assertEqual(skin.copySkin(source, [mlib.getNode(other).getShapes()[0]]), 1)
        self.assertTrue(mlib.getNode(other).getShapes()[0].getSkinClusters())
        with self.assertRaises(ValueError):
            skin.copySkin(source, [source.mesh])

    def test_export_import_round_trip(self):
        cmds.select(self.geo)
        found = target.require()
        before = _weights(self.skin, 20)
        path = os.path.join(tempfile.mkdtemp(), "weights.json")
        skin.exportWeights(found, path)
        weights.setValue(self.select_vertices(20), self.joints[2], 1.0)
        skin.importWeights(found, path)
        for name, value in before.items():
            self.assertAlmostEqual(_weights(self.skin, 20)[name], value, places=5)

    def test_move_joints_keeps_mesh(self):
        before = cmds.pointPosition("{}.vtx[40]".format(self.geo), world=True)
        session = skin.MoveJointsSession([mlib.getNode(self.joints[1])]).start()
        self.assertTrue(session.isActive())
        cmds.move(1, 0, 0, self.joints[1], relative=True)
        session.finish()
        self.assertFalse(session.isActive())
        after = cmds.pointPosition("{}.vtx[40]".format(self.geo), world=True)
        for a, b in zip(before, after):
            self.assertAlmostEqual(a, b, places=4)
        with self.assertRaises(ValueError):
            skin.MoveJointsSession([])


class FitColumnTest(unittest.TestCase):
    """列を変えて合計を1にする計算(シーンを使わない)。"""

    def test_scales_other_free_columns(self):
        row = weights.fitColumn([0.5, 0.5, 0.0], 2, 0.2, [False, False, False])
        for actual, expected in zip(row, [0.4, 0.4, 0.2]):
            self.assertAlmostEqual(actual, expected)

    def test_keeps_locked_and_clamps_to_room(self):
        row = weights.fitColumn([0.3, 0.7, 0.0], 2, 0.9, [True, False, False])
        for actual, expected in zip(row, [0.3, 0.0, 0.7]):
            self.assertAlmostEqual(actual, expected)

    def test_fills_room_when_others_are_zero(self):
        row = weights.fitColumn([1.0, 0.0], 0, 0.4, [False, False])
        self.assertAlmostEqual(row[0], 1.0)


class MoveTest(_Case):
    """インフルエンス間の移動。"""

    def test_move_weights_between_influences(self):
        found = self.select_vertices(20, 21)
        before = _weights(self.skin, 20)
        weights.moveWeights(found, self.joints[0], self.joints[1])
        after = _weights(self.skin, 20)
        self.assertAlmostEqual(after[self.joints[0]], 0.0, places=6)
        self.assertAlmostEqual(after[self.joints[1]], before[self.joints[0]] + before[self.joints[1]], places=5)
        with self.assertRaises(ValueError):
            weights.moveWeights(found, self.joints[1], self.joints[1])


class BlendTest(_Case):
    """スライド・ソフト選択・ランプ。"""

    def tearDown(self):
        """ソフト選択を無効へ戻す。"""
        cmds.softSelect(softSelectEnabled=False)

    def test_slide_session_writes_once_on_finish(self):
        found = self.select_vertices(20, 21)
        start = _weights(self.skin, 20)[self.joints[1]]
        session = blend.SlideSession(found, self.joints[1])
        session.apply(0.2)
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[1]], min(1.0, start + 0.2), places=5)
        session.apply(0.1)
        self.assertEqual(session.finish(), 2)
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[1]], min(1.0, start + 0.1), places=5)
        self.assert_normalized(20)
        cmds.undo()
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[1]], start, places=5)

    def test_slide_cancel_restores(self):
        found = self.select_vertices(20)
        start = _weights(self.skin, 20)[self.joints[1]]
        session = blend.SlideSession(found, self.joints[1])
        session.apply(-0.3)
        session.cancel()
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[1]], start, places=5)
        self.assertEqual(session.finish(), 0)

    def test_soft_target_without_soft_selection(self):
        cmds.softSelect(softSelectEnabled=False)
        self.select_vertices(20, 21)
        found, falloff = blend.softTarget()
        self.assertEqual(falloff, {20: 1.0, 21: 1.0})
        self.assertEqual(str(found.skin), self.skin)

    def test_soft_selection_weights_fall_off(self):
        cmds.softSelect(softSelectEnabled=True, softSelectDistance=3.0, softSelectFalloff=0)
        self.select_vertices(36)
        found, falloff = blend.softTarget()
        self.assertGreater(len(falloff), 1)
        self.assertAlmostEqual(falloff[36], 1.0, places=5)
        self.assertTrue(any(0.0 < value < 1.0 for value in falloff.values()))
        blend.fromSoftSelection(self.joints[2], found, falloff)
        some = [index for index, value in falloff.items() if 0.0 < value < 1.0][0]
        self.assertAlmostEqual(_weights(self.skin, some)[self.joints[2]], falloff[some], places=4)

    def test_ramp_between_two_joints(self):
        cmds.select(self.geo)
        cmds.select(["{}.vtx[{}]".format(self.geo, index) for index in range(cmds.polyEvaluate(self.geo, vertex=True))
                     if 0.0 <= cmds.pointPosition("{}.vtx[{}]".format(self.geo, index))[1] <= 4.0])
        found = target.require()
        blend.ramp(found, self.joints[0], self.joints[1])
        middle = [index for index in found.vertices
                  if abs(cmds.pointPosition("{}.vtx[{}]".format(self.geo, index))[1] - 2.0) < 1e-4][0]
        values = _weights(self.skin, middle)
        total = values[self.joints[0]] + values[self.joints[1]]
        self.assertAlmostEqual(values[self.joints[1]] / total, 0.5, places=4)
        self.assert_normalized(middle)
        with self.assertRaises(ValueError):
            blend.ramp(found, self.joints[0], self.joints[0])
        with self.assertRaises(ValueError):
            blend.ramp(found, self.joints[0], self.joints[1], easing="cubic")


class SymmetryTest(_Case):
    """左右の名前と、選んだ頂点だけのミラー。"""

    def test_opposite_names(self):
        cases = {"L_arm": "R_arm", "arm_l": "arm_r", "leg_L_01": "leg_R_01", "leftArm": "rightArm",
                 "armRight": "armLeft", "ns:L_hand": "ns:R_hand", "spine": "spine", "Lip": "Lip"}
        for name, expected in cases.items():
            self.assertEqual(symmetry.oppositeName(name), expected, name)

    def side_vertex(self):
        """+X 側(x > 0.5)にある頂点を1つ返す。"""
        for index in range(cmds.polyEvaluate(self.geo, vertex=True)):
            if cmds.pointPosition("{}.vtx[{}]".format(self.geo, index), local=True)[0] > 0.5:
                return index
        raise AssertionError("no side vertex")

    def test_missing_opposites(self):
        self.assertEqual(symmetry.missingOpposites(["L_arm", "R_arm", "L_hand", "spine"]), [("L_hand", "R_hand")])
        cmds.select(clear=True)
        cmds.joint(name="L_lonely", position=(2, 4, 0))
        cmds.skinCluster(self.skin, edit=True, addInfluence="L_lonely", weight=0.0)
        cmds.select(self.geo)
        report = reduction.analyze(target.require())
        self.assertEqual(report["missingOpposites"], [("L_lonely", "R_lonely")])
        self.assertIn("No opposite side", reduction.formatReport(report))

    def test_mirror_map_finds_opposite_vertex(self):
        vertex = self.side_vertex()
        mesh = mlib.getNode(self.shape)
        pairs = symmetry.mirrorMap(mesh, [vertex])
        position = cmds.pointPosition("{}.vtx[{}]".format(self.geo, vertex), local=True)
        mirrored = cmds.pointPosition("{}.vtx[{}]".format(self.geo, pairs[vertex]), local=True)
        self.assertAlmostEqual(mirrored[0], -position[0], places=4)
        self.assertAlmostEqual(mirrored[1], position[1], places=4)

    def test_mirror_selected_swaps_left_and_right(self):
        cmds.select(clear=True)
        left = cmds.joint(name="L_side", position=(2, 4, 0))
        cmds.select(clear=True)
        right = cmds.joint(name="R_side", position=(-2, 4, 0))
        cmds.skinCluster(self.skin, edit=True, addInfluence=[left, right], weight=0.0)
        vertex = self.side_vertex()
        found = self.select_vertices(vertex)
        weights.setValue(found, left, 1.0)
        copied, unmatched = symmetry.mirrorVertices(found, "x")
        self.assertEqual((copied, unmatched), (1, 0))
        opposite = symmetry.mirrorMap(mlib.getNode(self.shape), [vertex])[vertex]
        self.assertAlmostEqual(_weights(self.skin, opposite)[right], 1.0, places=5)

    def test_mirror_selected_needs_opposite_influences(self):
        cmds.select(clear=True)
        left = cmds.joint(name="L_only", position=(2, 4, 0))
        cmds.skinCluster(self.skin, edit=True, addInfluence=[left], weight=0.0)
        with self.assertRaises(ValueError):
            symmetry.mirrorVertices(self.select_vertices(self.side_vertex()), "x")


class GrowShrinkTest(_Case):
    """選択を広げる・狭める。"""

    def test_grow_then_shrink_returns(self):
        found = self.select_vertices(36)
        grown = selectionTools.grow(found)
        self.assertGreater(grown, 1)
        self.assertEqual(selectionTools.shrink(target.require()), 1)


class QuantizeTest(unittest.TestCase):
    """丸めと1頂点のリダクション(シーンを使わない)。"""

    def test_quantize_keeps_exact_sum(self):
        row = reduction.quantizeRow([1 / 3.0, 1 / 3.0, 1 / 3.0], 255, [False] * 3)
        self.assertEqual(sorted(int(round(value * 255)) for value in row), [85, 85, 85])
        row = reduction.quantizeRow([0.5, 0.3, 0.2], 100, [False] * 3)
        self.assertEqual([int(round(value * 100)) for value in row], [50, 30, 20])
        row = reduction.quantizeRow([0.333, 0.333, 0.334], 10, [False] * 3)
        self.assertEqual(sum(int(round(value * 10)) for value in row), 10)

    def test_reduce_row_prunes_limits_and_rounds(self):
        row = reduction.reduceRow([0.6, 0.3, 0.08, 0.02], [False] * 4, threshold=0.05, maxInfluences=2, steps=100)
        self.assertEqual([int(round(value * 100)) for value in row], [67, 33, 0, 0])

    def test_reduce_row_keeps_largest_when_all_tiny(self):
        row = reduction.reduceRow([0.01, 0.02], [False, False], threshold=0.5)
        self.assertEqual(row, [0.0, 1.0])

    def test_reduce_row_keeps_locked(self):
        row = reduction.reduceRow([0.2, 0.5, 0.3], [True, False, False], maxInfluences=2)
        self.assertAlmostEqual(row[0], 0.2)
        self.assertAlmostEqual(row[1], 0.8)
        self.assertAlmostEqual(row[2], 0.0)


class ReductionTest(_Case):
    """メッシュのリダクションと診断。"""

    def test_reduce_whole_mesh_to_game_limits(self):
        cmds.select(self.geo)
        found = target.require()
        before = reduction.analyze(found, threshold=0.05, maxInfluences=1)
        self.assertGreater(before["maxUsed"], 1)
        self.assertTrue(before["overLimit"])
        summary = reduction.reduce([found], threshold=0.05, maxInfluences=2, steps=255)
        self.assertEqual(summary["meshes"], 1)
        after = reduction.analyze(found, threshold=0.05, maxInfluences=2, steps=255)
        self.assertLessEqual(after["maxUsed"], 2)
        self.assertEqual(reduction.problemVertices(after), [])
        for vertex in (0, 20, 40):
            values = _weights(self.skin, vertex).values()
            self.assertAlmostEqual(sum(values), 1.0, places=6)
            for value in values:
                self.assertAlmostEqual(value * 255, round(value * 255), places=3)

    def test_reduce_sets_skin_limit_and_removes_unused(self):
        cmds.select(clear=True)
        extra = cmds.joint(name="swkUnused", position=(3, 3, 0))
        cmds.skinCluster(self.skin, edit=True, addInfluence=extra, weight=0.0)
        cmds.select(self.geo)
        summary = reduction.reduce([target.require()], maxInfluences=2, removeUnused=True, setSkinLimit=True)
        self.assertEqual(summary["removedInfluences"], 1)
        self.assertEqual(cmds.getAttr(self.skin + ".maxInfluences"), 2)
        self.assertTrue(cmds.getAttr(self.skin + ".maintainMaxInfluences"))

    def test_reduce_several_meshes_in_one_undo(self):
        other = cmds.polyCylinder(name="swkOther", height=8, subdivisionsY=4)[0]
        cmds.move(0, 4, 0, other)
        cmds.skinCluster(self.joints, other, toSelectedBones=True, maximumInfluences=3)
        cmds.select(self.geo, other)
        meshes = skin.selectedMeshes()
        targets = [target.Target(mesh, mesh.getSkinClusters()[0], None) for mesh in meshes]
        before = _weights(self.skin, 20)
        self.assertEqual(reduction.reduce(targets, maxInfluences=1)["meshes"], 2)
        cmds.undo()
        for name, value in before.items():
            self.assertAlmostEqual(_weights(self.skin, 20)[name], value, places=5)

    def test_select_problems_and_report(self):
        cmds.select(self.geo)
        found = target.require()
        count = reduction.selectProblems(found, maxInfluences=1)
        self.assertGreater(count, 0)
        report = reduction.analyze(found, maxInfluences=1)
        self.assertEqual(len(report["leastUsed"]), 3)
        self.assertLessEqual(report["leastUsed"][0][1], report["leastUsed"][-1][1])
        text = reduction.formatReport(report, "swkGeo")
        self.assertIn("max influences used", text)
        self.assertIn("Least used", text)
        with self.assertRaises(ValueError):
            reduction.reduce([found], maxInfluences=0)


class ShellTest(_Case):
    """シェルごとの剛体化。"""

    def test_rigid_shells(self):
        first = cmds.polyCube(name="swkPartA")[0]
        cmds.move(0, 2, 0, first)
        second = cmds.polyCube(name="swkPartB")[0]
        cmds.move(0, 6, 0, second)
        united = cmds.polyUnite(first, second, name="swkParts", constructionHistory=False)[0]
        part_skin = cmds.skinCluster(self.joints, united, toSelectedBones=True, maximumInfluences=3)[0]
        cmds.select(united)
        found = target.require()
        self.assertEqual(len(shells.shellsOf(found.mesh)), 2)
        self.assertEqual(shells.unifyShells(found, "rigid"), 2)
        for shell in shells.shellsOf(found.mesh):
            rows = [_weights(part_skin, vertex) for vertex in shell]
            for row in rows:
                self.assertEqual(sorted(round(value, 5) for value in row.values() if value > 1e-6), [1.0])
                self.assertEqual(row, rows[0])
        with self.assertRaises(ValueError):
            shells.unifyShells(found, "blend")


class TransferTest(_Case):
    """位置を含む書き出しと、番号・位置での読込み。"""

    def export(self):
        """円柱のウェイトを書き出し、パスを返す。"""
        cmds.select(self.geo)
        path = os.path.join(tempfile.mkdtemp(), "weights.json")
        self.assertEqual(transfer.exportWeights(target.require(), path), cmds.polyEvaluate(self.geo, vertex=True))
        return path

    def test_index_round_trip_and_selected_only(self):
        path = self.export()
        before = _weights(self.skin, 20)
        cmds.select(self.geo)
        weights.setValue(self.select_vertices(20, 21), self.joints[2], 1.0)
        transfer.importWeights(self.select_vertices(20), path, "index")
        for name, value in before.items():
            self.assertAlmostEqual(_weights(self.skin, 20)[name], value, places=5)
        self.assertAlmostEqual(_weights(self.skin, 21)[self.joints[2]], 1.0, places=5)

    def test_position_import_onto_other_topology(self):
        path = self.export()
        other = cmds.polyCylinder(name="swkDense", height=8, subdivisionsY=16, subdivisionsX=8)[0]
        cmds.move(0, 4, 0, other)
        cmds.makeIdentity(other, apply=True, translate=True)
        other_skin = cmds.skinCluster(self.joints, other, toSelectedBones=True, maximumInfluences=1)[0]
        cmds.select(other)
        found = target.require()
        with self.assertRaises(ValueError):
            transfer.importWeights(found, path, "index")
        transfer.importWeights(found, path, "position")
        # 同じ位置にある頂点(元の円柱の頂点20と同じ高さ・角度)は、同じウェイトになる。
        source = cmds.pointPosition("{}.vtx[20]".format(self.geo), local=True)
        for index in range(cmds.polyEvaluate(other, vertex=True)):
            position = cmds.pointPosition("{}.vtx[{}]".format(other, index), local=True)
            if sum((a - b) ** 2 for a, b in zip(position, source)) < 1e-8:
                expected = _weights(self.skin, 20)
                actual = _weights(other_skin, index)
                for name, value in expected.items():
                    self.assertAlmostEqual(actual[name], value, places=5)
                break
        else:
            self.fail("no matching vertex")

    def test_missing_influences(self):
        cmds.select(clear=True)
        extra = cmds.joint(name="swkExtra", position=(2, 4, 0))
        cmds.skinCluster(self.skin, edit=True, addInfluence=extra, weight=0.0)
        path = self.export()
        other = cmds.polyCylinder(name="swkSmall", height=8, subdivisionsY=8, subdivisionsX=8)[0]
        cmds.move(0, 4, 0, other)
        cmds.makeIdentity(other, apply=True, translate=True)
        other_skin = cmds.skinCluster(self.joints, other, toSelectedBones=True)[0]
        cmds.select(other)
        with self.assertRaises(ValueError):
            transfer.importWeights(target.require(), path, "index")
        transfer.importWeights(target.require(), path, "index", addMissing=True)
        self.assertIn(extra, cmds.skinCluster(other_skin, query=True, influence=True))

    def test_reads_mlib_skin_weights_format(self):
        cmds.select(self.geo)
        path = os.path.join(tempfile.mkdtemp(), "mlib.json")
        skin.exportWeights(target.require(), path)
        data = transfer.readFile(path)
        count = cmds.polyEvaluate(self.geo, vertex=True)
        self.assertEqual(len(data["positions"]), count)
        self.assertEqual(len(data["rows"]), count)
        self.assertEqual(sorted(data["influences"]), sorted(self.joints))
        before = _weights(self.skin, 20)
        weights.setValue(self.select_vertices(20), self.joints[2], 1.0)
        transfer.importWeights(self.select_vertices(20), path, "position")
        for name, value in before.items():
            self.assertAlmostEqual(_weights(self.skin, 20)[name], value, places=5)


class LoopRingTest(_Case):
    """エッジのループ・リング。"""

    def middle_edge(self, horizontal=True):
        """高さ4の輪にある横のエッジ(horizontal=False なら高さ4から上へ伸びる縦のエッジ)を返す。"""
        for index in range(cmds.polyEvaluate(self.geo, edge=True)):
            names = cmds.polyListComponentConversion("{}.e[{}]".format(self.geo, index), toVertex=True)
            heights = [cmds.pointPosition(name)[1] for name in cmds.ls(names, flatten=True)]
            if horizontal and all(abs(height - 4.0) < 1e-4 for height in heights):
                return index
            if not horizontal and sorted(round(height, 4) for height in heights) == [4.0, 5.0]:
                return index
        raise AssertionError("no edge")

    def test_horizontal_loop_goes_around(self):
        cmds.select("{}.e[{}]".format(self.geo, self.middle_edge()))
        self.assertEqual(selectionTools.selectLoop(), 8)

    def test_vertical_loop_stops_at_caps(self):
        cmds.select("{}.e[{}]".format(self.geo, self.middle_edge(horizontal=False)))
        self.assertEqual(selectionTools.selectLoop(), 8)

    def test_ring_crosses_quads_until_caps(self):
        cmds.select("{}.e[{}]".format(self.geo, self.middle_edge()))
        self.assertEqual(selectionTools.selectRing(), 9)

    def test_needs_edges(self):
        cmds.select(self.geo)
        with self.assertRaises(ValueError):
            selectionTools.selectLoop()


class SampleTest(_Case):
    """見本の頂点から配る。"""

    def test_average_of_samples(self):
        self.assertEqual(sample.sampleVertices(self.select_vertices(4, 60)), 2)
        first, second = _weights(self.skin, 4), _weights(self.skin, 60)
        sample.apply(self.select_vertices(36), "average")
        for name in first:
            self.assertAlmostEqual(_weights(self.skin, 36)[name], (first[name] + second[name]) / 2.0, places=5)

    def test_proximity_matches_sample_at_same_position(self):
        sample.sampleVertices(self.select_vertices(4, 60))
        expected = _weights(self.skin, 60)
        sample.apply(self.select_vertices(60, 36), "proximity")
        for name, value in expected.items():
            self.assertAlmostEqual(_weights(self.skin, 60)[name], value, places=5)
        self.assert_normalized(36)

    def test_errors(self):
        sample._sample["rows"] = None
        with self.assertRaises(ValueError):
            sample.apply(self.select_vertices(36))
        sample.sampleVertices(self.select_vertices(4))
        with self.assertRaises(ValueError):
            sample.apply(self.select_vertices(36), "nearest")


class TableTest(_Case):
    """ウェイトの表と、セルの書き換え。"""

    def test_table_and_set_values(self):
        found = self.select_vertices(20, 21)
        data = weights.table(found)
        self.assertEqual(data["vertices"], found.vertices)
        self.assertEqual(len(data["rows"]), 2)
        for total in data["sums"]:
            self.assertAlmostEqual(total, 1.0, places=5)
        weights.setVertexValues(found, [20], self.joints[1], 0.3)
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[1]], 0.3, places=5)
        self.assert_normalized(20)
        self.assertTrue(weights.table(found, limit=1)["truncated"])


class SmoothingMethodTest(_Case):
    """スムーズの重みの付け方。"""

    def test_neighbor_weights_sum_to_one(self):
        mesh = mlib.getNode(self.shape)
        for method in smoothing.METHODS:
            neighbors = smoothing.neighborWeights(mesh, method)
            self.assertAlmostEqual(sum(weight for _other, weight in neighbors[36]), 1.0, places=6)
            self.assertEqual(len(neighbors[36]), 4)
        with self.assertRaises(ValueError):
            smoothing.neighborWeights(mesh, "laplace")

    def test_gap_radius_links_unconnected_vertices(self):
        first = cmds.polyCube(name="swkGapA")[0]
        second = cmds.polyCube(name="swkGapB")[0]
        cmds.move(1.1, 0, 0, second)
        united = cmds.polyUnite(first, second, name="swkGap", constructionHistory=False)[0]
        mesh = mlib.getNode(united).getShapes()[0]
        plain = smoothing.neighborWeights(mesh, "uniform")
        linked = smoothing.neighborWeights(mesh, "uniform", radius=0.5)
        self.assertGreater(sum(len(item) for item in linked), sum(len(item) for item in plain))

    def test_methods_change_results_and_keep_max(self):
        weights.setValue(self.select_vertices(36), self.joints[2], 1.0)
        found = self.select_vertices(36)
        weights.smooth(found, 1.0, 1, "cotangent", 0.0, keepMax=True)
        values = _weights(self.skin, 36)
        self.assert_normalized(36)
        self.assertLessEqual(sum(1 for value in values.values() if value > 0.0),
                             cmds.getAttr(self.skin + ".maxInfluences"))

    def test_smooth_row_sharpen_moves_away(self):
        row = smoothing.smoothRow([0.6, 0.4], [([0.5, 0.5], 1.0)], -1.0, [False, False])
        self.assertGreater(row[0], 0.6)
        self.assertAlmostEqual(sum(row), 1.0)


class PaintSessionTest(_Case):
    """ブラシの1ストローク(Maya のペイントを通さずに計算を確かめる)。"""

    def mesh_target(self):
        """メッシュ全体の対象。"""
        cmds.select(self.geo)
        return target.require()

    def test_smooth_stroke_is_one_undo(self):
        weights.setValue(self.select_vertices(36), self.joints[2], 1.0)
        before = _weights(self.skin, 36)[self.joints[2]]
        session = paint.PaintSession(self.mesh_target(), "smooth")
        session.dab(36, 1.0)
        session.dab(36, 0.5)
        self.assertLess(_weights(self.skin, 36)[self.joints[2]], before)
        self.assertEqual(session.finish(), 1)
        self.assert_normalized(36)
        cmds.undo()
        self.assertAlmostEqual(_weights(self.skin, 36)[self.joints[2]], before, places=5)

    def test_remove_add_and_transfer(self):
        found = self.mesh_target()
        start = _weights(self.skin, 20)
        session = paint.PaintSession(found, "remove", self.joints[0])
        session.dab(20, 1.0)
        session.finish()
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[0]], 0.0, places=5)
        session = paint.PaintSession(found, "add", self.joints[0])
        session.dab(20, 0.5)
        session.finish()
        self.assertAlmostEqual(_weights(self.skin, 20)[self.joints[0]], 0.5, places=5)
        before = _weights(self.skin, 20)
        session = paint.PaintSession(found, "transfer", self.joints[1], self.joints[0])
        session.dab(20, 1.0)
        session.finish()
        after = _weights(self.skin, 20)
        self.assertAlmostEqual(after[self.joints[0]], 0.0, places=5)
        self.assertAlmostEqual(after[self.joints[1]], before[self.joints[1]] + before[self.joints[0]], places=5)
        self.assertNotEqual(start, after)

    def test_cancel_and_errors(self):
        found = self.mesh_target()
        before = _weights(self.skin, 20)
        session = paint.PaintSession(found, "remove", self.joints[0])
        session.dab(20, 1.0)
        session.cancel()
        self.assertEqual(session.finish(), 0)
        for name, value in before.items():
            self.assertAlmostEqual(_weights(self.skin, 20)[name], value, places=5)
        with self.assertRaises(ValueError):
            paint.PaintSession(found, "remove")
        with self.assertRaises(ValueError):
            paint.PaintSession(found, "transfer", self.joints[0], self.joints[0])
        with self.assertRaises(ValueError):
            paint.PaintSession(found, "blur")


class MoreToolsTest(_Case):
    """Hold/Fetch・別メッシュからのコピー・値の範囲での選択・Flood・デフォーマーの取り込み・ボーン数の削減。"""

    def test_hold_and_fetch(self):
        cmds.select(self.geo)
        found = target.require()
        before = _weights(self.skin, 20)
        self.assertFalse(hold.hasHold(found))
        hold.hold(found)
        weights.setValue(self.select_vertices(20, 21), self.joints[2], 1.0)
        cmds.select(self.geo)
        hold.fetch(target.require())
        for name, value in before.items():
            self.assertAlmostEqual(_weights(self.skin, 20)[name], value, places=5)

    def test_copy_from_mesh_to_selected_vertices(self):
        other = cmds.polyCylinder(name="swkSource", height=8, subdivisionsY=8, subdivisionsX=8)[0]
        cmds.move(0, 4, 0, other)
        cmds.makeIdentity(other, apply=True, translate=True)
        source_skin = cmds.skinCluster(self.joints, other, toSelectedBones=True, maximumInfluences=1)[0]
        cmds.select(other)
        source = target.require()
        destination = self.select_vertices(20)
        self.assertEqual(transfer.copyFromMesh(source, destination), 1)
        expected = cmds.skinPercent(source_skin, "{}.vtx[20]".format(other), query=True, value=True)
        actual = cmds.skinPercent(self.skin, "{}.vtx[20]".format(self.geo), query=True, value=True)
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=5)
        with self.assertRaises(ValueError):
            transfer.copyFromMesh(destination, destination)

    def test_vertices_in_range_and_flood(self):
        cmds.select(self.geo)
        found = target.require()
        weights.flood(found, self.joints[1], 1.0)
        self.assertEqual(len(influences.verticesInRange(found, self.joints[1], 0.99, 1.0)),
                         cmds.polyEvaluate(self.geo, vertex=True))
        self.assertEqual(influences.verticesInRange(found, self.joints[0], 0.5, 1.0), [])
        self.assertEqual(influences.selectInRange(found, self.joints[1], 0.5, 1.0),
                         cmds.polyEvaluate(self.geo, vertex=True))
        with self.assertRaises(ValueError):
            influences.verticesInRange(found, self.joints[0], 0.8, 0.2)

    def test_deformer_weights_to_influence(self):
        cluster = cmds.cluster("{}.vtx[0:30]".format(self.geo), name="swkCluster")[0]
        cmds.percent(cluster, "{}.vtx[0:30]".format(self.geo), value=0.25)
        cmds.select(self.geo)
        found = target.require()
        self.assertIn(cluster, [node.getNodeName() for node in deformers.listDeformers(found.mesh)])
        deformers.toInfluence(found, cluster, self.joints[2])
        self.assertAlmostEqual(_weights(self.skin, 10)[self.joints[2]], 0.25, places=4)
        self.assert_normalized(10)
        with self.assertRaises(ValueError):
            deformers.toInfluence(found, "missingDeformer", self.joints[2])

    def test_assign_closest_joint(self):
        cmds.select(self.geo)
        found = target.require()
        weights.assignClosest(found)
        bottom = [index for index in range(cmds.polyEvaluate(self.geo, vertex=True))
                  if cmds.pointPosition("{}.vtx[{}]".format(self.geo, index))[1] < 1.0][0]
        top = [index for index in range(cmds.polyEvaluate(self.geo, vertex=True))
               if cmds.pointPosition("{}.vtx[{}]".format(self.geo, index))[1] > 7.5][0]
        self.assertAlmostEqual(_weights(self.skin, bottom)[self.joints[0]], 1.0, places=5)
        self.assertAlmostEqual(_weights(self.skin, top)[self.joints[1]] + _weights(self.skin, top)[self.joints[2]],
                               1.0, places=5)
        for vertex in (bottom, top, 40):
            self.assertEqual(sum(1 for value in _weights(self.skin, vertex).values() if value > 1e-6), 1)

    def test_remove_matching_helpers(self):
        cmds.select(self.joints[2])
        end = cmds.joint(name="swkTip_end", position=(0, 10, 0))
        cmds.skinCluster(self.skin, edit=True, addInfluence=end, weight=0.0)
        weights.setValue(self.select_vertices(60), end, 0.5)
        cmds.select(self.geo)
        found = target.require()
        self.assertEqual([node.getNodeName() for node in influences.matchingInfluences(found, "*_end")], [end])
        before = _weights(self.skin, 60)
        removed = influences.removeMatching(found, "*_end, *_helper")
        self.assertEqual(removed[0][0], end)
        self.assertNotIn(end, cmds.skinCluster(self.skin, query=True, influence=True))
        self.assertAlmostEqual(_weights(self.skin, 60)[self.joints[2]], before[self.joints[2]] + before[end], places=5)
        with self.assertRaises(ValueError):
            influences.removeMatching(found, "*_nothing")

    def test_skin_settings(self):
        cmds.select(self.geo)
        found = target.require()
        self.assertEqual(skin.getSettings(found)["normalizeWeights"], "interactive")
        changed = skin.setSettings(found, skinningMethod="dualQuaternion", maxInfluences=2, maintainMaxInfluences=True)
        self.assertEqual(changed, {"skinningMethod": "dualQuaternion", "normalizeWeights": "interactive",
                                   "maxInfluences": 2, "maintainMaxInfluences": True})
        self.assertEqual(cmds.getAttr(self.skin + ".skinningMethod"), 1)
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.skin + ".skinningMethod"), 0)
        with self.assertRaises(ValueError):
            skin.setSettings(found, skinningMethod="spline")

    def test_limit_bones_merges_into_parents(self):
        cmds.select(self.geo)
        found = target.require()
        removed = reduction.limitBones(found, 1)
        self.assertEqual(len(removed), 2)
        self.assertEqual(cmds.skinCluster(self.skin, query=True, influence=True), [self.joints[0]])
        self.assert_normalized(40)
        with self.assertRaises(ValueError):
            reduction.limitBones(found, 0)


class SelectionHelperTest(_Case):
    """頂点の選択の補助。"""

    def test_select_vertices_and_clear(self):
        mesh = mlib.getNode(self.shape)
        self.assertEqual(target.selectVertices(mesh, [1, 2, 3]), 3)
        self.assertEqual(len(Selection.capture().getComponents()[0].indices), 3)
        self.assertEqual(target.selectVertices(mesh, []), 0)
        self.assertEqual(cmds.ls(selection=True), [])


if __name__ == "__main__":
    unittest.main()
