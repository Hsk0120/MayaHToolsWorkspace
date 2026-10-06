"""BlendShape編集・ベイク・保存復元を実際の変形とUndoで検証する。"""

import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest import mock

import hlib
import maya.cmds as cmds


class BlendShapeEditTest(unittest.TestCase):
    """各テストが作成したシーンだけを破棄するスタンドアロン用テスト。"""

    def setUp(self):
        self.before = set(cmds.ls(long=True))
        cmds.undoInfo(state=True)
        self.base = cmds.polyCube(ch=False)[0]
        self.target = cmds.duplicate(self.base)[0]
        cmds.move(0, 2, 0, self.target + ".vtx[0]", relative=True)
        self.bs = hlib.getNode(cmds.blendShape(self.target, self.base)[0])
        self.bs.getPlug("weight")[0].setAlias("smile")
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        added = set(cmds.ls(long=True)) - self.before
        for node in sorted(added, key=len, reverse=True):
            if cmds.objExists(node):
                cmds.delete(node)
        self.directory.cleanup()

    def point(self, vertex=0):
        """ベース頂点のオブジェクト空間位置を照会する。"""
        return cmds.xform(self.base + ".vtx[{}]".format(vertex), query=True, translation=True, objectSpace=True)

    def bake(self):
        """入力メッシュを削除してMaya標準のベイク状態にする。"""
        cmds.delete(self.target)

    def inbetween(self, relative=False):
        """heroとは異なる方向の中間形状を追加する。"""
        mesh = cmds.polyCube(ch=False)[0]
        cmds.move(0, 0, 1, mesh + ".vtx[0]", relative=True)
        self.bs.addInBetween("smile", mesh, 0.5, relative=relative)
        cmds.delete(mesh)

    def test_strict_target_listing(self):
        self.bs.getPlug("envelope").setAlias("allShapes")
        self.bs.getPlug("weight")[7].set(0)
        self.assertEqual(self.bs.getTargetIndices(), [0])
        self.assertEqual(self.bs.getTargetPlug("smile"), self.bs.getPlug("weight")[0])
        with self.assertRaises(ValueError):
            self.bs.getTargetPlug("allShapes")

    def test_get_live_deltas_at_zero_weight(self):
        cmds.move(0, 3, 0, self.target + ".vtx[0]", relative=True)
        self.assertAlmostEqual(self.bs.getTargetDeltas("smile")[0].y, 5)

    def test_set_deltas_guard_and_undo(self):
        with self.assertRaises(ValueError):
            self.bs.setTargetDeltas(0, {0: (0, 4, 0)})
        self.bs.setTargetDeltas(0, {0: (0, 4, 0)}, disconnect=True)
        self.assertAlmostEqual(self.bs.getTargetDeltas(0)[0].y, 4)
        cmds.undo()
        self.assertAlmostEqual(self.bs.getTargetDeltas(0)[0].y, 2)
        cmds.redo()
        self.bs.getTargetPlug(0).set(1)
        self.assertAlmostEqual(self.point()[1], 3.5)

    def test_empty_deltas(self):
        self.bake()
        self.bs.setTargetDeltas(0, {})
        self.bs.getTargetPlug(0).set(1)
        self.assertAlmostEqual(self.point()[1], -0.5)
        self.assertEqual(self.bs.getTargetDeltas(0), {})

    def test_vertex_weights_and_validation(self):
        self.bs.setTargetWeights(0, {0: 0.25})
        self.assertEqual(self.bs.getTargetWeights(0), [0.25] + [1.0] * 7)
        self.bs.getTargetPlug(0).set(1)
        self.assertAlmostEqual(self.point()[1], 0.0)
        with self.assertRaises(ValueError):
            self.bs.setTargetWeights(0, {0: 0.9, 8: 0.0})
        self.assertAlmostEqual(self.bs.getTargetWeights(0)[0], 0.25)

    def test_replace_retains_alias_value(self):
        mesh = cmds.polyCube(ch=False)[0]
        cmds.move(0, 4, 0, mesh + ".vtx[0]", relative=True)
        self.bs.getTargetPlug(0).set(0.5)
        self.bs.replaceTarget("smile", mesh)
        self.assertEqual(self.bs.getTargetAliases(), ["smile"])
        self.assertAlmostEqual(self.bs.getTargetPlug(0).get(), 0.5)
        self.assertAlmostEqual(self.point()[1], 1.5)

    def test_inbetween_add_remove_undo(self):
        self.inbetween()
        self.assertEqual(self.bs.getInBetweenWeights(0), [0.5])
        self.bs.getTargetPlug(0).set(0.5)
        self.assertAlmostEqual(self.point()[2], 1.5)
        self.bs.removeInBetween(0, 0.5)
        self.assertEqual(self.bs.getInBetweenWeights(0), [])
        self.assertAlmostEqual(self.point()[2], 0.5)
        cmds.undo()
        self.assertEqual(self.bs.getInBetweenWeights(0), [0.5])
        self.assertAlmostEqual(self.point()[2], 1.5)
        cmds.redo()
        self.assertEqual(self.bs.getInBetweenWeights(0), [])

    def test_remove_baked_target_undo(self):
        self.bake()
        self.inbetween()
        self.bs.setTargetWeights(0, {0: 0.3})
        self.bs.removeTarget(0)
        self.assertEqual(self.bs.getTargetIndices(), [])
        cmds.undo()
        self.assertEqual(self.bs.getTargetIndices(), [0])
        self.assertEqual(self.bs.getInBetweenWeights(0), [0.5])
        self.assertAlmostEqual(self.bs.getTargetWeights(0)[0], 0.3)
        self.assertAlmostEqual(self.bs.getTargetDeltas(0)[0].y, 2)
        cmds.redo()
        self.assertEqual(self.bs.getTargetIndices(), [])

    def test_duplicate_bakes_live_and_inbetweens(self):
        self.inbetween()
        self.bs.setTargetWeights(0, {0: 0.5})
        plug = self.bs.duplicateTarget("smile", weight_index=5, alias="smileCopy")
        self.assertEqual(self.bs.getTargetIndices(), [0, 5])
        self.assertEqual(self.bs.getInBetweenWeights(5), [0.5])
        self.assertAlmostEqual(self.bs.getTargetWeights(5)[0], 0.5)
        cmds.move(0, 3, 0, self.target + ".vtx[0]", relative=True)
        plug.set(1)
        self.assertAlmostEqual(self.point()[1], 0.5)

    def test_flip_and_mirror(self):
        self.bake()
        self.bs.flipTarget(0)
        self.assertNotIn(0, self.bs.getTargetDeltas(0))
        self.assertAlmostEqual(self.bs.getTargetDeltas(0)[1].y, 2)
        cmds.undo()
        self.assertIn(0, self.bs.getTargetDeltas(0))
        self.bs.mirrorTarget(0, direction=1)
        self.assertEqual(set(self.bs.getTargetDeltas(0)), {0, 1})

    def test_roundtrip_and_load_undo(self):
        self.inbetween()
        self.bs.setTargetWeights(0, {0: 0.4})
        self.bs.getTargetPlug(0).set(0.5)
        path = os.path.join(self.directory.name, "face.json")
        self.bs.dumpTargets(path)
        expected = self.point()
        base2 = cmds.polyCube(ch=False)[0]
        restored = hlib.getNode(cmds.blendShape(base2)[0])
        restored.loadTargets(path)
        actual = cmds.xform(base2 + ".vtx[0]", query=True, translation=True, objectSpace=True)
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b)
        self.assertEqual(restored.getTargetAliases(), ["smile"])
        self.assertEqual(restored.getInBetweenWeights(0), [0.5])
        cmds.undo()
        self.assertEqual(restored.getTargetIndices(), [])
        cmds.redo()
        self.assertEqual(restored.getTargetIndices(), [0])

    def test_relative_roundtrip(self):
        self.bake()
        self.inbetween(relative=True)
        path = os.path.join(self.directory.name, "relative.json")
        self.bs.dumpTargets(path)
        base2 = cmds.polyCube(ch=False)[0]
        restored = hlib.getNode(cmds.blendShape(base2)[0])
        restored.loadTargets(path)
        for weight in (0.25, 0.5, 0.75, 1.0):
            self.bs.getTargetPlug(0).set(weight)
            restored.getTargetPlug(0).set(weight)
            actual = cmds.xform(base2 + ".vtx[0]", query=True, translation=True, objectSpace=True)
            for a, b in zip(actual, self.point()):
                self.assertAlmostEqual(a, b)

    def test_bad_file_does_not_mutate_scene(self):
        path = os.path.join(self.directory.name, "bad.json")
        self.bs.dumpTargets(path)
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
        data["targets"]["0"]["bases"]["0"]["items"]["6000"]["absolute"][0][0] = 100
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        base2 = cmds.polyCube(ch=False)[0]
        restored = hlib.getNode(cmds.blendShape(base2)[0])
        with self.assertRaises(ValueError):
            restored.loadTargets(path)
        self.assertEqual(restored.getTargetIndices(), [])

    def test_input_validation(self):
        for value in (0.0001, float("nan"), -6):
            with self.assertRaises(ValueError):
                self.bs.addInBetween(0, self.target, value)
        with self.assertRaises(ValueError):
            self.bs.duplicateTarget(0, weight_index=0)
        with self.assertRaises(ValueError):
            self.bs.duplicateTarget(0, alias="smile")
        with self.assertRaises(ValueError):
            self.bs.removeInBetween(0, 1.0)
        with self.assertRaises(ValueError):
            self.bs.flipTarget(0)

    def test_multiple_bases_sparse_indices_and_roundtrip(self):
        second = cmds.polyCube(ch=False)[0]
        cmds.blendShape(self.bs.getName(), edit=True, geometry=second)
        other = cmds.polyCube(ch=False)[0]
        cmds.move(0, 0, 3, other + ".vtx[2]", relative=True)
        self.bs.addTarget(other, base=second, weight_index=0)
        # ベース別に同じweight番号へ異なるデルタが保持される。
        self.assertAlmostEqual(self.bs.getTargetDeltas(0, base=second)[2].z, 3)
        self.bs.duplicateTarget(0, weight_index=8, alias="copyBoth")
        self.assertAlmostEqual(self.bs.getTargetDeltas(8, base=second)[2].z, 3)
        self.assertAlmostEqual(self.bs.getTargetDeltas(8, base=self.base)[0].y, 2)
        path = os.path.join(self.directory.name, "multi.json")
        self.bs.dumpTargets(path)
        new_a = cmds.polyCube(ch=False)[0]
        new_b = cmds.polyCube(ch=False)[0]
        restored = hlib.getNode(cmds.blendShape(new_a)[0])
        cmds.blendShape(restored.getName(), edit=True, geometry=new_b)
        restored.loadTargets(path)
        self.assertEqual(restored.getTargetIndices(), [0, 8])
        self.assertAlmostEqual(restored.getTargetDeltas(8, base=new_b)[2].z, 3)

    def test_topology_rejected_before_replace(self):
        wrong = cmds.polyPlane(ch=False)[0]
        with self.assertRaises(ValueError):
            self.bs.replaceTarget(0, wrong)
        self.assertAlmostEqual(self.bs.getTargetDeltas(0)[0].y, 2)

    def test_nondefault_full_weight_duplicate(self):
        self.bs.addTarget(self.target, weight_index=4, full_weight=0.8)
        self.bs.duplicateTarget(4, weight_index=5)
        self.assertEqual(self.bs.getInBetweenWeights(5), [0.8])
        self.bs.getTargetPlug(5).set(0.8)
        self.assertAlmostEqual(self.point()[1], 1.5)

    def test_base_weights_roundtrip(self):
        cmds.setAttr(self.bs.getName() + ".inputTarget[0].baseWeights[0]", 0.2)
        self.bs.getTargetPlug(0).set(1)
        path = os.path.join(self.directory.name, "mask.json")
        self.bs.dumpTargets(path)
        mesh = cmds.polyCube(ch=False)[0]
        restored = hlib.getNode(cmds.blendShape(mesh)[0])
        restored.loadTargets(path)
        point = cmds.xform(mesh + ".vtx[0]", query=True, translation=True, objectSpace=True)
        self.assertAlmostEqual(point[1], self.point()[1])

    def test_duplicate_undo_redo(self):
        self.inbetween()
        self.bs.duplicateTarget(0, weight_index=5)
        cmds.undo()
        self.assertEqual(self.bs.getTargetIndices(), [0])
        cmds.redo()
        self.assertEqual(self.bs.getTargetIndices(), [0, 5])
        self.assertEqual(self.bs.getInBetweenWeights(5), [0.5])

    def test_load_existing_and_topology_mismatch_rejected(self):
        path = os.path.join(self.directory.name, "face.json")
        self.bs.dumpTargets(path)
        with self.assertRaises(ValueError):
            self.bs.loadTargets(path)
        mesh = cmds.polyPlane(ch=False)[0]
        restored = hlib.getNode(cmds.blendShape(mesh)[0])
        with self.assertRaises(ValueError):
            restored.loadTargets(path)
        self.assertEqual(restored.getTargetIndices(), [])

    def test_load_failure_rolls_back(self):
        path = os.path.join(self.directory.name, "face.json")
        self.bs.dumpTargets(path)
        mesh = cmds.polyCube(ch=False)[0]
        restored = hlib.getNode(cmds.blendShape(mesh)[0])
        restored.getPlug("envelope").setLocked(True)
        with self.assertRaises(RuntimeError):
            restored.loadTargets(path)
        self.assertEqual(restored.getTargetIndices(), [])
        restored.getPlug("envelope").setLocked(False)

    def test_relative_set_deltas(self):
        self.bake()
        self.inbetween(relative=True)
        original = self.bs.getTargetDeltas(0, full_weight=0.5)
        self.bs.setTargetDeltas(0, {0: (0, 0, 3)}, full_weight=0.5)
        actual = self.bs.getTargetDeltas(0, full_weight=0.5)
        self.assertAlmostEqual(actual[0].z, 3)
        cmds.undo()
        self.assertAlmostEqual(self.bs.getTargetDeltas(0, full_weight=0.5)[0].z, original[0].z)

    def test_readers_do_not_use_commands(self):
        self.inbetween(relative=True)
        self.bs.setTargetWeights(0, {0: 0.2})
        cmds.move(0, 3, 0, self.target + ".vtx[0]", relative=True)
        path = os.path.join(self.directory.name, "readOnly.json")
        with self._no_commands():
            self.assertEqual(self.bs.getTargetIndices(base=self.base), [0])
            self.assertEqual(self.bs.getInBetweenWeights("smile", base=self.base), [0.5])
            self.assertAlmostEqual(self.bs.getTargetWeights(0)[0], 0.2)
            self.assertAlmostEqual(self.bs.getTargetDeltas(0)[0].y, 5)
            self.bs.dumpTargets(path)

    def test_fast_weights_have_no_undo_entry(self):
        previous = cmds.undoInfo(query=True, undoName=True)
        with self._no_commands():
            self.assertIs(self.bs.setTargetWeights(0, {0: 0.3}, fast=True), self.bs)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), previous)
        self.bs.getTargetPlug(0).set(1)
        self.assertAlmostEqual(self.point()[1], 0.1)

    def test_fast_deltas_disconnect_and_no_undo_entry(self):
        previous = cmds.undoInfo(query=True, undoName=True)
        with self._no_commands():
            self.bs.setTargetDeltas(0, {0: (0, 4, 0)}, disconnect=True, fast=True)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), previous)
        self.assertAlmostEqual(self.bs.getTargetDeltas(0)[0].y, 4)
        self.bs.getTargetPlug(0).set(1)
        self.assertAlmostEqual(self.point()[1], 3.5)
        with self._no_commands():
            self.bs.setTargetDeltas(0, {}, fast=True)
        self.assertAlmostEqual(self.point()[1], -0.5)

    def test_fast_replace_keeps_lock_and_weight(self):
        mesh = cmds.polyCube(ch=False)[0]
        cmds.move(0, 5, 0, mesh + ".vtx[0]", relative=True)
        self.bs.getTargetPlug(0).set(0.5)
        destination = self.bs.getPlug("inputTarget[0].inputTargetGroup[0].inputTargetItem[6000].inputGeomTarget")
        destination.setLocked(True)
        previous = cmds.undoInfo(query=True, undoName=True)
        with self._no_commands():
            self.bs.replaceTarget("smile", mesh, fast=True)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), previous)
        self.assertTrue(destination.isLocked())
        self.assertEqual(self.bs.getTargetAliases(), ["smile"])
        self.assertAlmostEqual(self.point()[1], 2)
        destination.setLocked(False)

    def test_fast_duplicate_matches_normal(self):
        self.inbetween(relative=True)
        self.bs.setTargetWeights(0, {0: 0.5})
        self.bs.duplicateTarget(0, weight_index=4, alias="normalCopy")
        previous = cmds.undoInfo(query=True, undoName=True)
        with self._no_commands():
            copied = self.bs.duplicateTarget(0, weight_index=5, alias="fastCopy", fast=True)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), previous)
        self.assertEqual(copied, self.bs.getTargetPlug("fastCopy"))
        for weight in (0.25, 0.5, 0.75, 1.0):
            self.bs.getTargetPlug(4).set(weight)
            expected = self.point()
            self.bs.getTargetPlug(4).set(0)
            self.bs.getTargetPlug(5).set(weight)
            for a, b in zip(self.point(), expected):
                self.assertAlmostEqual(a, b)
            self.bs.getTargetPlug(5).set(0)

    def test_fast_load_matches_normal_and_works_without_undo(self):
        self.inbetween(relative=True)
        self.bs.getTargetPlug(0).set(0.5)
        self.bs.setTargetWeights(0, {0: 0.6})
        path = os.path.join(self.directory.name, "fastLoad.json")
        self.bs.dumpTargets(path)
        mesh = cmds.polyCube(ch=False)[0]
        restored = hlib.getNode(cmds.blendShape(mesh)[0])
        cmds.undoInfo(stateWithoutFlush=False)
        try:
            with self._no_commands():
                restored.loadTargets(path, fast=True)
            self.assertFalse(cmds.undoInfo(query=True, state=True))
        finally:
            cmds.undoInfo(stateWithoutFlush=True)
        actual = cmds.xform(mesh + ".vtx[0]", query=True, translation=True, objectSpace=True)
        for a, b in zip(actual, self.point()):
            self.assertAlmostEqual(a, b)
        self.assertEqual(restored.getInBetweenWeights("smile"), [0.5])

    def test_fast_rejects_invalid_and_locked_without_silent_write(self):
        self.bake()
        self.bs.setTargetWeights(0, {0: 0.25})
        weights = self.bs.getPlug("inputTarget[0].inputTargetGroup[0].targetWeights")
        weights.setLocked(True)
        with self.assertRaises(RuntimeError):
            self.bs.setTargetWeights(0, {0: 0.8}, fast=True)
        self.assertAlmostEqual(self.bs.getTargetWeights(0)[0], 0.25)
        weights.setLocked(False)
        for fast in (1, None, "true"):
            with self.assertRaises(TypeError):
                self.bs.setTargetDeltas(0, {0: (0, 3, 0)}, fast=fast)
            with self.assertRaises(TypeError):
                self.bs.duplicateTarget(0, fast=fast)
            with self.assertRaises(TypeError):
                self.bs.loadTargets("unused.json", fast=fast)

    def test_target_vertices_zero_filter_and_tolerance(self):
        self.bs.setTargetDeltas(0, {7: (0, 0, 0), 3: (0, 0.001, 0), 1: (0, 2, 0)}, disconnect=True)
        with self._no_commands():
            vertices = self.bs.getTargetVertices("smile")
            self.assertEqual(vertices.indices, (1, 3))
            self.assertEqual(vertices.shape, hlib.getNode(self.base).getShape())
            self.assertEqual(self.bs.getTargetVertices(0, tolerance=0.001).indices, (1,))
            self.assertEqual(self.bs.getTargetVertices(0, tolerance=2).indices, ())
        self.bs.setTargetDeltas(0, {})
        self.assertEqual(self.bs.getTargetVertices(0).indices, ())

    def test_target_vertices_live_and_ignore_masks(self):
        self.bs.getPlug("envelope").set(0)
        self.bs.setTargetWeights(0, {0: 0})
        cmds.move(1, 0, 0, self.target + ".vtx[4]", relative=True)
        with self._no_commands():
            self.assertEqual(self.bs.getTargetVertices(0).indices, (0, 4))

    def test_target_vertices_inbetween_and_second_base(self):
        self.inbetween()
        self.bs.setTargetDeltas(0, {2: (0, 0, 1)}, full_weight=0.5)
        self.assertEqual(self.bs.getTargetVertices(0, full_weight=0.5).indices, (2,))
        second = cmds.polyCube(ch=False)[0]
        target = cmds.polyCube(ch=False)[0]
        cmds.move(0, 0, 1, target + ".vtx[5]", relative=True)
        cmds.blendShape(self.bs.getName(), edit=True, geometry=second)
        self.bs.addTarget(target, base=second, weight_index=0)
        vertices = self.bs.getTargetVertices(0, base=second)
        self.assertEqual(vertices.indices, (5,))
        self.assertEqual(vertices.shape, hlib.getNode(second).getShape())

    def test_target_vertices_invalid_tolerance(self):
        for value in (-1, float("nan"), float("inf"), True, "0"):
            with self.assertRaises(ValueError):
                self.bs.getTargetVertices(0, tolerance=value)

    def test_delta_only_json_roundtrip_to_new_target(self):
        deltas = self.bs.getTargetDeltas("smile")
        path = os.path.join(self.directory.name, "deltas.json")
        with open(path, "w", encoding="utf-8") as stream:
            json.dump({str(i): list(delta) for i, delta in deltas.items()}, stream)
        with open(path, encoding="utf-8") as stream:
            restored_deltas = {int(i): xyz for i, xyz in json.load(stream).items()}
        mesh = cmds.polyCube(ch=False)[0]
        neutral = cmds.duplicate(mesh)[0]
        restored = hlib.getNode(cmds.blendShape(neutral, mesh)[0])
        cmds.delete(neutral)
        restored.setTargetDeltas(0, restored_deltas)
        restored.getTargetPlug(0).set(1)
        self.bs.getTargetPlug(0).set(1)
        actual = cmds.xform(mesh + ".vtx[0]", query=True, translation=True, objectSpace=True)
        for a, b in zip(actual, self.point()):
            self.assertAlmostEqual(a, b)

    def test_remove_deltas_undo_and_preserve_other_items(self):
        self.inbetween()
        self.bs.setTargetDeltas(0, {0: (0, 2, 0), 3: (0, 1, 0)}, disconnect=True)
        self.bs.setTargetWeights(0, {3: 0.4})
        before = self.bs.getTargetDeltas(0)
        half = self.bs.getTargetDeltas(0, full_weight=0.5)
        self.assertIs(self.bs.resetTargetVertices("smile", [0, 0]), self.bs)
        self.assertEqual(set(self.bs.getTargetDeltas(0)), {3})
        self.assertEqual(self.bs.getTargetDeltas(0, full_weight=0.5), half)
        self.assertAlmostEqual(self.bs.getTargetWeights(0)[3], 0.4)
        cmds.undo()
        self.assertEqual(self.bs.getTargetDeltas(0), before)
        cmds.redo()
        self.assertEqual(set(self.bs.getTargetDeltas(0)), {3})

    def test_remove_deltas_components_and_invalid_input(self):
        self.bs.setTargetDeltas(0, {0: (0, 2, 0), 3: (0, 1, 0)}, disconnect=True)
        shape = hlib.getNode(self.base).getShape()
        before = self.bs.getTargetDeltas(0)
        for values in ([0, True], [0, 0.0], [-1], [8], "0",
                       hlib.getNode(self.target).getShape().getVertices([0])):
            with self.assertRaises((ValueError, TypeError)):
                self.bs.resetTargetVertices(0, values)
            self.assertEqual(self.bs.getTargetDeltas(0), before)
        self.bs.resetTargetVertices(0, shape.getVertices([0])[0])
        self.assertEqual(set(self.bs.getTargetDeltas(0)), {3})
        self.bs.resetTargetVertices(0, shape.getVertices([3]))
        self.assertEqual(self.bs.getTargetDeltas(0), {})

    def test_remove_deltas_connected_and_noop(self):
        destination = self.bs.getPlug("inputTarget[0].inputTargetGroup[0].inputTargetItem[6000].inputGeomTarget").mplug()
        self.bs.resetTargetVertices(0, [])
        self.bs.resetTargetVertices(0, [7])
        self.assertTrue(destination.isDestination)
        self.bs.resetTargetVertices(0, 0)
        self.assertTrue(destination.isDestination)
        self.assertEqual(self.bs.getTargetVertices(0).indices, ())
        cmds.undo()
        self.assertTrue(destination.isDestination)
        self.assertIn(0, self.bs.getTargetDeltas(0))
        self.bs.resetTargetVertices(0, 0, disconnect=True)
        self.assertFalse(destination.isDestination)
        self.assertEqual(self.bs.getTargetDeltas(0), {})
        cmds.undo()
        self.assertTrue(destination.isDestination)
        self.assertIn(0, self.bs.getTargetDeltas(0))

    def test_remove_deltas_fast_and_relative_auxiliary(self):
        self.bs.setTargetDeltas(0, {0: (0, 2, 0), 3: (0, 1, 0)}, disconnect=True)
        path = self.bs._item_path(0, 0, 6000)
        self.bs._write_deltas(path, [[0, [0, 1, 0, 1]], [3, [0, 0.5, 0, 1]]], relative=True)
        previous = cmds.undoInfo(query=True, undoName=True)
        with self._no_commands():
            self.bs.resetTargetVertices(0, [0], fast=True)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), previous)
        data = self.bs._read_item(0, 0, 6000)
        self.assertEqual([row[0] for row in data["absolute"]], [3])
        self.assertEqual(data["relative"], [[3, [0, 0.5, 0, 1]]])

    def test_remove_deltas_inbetween(self):
        self.inbetween()
        before = self.bs.getTargetDeltas(0)
        self.bs.resetTargetVertices(0, 0, full_weight=0.5)
        self.assertEqual(self.bs.getTargetDeltas(0, full_weight=0.5), {})
        self.assertEqual(self.bs.getTargetDeltas(0), before)

    def test_reduce_deltas_default_boundary_and_undo(self):
        self.bs.setTargetDeltas(0, {0: (0, 0, 0), 1: (0, 0.125, 0),
                                   2: (0.125, 0.125, 0)}, disconnect=True)
        self.assertIs(self.bs.reduceTargetDeltas("smile"), self.bs)
        self.assertEqual(set(self.bs.getTargetDeltas(0)), {1, 2})
        cmds.undo()
        self.assertEqual(set(self.bs.getTargetDeltas(0)), {0, 1, 2})
        cmds.redo()
        self.bs.reduceTargetDeltas(0, 0.125)
        self.assertEqual(set(self.bs.getTargetDeltas(0)), {2})

    def test_reduce_deltas_fast_masks_and_inbetween(self):
        self.inbetween()
        self.bs.setTargetDeltas(0, {0: (0, 0, 0), 1: (0, 2, 0)}, full_weight=0.5)
        self.bs.setTargetWeights(0, {1: 0})
        self.bs.getPlug("envelope").set(0)
        full = self.bs.getTargetDeltas(0)
        previous = cmds.undoInfo(query=True, undoName=True)
        with self._no_commands():
            self.bs.reduceTargetDeltas(0, 1, full_weight=0.5, fast=True)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), previous)
        self.assertEqual(set(self.bs.getTargetDeltas(0, full_weight=0.5)), {1})
        self.assertEqual(self.bs.getTargetDeltas(0), full)
        self.assertEqual(self.bs.getTargetWeights(0)[1], 0)

    def test_reduce_deltas_validation_and_connected(self):
        before = self.bs.getTargetDeltas(0)
        for value in (-1, True, "0", float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.bs.reduceTargetDeltas(0, value)
        self.bs.reduceTargetDeltas(0)  # 除外対象なしなら接続を維持する。
        self.bs.reduceTargetDeltas(0, 2)
        self.assertEqual(self.bs.getTargetVertices(0).indices, ())
        cmds.undo()
        self.assertEqual(self.bs.getTargetDeltas(0), before)
        self.bs.reduceTargetDeltas(0, 2, disconnect=True)
        self.assertEqual(self.bs.getTargetDeltas(0), {})
        cmds.undo()
        self.assertEqual(self.bs.getTargetDeltas(0), before)

    def test_live_remove_preserves_connection_redo_and_later_edits(self):
        cmds.move(0, 1, 0, self.target + ".vtx[3]", r=True)
        self.bs.getTargetPlug(0).set(0.7)
        before = self.bs.getTargetDeltas(0)
        self.bs.resetTargetVertices(0, 0)
        self.assertEqual(self.bs.getTargetVertices(0).indices, (3,))
        cmds.undo()
        self.assertEqual(self.bs.getTargetDeltas(0), before)
        cmds.redo()
        self.assertEqual(self.bs.getTargetVertices(0).indices, (3,))
        cmds.move(0, 3, 0, self.target + ".vtx[0]", r=True)
        self.assertAlmostEqual(self.bs.getTargetDeltas(0)[0].y, 3)

    def test_live_reduce_fast_and_inbetween(self):
        mesh = cmds.polyCube(ch=False)[0]
        cmds.move(0, 0.125, 0, mesh + ".vtx[1]", r=True)
        cmds.move(0, 2, 0, mesh + ".vtx[2]", r=True)
        self.bs.addInBetween(0, mesh, 0.5)
        full = self.bs.getTargetDeltas(0)
        previous = cmds.undoInfo(q=True, undoName=True)
        with self._no_commands():
            self.bs.reduceTargetDeltas(0, 0.125, full_weight=0.5, fast=True)
        self.assertEqual(cmds.undoInfo(q=True, undoName=True), previous)
        self.assertEqual(self.bs.getTargetVertices(0, full_weight=0.5).indices, (2,))
        self.assertEqual(self.bs.getTargetDeltas(0), full)
        cmds.move(0, 1, 0, mesh + ".vtx[1]", r=True)
        self.assertIn(1, self.bs.getTargetVertices(0, full_weight=0.5).indices)

    def test_live_world_origin_transforms(self):
        cmds.setAttr(self.base + ".translate", 5, 0, 0)
        cmds.setAttr(self.base + ".scale", 2, 3, 4)
        cmds.setAttr(self.target + ".translate", 7, 1, 0)
        cmds.setAttr(self.target + ".scale", 4, 2, 3)
        self.bs.getPlug("origin").set(0)
        before = self.bs.getTargetDeltas(0)
        self.bs.resetTargetVertices(0, 0)
        self.assertNotIn(0, self.bs.getTargetVertices(0, tolerance=1e-6).indices)
        after = self.bs.getTargetDeltas(0)
        for index in range(1, 8):
            self.assertEqual(after[index], before[index])
        cmds.undo()
        self.assertEqual(self.bs.getTargetDeltas(0), before)

    def test_live_relative_inbetween_and_history_guard(self):
        mesh = cmds.polyCube(ch=True)[0]
        cmds.move(0, 1, 0, mesh + ".vtx[0]", r=True)
        self.bs.addInBetween(0, mesh, 0.5, relative=True)
        before = self.bs.getTargetDeltas(0, full_weight=0.5)
        with self.assertRaises(NotImplementedError):
            self.bs.resetTargetVertices(0, 0, full_weight=0.5, fast=True)
        self.assertEqual(self.bs.getTargetDeltas(0, full_weight=0.5), before)
        self.bs.resetTargetVertices(0, 0, full_weight=0.5)
        self.assertEqual(self.bs.getTargetVertices(0, full_weight=0.5).indices, ())
        cmds.undo()
        self.assertEqual(self.bs.getTargetDeltas(0, full_weight=0.5), before)

    def test_target_edit_toggle_and_undo(self):
        state = self.bs.getPlug("inputTarget[0].sculptTargetIndex")
        self.assertIs(self.bs.targetEdit("smile", True), self.bs)
        self.assertEqual(state.get(), 0)
        self.assertIs(self.bs.targetEdit(state=False), self.bs)
        self.assertEqual(state.get(), -1)
        cmds.undo()
        self.assertEqual(state.get(), 0)
        cmds.redo()
        self.assertEqual(state.get(), -1)
        self.bs.targetEdit(0)
        self.bs.targetEdit("smile", False)
        self.assertEqual(state.get(), -1)

    def test_target_edit_inbetween_and_validation(self):
        self.inbetween()
        self.bs.targetEdit("smile", True, full_weight=0.5)
        self.assertAlmostEqual(self.bs.getPlug("inputTarget[0].sculptInbetweenWeight").get(), 0.5)
        for kwargs, error in (({}, ValueError), ({"target": "missing"}, ValueError),
                              ({"target": 0, "full_weight": 0.25}, ValueError),
                              ({"target": 0, "state": 1}, TypeError)):
            with self.assertRaises(error):
                self.bs.targetEdit(**kwargs)
        self.assertEqual(self.bs.getPlug("inputTarget[0].sculptTargetIndex").get(), 0)
        self.bs.targetEdit(state=False)

    @staticmethod
    def _no_commands():
        """OpenMaya経路がcmds/MELに戻らないことを実際のAPI結果と併せて検証する。"""
        stack = ExitStack()
        for name in ("getAttr", "setAttr", "connectionInfo", "listRelatives", "aliasAttr",
                     "blendShape", "duplicate", "delete", "undoInfo", "connectAttr",
                     "disconnectAttr", "removeMultiInstance"):
            stack.enter_context(mock.patch.object(cmds, name, side_effect=AssertionError("Unexpected cmds." + name)))
        stack.enter_context(mock.patch("maya.mel.eval", side_effect=AssertionError("Unexpected MEL")))
        return stack


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
