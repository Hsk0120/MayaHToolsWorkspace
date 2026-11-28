"""専用mayapyプロセスで実行する布ソルバーの回帰検証。GUIへ送信しない。"""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

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

    def test_static_maya_field(self):
        """布の質点に放射場を加え、切断とUndoで軌道が復帰する。"""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "SimplePhysics" / "scripts"))
        try:
            import mayaParticleFields
        finally:
            sys.path.pop(0)
        baseline = self.points(6)
        field = cmds.radial(position=(0, 8, 0), magnitude=25, attenuation=1)[0]
        cmds.select(field)
        mayaParticleFields.selected(self.node)
        changed = self.points(6)
        self.assertGreater((changed[-1] - baseline[-1]).length(), 1e-3)
        self.assertLess((changed[0] - baseline[0]).length(), 1e-6)
        mayaParticleFields.selected(self.node, disconnect=True)
        self.assertLess((om.MVector(cmds.pointPosition(self.output+".vtx[8]", world=True))-baseline[-1]).length(), 1e-6)
        cmds.undo()
        self.assertLess((self.points(6)[-1] - changed[-1]).length(), 1e-6)

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

    def test_contact_count(self):
        """接触面に並ぶ粒子を数え、同じ位置の床を追加しても二重に数えない。"""
        attr = self.node + ".contactParticleCount"
        self.assertEqual(cmds.getAttr(attr), 0)
        height = 6 - cmds.getAttr(self.node + ".collisionThickness")
        for _ in range(2):
            plane = api.addCollider(self.node, "plane")
            cmds.setAttr(plane + ".translateY", height)
            self.assertEqual(cmds.getAttr(attr), 9)
        cmds.setAttr(plane + ".translateY", height - 1)
        self.assertEqual(cmds.getAttr(attr), 9)

    def test_particle_diagnostics(self):
        """静止、端数時刻への移動、巻き戻し、全固定の診断を確認する。"""
        speed = self.node + ".peakParticleSpeed"
        pins = self.node + ".pinnedVertexCount"
        self.assertEqual(cmds.getAttr(speed), 0)
        self.assertEqual(cmds.getAttr(pins), 3)
        cmds.currentTime(6.25)
        peak = cmds.getAttr(speed)
        self.assertGreater(peak, 0)
        cmds.currentTime(1)
        self.assertEqual(cmds.getAttr(speed), 0)
        cmds.currentTime(6.25)
        self.assertAlmostEqual(cmds.getAttr(speed), peak)
        cmds.setAttr(self.node + ".maxDistance", 0)
        self.assertEqual(cmds.getAttr(pins), 9)
        self.assertAlmostEqual(cmds.getAttr(speed), 0)

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

    def test_collider_controls_and_reload(self):
        """各形状を同じ入力で比較し、近接時だけ出力が変わり、再読込で再現することを確かめる。"""
        reference = self.points(12)

        def difference(expected):
            return max((a - b).length() for a, b in zip(self.points(12), expected))

        for kind in ("sphere", "capsule", "plane"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                collider = api.addCollider(self.node, kind, radius=3, height=4)
                cmds.setAttr(collider + ".translateY", -1000)
                self.assertLess(difference(reference), 1e-6)
                position = tuple(reference[-1]) if kind != "plane" else (0, 4, 0)
                cmds.setAttr(collider + ".translate", *position)
                self.assertGreater(difference(reference), 0.1)
                near = self.points(12)
                path = str(Path(folder) / "collider.ma")
                cmds.file(rename=path)
                cmds.file(save=True, type="mayaAscii")
                cmds.file(path, open=True, force=True)
                self.assertLess(difference(near), 1e-5)
                api.removeCollider(self.node, collider)
                self.assertLess(difference(reference), 1e-6)

    def test_panel_curve_capsules_undo(self):
        """パネルで生成した全ガイドと選択を1回のUndoで元に戻す。"""
        from simpleCloth import ui

        curve = cmds.curve(degree=1, point=[(0, 0, 0), (2, 0, 0), (2, 3, 0)])
        cmds.select(curve)
        panel = ui.ClothWindow.__new__(ui.ClothWindow)
        panel.solver = self.node
        panel._curve_capsules()
        guides = cmds.ls(selection=True, long=True)
        self.assertEqual(len(guides), 2)
        cmds.undo()
        self.assertFalse(any(cmds.objExists(guide) for guide in guides))
        self.assertEqual(cmds.ls(selection=True), [curve])
        cmds.redo()
        self.assertEqual(cmds.ls(selection=True, long=True), guides)

    def test_bent_curve_capsules(self):
        """折れ線の各辺をカプセルにし、閉じたメッシュ内の自由点が押し出されることを確かめる。"""
        cmds.setAttr(self.node + ".gravity", 0, 0, 0, type="float3")
        reference = self.points(2)
        tip = reference[-1]
        bend = tip + om.MVector(0.25, 0, 0)
        vertices = [bend + om.MVector(0, 2, 0), bend, bend + om.MVector(0, 0, 2)]
        curve = cmds.curve(degree=1, point=[tuple(v) for v in vertices])
        # 同じ曲がり角の半径1cmの球メッシュを使い、先端が衝突体の内部にあることを独立に確認する。
        sphere = cmds.polySphere(radius=1, subdivisionsX=48, subdivisionsY=32)[0]
        cmds.xform(sphere, worldSpace=True, translation=tuple(bend))
        selection = om.MSelectionList()
        selection.add(cmds.listRelatives(sphere, shapes=True, fullPath=True)[0])
        mesh = om.MFnMesh(selection.getDagPath(0))
        surface, normal, _ = mesh.getClosestPointAndNormal(om.MPoint(tip), om.MSpace.kWorld)
        self.assertLess((om.MPoint(tip) - surface) * normal, -0.7)
        guides = api.addCurveCapsules(self.node, curve)
        self.assertEqual(len(guides), 2)
        cmds.undo()
        self.assertTrue(all(not cmds.objExists(guide) for guide in guides))
        cmds.redo()
        output = self.points(2)
        self.assertGreater((output[-1] - tip).length(), 0.1)
        self.points(1)
        self.assertLess(max((a - b).length() for a, b in zip(output, self.points(2))), 1e-6)
        for guide in reversed(guides):
            api.removeCollider(self.node, guide)
        self.assertLess(max((a - b).length() for a, b in zip(reference, self.points(2))), 1e-6)

    def test_curve_capsule_units_and_rejections(self):
        """m・rad表示で位置・軸・寸法を確認し、不正な曲線に部分生成しない。"""
        curve = cmds.curve(degree=1, point=[(3, 4, 5), (5, 4, 5)])
        bad = cmds.curve(degree=1, point=[(0, 0, 0), (1, 0, 0), (1, 0, 0)])
        previous_angle = cmds.currentUnit(query=True, angle=True)
        cmds.currentUnit(linear="m", angle="rad")
        try:
            guide, = api.addCurveCapsules(self.node, curve, radius=0.25)
            matrix = om.MMatrix(cmds.getAttr(guide + ".worldMatrix[0]"))
            self.assertLess((om.MVector(matrix[12], matrix[13], matrix[14]) - om.MVector(4, 4, 5)).length(), 1e-7)
            self.assertLess((om.MVector(0, 1, 0) * matrix - om.MVector(1, 0, 0)).length(), 1e-7)
            self.assertAlmostEqual(cmds.getAttr(guide + ".clothHeight"), 2)
            self.assertAlmostEqual(cmds.getAttr(guide + ".clothRadius"), 0.25)
            for invalid in (bad, curve + ".cv[0]"):
                with self.assertRaises(ValueError):
                    api.addCurveCapsules(self.node, invalid)
            self.assertEqual(cmds.getAttr(self.node + ".colliderTypes"), "[1]")
        finally:
            cmds.currentUnit(linear="cm", angle=previous_angle)

    def test_moving_mesh_response(self):
        """同じ固定刻みで解析カプセルと閉じた丸端メッシュへの投影を比較する。"""
        cmds.setAttr(self.node + ".gravity", 0, 0, 0, type="float3")
        shape = cmds.polyCylinder(radius=1, height=4, roundCap=True, subdivisionsX=96,
                                  subdivisionsCaps=24, constructionHistory=False)[0]
        selection = om.MSelectionList()
        selection.add(cmds.listRelatives(shape, shapes=True, fullPath=True)[0])
        mesh = om.MFnMesh(selection.getDagPath(0))

        def project_mesh(point, collider, padding):
            matrix = collider[0]
            local = om.MPoint(point) * matrix.inverse()
            closest, normal, _ = mesh.getClosestPointAndNormal(local, om.MSpace.kObject)
            depth = padding - (local - closest) * normal
            if depth <= 0:
                return point
            return om.MVector((closest + normal * padding) * matrix)

        for rate in (24, 96):
            cmds.setAttr(self.node + ".solverRate", rate)
            reference = self.points(2)
            tip = reference[-1]
            results = []
            for projection in (solver.project_collider, project_mesh):
                guide = api.addCollider(self.node, "capsule", radius=1, height=2)
                cmds.setAttr(guide + ".translate", tip.x + 0.25, tip.y, tip.z)
                for frame, offset in ((1, -6), (2, 6)):
                    cmds.setKeyframe(guide, attribute="translateZ", time=frame, value=tip.z + offset)
                cmds.keyTangent(guide, attribute="translateZ", inTangentType="linear", outTangentType="linear")
                with patch.object(solver, "project_collider", wraps=projection) as project:
                    cmds.setAttr(self.node + ".resetSerial", cmds.getAttr(self.node + ".resetSerial") + 1)
                    results.append(self.points(2))
                    self.assertGreater(project.call_count, 0)
                api.removeCollider(self.node, guide)
            for result in results:
                displacement = max((a - b).length() for a, b in zip(result, reference))
                if rate == 24:
                    self.assertLess(displacement, 1e-5)
                else:
                    self.assertGreater(displacement, 0.01)
            difference = max((a - b).length() for a, b in zip(*results))
            self.assertLess(difference, 0.1, (rate, difference))

    def test_moving_capsule_sampling(self):
        """1フレームで通過するカプセルを粗い刻みと細かい刻みの無衝突基準に照合する。"""
        cmds.setAttr(self.node + ".gravity", 0, 0, 0, type="float3")
        displacement = {}
        for rate, radius in ((24, 1.0), (96, 1.0), (96, 0.1)):
            with self.subTest(rate=rate, radius=radius):
                cmds.setAttr(self.node + ".solverRate", rate)
                reference = self.points(2)
                tip = reference[-1]
                collider = api.addCollider(self.node, "capsule", radius=radius, height=2.0)
                cmds.setAttr(collider + ".translate", tip.x + 0.25, tip.y, tip.z)
                for frame, offset in ((1, -6), (2, 6)):
                    cmds.setKeyframe(collider, attribute="translateZ", time=frame, value=tip.z + offset)
                cmds.keyTangent(collider, attribute="translateZ", inTangentType="linear", outTangentType="linear")
                output = self.points(2)
                delta = max((a - b).length() for a, b in zip(output, reference))
                displacement[rate, radius] = delta
                if rate == 24:
                    self.assertLess(delta, 1e-5)
                else:
                    self.assertGreater(delta, 0.01)
                self.points(1)
                repeat = self.points(2)
                self.assertLess(max((a - b).length() for a, b in zip(output, repeat)), 1e-6)
                api.removeCollider(self.node, collider)
        self.assertLess(displacement[96, 0.1], displacement[96, 1.0])

    def test_compare_cold_jump_to_playback(self):
        """保存前のシーンを開き直し、連続再生と直接移動の現在評価を保存状態と比較する。"""
        from simpleCloth import checkpoint

        cmds.setAttr(self.node + ".solverRate", 24)
        floor = api.addCollider(self.node, "plane")
        cmds.setAttr(floor + ".translateY", 5)
        self.points(1)
        with tempfile.TemporaryDirectory() as directory:
            scene = str(Path(directory) / "start.mb")
            path = Path(directory) / "playback.json"
            cmds.file(rename=scene)
            cmds.file(save=True, type="mayaBinary")
            for frame in range(2, 13):
                self.points(frame)
            checkpoint.saveState(self.node, path)
            cmds.file(scene, open=True, force=True)
            self.assertAlmostEqual(cmds.currentTime(query=True), 1)
            self.points(12)
            result = checkpoint.compareState(self.node, path)
            self.assertLess(result["maxPositionDifference"], 1e-7)
            self.assertLess(result["maxVelocityDifference"], 1e-7)

    def test_checkpoint_panel_operations(self):
        """保存・比較・再開の画面処理が選択したファイルと対象を使うことを確かめる。"""
        from simpleCloth import ui

        panel = object.__new__(ui.ClothWindow)
        panel.solver = self.node
        self.points(12)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "panel-state.json"
            with patch.object(cmds, "fileDialog2", return_value=[str(path)]) as chooser:
                panel._checkpoint(False)
                self.assertEqual(chooser.call_args.kwargs["fileMode"], 0)
                saved = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(saved["solver"], cmds.ls(self.node, uuid=True)[0])
                with patch.object(cmds, "confirmDialog") as dialog:
                    panel._compare_state()
                    self.assertEqual(dialog.call_args.kwargs["message"],
                                     "Maximum position difference: 0 cm\nMaximum velocity difference: 0 cm/s")
                self.points(1)
                panel._checkpoint(True)
                self.assertEqual(chooser.call_args.kwargs["fileMode"], 1)
                self.assertEqual(json.loads(cmds.getAttr(self.node + ".resumeState")), saved)
                cmds.undo()
                self.assertFalse(cmds.getAttr(self.node + ".resumeState"))
                chooser.return_value = []
                panel._checkpoint(True)
                self.assertFalse(cmds.getAttr(self.node + ".resumeState"))

    def test_checkpoint_operations(self):
        """移動床と固定辺を使い、保存・再開の製品操作で全頂点の位置・速度を照合する。"""
        from simpleCloth import checkpoint

        cmds.setAttr(self.node + ".solverRate", 24)
        floor = api.addCollider(self.node, "plane")
        for frame, height in ((1, 2), (24, 6), (60, 3)):
            cmds.setKeyframe(floor, attribute="translateY", time=frame, value=height)
        self.points(12)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            checkpoint.saveState(self.node, path)
            instance, _ = checkpoint._context(self.node)
            expected = {}
            for frame in range(12, 101):
                expected[frame] = self.points(frame), list(instance._cache[frame - 1][1][1])
            self.points(1)
            cmds.setAttr(self.node + ".damping", 3)
            with self.assertRaisesRegex(ValueError, "設定"):
                checkpoint.loadState(self.node, path)
            cmds.undo()
            checkpoint.loadState(self.node, path)
            cmds.undo()
            self.assertFalse(cmds.getAttr(self.node + ".resumeState"))
            cmds.redo()
            for frame, (points, velocities) in expected.items():
                self.assertPoints(self.points(frame), points, 1e-7)
                self.assertPoints(instance._cache[frame - 12][1][1], velocities, 1e-7)
            self.assertEqual(len(instance._cache), 89)
            self.points(12)
            result = checkpoint.compareState(self.node, path)
            self.assertAlmostEqual(result["maxPositionDifference"], 0)
            self.assertAlmostEqual(result["maxVelocityDifference"], 0)
            self.points(4)
            self.assertEqual(instance._cache_origin[0], 0)
            scene = str(Path(folder) / "checkpoint.mb")
            cmds.file(rename=scene)
            cmds.file(save=True, type="mayaBinary")
            cmds.file(scene, open=True, force=True)
            reopened = self.points(100)
            instance, _ = checkpoint._context(self.node)
            self.assertEqual(instance._cache_origin[0], 11)
            self.assertLess(max((a - b).length() for a, b in zip(reopened, expected[100][0])), 1e-7)

    def test_resume_with_moving_plane(self):
        """12Fの位置・速度から、動く床と固定辺がある布の100Fまでを照合する。"""
        cmds.setAttr(self.node + ".solverRate", 24)
        floor = api.addCollider(self.node, "plane")
        for frame, height in ((1, 2), (24, 6), (60, 3)):
            cmds.setKeyframe(floor, attribute="translateY", time=frame, value=height)
        self.points(12)
        selection = om.MSelectionList()
        selection.add(self.node)
        instance = om.MFnDependencyNode(selection.getDependNode(0)).userNode()
        encoded = json.dumps([[list(vector) for vector in values] for values in instance._cache[11][1]])
        state = tuple([om.MVector(vector) for vector in values] for values in json.loads(encoded))
        self.assertGreater(max(v.length() for v in state[1]), 0.001)
        reference = json.loads(cmds.getAttr(self.node + ".referenceData"))
        constraints = solver.build_constraints([om.MVector(p) for p in reference["points"]], reference["triangles"])
        settings = {key: cmds.getAttr(self.node + "." + key) for key in (*node.SCALARS, *node.INTEGERS, "selfCollision")}
        for key in ("gravity", "wind"):
            settings[key] = cmds.getAttr(self.node + "." + key)[0]
        weights = cmds.getAttr(self.node + ".maxDistanceMap")
        kinds = json.loads(cmds.getAttr(self.node + ".colliderTypes"))
        self.points(100)
        for frame in range(13, 101):
            targets, normals, colliders, _ = instance._sample(frame / 24, reference, kinds)
            state = solver.step(state, targets, normals, weights, constraints, colliders, settings, 1 / 24)
            for actual, expected in zip(state, instance._cache[frame - 1][1]):
                self.assertLess(max((a - b).length() for a, b in zip(actual, expected)), 1e-7, frame)

    def test_invalid_and_disconnected_collider(self):
        """不正スケールと接続切れをサンプル時に拒否し、修復後は出力が戻る。"""
        collider = api.addCollider(self.node, "sphere", radius=2)
        baseline = self.points(12)
        selection = om.MSelectionList()
        selection.add(self.node)
        instance = om.MFnDependencyNode(selection.getDependNode(0)).userNode()
        config = json.loads(cmds.getAttr(self.node + ".referenceData"))
        cmds.setAttr(collider + ".scaleX", 2)
        with self.assertRaisesRegex(ValueError, "スケール"):
            instance._sample(1.0, config, [0])
        cmds.setAttr(collider + ".scaleX", 1)
        matrix = self.node + ".colliderMatrix[0]"
        source = cmds.connectionInfo(matrix, sourceFromDestination=True)
        cmds.disconnectAttr(source, matrix)
        with self.assertRaisesRegex(ValueError, "接続"):
            instance._sample(1.0, config, [0])
        cmds.connectAttr(source, matrix)
        self.assertLess(max((a - b).length() for a, b in zip(baseline, self.points(12))), 1e-6)

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
