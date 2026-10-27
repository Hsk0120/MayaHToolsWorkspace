"""専用mayapyプロセスで実行するSimple Physics回帰検証。

実行すると専用プロセス内のシーンを新規作成する。ユーザーGUIへ送信しない。
"""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import maya.standalone
from maya import cmds
from maya.api import OpenMaya as om

from simplePhysics import api, solver


class PhysicsTests(unittest.TestCase):
    """ソルバー・時間評価・保存・編集操作の契約を検証する。"""

    def setUp(self):
        """専用シーンに水平な3ボーンと根元アニメーションを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(time="film", linear="cm")
        cmds.playbackOptions(minTime=1, maxTime=25)
        self.root = cmds.joint(name="root", position=(0, 10, 0))
        self.middle = cmds.joint(name="middle", position=(5, 10, 0))
        self.tip = cmds.joint(name="tip", position=(10, 10, 0))
        for frame, value in ((1, 0), (13, 4), (25, 0)):
            cmds.setKeyframe(self.root, attribute="translateZ", time=frame, value=value)
        cmds.currentTime(1)
        self.node = api.create([self.root])
        cmds.setAttr(self.node + ".gravity", 0, -98, 0, type="float3")
        cmds.setAttr(self.node + ".radius", 0.25)
        self.outputs = api.connections(self.node, "outputBones")

    def points(self, frame):
        """指定時刻に実DG出力のワールド位置を取得する。"""
        cmds.currentTime(frame, edit=True)
        return [om.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True)) for node in self.outputs]

    def test_dynamics_lengths_and_seek(self):
        """実際に揺れ、骨長と任意順再生の結果を維持する。"""
        first = self.points(1)
        result = self.points(25)
        self.assertGreater((result[-1] - first[-1]).length(), 0.1)
        for a, b in zip(result, result[1:]):
            self.assertAlmostEqual((b - a).length(), 5, places=5)
        self.points(4)
        repeated = self.points(25)
        for a, b in zip(result, repeated):
            self.assertLess((a - b).length(), 1.0e-7)
        self.points(11.5)
        repeated = self.points(25)
        for a, b in zip(result, repeated):
            self.assertLess((a - b).length(), 1.0e-7)

    def test_historical_edit_invalidates_cache(self):
        """現在時刻より前のキー編集が再生結果へ反映される。"""
        before = self.points(25)
        cmds.setKeyframe(self.root, attribute="translateZ", time=13, value=15)
        after = self.points(25)
        self.assertGreater((before[-1] - after[-1]).length(), 0.01)

    def test_blend_zero_and_angle(self):
        """Alpha 0は入力姿勢、角度制限は入力ポーズ基準になる。"""
        cmds.setAttr(self.node + ".blend", 0)
        actual = self.points(20)
        for source, value in zip((self.root, self.middle, self.tip), actual):
            reference = om.MVector(cmds.xform(source, query=True, worldSpace=True, translation=True))
            self.assertLess((reference - value).length(), 1.0e-6)
        cmds.setAttr(self.node + ".blend", 1)
        cmds.setAttr(self.node + ".limitAngle", 5)
        values = self.points(25)
        for first, second in zip(values, values[1:]):
            self.assertLessEqual(om.MVector(1, 0, 0).angle(second - first), 0.087267)

    def test_colliders_and_remove(self):
        """各コライダーを作成・評価し、削除後に番号が整合する。"""
        sphere = api.addCollider(self.node, "sphere", radius=2)
        capsule = api.addCollider(self.node, "capsule", radius=1, height=4)
        plane = api.addCollider(self.node, "plane")
        self.points(12)
        api.removeCollider(self.node, capsule)
        self.assertEqual(json.loads(cmds.getAttr(self.node + ".colliderTypes")), [0, 2])
        self.assertEqual(api.connections(self.node, "colliderObjects"), [sphere, plane])
        self.points(12)
        with self.assertRaises(ValueError):
            api.addCollider(self.node, attachTo=self.outputs[1])

    def test_collision_projection(self):
        """球・カプセル・平面への押し出しを既知の位置で確認する。"""
        matrix = om.MMatrix()
        sphere = solver._project_collision(om.MVector(0, 0, 0), 0.5, (matrix, 0, 2, 0))
        self.assertAlmostEqual(sphere.length(), 2.5)
        capsule = solver._project_collision(om.MVector(0.2, 1, 0), 0.5, (matrix, 1, 2, 4))
        self.assertAlmostEqual(capsule.x, 2.5)
        plane = solver._project_collision(om.MVector(1, -3, 0), 0.5, (matrix, 2, 0, 0))
        self.assertAlmostEqual(plane.y, 0.5)

    def test_xpbd_pinned_root(self):
        """距離拘束は逆質量0の点を動かさない。"""
        points = [om.MVector(0, 0, 0), om.MVector(10, 0, 0)]
        solver._distance_constraints(points, [-1, 0], [(0, 1, 5, 0)], 1 / 60, 4)
        self.assertEqual(points[0].length(), 0)
        self.assertAlmostEqual(points[1].length(), 5)

    def test_preset_roundtrip_and_validation(self):
        """プリセットの往復と不正値による部分更新の防止を確認する。"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preset.json"
            cmds.setAttr(self.node + ".damping", 0.3)
            api.savePreset(self.node, path)
            cmds.setAttr(self.node + ".damping", 0.8)
            api.loadPreset(self.node, path)
            self.assertAlmostEqual(cmds.getAttr(self.node + ".damping"), 0.3)
            content = json.loads(path.read_text(encoding="utf-8"))
            content["settings"]["damping"] = 0.7
            content["settings"]["targetFramerate"] = -1
            path.write_text(json.dumps(content), encoding="utf-8")
            with self.assertRaises(ValueError):
                api.loadPreset(self.node, path)
            self.assertAlmostEqual(cmds.getAttr(self.node + ".damping"), 0.3)

    def test_save_reopen(self):
        """保存前後の任意時刻で同じ結果を再構成できる。"""
        expected = self.points(20)
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "simplePhysics.ma")
            cmds.file(rename=path)
            cmds.file(save=True, type="mayaAscii")
            cmds.file(new=True, force=True)
            cmds.file(path, open=True, force=True)
            actual = self.points(20)
            for first, second in zip(expected, actual):
                self.assertLess((first - second).length(), 1.0e-6)

    def test_bake_and_remove_undo(self):
        """ベイクは独立したキーを持ち、セットアップ削除はUndoできる。"""
        expected = self.points(10)
        group = api.bake(self.node, 1, 12)
        baked = cmds.listRelatives(group, allDescendents=True, type="joint", fullPath=True)
        baked.sort(key=lambda value: value.count("|"))
        cmds.currentTime(10)
        for target, point in zip(baked, expected):
            actual = om.MVector(cmds.xform(target, query=True, worldSpace=True, translation=True))
            self.assertLess((actual - point).length(), 1.0e-5)
        api.remove(self.node)
        self.assertTrue(cmds.objExists(self.root))
        self.assertTrue(cmds.objExists(group))
        self.assertFalse(cmds.objExists(self.node))
        cmds.undo()
        self.assertTrue(cmds.objExists(self.node))
        self.points(10)

    def test_dummy_exclude_and_creation_undo(self):
        """除外枝と末端仮想ボーン、作成のUndo/Redoを確認する。"""
        other = api.create([self.root], excluded=[self.tip], dummyLength=2)
        topology = json.loads(cmds.getAttr(other + ".topology"))
        self.assertEqual(len(topology), 3)
        self.assertEqual(topology[-1]["dummyOffset"], [2, 0, 0])
        cmds.undo()
        self.assertFalse(cmds.objExists(other))
        cmds.redo()
        self.assertTrue(cmds.objExists(other))

    def test_failed_transaction_preserves_previous_edit(self):
        """編集前の失敗で以前の操作を取り消さず、途中失敗はロールバックする。"""
        marker = cmds.createNode("transform", name="preserveMe")
        with self.assertRaises(ValueError):
            with api._transaction("Empty failure"):
                raise ValueError("before edits")
        self.assertTrue(cmds.objExists(marker))
        with self.assertRaises(ValueError):
            with api._transaction("Partial failure"):
                cmds.createNode("transform", name="rollbackMe")
                raise ValueError("after edits")
        self.assertFalse(cmds.objExists("rollbackMe"))
        self.assertTrue(cmds.objExists(marker))

    def test_units_constraints_and_bake(self):
        """表示単位mでも距離拘束はcmを保持し、ベイク位置が一致する。"""
        cmds.currentUnit(linear="m")
        try:
            api.addConstraint(self.node, self.outputs[0], self.outputs[-1])
            self.assertAlmostEqual(json.loads(cmds.getAttr(self.node + ".boneConstraints"))[0][2], 10)
            expected = self.points(10)
            group = api.bake(self.node, 1, 12)
            baked = cmds.listRelatives(group, allDescendents=True, type="joint", fullPath=True)
            baked.sort(key=lambda value: value.count("|"))
            cmds.currentTime(10)
            for target, point in zip(baked, expected):
                actual = om.MVector(cmds.xform(target, query=True, worldSpace=True, translation=True))
                self.assertLess((actual - point).length(), 1.0e-6)
        finally:
            cmds.currentUnit(linear="cm")

    def test_ramp_and_rotated_joint_orientation(self):
        """カーブ変更が再計算され、入力回転を含めて子の方向へ向く。"""
        cmds.setAttr(self.root + ".jointOrient", 20, 30, 40)
        cmds.setAttr(self.node + ".stiffness", 1)
        reference = self.points(20)
        cmds.setAttr(self.node + ".stiffnessCurve[1].stiffnessCurve_FloatValue", 0)
        result = self.points(20)
        self.assertGreater((reference[-1] - result[-1]).length(), 0.1)
        matrix = om.MMatrix(cmds.getAttr(self.outputs[0] + ".worldMatrix[0]"))
        aim = om.MVector(1, 0, 0) * matrix
        self.assertLess(aim.angle(result[1] - result[0]), 1.0e-6)

    def test_parallel_and_serial_evaluation(self):
        """DG・Serial・Parallelで任意順の評価結果が一致する。"""
        previous = cmds.evaluationManager(query=True, mode=True)[0]
        try:
            cmds.evaluationManager(mode="off")
            expected = self.points(25)
            for mode in ("serial", "parallel"):
                cmds.evaluationManager(mode=mode)
                self.points(7)
                actual = self.points(25)
                for first, second in zip(expected, actual):
                    self.assertLess((first - second).length(), 1.0e-6)
        finally:
            cmds.evaluationManager(mode=previous)

    def test_plane_collision_in_dg(self):
        """実DGで水平床を評価し、動く点の半径分の距離を保つ。"""
        cmds.setAttr(self.node + ".stiffness", 0)
        cmds.setAttr(self.node + ".gravity", 0, -980, 0, type="float3")
        cmds.setAttr(self.node + ".collisionIterations", 20)
        floor = api.addCollider(self.node, "plane")
        cmds.setAttr(floor + ".translateY", 6)
        result = self.points(25)
        self.assertGreaterEqual(min(point.y for point in result[1:]), 6.25 - 1.0e-4)
        self.assertLess(cmds.getAttr(self.node + ".residualPenetration"), 1.0e-4)
        cmds.setAttr(floor + ".translateY", 7)
        changed = self.points(25)
        self.assertGreater((result[-1] - changed[-1]).length(), 0.1)


if __name__ == "__main__":
    maya.standalone.initialize()
    try:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PhysicsTests))
    finally:
        maya.standalone.uninitialize()
    sys.exit(0 if result.wasSuccessful() else 1)
