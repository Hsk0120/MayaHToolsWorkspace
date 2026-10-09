"""用途別Snapshot入口と保存能力・計画の判定を検証する。"""
import unittest
import uuid
from unittest.mock import patch

from maya import cmds
import hlib


class SnapshotWorkflowsTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibSnapshotWorkflow_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns, parent=":")
        self.selection = cmds.ls(selection=True, long=True) or []
        self.node = hlib.createNode("transform", name=self.ns + ":node", skipSelect=True)

    def tearDown(self):
        cmds.namespace(removeNamespace=":" + self.ns, deleteNamespaceContent=True)
        cmds.select(self.selection, replace=True) if self.selection else cmds.select(clear=True)

    def test_pose_capture_roundtrip_plan_apply_undo(self):
        """型から取得し、保存・読込・計画・適用をそのまま続けられる。"""
        plug = self.node.getFullName() + ".translateX"
        cmds.setAttr(plug, 5)
        captured = hlib.json.PoseSnapshot.capture(self.node)
        saved = hlib.json.loads(hlib.json.dumps(captured))
        self.assertIs(type(saved), hlib.json.PoseSnapshot)
        self.assertTrue(saved.supportsApply)
        self.assertEqual(set(saved.asData()), {"kind", "records", "units", "version"})
        cmds.setAttr(plug, 10)
        plan = saved.plan()
        self.assertTrue(plan.valid)
        plan.apply()
        self.assertEqual(cmds.getAttr(plug), 5)
        cmds.undo()
        self.assertEqual(cmds.getAttr(plug), 10)
        cmds.redo()
        self.assertEqual(cmds.getAttr(plug), 5)

    def test_attributes_and_selection_typed_capture(self):
        """必要な引数を公開し、既存保存用途へ同じ内容を取得する。"""
        attrs = hlib.json.AttributesSnapshot.capture(self.node, ["translate", "visibility"])
        legacy = hlib.json.capture(self.node, kind="attributes", attributes=["translate", "visibility"])
        self.assertEqual(attrs.asData(), legacy.asData())
        cmds.select(self.node.getFullName())
        selection = hlib.json.SelectionSnapshot.capture()
        self.assertEqual(selection.kind, "selection")
        cmds.select(clear=True)
        selection.apply()
        self.assertEqual(cmds.ls(selection=True, long=True), [self.node.getFullName()])

    def test_all_typed_entries_delegate_to_existing_capture(self):
        """固定kindと対象を既存処理へ渡し、別の保存方式を作らない。"""
        pairs = (("PoseSnapshot", "pose"), ("NurbsCurveSnapshot", "curve"),
                 ("SkinWeightsSnapshot", "skin_weights"), ("AnimationSnapshot", "animation"),
                 ("DrivenKeysSnapshot", "driven_keys"), ("EditorSnapshot", "editor"))
        with patch("hlib.json.snapshots.capture", return_value=self.node) as capture:
            for name, kind in pairs:
                with self.subTest(name=name):
                    self.assertIs(getattr(hlib.json, name).capture(self.node), self.node)
                    capture.assert_called_with(self.node, kind=kind)
            self.assertIs(hlib.json.Snapshot.capture(self.node, kind="pose"), self.node)
            capture.assert_called_with(self.node, kind="pose", attributes=None)

    def test_editor_capability_remains_false_after_json_roundtrip(self):
        """能力情報を保存キーへ混ぜず、適用未対応の制限を保持する。"""
        captured = hlib.json.EditorSnapshot.capture(hlib.common.TimeSlider())
        loaded = hlib.json.loads(hlib.json.dumps(captured))
        self.assertFalse(loaded.supportsApply)
        self.assertFalse(loaded.plan().valid)
        with self.assertRaises(NotImplementedError):
            loaded.apply()
        self.assertEqual(set(loaded.asData()), {"kind", "records", "units", "version"})

    def test_capability_and_plan_valid_only_use_held_values(self):
        """能力と計画エラーを保持値だけで判定し、実対象検証と混同しない。"""
        pairs = (("SelectionSnapshot", "selection"), ("AttributesSnapshot", "attributes"),
                 ("PoseSnapshot", "pose"), ("NurbsCurveSnapshot", "curve"),
                 ("SkinWeightsSnapshot", "skin_weights"), ("AnimationSnapshot", "animation"),
                 ("DrivenKeysSnapshot", "driven_keys"))
        with patch("hlib.json.snapshots._units", side_effect=AssertionError("Unexpected Maya query")):
            for name, kind in pairs:
                self.assertTrue(getattr(hlib.json, name)(kind, [], {}).supportsApply)
            plan = hlib.json.ApplyPlan(None)
            self.assertTrue(plan.valid)
            plan.errors.append("target missing")
            self.assertFalse(plan.valid)
            self.assertTrue(bool(plan))


if __name__ == "__main__":
    unittest.main()
