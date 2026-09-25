"""JSONの型往復・参照・事前検証・Undoを実Mayaで検証する。"""
import math
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
import maya.cmds as cmds
import hlib

hlib.reload()


class JsonTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibJson_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.selection = cmds.ls(selection=True, long=True) or []
        self.paths = []

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        cmds.select(self.selection, replace=True) if self.selection else cmds.select(clear=True)
        for path in self.paths:
            if Path(path).exists():
                Path(path).unlink()

    def node(self, kind="transform", suffix="node"):
        return hlib.createNode(kind, name=self.ns + ":" + suffix)

    def roundtrip(self, value):
        return hlib.json.loads(hlib.json.dumps(value))

    def test_math_and_dict_tags(self):
        from hlib import maths
        values = [maths.Vector(1, 2, 3), maths.Translation(1, 2, 3), maths.EulerRotation(.1, .2, .3),
                  maths.Scale(1, 2, 3), maths.Shear(1, 2, 3), maths.EulerRotation(.1, .2, .3, "zyx"),
                  maths.Quaternion(0, 0, 0, 1), maths.Matrix()]
        for value in values:
            restored = self.roundtrip(value)
            self.assertIs(type(restored), type(value))
            self.assertEqual(list(restored), list(value))
        self.assertEqual(self.roundtrip(values[5]).order, "zyx")
        raw = {"type": "NodeRef", "value": {"日本語": (True, None, 4)}}
        self.assertEqual(self.roundtrip(raw), raw)
        for invalid in [math.nan, math.inf, object(), {2: "value"}]:
            with self.assertRaises((ValueError, TypeError)):
                hlib.json.dumps(invalid)

    def test_storage_atomic_and_version(self):
        path = hlib.json.dump({"日本語": 1}, metadata={"label": "test"})
        self.paths.append(path)
        self.assertEqual(hlib.json.load(path), {"日本語": 1})
        self.assertEqual(hlib.json.load_document(path).metadata["label"], "test")
        with patch("hlib.json.storage.os.replace", side_effect=OSError("test failure")):
            with self.assertRaises(OSError):
                hlib.json.dump({"new": 2}, path)
        self.assertEqual(hlib.json.load(path), {"日本語": 1})
        with self.assertRaises(ValueError):
            hlib.json.loads(hlib.json.dumps(1).replace('"version": 1', '"version": 999'))
        with self.assertRaises(ValueError):
            hlib.json.loads('{"a":1,"a":2}')

    def test_refs_and_explicit_mapping(self):
        first, second = self.node(suffix="a"), self.node(suffix="b")
        ref = self.roundtrip(first)
        cmds.rename(first.full_name(), self.ns + ":renamed")
        self.assertEqual(ref.resolve().uuid(), first.uuid())
        self.assertEqual(ref.resolve(mapping={ref.path: second.full_name()}).uuid(), second.uuid())
        with self.assertRaises(ValueError):
            ref.resolve(mapping={ref.path: "missing_json_target"})
        plug = self.roundtrip(second.plug("translateX"))
        self.assertEqual(plug.resolve().full_name(), second.plug("translateX").full_name())
        cmds.delete(first.full_name())
        # 削除した参照もJSONとして読むことはできる。
        self.assertEqual(self.roundtrip(ref), ref)
        with self.assertRaises(ValueError):
            ref.resolve()

    def test_pose_apply_and_preflight(self):
        first, second = self.node(suffix="a"), self.node(suffix="b")
        cmds.setAttr(first.full_name() + ".tx", 5)
        snapshot = self.roundtrip(hlib.json.capture([first, second], kind="pose"))
        cmds.setAttr(first.full_name() + ".tx", 10)
        cmds.setAttr(second.full_name() + ".tx", lock=True)
        with self.assertRaises(ValueError):
            snapshot.apply()
        self.assertEqual(cmds.getAttr(first.full_name() + ".tx"), 10)
        cmds.setAttr(second.full_name() + ".tx", lock=False)
        self.assertTrue(snapshot.validate().valid)
        snapshot.apply()
        self.assertEqual(cmds.getAttr(first.full_name() + ".tx"), 5)
        cmds.undo()
        self.assertEqual(cmds.getAttr(first.full_name() + ".tx"), 10)
        cmds.redo()
        self.assertEqual(cmds.getAttr(first.full_name() + ".tx"), 5)
        snapshot.units["linear"] = "invalid"
        self.assertFalse(snapshot.validate().valid)

    def test_curve_selection_and_undo(self):
        name = cmds.circle(name=self.ns + ":curve", constructionHistory=False)[0]
        curve = hlib.node(name)
        snapshot = self.roundtrip(hlib.json.capture(curve, kind="curve"))
        cv = curve.shape().full_name() + ".cv[0]"
        before = cmds.xform(cv, query=True, translation=True, objectSpace=True)
        cmds.xform(cv, translation=(7, 8, 9), objectSpace=True)
        snapshot.apply()
        self.assertEqual(cmds.xform(cv, query=True, translation=True, objectSpace=True), before)
        cmds.undo()
        self.assertEqual(cmds.xform(cv, query=True, translation=True, objectSpace=True), [7, 8, 9])
        cmds.select(cv)
        selected = cmds.ls(selection=True, long=True)
        selection = self.roundtrip(hlib.json.capture(kind="selection"))
        cmds.select(clear=True)
        selection.apply()
        self.assertEqual(cmds.ls(selection=True, long=True), selected)
        cmds.undo()
        self.assertEqual(cmds.ls(selection=True), [])

    def test_animation_tangents_and_undo(self):
        curve = self.node("animCurveUU")
        curve.set_key(0, 1)
        curve.set_key(3, 4)
        curve.set_tangent(0, weightedTangents=True, lock=False, weightLock=False,
                          inTangentType="fixed", outTangentType="fixed")
        curve.set_tangent(0, inAngle=12, outAngle=25, inWeight=.5, outWeight=.8)
        snapshot = self.roundtrip(hlib.json.capture(curve, kind="animation"))
        expected = curve.tangent(0)
        curve.set_key(7, 8)
        snapshot.apply()
        self.assertEqual(curve.key_inputs(), [0, 3])
        for key in ("inAngle", "outAngle", "inWeight", "outWeight"):
            self.assertAlmostEqual(curve.tangent(0)[key], expected[key], places=5)
        cmds.undo()
        self.assertEqual(curve.key_inputs(), [0, 3, 7])

    def test_skin_sparse_weights(self):
        joints = [self.node("joint", "j" + str(i)) for i in range(2)]
        mesh = cmds.polyCube(name=self.ns + ":mesh", constructionHistory=False)[0]
        name = cmds.skinCluster([j.full_name() for j in joints], mesh, name=self.ns + ":skin")[0]
        skin = hlib.node(name)
        pose = skin.bind_pose()
        if pose:
            cmds.rename(pose.full_name(), self.ns + ":pose")
        names = [j.full_name() for j in joints]
        skin.set_weights(names, [.25, .75])
        snapshot = self.roundtrip(hlib.json.capture(skin, kind="skin_weights"))
        skin.set_weights(names, [.9, .1])
        snapshot.apply()
        self.assertAlmostEqual(list(skin.get_weights(names))[0], .25)
        cmds.undo()
        self.assertAlmostEqual(list(skin.get_weights(names))[0], .9)

    def test_sdk_graph_validation(self):
        driver, driven = self.node(suffix="driver"), self.node(suffix="driven")
        sdk = hlib.drivenKey(driver.plug("tx"), driven.plug("ty"))
        sdk.set_key(0, 1)
        sdk.set_key(2, 3)
        snapshot = self.roundtrip(hlib.json.capture(driven, kind="driven_keys"))
        sdk.set_key(4, 5)
        snapshot.apply()
        self.assertEqual(sdk.curves()[0].key_count(), 2)
        cmds.undo()
        self.assertEqual(sdk.curves()[0].key_count(), 3)
        cmds.disconnectAttr(driver.plug("tx").full_name(), sdk.curves()[0].full_name() + ".input")
        self.assertFalse(snapshot.validate().valid)

    def test_attributes_and_namespace_map(self):
        first, second = self.node(suffix="a"), self.node(suffix="b")
        for node in (first, second):
            cmds.addAttr(node.full_name(), longName="label", dataType="string")
        cmds.setAttr(first.full_name() + ".label", "日本語", type="string")
        snapshot = self.roundtrip(hlib.json.capture(first, kind="attributes", attributes=["label", "translate"]))
        snapshot.apply(mapping={snapshot.records[0]["node"].path: second.full_name()})
        self.assertEqual(cmds.getAttr(second.full_name() + ".label"), "日本語")
        ref = hlib.json.NodeRef.capture(first)
        with self.assertRaises(ValueError):
            ref.resolve(namespace_map={self.ns: "missing_namespace"})

    def test_editor_timeline_read_only(self):
        original = hlib.json.capture(hlib.timeSlider(), kind="editor")
        try:
            saved = self.roundtrip(original)
            original_time = cmds.currentTime(query=True)
            cmds.currentTime(original_time + 3)
            plan = saved.plan()
            self.assertTrue(plan.errors)
            self.assertEqual(plan.changes[0]["before"]["values"]["currentTime"], original_time + 3)
            self.assertFalse(saved.validate().valid)
            with patch.object(cmds, "loadPlugin", side_effect=AssertionError("Plugin loading forbidden")):
                with self.assertRaises(NotImplementedError):
                    saved.apply()
                with self.assertRaises(NotImplementedError):
                    plan.apply()
            self.assertEqual(cmds.currentTime(query=True), original_time + 3)
        finally:
            cmds.currentTime(original_time)

    def test_all_animation_types(self):
        for suffix in ("TA", "TL", "TT", "TU", "UA", "UL", "UT", "UU"):
            with self.subTest(suffix=suffix):
                curve = self.node("animCurve" + suffix, "curve" + suffix)
                curve.set_key(0, 1)
                curve.set_key(2, 3)
                saved = self.roundtrip(hlib.json.capture(curve, kind="animation"))
                curve.set_key(2, 5)
                saved.apply()
                self.assertAlmostEqual(curve.values()[1], 3, places=5)

    def test_plan_revalidates_and_rejects_connected_attribute(self):
        first, second = self.node(suffix="a"), self.node(suffix="b")
        saved = hlib.json.capture(first, kind="attributes", attributes=["tx"])
        plan = saved.plan()
        self.assertEqual(plan.errors, [])
        cmds.connectAttr(second.full_name() + ".ty", first.full_name() + ".tx")
        with self.assertRaises(ValueError):
            plan.apply()

    def test_edited_json_rejected_before_changes(self):
        first, second = self.node(suffix="a"), self.node(suffix="b")
        saved = hlib.json.capture([first, second], kind="attributes", attributes=["tx"])
        cmds.setAttr(first.full_name() + ".tx", 7)
        saved.records[1]["attributes"][0]["value"] = "invalid"
        with self.assertRaises(ValueError):
            saved.apply()
        self.assertEqual(cmds.getAttr(first.full_name() + ".tx"), 7)

    def test_reload_entry(self):
        hlib.reload()
        self.assertEqual(hlib.json.loads(hlib.json.dumps({"ok": 1})), {"ok": 1})

    @unittest.skipIf(cmds.about(batch=True), "Requires Maya GUI")
    def test_editor_panels_read_only(self):
        window = cmds.window(title="hlib JSON editor test")
        try:
            cmds.paneLayout(configuration="vertical2")
            panel = cmds.modelPanel()
            editor = cmds.outlinerEditor()
            cmds.showWindow(window)
            viewport, outliner = hlib.viewport(panel), hlib.outliner(editor)
            saved = self.roundtrip(hlib.json.capture([viewport, outliner], kind="editor"))
            original = viewport.settings("grid")["grid"]
            viewport.set_settings(grid=not original)
            self.assertTrue(saved.plan().errors)
            with self.assertRaises(NotImplementedError):
                saved.apply()
            self.assertEqual(viewport.settings("grid")["grid"], not original)
            self.assertEqual(outliner.settings(), saved.records[1]["values"])
        finally:
            cmds.deleteUI(window)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
