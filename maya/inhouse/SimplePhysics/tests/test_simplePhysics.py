"""専用mayapyプロセスで実行するSimple Physics回帰検証。

実行すると専用プロセス内のシーンを新規作成する。ユーザーGUIへ送信しない。
"""

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

    def test_settled_pose_indicator_and_hinge(self):
        """開始速度0、粒子の表示端点、非対称ヒンジ範囲とUndoを実DGで確認する。"""
        middle = self.outputs[1]
        api.setHinge(self.node, middle, "Z", -2, 4)
        curve = api.createVelocityIndicator(self.node, middle)
        points = self.points(13)
        v = cmds.getAttr(self.node + ".particlePosition[1]")[0]
        self.assertLess((om.MVector(v) - points[1]).length(), 1e-5)
        self.assertLess((om.MVector(cmds.pointPosition(curve+".cv[0]", world=True)) - points[1]).length(), 1e-5)
        end = om.MVector(cmds.pointPosition(curve+".cv[1]", world=True))
        # Frame 13 lands on a fixed step at 60 Hz in a 24-fps scene.
        earlier = om.MVector(cmds.getAttr(self.node+".particlePosition[1]", time=12.6)[0])
        self.assertLess(((points[1]-earlier)*60 - (end-points[1])).length(), 1e-5)
        direction = points[1] - points[0]
        import math
        self.assertLess(abs(direction.z), 1e-5)
        self.assertAlmostEqual(math.degrees(math.atan2(direction.y, direction.x)), -2, delta=0.001)
        api.captureSettledPose(self.node)
        start = self.points(1)
        self.assertLess(((points[1]-points[0]) - (start[1]-start[0])).length(), 1e-6)
        self.assertAlmostEqual(cmds.getAttr(self.node + ".maxParticleSpeed"), 0)
        before = self.points(6)
        self.points(1)
        self.assertLess((before[-1]-self.points(6)[-1]).length(), 1e-6)
        self.points(1)
        api.resetSettledPose(self.node)
        self.assertGreater((om.MVector(cmds.getAttr(self.node + ".particlePosition[1]")[0])-start[1]).length(), 1e-3)
        cmds.undo()
        self.assertLess((self.points(1)[1]-start[1]).length(), 1e-6)

    def test_static_maya_field(self):
        """Mayaフィールドを接続、変更、切断した際に過去キャッシュが残らない。"""
        import mayaParticleFields
        original = self.points(12)[1]
        field = cmds.radial(position=(5, 20, 0), magnitude=2000, attenuation=1)[0]
        cmds.select(field)
        mayaParticleFields.selected(self.node)
        changed = self.points(12)[1]
        self.assertGreater((changed-original).length(), 1e-3)
        cmds.setAttr(field+".magnitude", 0)
        self.assertLess((original-self.points(12)[1]).length(), 1e-5)
        cmds.setAttr(field+".magnitude", 2000)
        self.assertLess((changed-self.points(12)[1]).length(), 1e-5)
        mayaParticleFields.selected(self.node, disconnect=True)
        self.assertLess((original-self.points(12)[1]).length(), 1e-5)

    def test_edit_active_chains(self):
        """追加・除外しても既存出力・通常設定を保ち、旧構成の再開を拒否する。"""
        from simplePhysics import checkpoint

        cmds.setAttr(self.node + ".targetFramerate", 24)
        baseline = self.points(12)
        connections = [cmds.connectionInfo(j + ".offsetParentMatrix", sourceFromDestination=True) for j in self.outputs]
        cmds.select(clear=True)
        root = cmds.joint(name="otherRoot", position=(0, 20, 0))
        tip = cmds.joint(name="otherTip", position=(5, 20, 0))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            checkpoint.saveState(self.node, path)
            checkpoint.loadState(self.node, path)
            api.addChains(self.node, [root])
            self.assertFalse(cmds.getAttr(self.node + ".resumeState"))
            with self.assertRaises(ValueError):
                checkpoint.loadState(self.node, path)
            self.assertEqual(cmds.getAttr(self.node + ".fixedRootCount"), 2)
            cmds.undo()
            self.assertEqual(api.connections(self.node, "outputBones"), self.outputs)
            self.assertTrue(cmds.getAttr(self.node + ".resumeState"))
            cmds.redo()
        output = api.connections(self.node, "outputBones")[-1]
        def point(joint):
            return om.MVector(cmds.xform(joint, query=True, worldSpace=True, translation=True))
        simulated = point(output)
        self.assertGreater((simulated - point(tip)).length(), 0.01)
        api.setChainsExcluded(self.node, [root])
        self.assertLess((point(output) - point(tip)).length(), 1e-7)
        self.assertEqual(cmds.getAttr(self.node + ".fixedRootCount"), 1)
        self.assertLess(max((a - b).length() for a, b in zip(baseline, self.points(12))), 1e-7)
        self.assertEqual(connections, [cmds.connectionInfo(j + ".offsetParentMatrix", sourceFromDestination=True) for j in self.outputs])
        api.setChainsExcluded(self.node, [root], False)
        self.assertLess((simulated - point(output)).length(), 1e-7)
        cmds.undo()
        self.assertLess((point(output) - point(tip)).length(), 1e-7)
        with self.assertRaises(ValueError):
            api.addChains(self.node, [self.root])
        with self.assertRaises(ValueError):
            api.setChainsExcluded(self.node, [tip])

    def test_strand_frame_measurements(self):
        """折れ線・急な折返し・逆順の平行列、交差する列で間隔とねじれを実測する。"""
        def chain(points):
            cmds.select(clear=True)
            joints = [cmds.joint(position=point) for point in points]
            cmds.joint(joints[0], edit=True, orientJoint="xyz", secondaryAxisOrient="zup", children=True)
            cmds.setAttr(joints[-1] + ".jointOrient", 0, 0, 0)
            return joints
        path = [(0, 0, 0), (5, 0, 0), (5.2, 2, 0), (0.4, 0.8, 0)]
        for points in (path, list(reversed(path))):
            first = chain(points)
            second = chain([(x, y, z + 2) for x, y, z in points])
            node = api.create([first[0], second[0]])
            gap, widest, crossings, twist = api.compareStrands(node)
            self.assertAlmostEqual(gap, 2)
            self.assertAlmostEqual(widest, 2)
            self.assertEqual(crossings, 0)
            # 終端にも親と同じ向きを与え、そこから接線まわりに既知の角度を加える。
            self.assertLess(twist, 1e-4)
            cmds.setAttr(second[-1] + ".rotateX", 37)
            self.assertAlmostEqual(api.compareStrands(node)[3], 37, places=4)
        left = chain([(-1, -1, 0), (1, 1, 0)])
        right = chain([(-1, 1, 0), (1, -1, 0)])
        gap, _, crossings, _ = api.compareStrands(api.create([left[0], right[0]]))
        self.assertLess(gap, 1e-7)
        self.assertEqual(crossings, 1)

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

    def test_contact_count(self):
        """接触面に並ぶ粒子を数え、同じ位置の床を追加しても二重に数えない。"""
        attr = self.node + ".contactParticleCount"
        self.assertEqual(cmds.getAttr(attr), 0)
        cmds.setAttr(self.node + ".warmupSteps", 0)
        height = 10 - cmds.getAttr(self.node + ".radius")
        for _ in range(2):
            plane = api.addCollider(self.node, "plane")
            cmds.setAttr(plane + ".translateY", height)
            self.assertEqual(cmds.getAttr(attr), 2)
        cmds.setAttr(plane + ".translateY", height - 1)
        self.assertEqual(cmds.getAttr(attr), 2)

    def test_particle_diagnostics(self):
        """半端な末尾ステップの速度を実座標と照合し、巻き戻し後も同じ値になることを確かめる。"""
        cmds.setAttr(self.node + ".targetFramerate", 24)
        cmds.setAttr(self.node + ".warmupSteps", 0)
        self.assertEqual(cmds.getAttr(self.node + ".fixedRootCount"), 1)
        self.assertEqual(cmds.getAttr(self.node + ".maxParticleSpeed"), 0)
        before = self.points(6)
        after = self.points(6.25)
        expected = max((a - b).length() for a, b in zip(after, before)) * 96
        self.assertGreater(expected, 0)
        self.assertAlmostEqual(cmds.getAttr(self.node + ".maxParticleSpeed"), expected, places=5)
        self.points(1)
        for frame in range(2, 7):
            self.points(frame)
        self.points(6.25)
        self.assertAlmostEqual(cmds.getAttr(self.node + ".maxParticleSpeed"), expected, places=5)

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

    def test_collider_controls_and_reload(self):
        """各形状を同じ入力で比較し、近接時だけ出力が変わり、再読込で再現することを確かめる。"""
        cmds.setAttr(self.node + ".stiffness", 0)
        cmds.setAttr(self.node + ".gravity", 0, -980, 0, type="float3")
        cmds.setAttr(self.node + ".collisionIterations", 20)
        reference = self.points(12)

        def difference(expected):
            return max((a - b).length() for a, b in zip(self.points(12), expected))

        for kind in ("sphere", "capsule", "plane"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                collider = api.addCollider(self.node, kind, radius=3, height=4)
                cmds.setAttr(collider + ".translateY", -1000)
                self.assertLess(difference(reference), 1e-6)
                position = tuple(reference[-1]) if kind != "plane" else (0, 6, 0)
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
        from simplePhysics import ui

        curve = cmds.curve(degree=1, point=[(0, 0, 0), (2, 0, 0), (2, 3, 0)])
        cmds.select(curve)
        panel = ui.PhysicsWindow.__new__(ui.PhysicsWindow)
        panel.node = self.node
        with patch.object(panel, "_edit"):
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
            self.assertAlmostEqual(cmds.getAttr(guide + ".physicsHeight"), 2)
            self.assertAlmostEqual(cmds.getAttr(guide + ".physicsRadius"), 0.25)
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

        def project_mesh(point, padding, collider):
            matrix = collider[0]
            local = om.MPoint(point) * matrix.inverse()
            closest, normal, _ = mesh.getClosestPointAndNormal(local, om.MSpace.kObject)
            depth = padding - (local - closest) * normal
            if depth <= 0:
                return point
            return om.MVector((closest + normal * padding) * matrix)

        for rate in (24, 96):
            cmds.setAttr(self.node + ".targetFramerate", rate)
            reference = self.points(2)
            tip = reference[-1]
            results = []
            for projection in (solver._project_collision, project_mesh):
                guide = api.addCollider(self.node, "capsule", radius=1, height=2)
                cmds.setAttr(guide + ".translate", tip.x + 0.25, tip.y, tip.z)
                for frame, offset in ((1, -6), (2, 6)):
                    cmds.setKeyframe(guide, attribute="translateZ", time=frame, value=tip.z + offset)
                cmds.keyTangent(guide, attribute="translateZ", inTangentType="linear", outTangentType="linear")
                with patch.object(solver, "_project_collision", wraps=projection) as project:
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
                cmds.setAttr(self.node + ".targetFramerate", rate)
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

    def test_invalid_and_disconnected_collider(self):
        """不正スケールと接続切れをサンプル時に拒否し、修復後は出力が戻る。"""
        collider = api.addCollider(self.node, "sphere", radius=2)
        cmds.setAttr(self.node + ".targetFramerate", 24)
        baseline = self.points(12)
        selection = om.MSelectionList()
        selection.add(self.node)
        instance = om.MFnDependencyNode(selection.getDependNode(0)).userNode()
        config = json.loads(cmds.getAttr(self.node + ".topology"))
        cmds.setAttr(collider + ".scaleX", 2)
        with self.assertRaisesRegex(ValueError, "スケール"):
            instance._sample(om.MDGContext(om.MTime(1, om.MTime.kSeconds)), config, [0])
        cmds.setAttr(collider + ".scaleX", 1)
        matrix = self.node + ".colliderMatrix[0]"
        source = cmds.connectionInfo(matrix, sourceFromDestination=True)
        cmds.disconnectAttr(source, matrix)
        with self.assertRaisesRegex(ValueError, "接続"):
            instance._sample(om.MDGContext(om.MTime(1, om.MTime.kSeconds)), config, [0])
        cmds.connectAttr(source, matrix)
        self.assertLess(max((a - b).length() for a, b in zip(baseline, self.points(12))), 1e-6)

    def test_collision_projection(self):
        """球・カプセル・平面への押し出しを既知の位置で確認する。"""
        matrix = om.MMatrix()
        sphere = solver._project_collision(om.MVector(0, 0, 0), 0.5, (matrix, 0, 2, 0))
        self.assertAlmostEqual(sphere.length(), 2.5)
        capsule = solver._project_collision(om.MVector(0.2, 1, 0), 0.5, (matrix, 1, 2, 4))
        self.assertAlmostEqual(capsule.x, 2.5)
        plane = solver._project_collision(om.MVector(1, -3, 0), 0.5, (matrix, 2, 0, 0))
        self.assertAlmostEqual(plane.y, 0.5)

    def test_compare_cold_jump_to_playback(self):
        """保存前のシーンを開き直し、連続再生と直接移動の現在評価を保存状態と比較する。"""
        from simplePhysics import checkpoint

        cmds.setAttr(self.node + ".targetFramerate", 24)
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
        from simplePhysics import ui

        panel = object.__new__(ui.PhysicsWindow)
        panel.node = self.node
        cmds.setAttr(self.node + ".targetFramerate", 24)
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
        """製品入口から再開し、保存点以前を再計算せずに全区間を再現する。"""
        from simplePhysics import checkpoint

        cmds.setAttr(self.node + ".targetFramerate", 24)
        floor = api.addCollider(self.node, "plane")
        cmds.setAttr(floor + ".translateY", 7)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            self.points(12)
            checkpoint.saveState(self.node, path)
            expected = [(self.points(f), cmds.getAttr(self.node + ".maxParticleSpeed")) for f in range(12, 101)]
            self.points(1)
            cmds.setAttr(self.node + ".damping", 0.2)
            with self.assertRaises(ValueError):
                checkpoint.loadState(self.node, path)
            cmds.undo()
            checkpoint.loadState(self.node, path)
            cmds.undo()
            self.assertFalse(cmds.getAttr(self.node + ".resumeState"))
            cmds.redo()
            self.points(12)
            self.assertLess(checkpoint.compareState(self.node, path)["maxPositionDifference"], 1e-7)
            for frame, (points, speed) in enumerate(expected, 12):
                self.assertLess(max((a - b).length() for a, b in zip(points, self.points(frame))), 1e-7)
                self.assertAlmostEqual(cmds.getAttr(self.node + ".maxParticleSpeed"), speed, places=7)
            selection = om.MSelectionList()
            selection.add(self.node)
            instance = om.MFnDependencyNode(selection.getDependNode(0)).userNode()
            self.assertEqual(instance._cache_origin[0], 11)
            self.assertEqual(len(instance._cache), 89)
            self.points(4)
            self.assertEqual(instance._cache_origin[0], 0)
            scene = str(Path(directory) / "checkpoint.mb")
            cmds.file(rename=scene)
            cmds.file(save=True, type="mayaBinary")
            cmds.file(scene, open=True, force=True)
            reopened = self.points(100)
            instance, _ = checkpoint._context(self.node)
            self.assertEqual(instance._cache_origin[0], 11)
            self.assertLess(max((a - b).length() for a, b in zip(reopened, expected[-1][0])), 1e-7)

    def test_checkpoint_rejections_and_comparison(self):
        """対象・時刻・速度を取り違えず、検証失敗時は既存状態を保持する。"""
        from simplePhysics import checkpoint

        cmds.setAttr(self.node + ".targetFramerate", 24)
        self.points(12)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            checkpoint.saveState(self.node, path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.points(12.5)
            with self.assertRaisesRegex(ValueError, "固定刻み"):
                checkpoint.saveState(self.node, path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), saved)
            cmds.select(clear=True)
            other_root = cmds.joint(name='otherRoot', position=(0, 10, 0))
            cmds.joint(name='otherTip', position=(5, 10, 0))
            other = api.create([other_root])
            with self.assertRaisesRegex(ValueError, "対象"):
                checkpoint.loadState(other, path)
            self.points(12)
            saved["state"][1][-1][0] += 0.25
            path.write_text(json.dumps(saved), encoding="utf-8")
            result = checkpoint.compareState(self.node, path)
            self.assertAlmostEqual(result["maxPositionDifference"], 0)
            self.assertAlmostEqual(result["maxVelocityDifference"], 6.0)
            saved["state"][0].pop()
            path.write_text(json.dumps(saved), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "位置"):
                checkpoint.loadState(self.node, path)
            self.assertFalse(cmds.getAttr(self.node + ".resumeState"))

    def test_resume_state_requirements(self):
        """固定刻みの実DGで保存した位置・過去位置・入力姿勢を使い、12F以降の各ステップを再現する。"""
        from simplePhysics.node import DEFAULTS, INTEGERS

        cmds.setAttr(self.node + ".targetFramerate", 24)
        floor = api.addCollider(self.node, "plane")
        cmds.setAttr(floor + ".translateY", 7)
        self.points(12)
        selection = om.MSelectionList()
        selection.add(self.node)
        fn = om.MFnDependencyNode(selection.getDependNode(0))
        instance = fn.userNode()
        topology = json.loads(cmds.getAttr(self.node + ".topology"))
        parents = [bone["parent"] for bone in topology]
        options = {name: cmds.getAttr(self.node + "." + name) for name in (*DEFAULTS, *INTEGERS, "planarConstraint")}
        options.update(gravity=cmds.getAttr(self.node + ".gravity")[0], wind=cmds.getAttr(self.node + ".wind")[0], previousDt=1 / 24)
        settings = []
        for bone in topology:
            values = {}
            for name in solver.PARAMETERS:
                ramp = om.MRampAttribute(fn.object(), fn.attribute(name + "Curve"))
                values[name] = options[name] * ramp.getValueAtPosition(bone["rate"])
            settings.append(values)

        def sample(frame):
            context = om.MDGContext(om.MTime(frame, om.MTime.kFilm))
            return instance._sample(context, topology, [2])

        poses, _, _ = sample(12)
        saved = json.loads(json.dumps({
            "state": [[list(v) for v in array] for array in instance._cache[11][1]],
            "poses": [list(matrix) for matrix in poses],
        }))
        state = tuple([om.MVector(value) for value in array] for array in saved["state"])
        self.assertGreater(max((a - b).length() for a, b in zip(*state)), 0.001)
        poses = [om.MMatrix(value) for value in saved["poses"]]
        self.points(100)
        for frame in range(13, 101):
            current, colliders, _ = sample(frame)
            state = solver.step(state, poses, current, parents, settings, colliders, [], options, 1 / 24)
            poses = current
            for actual, expected in zip(state, instance._cache[frame - 1][1]):
                self.assertLess(max((a - b).length() for a, b in zip(actual, expected)), 1e-7, frame)

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
