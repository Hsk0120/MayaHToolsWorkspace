"""mlib.json の AnimationSnapshot・DrivenKeysSnapshot を確かめる。"""

import json as std_json
import os
import shutil
import sys
import tempfile
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.json._animCurveData import _read_curve
from mlib.json.animationSnapshot import AnimationSnapshot
from mlib.json.drivenKeysSnapshot import DrivenKeysSnapshot
from support.specCase import NamespaceCase

#: テストの前後で差分を取り、テストが作ったものを消すノード型。
_CLEANUP_TYPES = ["animCurve", "animBlendNodeBase", "animLayer", "blendWeighted", "unitConversion"]


class _AnimCase(NamespaceCase):
    """カーブ・レイヤー等の後片付けと、カーブの比較を持つ基底。"""

    PREFIX = "mlibSpecJsonAnim_"

    def setUp(self):
        super().setUp()
        self.time_unit = cmds.currentUnit(query=True, time=True)
        cmds.currentUnit(time="film")
        self.before = set(cmds.ls(type=_CLEANUP_TYPES) or [])
        self.other = self.ns + "B"
        cmds.namespace(add=self.other)
        self.extra_namespaces.append(self.other)
        self.folder = tempfile.mkdtemp(prefix="mlibJsonAnim")

    def tearDown(self):
        cmds.currentUnit(time=self.time_unit)
        created = [node for node in cmds.ls(type=_CLEANUP_TYPES) or [] if node not in self.before]
        layers = [node for node in created if cmds.nodeType(node) == "animLayer"]
        for layer in layers:
            if cmds.objExists(layer):
                cmds.animLayer(layer, edit=True, lock=False)
        created = [node for node in created if cmds.objExists(node)]
        if created:
            cmds.delete(created)
        shutil.rmtree(self.folder, ignore_errors=True)
        super().tearDown()

    def other_name(self, text):
        """もう1つの名前空間の名前を返す。"""
        return self.other + ":" + text

    def curve(self, plug):
        """Plugへ直接つながるカーブ名を返す。"""
        curves = cmds.listConnections(plug, source=True, destination=False, skipConversionNodes=True,
                                      type="animCurve") or []
        return curves[0] if curves else None

    def assertCurveData(self, actual, expected):
        """カーブの辞書が同じ形か確かめる。接線は float32 で保持されるため誤差を許す。"""
        for name in ("curveType", "weighted", "preInfinity", "postInfinity"):
            self.assertEqual(actual[name], expected[name], name)
        self.assertEqual(len(actual["keys"]), len(expected["keys"]))
        for got, want in zip(actual["keys"], expected["keys"]):
            for name, value in want.items():
                if name.endswith("Weight") and want[name[:-6] + "Type"] in ("step", "stepnext"):
                    continue  # step の接線は形を持たず、Maya のウェイトの報告が一定でない。
                if isinstance(value, float):
                    self.assertAlmostEqual(got[name], value, places=4, msg=f"{name} at {want['input']}")
                else:
                    self.assertEqual(got[name], value, f"{name} at {want['input']}")

    def keyTimes(self, plug):
        """Plug のキーの時刻を返す。"""
        return cmds.keyframe(plug, query=True, timeChange=True) or []


