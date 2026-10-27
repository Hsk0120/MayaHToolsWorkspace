"""専用mayapyプロセスで実行する布ソルバーの回帰検証。GUIへ送信しない。"""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import maya.standalone
from maya import cmds
from maya.api import OpenMaya as om

from simpleCloth import api, node, solver


class ClothTests(unittest.TestCase):
    """実DGの動き・固定・時間評価・編集・保存とベイクを検査する。"""

    def setUp(self):
        """専用シーンに9頂点の水平布と固定辺を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", time="film")
        cmds.currentTime(1)
        self.source = cmds.polyPlane(width=4, height=4, subdivisionsX=2, subdivisionsY=2, constructionHistory=False)[0]
        cmds.setAttr(self.source + ".translateY", 6)
        self.node = api.create(self.source)
        self.output = api.getConnection(self.node, "outputMeshObject")
        api.setVertexWeights(self.node, [0, 1, 2], 0)
        cmds.setAttr(self.node + ".gravity", 0, -98, 0, type="float3")
        cmds.setAttr(self.node + ".solverRate", 48)

    def points(self, frame, mesh=None):
        """実メッシュのワールド頂点位置を取得する。"""
        cmds.currentTime(frame)
        path = api._mesh(mesh or self.output)
        return [om.MVector(point) for point in om.MFnMesh(path).getPoints(om.MSpace.kWorld)]

    def assertPoints(self, first, second, tolerance=1.0e-5):
        """全頂点が許容誤差内で一致することを確認する。"""
        self.assertEqual(len(first), len(second))
        self.assertLess(max((a - b).length() for a, b in zip(first, second)), tolerance)

    def test_dynamics_pins_and_seek(self):
        """自由頂点が落下し固定辺を維持、逆順・端数時刻が再現する。"""
        initial = self.points(1)
        end = self.points(13.25)
        self.assertLess(end[-1].y, initial[-1].y - 0.5)
        self.assertPoints(end[:3], initial[:3])
        self.points(7)
        self.assertPoints(end, self.points(13.25))
        self.assertLess(cmds.getAttr(self.node + ".stretchError"), 0.08)

    def test_animated_source_and_history_edit(self):
        """現在時刻の姿勢が同じでも過去キー変更を検出する。"""
        for frame, value in ((1, 0), (7, 2), (13, 0)):
            cmds.setKeyframe(self.source, attribute="translateX", time=frame, value=value)
        first = self.points(13)
        cmds.setKeyframe(self.source, attribute="translateX", time=7, value=-2)
        changed = self.points(13)
        self.assertGreater((first[-1] - changed[-1]).length(), 0.1)
        self.assertPoints(changed[:3], self.points(13, self.source)[:3])

    def test_max_distance_and_blend(self):
        """距離上限を守り、Blend 0で元メッシュと一致する。"""
        cmds.setAttr(self.node + ".maxDistance", 0.5)
        result = self.points(13)
        reference = self.points(13, self.source)
        self.assertLessEqual(max((a - b).length() for a, b in zip(result, reference)), 0.50001)
        cmds.setAttr(self.node + ".blend", 0)
        self.assertPoints(reference, self.points(13))

    def test_floor_collision_and_guides(self):
        """平面で落下を止め、コライダーの追加・中間削除・Undoを検査する。"""
        floor = api.addCollider(self.node, "plane")
        cmds.setAttr(floor + ".translateY", 3)
        sphere = api.addCollider(self.node, "sphere", radius=1)
        cmds.setAttr(sphere + ".translateX", 20)
        capsule = api.addCollider(self.node, "capsule", radius=0.5, height=2)
        cmds.setAttr(capsule + ".translateX", -20)
        self.assertGreaterEqual(min(point.y for point in self.points(25)), 3.2 - 1.0e-4)
        self.assertLess(cmds.getAttr(self.node + ".residualPenetration"), 1.0e-4)
        api.removeCollider(self.node, sphere)
        self.assertEqual(api.getColliders(self.node), [floor, capsule])
        cmds.undo()
        self.assertEqual(api.getColliders(self.node), [floor, sphere, capsule])

    def test_sphere_capsule_backstop_self_collision(self):
        """境界投影と重なった粒子の分離を解析値で検査する。"""
        for kind in (0, 1):
            projected = solver.project_collider(om.MVector(), (om.MMatrix(), kind, 2, 4), 0.2)
            self.assertAlmostEqual(projected.x, 2.2)
        points = [om.MVector(0, -0.4, 0)]
        settings = {name: value[0] for name, value in node.SCALARS.items()}
        settings.update(backstopRadius=1, backstopDistance=0)
        solver._limits(points, [om.MVector()], [om.MVector(0, 1, 0)], [1], settings)
        self.assertAlmostEqual(points[0].y, 0)
        points = [om.MVector(), om.MVector(0.05, 0, 0)]
        solver._self_collide(points, [1, 1], set(), 0.4)
        self.assertAlmostEqual((points[0] - points[1]).length(), 0.4)

    def test_preset_atomic_rejection_and_undo(self):
        """係数・Mapを復元し、異常JSONは更新前に拒否する。"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cloth.json"
            api.savePreset(self.node, path)
            cmds.setAttr(self.node + ".damping", 5)
            api.setVertexWeights(self.node, [4], 0.25)
            api.loadPreset(self.node, path)
            self.assertEqual(api.getMap(self.node)[4], 1)
            self.assertEqual(cmds.getAttr(self.node + ".damping"), 2)
            cmds.undo()
            self.assertEqual(api.getMap(self.node)[4], 0.25)
            self.assertEqual(cmds.getAttr(self.node + ".damping"), 5)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["map"][0] = -1
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                api.loadPreset(self.node, path)
            self.assertEqual(cmds.getAttr(self.node + ".damping"), 5)

    def test_save_open_uv_and_evaluation_modes(self):
        """UVとシーン保存・再読込、DG/Serial/Parallelの結果を比較する。"""
        expected = self.points(13)
        self.assertEqual(om.MFnMesh(api._mesh(self.source)).numUVs(), om.MFnMesh(api._mesh(self.output)).numUVs())
        for mode in ("off", "serial", "parallel"):
            cmds.evaluationManager(mode=mode)
            api.reset(self.node)
            self.assertPoints(expected, self.points(13))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cloth.ma"
            cmds.file(rename=str(path))
            cmds.file(save=True, type="mayaAscii")
            cmds.file(str(path), open=True, force=True)
            self.assertPoints(expected, self.points(13))

    def test_bake_and_remove(self):
        """ベイクが実出力と一致し、Solver削除後も独立再生できる。"""
        expected = {frame: self.points(frame) for frame in (1, 4, 7)}
        baked = api.bake(self.node, 1, 7)
        for frame, points in expected.items():
            self.assertPoints(points, self.points(frame, baked))
        api.remove(self.node)
        self.assertTrue(cmds.objExists(self.source))
        self.assertTrue(cmds.objExists(baked))
        cmds.undo()
        self.assertTrue(cmds.objExists(self.node))
        cmds.redo()
        for frame, points in expected.items():
            self.assertPoints(points, self.points(frame, baked))
        self.assertPoints(expected[1], self.points(-5, baked))
        self.assertPoints(expected[7], self.points(15, baked))

    def test_units_and_validation(self):
        """m表示単位でも頂点計算はcm、入力検証失敗でシーンを変えない。"""
        expected = self.points(13)
        cmds.currentUnit(linear="m")
        self.assertPoints(expected, self.points(13))
        before = api.getMap(self.node)
        with self.assertRaises(ValueError):
            api.setVertexWeights(self.node, [3, 999], 0)
        self.assertEqual(api.getMap(self.node), before)
        with self.assertRaises(TypeError):
            api.setVertexWeights(self.node, [True], 0)
        with self.assertRaises(ValueError):
            api.addCollider(self.node, attachTo=self.output)
        cmds.currentUnit(linear="cm")

    def test_create_undo_redo_and_failure_scope(self):
        """作成のUndo/Redoと編集前失敗時の既存Undo保護を検査する。"""
        other = api.create(self.source, name="otherCloth")
        cmds.undo()
        self.assertFalse(cmds.objExists(other))
        cmds.redo()
        self.assertTrue(cmds.objExists(other))
        marker = cmds.createNode("transform", name="previousUserEdit")
        with self.assertRaises(ValueError):
            with api._transaction("No changes"):
                raise ValueError("test")
        self.assertTrue(cmds.objExists(marker))

    def test_skin_input_and_backstop(self):
        """実skinClusterを入力にでき、Backstopが法線背面への落下を抑える。"""
        cmds.setAttr(self.node + ".backstopRadius", 10)
        self.assertPoints(self.points(1), self.points(13))
        cmds.setAttr(self.node + ".backstopRadius", 0)
        cmds.currentTime(1)
        cmds.select(clear=True)
        joint = cmds.joint(position=(0, 6, 0))
        cmds.skinCluster(joint, self.source, toSelectedBones=True)
        for frame, value in ((1, 0), (7, 2), (13, 0)):
            cmds.setKeyframe(joint, attribute="translateZ", time=frame, value=value)
        result = self.points(7)
        source = self.points(7, self.source)
        self.assertPoints(result[:3], source[:3])
        self.assertGreater((result[-1] - source[-1]).length(), 0.1)

    def test_collider_display_units(self):
        """m表示単位で作成したガイドの実寸と計算半径が一致する。"""
        cmds.currentUnit(linear="m")
        guide = api.addCollider(self.node, "sphere", radius=2)
        shapes = cmds.listRelatives(guide, allDescendents=True, type="mesh", fullPath=True)
        function = om.MFnMesh(api._mesh(shapes[0]))
        points = function.getPoints(om.MSpace.kWorld)
        self.assertAlmostEqual(max(point.x for point in points), 2, places=4)
        cmds.currentUnit(linear="cm")

    def test_user_duplicate_is_not_owned(self):
        """ユーザーの通常複製をセットアップ削除に巻き込まない。"""
        duplicate = cmds.duplicate(self.output, name="userDuplicate")[0]
        api.remove(self.node)
        self.assertTrue(cmds.objExists(duplicate))


if __name__ == "__main__":
    maya.standalone.initialize()
    try:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ClothTests))
    finally:
        maya.standalone.uninitialize()
    sys.exit(0 if result.wasSuccessful() else 1)
