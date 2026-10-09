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

    def getNode(self, kind="transform", suffix="node"):
        return hlib.createNode(kind, name=self.ns + ":" + suffix)

    def roundtrip(self, value):
        return hlib.json.loads(hlib.json.dumps(value))

    def test_math_and_dict_tags(self):
        from hlib import maths
        values = [maths.Vector(1, 2, 3), maths.Translate(1, 2, 3), maths.EulerRotate(.1, .2, .3),
                  maths.Scale(1, 2, 3), maths.Shear(1, 2, 3), maths.EulerRotate(.1, .2, .3, "zyx"),
                  maths.Quaternion(0, 0, 0, 1), maths.Matrix()]
        for value in values:
            restored = self.roundtrip(value)
            self.assertIs(type(restored), type(value))
            self.assertEqual(list(restored), list(value))
        # order は om2 の番号(int)。JSON には名前で保存し、名前で読み戻せる。
        self.assertEqual(self.roundtrip(values[5]).orderName, "zyx")
        self.assertEqual(hlib.json.dumps(values[5]).count('"zyx"'), 1)
        raw = {"type": "NodeRef", "value": {"日本語": (True, None, 4)}}
        self.assertEqual(self.roundtrip(raw), raw)
        for invalid in [math.nan, math.inf, object(), {2: "value"}]:
            with self.assertRaises((ValueError, TypeError)):
                hlib.json.dumps(invalid)

    def test_om2_math_results_are_saved_as_hlib_types(self):
        import maya.api.OpenMaya as om2
        from hlib import maths
        # om2 名のメソッドが返す om2 の基底型も、対応する hlib の型として保存・復元する。
        pairs = [
            (maths.Vector(1, 0, 0).normal(), maths.Vector),
            (maths.Quaternion(0.1, 0.2, 0.3, 0.9).normal(), maths.Quaternion),
            (maths.Quaternion(0.1, 0.2, 0.3, 0.9).asEulerRotation().reorder(5), maths.EulerRotate),
            (maths.Matrix(translate=(1, 2, 3)).adjoint(), maths.Matrix),
        ]
        for value, expected_type in pairs:
            restored = self.roundtrip(value)
            self.assertIs(type(restored), expected_type)
            self.assertEqual(list(restored), list(value))
        self.assertEqual(self.roundtrip(pairs[2][0]).orderName, "zyx")
        # 利用者の派生クラスや MPoint は対象外。
        subclass = type("UserVector", (maths.Vector,), {})
        for invalid in (subclass(1, 2, 3), om2.MPoint(1, 2, 3)):
            with self.assertRaises(TypeError):
                hlib.json.dumps(invalid)

    def test_codec_type_map_uses_exact_types_and_follows_reload(self):
        import collections
        from hlib import maths
        codec = sys.modules["hlib.json.codec"]
        # 数学型の対応表はモジュールの読み込み時に1回だけ作り、公開クラスそのものを指す。
        names = (("Vector", "Vector"), ("Translation", "Translate"), ("Scale", "Scale"),
                 ("Shear", "Shear"), ("EulerRotation", "EulerRotate"),
                 ("Quaternion", "Quaternion"), ("Matrix", "Matrix"))
        for saved_name, class_name in names:
            cls = getattr(maths, class_name)
            self.assertIs(codec._MATH_CLASSES[saved_name], cls)
            self.assertEqual(codec._math_type_name(cls()), saved_name)
        self.assertIsNone(codec._math_type_name({"values": [1.0, 2.0, 3.0]}))
        self.assertIsNone(codec._math_type_name([1.0, 2.0, 3.0]))
        # hlib.reload() 後は再読み込みした新しいクラスで作り直される。
        hlib.reload()
        from hlib import maths as reloaded
        codec = sys.modules["hlib.json.codec"]
        for saved_name, class_name in names:
            self.assertIs(codec._MATH_CLASSES[saved_name], getattr(reloaded, class_name))
        value = reloaded.Matrix(translate=(1, 2, 3))
        self.assertEqual(codec._math_type_name(value), "Matrix")
        restored = self.roundtrip(value)
        self.assertIs(type(restored), reloaded.Matrix)
        self.assertEqual(list(restored), list(value))
        # dict / list / tuple も型そのもので判定し、派生クラスは従来どおり未対応型。
        pair = collections.namedtuple("Pair", "a b")
        for invalid in (pair(1, 2), type("UserList", (list,), {})([1]), type("UserDict", (dict,), {})(a=1)):
            with self.assertRaises(TypeError, msg=type(invalid).__name__):
                hlib.json.dumps(invalid)
        nested = (1, [2.0, {"a": None, "b": (True, "x")}], reloaded.Vector(1, 2, 3))
        restored = self.roundtrip(nested)
        self.assertEqual(restored[:2], nested[:2])
        self.assertIs(type(restored[2]), reloaded.Vector)

    def test_math_records_are_validated(self):
        # 要素数・要素の型・キーを検査し、om2 のコンストラクタが黙って補う形も拒否する。
        import json as std_json

        def edited(value, edit):
            document = std_json.loads(hlib.json.dumps(value))
            edit(document["data"]["value"]["value"])
            return std_json.dumps(document)

        def set_values(values):
            def edit(fields):
                fields["values"]["value"] = values
            return edit

        vector = hlib.maths.Vector(1, 2, 3)
        self.assertEqual(tuple(hlib.json.loads(edited(vector, set_values([1.0, 2.0, 3.0])))), (1.0, 2.0, 3.0))
        self.assertEqual(tuple(hlib.json.loads(edited(vector, set_values([1, 2, 3])))), (1.0, 2.0, 3.0))
        invalid_values = [
            [1.0, 2.0],
            [],
            [1.0, 2.0, 3.0, 4.0],
            [True, 2.0, 3.0],
            ["1", "2", "3"],
            [None, 2.0, 3.0],
            [{"type": "list", "value": [1.0, 2.0, 3.0]}],
        ]
        for values in invalid_values:
            with self.assertRaises(ValueError, msg=repr(values)):
                hlib.json.loads(edited(vector, set_values(values)))
        with self.assertRaises(ValueError):
            hlib.json.loads(edited(vector, lambda fields: fields.update(extra=1)))
        with self.assertRaises(ValueError):
            hlib.json.loads(edited(vector, lambda fields: fields.pop("values")))
        with self.assertRaises(ValueError):
            hlib.json.loads(edited(hlib.maths.Quaternion(0, 0, 0, 1), set_values([])))
        with self.assertRaises(ValueError):
            hlib.json.loads(edited(hlib.maths.Matrix(), set_values([1.0] * 15)))

        euler = hlib.maths.EulerRotate(0.1, 0.2, 0.3, "zyx")
        self.assertEqual(hlib.json.loads(edited(euler, lambda fields: fields.update(order=5))).orderName, "zyx")
        for order in ("abc", 6, True, None):
            with self.assertRaises(ValueError, msg=repr(order)):
                hlib.json.loads(edited(euler, lambda fields, order=order: fields.update(order=order)))
        # order を省略した記録は XYZ 順序。
        restored = hlib.json.loads(edited(euler, lambda fields: fields.pop("order")))
        self.assertEqual(restored.orderName, "xyz")

    def test_storage_atomic_and_version(self):
        path = hlib.json.dump({"日本語": 1}, metadata={"label": "test"})
        self.paths.append(path)
        self.assertEqual(hlib.json.load(path), {"日本語": 1})
        self.assertEqual(hlib.json.loadDocument(path).metadata["label"], "test")
        with patch("hlib.json.storage.os.replace", side_effect=OSError("test failure")):
            with self.assertRaises(OSError):
                hlib.json.dump({"new": 2}, path)
        self.assertEqual(hlib.json.load(path), {"日本語": 1})
        with self.assertRaises(ValueError):
            hlib.json.loads(hlib.json.dumps(1).replace('"version": 1', '"version": 999'))
        with self.assertRaises(ValueError):
            hlib.json.loads('{"a":1,"a":2}')

    def test_refs_and_explicit_mapping(self):
        first, second = self.getNode(suffix="a"), self.getNode(suffix="b")
        ref = self.roundtrip(first)
        cmds.rename(first.getFullName(), self.ns + ":renamed")
        self.assertEqual(ref.resolve().getUuid(), first.getUuid())
        self.assertEqual(ref.resolve(mapping={ref.path: second.getFullName()}).getUuid(), second.getUuid())
        with self.assertRaises(ValueError):
            ref.resolve(mapping={ref.path: "missing_json_target"})
        plug = self.roundtrip(second.getPlug("translateX"))
        self.assertEqual(plug.resolve().getFullName(), second.getPlug("translateX").getFullName())
        # 配列要素・子アトリビュート・エイリアスのアトリビュートパスも Node.getPlug() で解決できる(要素は作らない)。
        average = self.getNode("plusMinusAverage", "average")
        base = cmds.polyCube(name=self.ns + ":base")[0]
        target = cmds.polyCube(name=self.ns + ":target")[0]
        blend = hlib.getNode(cmds.blendShape(target, base, name=self.ns + ":blend")[0])
        for element in (average.getPlug("input1D[3]"), average.getPlug("input3D[2].input3Dy"),
                        second.getPlug("worldMatrix[0]"), blend.getPlug("weight")[0],
                        blend.getPlug("inputTarget[0].inputTargetGroup[0].inputTargetItem[6000]"
                                   ".inputComponentsTarget")):
            with self.subTest(plug=element.getFullName()):
                restored = self.roundtrip(element).resolve()
                self.assertEqual(restored.getFullName(), element.getFullName())
                self.assertEqual(restored.mplug(), element.mplug())
        self.assertEqual(cmds.getAttr(average.getFullName() + ".input1D", multiIndices=True), None)
        cmds.delete(first.getFullName())
        # 削除した参照もJSONとして読むことはできる。
        self.assertEqual(self.roundtrip(ref), ref)
        with self.assertRaises(ValueError):
            ref.resolve()

    def test_pose_apply_and_preflight(self):
        first, second = self.getNode(suffix="a"), self.getNode(suffix="b")
        cmds.setAttr(first.getFullName() + ".tx", 5)
        snapshot = self.roundtrip(hlib.json.capture([first, second], kind="pose"))
        cmds.setAttr(first.getFullName() + ".tx", 10)
        cmds.setAttr(second.getFullName() + ".tx", lock=True)
        with self.assertRaises(ValueError):
            snapshot.apply()
        self.assertEqual(cmds.getAttr(first.getFullName() + ".tx"), 10)
        cmds.setAttr(second.getFullName() + ".tx", lock=False)
        self.assertTrue(snapshot.validate().valid)
        snapshot.apply()
        self.assertEqual(cmds.getAttr(first.getFullName() + ".tx"), 5)
        cmds.undo()
        self.assertEqual(cmds.getAttr(first.getFullName() + ".tx"), 10)
        cmds.redo()
        self.assertEqual(cmds.getAttr(first.getFullName() + ".tx"), 5)
        snapshot.units["linear"] = "invalid"
        self.assertFalse(snapshot.validate().valid)

    def test_curve_selection_and_undo(self):
        name = cmds.circle(name=self.ns + ":curve", constructionHistory=False)[0]
        curve = hlib.getNode(name)
        snapshot = self.roundtrip(hlib.json.capture(curve, kind="curve"))
        cv = curve.getShape().getFullName() + ".cv[0]"
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
        curve = self.getNode("animCurveUU")
        curve.setKey(0, 1)
        curve.setKey(3, 4)
        curve.setTangent(0, weightedTangents=True, lock=False, weightLock=False,
                          inTangentType="fixed", outTangentType="fixed")
        curve.setTangent(0, inAngle=12, outAngle=25, inWeight=.5, outWeight=.8)
        snapshot = self.roundtrip(hlib.json.capture(curve, kind="animation"))
        expected = curve.getTangent(0)
        curve.setKey(7, 8)
        snapshot.apply()
        self.assertEqual(curve.getKeyInputs(), [0, 3])
        for key in ("inAngle", "outAngle", "inWeight", "outWeight"):
            self.assertAlmostEqual(curve.getTangent(0)[key], expected[key], places=5)
        cmds.undo()
        self.assertEqual(curve.getKeyInputs(), [0, 3, 7])

    def test_skin_sparse_weights(self):
        joints = [self.getNode("joint", "j" + str(i)) for i in range(2)]
        mesh = cmds.polyCube(name=self.ns + ":mesh", constructionHistory=False)[0]
        name = cmds.skinCluster([j.getFullName() for j in joints], mesh, name=self.ns + ":skin")[0]
        skin = hlib.getNode(name)
        pose = skin.getBindPose()
        if pose:
            cmds.rename(pose.getFullName(), self.ns + ":pose")
        names = [j.getFullName() for j in joints]
        skin.setWeights(names, [.25, .75])
        snapshot = self.roundtrip(hlib.json.capture(skin, kind="skin_weights"))
        skin.setWeights(names, [.9, .1])
        snapshot.apply()
        self.assertAlmostEqual(list(skin.getWeights(names))[0], .25)
        cmds.undo()
        self.assertAlmostEqual(list(skin.getWeights(names))[0], .9)

    def test_sdk_graph_validation(self):
        driver, driven = self.getNode(suffix="driver"), self.getNode(suffix="driven")
        sdk = hlib.getDrivenKey(driver.getPlug("tx"), driven.getPlug("ty"))
        sdk.setKey(0, 1)
        sdk.setKey(2, 3)
        snapshot = self.roundtrip(hlib.json.capture(driven, kind="driven_keys"))
        sdk.setKey(4, 5)
        snapshot.apply()
        self.assertEqual(sdk.getCurves()[0].getKeyCount(), 2)
        cmds.undo()
        self.assertEqual(sdk.getCurves()[0].getKeyCount(), 3)
        cmds.disconnectAttr(driver.getPlug("tx").getFullName(), sdk.getCurves()[0].getFullName() + ".input")
        self.assertFalse(snapshot.validate().valid)

    def test_attributes_and_namespace_map(self):
        first, second = self.getNode(suffix="a"), self.getNode(suffix="b")
        for node in (first, second):
            cmds.addAttr(node.getFullName(), longName="label", dataType="string")
        cmds.setAttr(first.getFullName() + ".label", "日本語", type="string")
        snapshot = self.roundtrip(hlib.json.capture(first, kind="attributes", attributes=["label", "translate"]))
        snapshot.apply(mapping={snapshot.records[0]["node"].path: second.getFullName()})
        self.assertEqual(cmds.getAttr(second.getFullName() + ".label"), "日本語")
        ref = hlib.json.NodeRef.capture(first)
        with self.assertRaises(ValueError):
            ref.resolve(namespace_map={self.ns: "missing_namespace"})

    def test_editor_timeline_read_only(self):
        original = hlib.json.capture(hlib.getTimeSlider(), kind="editor")
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
                curve = self.getNode("animCurve" + suffix, "curve" + suffix)
                curve.setKey(0, 1)
                curve.setKey(2, 3)
                saved = self.roundtrip(hlib.json.capture(curve, kind="animation"))
                curve.setKey(2, 5)
                saved.apply()
                self.assertAlmostEqual(curve.getKeyValues()[1], 3, places=5)

    def test_plan_revalidates_and_rejects_connected_attribute(self):
        first, second = self.getNode(suffix="a"), self.getNode(suffix="b")
        saved = hlib.json.capture(first, kind="attributes", attributes=["tx"])
        plan = saved.plan()
        self.assertEqual(plan.errors, [])
        cmds.connectAttr(second.getFullName() + ".ty", first.getFullName() + ".tx")
        with self.assertRaises(ValueError):
            plan.apply()

    def test_edited_json_rejected_before_changes(self):
        first, second = self.getNode(suffix="a"), self.getNode(suffix="b")
        saved = hlib.json.capture([first, second], kind="attributes", attributes=["tx"])
        cmds.setAttr(first.getFullName() + ".tx", 7)
        saved.records[1]["attributes"][0]["value"] = "invalid"
        with self.assertRaises(ValueError):
            saved.apply()
        self.assertEqual(cmds.getAttr(first.getFullName() + ".tx"), 7)

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
            viewport, outliner = hlib.getViewport(panel), hlib.getOutliner(editor)
            saved = self.roundtrip(hlib.json.capture([viewport, outliner], kind="editor"))
            original = viewport.getSettings("grid")["grid"]
            viewport.setSettings(grid=not original)
            self.assertTrue(saved.plan().errors)
            with self.assertRaises(NotImplementedError):
                saved.apply()
            self.assertEqual(viewport.getSettings("grid")["grid"], not original)
            self.assertEqual(outliner.getSettings(), saved.records[1]["values"])
        finally:
            cmds.deleteUI(window)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
