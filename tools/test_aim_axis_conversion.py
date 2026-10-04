"""使い捨てMayaでAim軸変換の数値・接続・Undo・保存読込を検証する。"""

import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "maya/inhouse"))


class AimAxisConversionTest(unittest.TestCase):
    """全方式を実際のAimと標準DGで評価する。"""

    def setUp(self):
        """隔離プロセスの空シーンへ実Aimを作る。"""
        import maya.cmds as cmds
        import maya.api.OpenMaya as om
        from hrig.setups.aimAxisConversion import AimAxisConversion
        self.cmds, self.om, self.cls = cmds, om, AimAxisConversion
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg")
        cmds.undoInfo(state=True)
        self.driver = cmds.createNode("transform", name="aimTarget")
        self.driven = cmds.createNode("transform", name="driven")
        cmds.setAttr(self.driver + ".translateX", 10)
        self.source = cmds.aimConstraint(self.driver, self.driven, worldUpType="vector")[0]

    def pose(self, degrees, order=0):
        """Aimのターゲット方向とUpを指定回転から独立に設定する。"""
        self.cmds.setAttr(self.driven + ".rotateOrder", order)
        rotation = self.om.MEulerRotation(*[math.radians(v) for v in degrees], order).asMatrix()
        forward = self.om.MVector(10, 0, 0) * rotation
        up = self.om.MVector(0, 1, 0) * rotation
        self.cmds.setAttr(self.driver + ".translate", *forward)
        self.cmds.setAttr(self.source + ".worldUpVector", *up)
        return rotation

    def angles(self, graph):
        """変換出力を度で取得する。"""
        return [math.degrees(graph.container.plug("output" + a).get()) for a in "XYZ"]

    def test_three_modes_and_restore(self):
        """単軸の純回転は3方式とも一致し、復元で生成物が全て消える。"""
        # 標準Aimも拘束対象の子に置くとcycleCheck(dag=True)の候補になる。
        # DAGも含めて非循環のテスト条件を作り、新しい循環を持ち込まないことを確認する。
        self.source = self.cmds.parent(self.source, world=True)[0]
        self.pose((30, 0, 0))
        baseline = set(self.cmds.ls())
        for mode in ("euler", "direction", "twist"):
            graph = self.cls.create(self.source, axes="x", mode=mode, direction="y", preserve_pose=False)
            self.assertAlmostEqual(self.angles(graph)[0], 30, places=4)
            self.assertGreater(graph.container.plug("valid").get(), 0.5)
            self.assertIsNotNone(self.cls.find(self.source))
            self.assertFalse(self.cmds.cycleCheck(all=True, dag=True, list=True))
            graph.restore()
            self.assertEqual(set(self.cmds.ls()), baseline)
            self.assertTrue(self.cmds.isConnected(self.source + ".constraintRotateX", self.driven + ".rotateX"))

    def test_euler_flip_all_orders(self):
        """6回転順の中央軸90度通過で外側1・2軸が180度反転しない。"""
        for order, name in enumerate(("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")):
            middle = "xyz".index(name[1])
            axes = "".join(sorted((name[0], name[2])))
            self.pose((0, 0, 0), order)
            graph = self.cls.create(self.source, axes=axes, mode="euler", preserve_pose=False)
            for angle in (88, 89.9, 90.1, 92, 120):
                desired = [15, 15, 15]
                desired[middle] = angle
                self.pose(desired, order)
                actual = self.angles(graph)
                for axis in axes:
                    self.assertAlmostEqual(actual["xyz".index(axis)], 15, places=3)
                self.assertGreater(graph.container.plug("valid").get(), 0.5)
            graph.restore()

    def test_direction_two_axes_all_orders(self):
        """6回転順の各2軸を幾何的な方向で照合する。"""
        for order, name in enumerate(("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")):
            for omit in "xyz":
                axes = "".join(a for a in "xyz" if a != omit)
                desired = [25 if a in axes else 0 for a in "xyz"]
                expected = self.pose(desired, order)
                graph = self.cls.create(self.source, axes=axes, mode="direction", direction=omit, preserve_pose=False)
                values = self.angles(graph)
                values["xyz".index(omit)] = 0
                actual = self.om.MEulerRotation(*[math.radians(v) for v in values], order).asMatrix()
                basis = self.om.MVector(*[1 if a == omit else 0 for a in "xyz"])
                self.assertLess(((basis * actual) - (basis * expected)).length(), 1e-5)
                graph.restore()

    def test_twist_two_axes_matches_quaternion(self):
        """Twist射影式に一致し、混合回転では元Eulerとは異なる。"""
        matrix = self.pose((35, 55, 20))
        q = self.om.MTransformationMatrix(matrix).rotation(asQuaternion=True)
        graph = self.cls.create(self.source, axes="xy", mode="twist", preserve_pose=False)
        for index in (0, 1):
            component = (q.x, q.y)[index]
            expected = math.degrees(math.atan2(2 * component * q.w, q.w * q.w - component * component))
            self.assertAlmostEqual(self.angles(graph)[index], expected, places=4)

    def test_switch_undo_redo(self):
        """方式切替・復元がUndo/Redoでまとまり、元ノードを削除しない。"""
        self.pose((20, 10, 5))
        first = self.cls.create(self.source, mode="euler")
        first_uuid = first.container.uuid()
        second = self.cls.create(self.source, mode="twist")
        self.assertNotEqual(first_uuid, second.container.uuid())
        self.cmds.undo()
        self.assertEqual(first_uuid, self.cls.find(self.source).container.uuid())
        self.cmds.redo()
        self.assertIsNotNone(self.cls.find(self.source))
        self.cls.find(self.source).restore()
        self.assertIsNone(self.cls.find(self.source))
        self.cmds.undo()
        self.assertIsNotNone(self.cls.find(self.source))

    def test_save_rename_restore(self):
        """改名・保存読込後もmessage参照で復元できる。"""
        graph = self.cls.create(self.source, axes="xz", mode="twist")
        self.source = self.cmds.rename(self.source, "renamedAim")
        self.driven = self.cmds.rename(self.driven, "renamedDriven")
        output = ROOT / ".maya-output/aim-axis-test.ma"
        output.parent.mkdir(exist_ok=True)
        self.cmds.file(rename=str(output))
        self.cmds.file(save=True, type="mayaAscii", force=True)
        self.cmds.file(str(output), open=True, force=True)
        self.cls.find(self.source).restore()
        self.assertTrue(self.cmds.isConnected(self.source + ".constraintRotateX", self.driven + ".rotateX"))

    def test_reject_and_rollback(self):
        """不正な軸・ロック・他接続を壊さず、失敗した切替を巻き戻す。"""
        graph = self.cls.create(self.source, axes="x", mode="twist")
        owner_uuid = graph.container.uuid()
        with self.assertRaises(ValueError):
            self.cls.create(self.source, axes="x", mode="direction", direction="x")
        self.assertEqual(owner_uuid, self.cls.find(self.source).container.uuid())
        self.cmds.setAttr(self.driven + ".rotateX", lock=True)
        with self.assertRaises(ValueError):
            self.cls.find(self.source).restore()
        self.cmds.setAttr(self.driven + ".rotateX", lock=False)
        self.cls.find(self.source).restore()
        self.cmds.disconnectAttr(self.source + ".constraintRotateX", self.driven + ".rotateX")
        other = self.cmds.createNode("animCurveTA")
        self.cmds.connectAttr(other + ".output", self.driven + ".rotateX")
        with self.assertRaises(ValueError):
            self.cls.create(self.source, axes="x")
        self.assertTrue(self.cmds.isConnected(other + ".output", self.driven + ".rotateX"))

    def test_units_and_pose_offset(self):
        """角度UI単位変更でも計算値が変わらず、固定オフセットで初期姿勢を維持する。"""
        self.pose((35, 55, 20))
        before = self.cmds.getAttr(self.driven + ".rotate")[0]
        graph = self.cls.create(self.source, axes="xy", mode="twist", preserve_pose=True)
        for a, b in zip(self.angles(graph), before):
            self.assertAlmostEqual(a, b, places=4)
        self.cmds.currentUnit(angle="rad")
        for a, b in zip(self.angles(graph), before):
            self.assertAlmostEqual(a, b, places=4)
        graph.restore()

    def test_singular_and_range_diagnostic(self):
        """範囲外・Twist特異点・Rotate Order変更はvalid=0を返す。"""
        self.pose((120, 0, 0))
        graph = self.cls.create(self.source, axes="x", half_range=math.radians(20))
        self.assertLess(graph.container.plug("valid").get(), 0.5)
        graph.restore()
        self.pose((0, 180, 0))
        graph = self.cls.create(self.source, axes="x", mode="twist", preserve_pose=False)
        self.assertLess(graph.container.plug("valid").get(), 0.5)
        self.assertAlmostEqual(self.angles(graph)[0], 0, places=4)
        graph.restore()
        self.pose((0, 0, 0))
        graph = self.cls.create(self.source)
        self.cmds.setAttr(self.driven + ".rotateOrder", 2)
        self.assertLess(graph.container.plug("valid").get(), 0.5)

    def test_compound_and_skipped_axes(self):
        """複合接続と元のskip状態を正確に復元する。"""
        for axis in "XYZ":
            self.cmds.disconnectAttr(self.source + ".constraintRotate" + axis, self.driven + ".rotate" + axis)
        self.cmds.connectAttr(self.source + ".constraintRotate", self.driven + ".rotate")
        graph = self.cls.create(self.source, axes="xy", mode="twist")
        graph.restore()
        self.assertTrue(self.cmds.isConnected(self.source + ".constraintRotate", self.driven + ".rotate"))
        self.cmds.disconnectAttr(self.source + ".constraintRotate", self.driven + ".rotate")
        self.cmds.connectAttr(self.source + ".constraintRotateY", self.driven + ".rotateY")
        self.cmds.setAttr(self.driven + ".rotateX", 12)
        self.cmds.setAttr(self.driven + ".rotateZ", 34)
        graph = self.cls.create(self.source, axes="xz", mode="twist")
        graph.restore()
        self.assertFalse(self.cmds.listConnections(self.driven + ".rotateX", source=True, destination=False))
        self.assertAlmostEqual(self.cmds.getAttr(self.driven + ".rotateX"), 12)
        self.assertAlmostEqual(self.cmds.getAttr(self.driven + ".rotateZ"), 34)
        self.assertTrue(self.cmds.isConnected(self.source + ".constraintRotateY", self.driven + ".rotateY"))

    def test_joint_and_maintain_offset(self):
        """親姿勢・jointOrient・Aim offsetを持つジョイントで初期姿勢と復元を確認する。"""
        self.cmds.delete(self.source, self.driven)
        parent = self.cmds.createNode("transform")
        self.driven = self.cmds.createNode("joint", parent=parent)
        self.cmds.setAttr(parent + ".rotate", 10, 20, 30)
        self.cmds.setAttr(self.driven + ".jointOrient", 15, 25, 35)
        self.cmds.setAttr(self.driven + ".rotate", 12, 18, 24)
        self.source = self.cmds.aimConstraint(self.driver, self.driven, maintainOffset=True, worldUpType="vector")[0]
        baseline = self.cmds.xform(self.driven, query=True, matrix=True, worldSpace=True)
        graph = self.cls.create(self.source, axes="xz", mode="twist", preserve_pose=True)
        after = self.cmds.xform(self.driven, query=True, matrix=True, worldSpace=True)
        self.assertLess(max(abs(a - b) for a, b in zip(baseline, after)), 1e-5)
        graph.restore()
        restored = self.cmds.xform(self.driven, query=True, matrix=True, worldSpace=True)
        self.assertLess(max(abs(a - b) for a, b in zip(baseline, restored)), 1e-5)

    def test_single_axes_and_negative_direction(self):
        """全単軸の負方向ヒンジと正負回転を連続更新して検証する。"""
        for axis, direction in zip("xyz", ("-y", "-z", "-x")):
            self.pose((0, 0, 0))
            graph = self.cls.create(self.source, axes=axis, mode="direction",
                                    direction=direction, preserve_pose=False)
            for angle in (-145, -30, 0, 40, 160):
                values = [0, 0, 0]
                values["xyz".index(axis)] = angle
                self.pose(values)
                self.assertAlmostEqual(self.angles(graph)["xyz".index(axis)], angle, places=3)
            graph.restore()

    def test_restore_rejects_edited_connection(self):
        """変換後に別の入力へ付け替えられた接続を復元で壊さない。"""
        graph = self.cls.create(self.source, axes="x", mode="twist")
        output = graph.container.plug("outputX").fullName()
        self.cmds.disconnectAttr(output, self.driven + ".rotateX")
        other = self.cmds.createNode("animCurveTA")
        self.cmds.connectAttr(other + ".output", self.driven + ".rotateX")
        with self.assertRaises(ValueError):
            graph.restore()
        self.assertTrue(self.cmds.isConnected(other + ".output", self.driven + ".rotateX"))
        self.assertIsNotNone(self.cls.find(self.source))



    def test_restore_original_settings_and_structure(self):
        """元Aimの値・直接接続を復元し、補正やcontainerを残さない。"""
        self.cmds.setAttr(self.source + ".restRotate", 12, 23, 34)
        self.cmds.setAttr(self.source + ".offset", 5, 10, 15)
        baseline = set(self.cmds.ls())
        values = self.cmds.getAttr(self.driven + ".rotate")[0]
        graph = self.cls.create(self.source, axes="xy", mode="twist")
        self.cmds.setAttr(self.source + ".offset", 180, -180, 90)
        self.cmds.setAttr(self.source + ".restRotate", -180, -180, -180)
        graph.restore()
        self.assertEqual(set(self.cmds.ls()), baseline)
        self.assertIsNone(self.cls.find(self.source))
        for actual, expected in zip(self.cmds.getAttr(self.source + ".offset")[0], (5, 10, 15)):
            self.assertAlmostEqual(actual, expected, places=6)
        for actual, expected in zip(self.cmds.getAttr(self.driven + ".rotate")[0], values):
            self.assertAlmostEqual(actual, expected, places=5)
        for axis in "XYZ":
            self.assertTrue(self.cmds.isConnected(self.source + ".constraintRotate" + axis,
                                                 self.driven + ".rotate" + axis))

    def test_direct_graph_modes_restore_and_switch(self):
        """全方式で直接接続の数値、コンテナ切替、復元時の全削除を確認する。"""
        baseline = set(self.cmds.ls())
        self.pose((20, 30, 15))
        for mode in ("euler", "direction", "twist"):
            with self.subTest(mode=mode):
                contained = self.cls.create(self.source, axes="xy", mode=mode, direction="z")
                expected = self.cmds.getAttr(self.driven + ".rotate")[0]
                graph = self.cls.create(self.source, axes="xy", mode=mode, direction="z", use_container=False)
                self.assertEqual(graph.container.type(), "network")
                self.assertFalse(self.cmds.ls(type="container"))
                for axis, value in zip("XYZ", expected):
                    self.assertAlmostEqual(self.cmds.getAttr(self.driven + ".rotate" + axis), value, places=5)
                for axis in "XY":
                    plug = graph.container.plug("output" + axis).source()
                    self.assertTrue(self.cmds.isConnected(plug.fullName(), self.driven + ".rotate" + axis))
                graph.restore()
                self.assertEqual(set(self.cmds.ls()), baseline)

    def test_direct_graph_save_rename_undo(self):
        """直接接続の管理情報がUndo・改名・保存読込後も使える。"""
        graph = self.cls.create(self.source, axes="x", mode="twist", use_container=False)
        self.cmds.undo()
        self.assertIsNone(self.cls.find(self.source))
        self.cmds.redo()
        self.source = self.cmds.rename(self.source, "renamedAim")
        path = ROOT / ".maya-output/aim-direct-test.ma"
        path.parent.mkdir(exist_ok=True)
        self.cmds.file(rename=str(path))
        self.cmds.file(save=True, type="mayaAscii")
        self.cmds.file(str(path), open=True, force=True)
        graph = self.cls.find(self.source)
        self.assertEqual(graph.container.type(), "network")
        graph = self.cls.create(self.source, mode="twist", use_container=True)
        self.assertEqual(graph.container.type(), "container")
        graph.restore()
        self.assertFalse(self.cmds.ls(type="container"))
        self.assertFalse(self.cmds.ls("*_axisConversion*"))

    def test_restore_legacy_correction_removes_all_nodes(self):
        """旧版の補正付き復元の保存情報からも元Aimだけへ戻せる。"""
        from hlib.json import JsonText
        baseline = set(self.cmds.ls())
        graph = self.cls.create(self.source, axes="xy")
        state = JsonText.loads(graph.container.plug("settings").get())
        state["mode"] = "rest"
        state["axes"] = "xyz"
        graph.container.plug("outputZ").connect(self.driven + ".rotateZ")
        state.pop("constraintSettings")
        graph.container.plug("settings").set(JsonText.dumps(state))
        graph.restore()
        self.assertEqual(set(self.cmds.ls()), baseline)


def runTests():
    """専用プロセス内でテストを実行する。"""
    return unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(AimAxisConversionTest))


if __name__ == "__main__":
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        success = runTests().wasSuccessful()
    finally:
        maya.standalone.uninitialize()
    sys.exit(0 if success else 1)