class AnimationSnapshotTest(_AnimCase):
    """時間入力のアニメカーブの保存と適用。"""

    def setUp(self):
        super().setUp()
        self.a = cmds.createNode("transform", name=self.name("a"))
        self.b = cmds.createNode("transform", name=self.other_name("a"))
        for frame, value in ((0, 0), (10, 5), (15, 1), (20, -3), (30, 2)):
            cmds.setKeyframe(self.a + ".tx", time=frame, value=value)
            cmds.setKeyframe(self.a + ".rx", time=frame, value=value * 10)
        cmds.setKeyframe(self.a + ".visibility", time=0, value=1)
        cmds.setKeyframe(self.a + ".visibility", time=40, value=0)
        for attribute in ("tx", "rx"):
            curve = self.curve(self.a + "." + attribute)
            cmds.keyTangent(curve, edit=True, weightedTangents=True)
            cmds.keyTangent(curve, edit=True, index=(1, 1), lock=False, weightLock=False)
            cmds.keyTangent(curve, edit=True, index=(1, 1), outAngle=30, outWeight=5, inAngle=-10, inWeight=2)
            cmds.keyTangent(curve, edit=True, index=(1, 1), lock=True)
            cmds.keyTangent(curve, edit=True, index=(3, 3), inTangentType="linear", outTangentType="step")
            cmds.keyTangent(curve, edit=True, index=(4, 4), inTangentType="flat", outTangentType="clamped",
                            weightLock=False)
            cmds.keyframe(curve, edit=True, index=(2, 2), breakdown=True)
            cmds.setInfinity(self.a + "." + attribute, preInfinite="cycle", postInfinite="oscillate")

    def original(self, attribute):
        """元のノードのカーブの辞書を返す。"""
        return _read_curve(self.curve(self.a + "." + attribute))

    def test_round_trip_through_file(self):
        expected = {attribute: self.original(attribute) for attribute in ("tx", "rx", "visibility")}
        self.assertEqual((expected["tx"]["preInfinity"], expected["tx"]["weighted"]), ("cycle", True))
        self.assertTrue(expected["tx"]["keys"][2]["breakdown"])
        snap = AnimationSnapshot.capture(self.a)
        path = snap.save(os.path.join(self.folder, "anim.json"))
        with open(str(path), encoding="utf-8") as stream:
            raw = std_json.load(stream)
        self.assertEqual(raw["header"]["format"], "mlib.animation")
        self.assertEqual(len(raw["data"]["curves"]), 3)
        self.assertEqual(raw["data"]["layers"], [])
        loaded = AnimationSnapshot.load(path)
        self.assertEqual(loaded.toData(), snap.toData())
        cmds.cutKey(self.a, clear=True)
        self.assertIsNone(self.curve(self.a + ".tx"))
        report = loaded.apply()
        self.assertEqual((report.missing, report.skipped), ([], []))
        for attribute, data in expected.items():
            with self.subTest(attribute=attribute):
                self.assertCurveData(_read_curve(self.curve(self.a + "." + attribute)), data)
        cmds.currentTime(12)
        self.assertAlmostEqual(cmds.getAttr(self.a + ".tx"), cmds.getAttr(self.a + ".tx", time=12))

    def test_fast_matches_and_leaves_no_undo(self):
        expected = self.original("tx")
        snap = AnimationSnapshot.capture(self.a)
        self.flushUndo()
        snap.apply(namespaceMap={self.ns: self.other}, fast=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertCurveData(_read_curve(self.curve(self.b + ".tx")), expected)
        self.assertCurveData(_read_curve(self.curve(self.b + ".rx")), self.original("rx"))

    def test_namespace_mapping_and_missing(self):
        snap = AnimationSnapshot.capture([self.a])
        report = snap.apply(namespaceMap={self.ns: self.other})
        self.assertCurveData(_read_curve(self.curve(self.b + ".rx")), self.original("rx"))
        self.assertEqual(report.missing, [])
        report = snap.validate(namespaceMap={self.ns: "noSuchNs"})
        self.assertEqual(report.missing, ["noSuchNs:a"])
        self.assertTrue(report.valid)

    def test_values_are_independent_of_ui_units(self):
        expected = {attribute: self.original(attribute) for attribute in ("tx", "rx")}
        snap = AnimationSnapshot.capture(self.a)
        cmds.currentUnit(angle="rad", linear="m")
        self.assertEqual(AnimationSnapshot.capture(self.a).toData()["curves"][0]["curve"]["keys"][1]["value"],
                         snap.toData()["curves"][0]["curve"]["keys"][1]["value"])
        snap.apply(namespaceMap={self.ns: self.other})
        cmds.currentUnit(angle="deg", linear="cm")
        for attribute, data in expected.items():
            with self.subTest(attribute=attribute):
                self.assertCurveData(_read_curve(self.curve(self.b + "." + attribute)), data)
        self.assertAlmostEqual(cmds.getAttr(self.b + ".rx", time=10), 50.0)
        self.assertAlmostEqual(cmds.getAttr(self.b + ".tx", time=10), 5.0)

    def test_fps_change_with_timing(self):
        path = AnimationSnapshot.capture(self.a).save(os.path.join(self.folder, "fps.json"))
        cmds.currentUnit(time="ntsc")
        loaded = AnimationSnapshot.load(path)
        self.assertAlmostEqual(loaded.header.fps, 24.0)
        loaded.apply(namespaceMap={self.ns: self.other})
        self.assertEqual(self.keyTimes(self.b + ".tx"), [0.0, 10.0, 15.0, 20.0, 30.0])
        loaded.apply(namespaceMap={self.ns: self.other}, timing="second")
        self.assertSequenceAlmostEqual(self.keyTimes(self.b + ".tx"), [0.0, 12.5, 18.75, 25.0, 37.5], places=6)
        self.assertAlmostEqual(cmds.getAttr(self.b + ".tx", time=12.5), 5.0)
        # 秒を保つ換算では、接線の傾き(値/フレーム)が fps の比で緩やかになる。
        out_angle = _read_curve(self.curve(self.b + ".tx"))["keys"][1]["outAngle"]
        self.assertLess(out_angle, 30.0)
        self.assertGreater(out_angle, 20.0)

    def test_time_range_and_offset(self):
        snap = AnimationSnapshot.capture(self.a, time=(10, 20))
        self.assertEqual(snap.toData()["timeRange"], [10.0, 20.0])
        self.assertEqual(len(snap.toData()["curves"]), 2)  # visibility は範囲内にキーが無い。
        snap.apply(namespaceMap={self.ns: self.other}, timeOffset=100)
        self.assertEqual(self.keyTimes(self.b + ".tx"), [110.0, 115.0, 120.0])
        self.assertAlmostEqual(cmds.getAttr(self.b + ".tx", time=110), 5.0)
        self.assertIsNone(self.curve(self.b + ".visibility"))
        with self.assertRaises(ValueError):
            AnimationSnapshot.capture(self.a, time=(5, 1))
        with self.assertRaises(TypeError):
            AnimationSnapshot.capture(self.a, time=5)

    def test_modes(self):
        snap = AnimationSnapshot.capture(self.a, time=(10, 20))
        target = self.b + ".tx"
        expectations = {
            "replace": [10.0, 15.0, 20.0],
            "insert": [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 40.0],
            "merge": [0.0, 5.0, 10.0, 12.0, 15.0, 20.0, 25.0, 40.0],
        }
        for mode, times in expectations.items():
            with self.subTest(mode=mode):
                cmds.cutKey(self.b, clear=True)
                for frame in (0, 5, 12, 20, 25, 40):
                    cmds.setKeyframe(target, time=frame, value=-50)
                cmds.setInfinity(target, postInfinite="linear")
                snap.apply(namespaceMap={self.ns: self.other}, mode=mode)
                self.assertEqual(self.keyTimes(target), times)
                self.assertAlmostEqual(cmds.getAttr(target, time=20), -3.0)
                self.assertAlmostEqual(cmds.getAttr(target, time=10), 5.0)
                if mode != "replace":
                    self.assertAlmostEqual(cmds.getAttr(target, time=25), -50.0)
                post = cmds.setInfinity(target, query=True, postInfinite=True)[0]
                self.assertEqual(post, "oscillate" if mode == "replace" else "linear")

    def test_skips_locked_and_constrained(self):
        snap = AnimationSnapshot.capture(self.a)
        cmds.setAttr(self.b + ".tx", lock=True)
        driver = cmds.createNode("transform", name=self.other_name("driver"))
        cmds.connectAttr(driver + ".ry", self.b + ".rx")
        report = snap.apply(namespaceMap={self.ns: self.other})
        self.assertEqual(len(report.skipped), 2)
        self.assertTrue(any("locked" in item for item in report.skipped))
        self.assertTrue(any("connected to transform" in item for item in report.skipped))
        self.assertIsNotNone(self.curve(self.b + ".visibility"))

    def test_one_undo_restores(self):
        snap = AnimationSnapshot.capture(self.a)
        cmds.setKeyframe(self.b + ".tx", time=3, value=9)
        self.flushUndo()
        snap.apply(namespaceMap={self.ns: self.other})
        self.assertEqual(len(self.keyTimes(self.b + ".tx")), 5)
        cmds.undo()
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertEqual(self.keyTimes(self.b + ".tx"), [3.0])
        self.assertIsNone(self.curve(self.b + ".rx"))

    def test_invalid_input(self):
        snap = AnimationSnapshot.capture(self.a)
        good = snap.toData()
        for mutate in (lambda d: d.update(curves="x"),
                       lambda d: d["curves"][0]["curve"].update(curveType="animCurveUL"),
                       lambda d: d["curves"][0]["curve"]["keys"][0].update(inType="bogus"),
                       lambda d: d["curves"][0]["curve"]["keys"][0].pop("lock"),
                       lambda d: d["curves"][0].update(layer="noLayer"),
                       lambda d: d.update(timeRange=[3, 1])):
            data = snap.toData()
            mutate(data)
            with self.assertRaises(ValueError):
                AnimationSnapshot(data)
        self.assertEqual(snap.toData(), good)
        for kwargs, error in (({"mode": "add"}, ValueError), ({"timeOffset": "1"}, TypeError),
                              ({"timeOffset": float("inf")}, ValueError), ({"timing": "sec"}, ValueError),
                              ({"createLayers": 1}, TypeError), ({"fast": 1}, TypeError)):
            with self.subTest(kwargs=kwargs), self.assertRaises(error):
                snap.apply(**kwargs)
        with self.assertRaises(TypeError):
            AnimationSnapshot.capture([1])
        path = os.path.join(self.folder, "keys.json")
        DrivenKeysSnapshot({"items": []}).save(path)
        with self.assertRaises(ValueError):
            AnimationSnapshot.load(path)


class AnimationLayerTest(_AnimCase):
    """アニメーションレイヤーの保存と作り直し。"""

    def setUp(self):
        super().setUp()
        self.a = cmds.createNode("transform", name=self.name("a"))
        self.b = cmds.createNode("transform", name=self.other_name("a"))
        self.layer1 = self.ns + "_L1"
        self.layer2 = self.ns + "_L2"
        cmds.setKeyframe(self.a + ".tx", time=0, value=1)
        cmds.setKeyframe(self.a + ".tx", time=10, value=2)
        cmds.animLayer(self.layer1, override=True, weight=0.5)
        cmds.animLayer(self.layer2, parent=self.layer1)
        cmds.animLayer(self.layer1, edit=True, attribute=[self.a + ".tx", self.a + ".ry"])
        cmds.animLayer(self.layer2, edit=True, attribute=[self.a + ".tx"])
        cmds.setKeyframe(self.a + ".tx", time=5, value=7, animLayer=self.layer1)
        cmds.setKeyframe(self.a + ".tx", time=8, value=9, animLayer=self.layer1)
        cmds.setKeyframe(self.a + ".ry", time=2, value=30, animLayer=self.layer1)
        cmds.setKeyframe(self.a + ".tx", time=3, value=4, animLayer=self.layer2)
        cmds.animLayer(self.layer2, edit=True, mute=True)
        cmds.setAttr(self.layer2 + ".rotationAccumulationMode", 1)

    def layerCurve(self, layer, plug):
        """レイヤーのカーブの辞書を返す。"""
        return _read_curve(cmds.animLayer(layer, query=True, findCurveForPlug=plug)[0])

    def test_capture_records_layers(self):
        data = AnimationSnapshot.capture(self.a).toData()
        self.assertEqual(data["rootLayer"], cmds.animLayer(query=True, root=True))
        self.assertEqual([layer["name"] for layer in data["layers"]], [self.layer1, self.layer2])
        first, second = data["layers"]
        self.assertEqual((first["parent"], first["override"], first["weight"]), (None, True, 0.5))
        self.assertEqual((second["parent"], second["mute"]), (self.layer1, True))
        self.assertEqual(sorted(str(entry["layer"]) for entry in data["curves"]),
                         sorted(["None", self.layer1, self.layer1, self.layer2]))

    def test_recreates_layers(self):
        snap = AnimationSnapshot.capture(self.a)
        root = cmds.animLayer(query=True, root=True)
        expected = {layer: self.layerCurve(layer, self.a + ".tx") for layer in (root, self.layer1, self.layer2)}
        settings = {attribute: cmds.getAttr(self.layer2 + "." + attribute)
                    for attribute in ("rotationAccumulationMode", "scaleAccumulationMode")}
        expected_ry = self.layerCurve(self.layer1, self.a + ".ry")
        cmds.delete(self.layer2, self.layer1)
        self.assertFalse(cmds.objExists(self.layer1))
        self.flushUndo()
        report = snap.apply(namespaceMap={self.ns: self.other})
        self.assertEqual(report.skipped, [])
        self.assertTrue(cmds.objExists(self.layer1))
        self.assertEqual(cmds.animLayer(self.layer2, query=True, parent=True), self.layer1)
        self.assertTrue(cmds.animLayer(self.layer1, query=True, override=True))
        self.assertAlmostEqual(cmds.animLayer(self.layer1, query=True, weight=True), 0.5)
        self.assertTrue(cmds.animLayer(self.layer2, query=True, mute=True))
        for attribute, value in settings.items():
            self.assertEqual(cmds.getAttr(self.layer2 + "." + attribute), value)
        for layer, data in expected.items():
            with self.subTest(layer=layer):
                self.assertCurveData(self.layerCurve(layer, self.b + ".tx"), data)
        self.assertCurveData(self.layerCurve(self.layer1, self.b + ".ry"), expected_ry)
        cmds.undo()
        self.assertFalse(cmds.objExists(self.layer1))
        self.assertIsNone(cmds.listConnections(self.b + ".tx", source=True, destination=False))

    def test_existing_layer_is_reused_and_create_layers_false(self):
        snap = AnimationSnapshot.capture(self.a)
        cmds.delete(self.layer2)
        report = snap.apply(namespaceMap={self.ns: self.other}, createLayers=False)
        self.assertFalse(cmds.objExists(self.layer2))
        self.assertEqual(len(report.skipped), 1)
        self.assertIn(self.layer2 + " not found", report.skipped[0])
        self.assertTrue(cmds.animLayer(self.layer1, query=True, override=True))
        self.assertCurveData(self.layerCurve(self.layer1, self.b + ".tx"), self.layerCurve(self.layer1, self.a + ".tx"))


class DrivenKeysSnapshotTest(_AnimCase):
    """ドリブンキーの保存と作り直し。"""

    def setUp(self):
        super().setUp()
        for namespace in (self.ns, self.other):
            for text in ("drvA", "drvB", "dvn"):
                cmds.createNode("transform", name=namespace + ":" + text)
        self.driverA, self.driverB, self.driven = (self.name(text) for text in ("drvA", "drvB", "dvn"))
        # 1つのドライバー(角度→距離)。
        for x, y in ((0, 0), (45, 2), (90, 10)):
            cmds.setDrivenKeyframe(self.driven + ".tx", currentDriver=self.driverA + ".rz", driverValue=x, value=y)
        curve = self.curve(self.driven + ".tx")
        cmds.keyTangent(curve, edit=True, index=(1, 1), lock=False)
        cmds.keyTangent(curve, edit=True, index=(1, 1), outAngle=10)
        cmds.setInfinity(self.driven + ".tx", postInfinite="linear")
        # 2つのドライバー(blendWeighted)。
        for x, y in ((0, 0), (90, 45)):
            cmds.setDrivenKeyframe(self.driven + ".rx", currentDriver=self.driverA + ".rz", driverValue=x, value=y)
        for x, y in ((0, 0), (10, 30)):
            cmds.setDrivenKeyframe(self.driven + ".rx", currentDriver=self.driverB + ".tx", driverValue=x, value=y)
        blend = cmds.listConnections(self.driven + ".rx", source=True, destination=False,
                                     skipConversionNodes=True)[0]
        self.assertEqual(cmds.nodeType(blend), "blendWeighted")
        cmds.setAttr(blend + ".weight[1]", 0.5)

    def sample(self, namespace):
        """ドライバーを動かしたときの駆動先の値を返す。"""
        values = []
        for a, b in ((0, 0), (30, 3), (60, 7), (120, 12)):
            cmds.setAttr(namespace + ":drvA.rz", a)
            cmds.setAttr(namespace + ":drvB.tx", b)
            values.append((cmds.getAttr(namespace + ":dvn.tx"), cmds.getAttr(namespace + ":dvn.rx")))
        return values

    def assertSampled(self, actual, expected):
        for got, want in zip(actual, expected):
            self.assertSequenceAlmostEqual(got, want, places=5)

    def test_round_trip_to_other_namespace(self):
        snap = DrivenKeysSnapshot.capture(self.driven)
        data = snap.toData()["items"]
        self.assertEqual(sorted(item["blendWeighted"] for item in data), [False, True])
        single = next(item for item in data if not item["blendWeighted"])
        self.assertEqual([key["input"] for key in single["drivers"][0]["curve"]["keys"]], [0.0, 45.0, 90.0])
        path = snap.save(os.path.join(self.folder, "dk.json"))
        report = DrivenKeysSnapshot.load(path).apply(namespaceMap={self.ns: self.other})
        self.assertEqual((report.missing, report.skipped), ([], []))
        blend = cmds.listConnections(self.other_name("dvn.rx"), source=True, destination=False,
                                     skipConversionNodes=True)[0]
        self.assertEqual(cmds.nodeType(blend), "blendWeighted")
        self.assertSampled(self.sample(self.other), self.sample(self.ns))
        self.assertCurveData(_read_curve(self.curve(self.other_name("dvn.tx")), 1.0),
                             _read_curve(self.curve(self.driven + ".tx"), 1.0))

    def test_replaces_existing_and_unit_independent(self):
        snap = DrivenKeysSnapshot.capture(self.driven)
        expected = self.sample(self.ns)
        cmds.setDrivenKeyframe(self.other_name("dvn.tx"), currentDriver=self.other_name("drvA.rz"),
                               driverValue=5, value=-7)
        cmds.currentUnit(angle="rad", linear="m")
        snap.apply(namespaceMap={self.ns: self.other})
        cmds.currentUnit(angle="deg", linear="cm")
        self.assertSampled(self.sample(self.other), expected)
        self.assertEqual(len(cmds.keyframe(self.curve(self.other_name("dvn.tx")), query=True,
                                           floatChange=True)), 3)

    def test_missing_driver_and_one_undo(self):
        snap = DrivenKeysSnapshot.capture(self.driven)
        cmds.delete(self.other_name("drvB"))
        self.flushUndo()
        report = snap.apply(namespaceMap={self.ns: self.other})
        self.assertEqual(report.missing, [self.other_name("drvB")])
        self.assertIsNotNone(self.curve(self.other_name("dvn.tx")))
        cmds.undo()
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertIsNone(cmds.listConnections(self.other_name("dvn.tx"), source=True, destination=False))
        self.assertIsNone(cmds.listConnections(self.other_name("dvn.rx"), source=True, destination=False))

    def test_invalid_data(self):
        good = DrivenKeysSnapshot.capture(self.driven).toData()
        for mutate in (lambda d: d.update(items={}),
                       lambda d: d["items"][0].pop("blendWeighted"),
                       lambda d: d["items"][0]["drivers"][0].update(weight="1"),
                       lambda d: d["items"][0]["drivers"][0]["curve"].update(curveType="animCurveTL")):
            data = DrivenKeysSnapshot(good).toData()
            mutate(data)
            with self.assertRaises(ValueError):
                DrivenKeysSnapshot(data)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
