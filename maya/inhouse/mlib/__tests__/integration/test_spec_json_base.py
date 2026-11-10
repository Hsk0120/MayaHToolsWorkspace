"""mlib.json の基盤(codec・file・名前の対応付け・参照・Snapshot 基底)を確かめる。"""

import json as std_json
import os
import shutil
import sys
import tempfile
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.json import (ComponentRef, Header, NameMapping, NodeRef, PlugRef, Snapshot, ValidationReport,
                       decode, dump, encode, load)
from mlib.maths import EulerRotate, Matrix, Quaternion, Scale, Translate, Vector
from support.specCase import NamespaceCase


class CodecTest(unittest.TestCase):
    """数学型の変換と往復。"""

    def test_round_trip_keeps_types(self):
        values = {
            "t": Translate(1.0, 2.5, -3.0),
            "s": Scale(1.0, 2.0, 3.0),
            "v": Vector(0.1, 0.2, 0.3),
            "q": Quaternion(0.0, 0.70710678, 0.0, 0.70710678),
            "r": EulerRotate.fromDegrees(10.0, 20.0, 30.0, "zxy"),
            "m": Matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 5, 6, 7, 1]),
            "list": [1, "a", None, True, [Vector(1, 0, 0)]],
        }
        encoded = encode(values)
        self.assertEqual(encoded["t"], {"type": "Translate", "value": [1.0, 2.5, -3.0]})
        self.assertEqual(encoded["r"]["order"], "zxy")
        self.assertAlmostEqual(encoded["r"]["value"][1], 20.0)
        std_json.dumps(encoded, allow_nan=False)
        decoded = decode(std_json.loads(std_json.dumps(encoded)))
        self.assertIs(type(decoded["t"]), Translate)
        self.assertIs(type(decoded["s"]), Scale)
        self.assertIs(type(decoded["r"]), EulerRotate)
        self.assertEqual(decoded["r"].orderName, "zxy")
        self.assertTrue(decoded["r"].isEquivalent(values["r"], 1e-9))
        self.assertTrue(decoded["m"].isEquivalent(values["m"], 1e-12))
        self.assertTrue(decoded["q"].isEquivalent(values["q"], 1e-9))
        self.assertIs(type(decoded["list"][4][0]), Vector)

    def test_plain_dicts_with_type_key_stay_dicts(self):
        data = {"node": {"name": "a", "path": None, "type": "joint"}, "x": {"type": "Vector", "value": [1, 2]}}
        with self.assertRaises(ValueError):
            decode(data)
        self.assertEqual(decode(data["node"]), data["node"])

    def test_rejects_unsupported_values(self):
        for value in ({1: 2}, object(), float("nan")):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                encode(value)


class FileTest(unittest.TestCase):
    """ヘッダー付きファイルの書き出しと読み込み。"""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="mlibJsonTest")
        self.path = os.path.join(self.folder, "data.json")
        self.time_unit = cmds.currentUnit(query=True, time=True)

    def tearDown(self):
        cmds.currentUnit(time=self.time_unit)
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_dump_and_load(self):
        written = dump({"pivot": Translate(0, 12.5, 0), "name": "日本語"}, self.path, "mlib.test", 2)
        self.assertEqual(str(written), os.path.realpath(self.path))
        with open(self.path, encoding="utf-8") as stream:
            text = stream.read()
        self.assertIn("日本語", text)
        self.assertIn('\n  "header"', text)
        raw = std_json.loads(text)
        self.assertEqual(raw["header"]["format"], "mlib.test")
        self.assertEqual(raw["header"]["mlib"], mlib.__version__)
        self.assertEqual(raw["header"]["units"]["angle"], "deg")
        header, data = load(self.path, "mlib.test", 2)
        self.assertIsInstance(header, Header)
        self.assertIs(type(data["pivot"]), Translate)
        self.assertEqual(data["name"], "日本語")
        self.assertEqual([name for name in os.listdir(self.folder)], ["data.json"])

    def test_format_and_version_mismatch(self):
        dump({}, self.path, "mlib.test", 1)
        with self.assertRaisesRegex(ValueError, "format"):
            load(self.path, "mlib.other", 1)
        with self.assertRaisesRegex(ValueError, "version"):
            load(self.path, "mlib.test", 2)
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write("{broken")
        with self.assertRaises(ValueError):
            load(self.path, "mlib.test", 1)

    def test_failed_dump_keeps_existing_file(self):
        dump({"a": 1}, self.path, "mlib.test", 1)
        with self.assertRaises(ValueError):
            dump({"a": float("inf")}, self.path, "mlib.test", 1)
        self.assertEqual(load(self.path, "mlib.test", 1)[1], {"a": 1})
        self.assertEqual(os.listdir(self.folder), ["data.json"])

    def test_convert_time(self):
        cmds.currentUnit(time="ntsc")
        dump({}, self.path, "mlib.test", 1)
        header, _data = load(self.path, "mlib.test", 1)
        self.assertAlmostEqual(header.fps, 30.0)
        cmds.currentUnit(time="film")
        self.assertEqual(header.convertTime(30.0), 30.0)
        self.assertAlmostEqual(header.convertTime(30.0, timing="second"), 24.0)
        with self.assertRaises(ValueError):
            header.convertTime(1.0, timing="seconds")


class NameMappingTest(unittest.TestCase):
    """名前の変換の順序。"""

    def test_order_and_priority(self):
        mapping = NameMapping(nameMap={"arm_L_jnt": "leftArm"}, replace=[("_L_", "_R_")],
                              namespaceMap={"chrA": "chrB"})
        self.assertEqual(mapping.apply("chrA:arm_L_jnt"), "chrB:leftArm")
        self.assertEqual(mapping.apply("chrA:leg_L_jnt"), "chrB:leg_R_jnt")
        self.assertEqual(mapping.apply("leg_L_jnt"), "leg_R_jnt")
        self.assertEqual(mapping.applyPath("|chrA:root|chrA:arm_L_jnt"), "|chrB:root|chrB:leftArm")

    def test_namespaces(self):
        mapping = NameMapping(namespaceMap={"": "chrB", ":chrA:": "", "chrC": "x:y"})
        self.assertEqual(mapping.apply("root"), "chrB:root")
        self.assertEqual(mapping.apply("chrA:root"), "root")
        self.assertEqual(mapping.apply("chrC:sub:root"), "x:y:sub:root")
        self.assertTrue(NameMapping().isIdentity())
        self.assertEqual(NameMapping().apply("a:b"), "a:b")

    def test_invalid(self):
        for kwargs, error in (({"nameMap": []}, TypeError), ({"replace": "ab"}, TypeError),
                              ({"replace": [("a",)]}, ValueError), ({"replace": [("", "b")]}, ValueError),
                              ({"namespaceMap": {"a": 1}}, TypeError)):
            with self.subTest(kwargs=kwargs), self.assertRaises(error):
                NameMapping(**kwargs)


class ReferenceTest(NamespaceCase):
    """ノード・Plug・コンポーネントの参照。"""

    PREFIX = "mlibSpecJsonRef_"

    def setUp(self):
        super().setUp()
        self.other = self.ns + "B"
        cmds.namespace(add=self.other)
        self.extra_namespaces.append(self.other)
        self.root = cmds.createNode("transform", name=self.name("root"))
        self.joint = cmds.createNode("joint", name=self.name("arm"), parent=self.root)
        self.root_b = cmds.createNode("transform", name=self.other + ":root")
        self.joint_b = cmds.createNode("joint", name=self.other + ":arm", parent=self.root_b)

    def test_node_ref(self):
        ref = NodeRef.capture(self.joint)
        self.assertEqual(ref.name, self.name("arm"))
        self.assertEqual(ref.type, "joint")
        self.assertTrue(ref.path.startswith("|"))
        self.assertEqual(NodeRef.fromData(std_json.loads(std_json.dumps(ref.toData()))), ref)
        self.assertEqual(ref.resolve().getFullName(), cmds.ls(self.joint, long=True)[0])
        mapped = ref.resolve(NameMapping(namespaceMap={self.ns: self.other}))
        self.assertEqual(mapped.getFullName(), cmds.ls(self.joint_b, long=True)[0])
        self.assertIsNone(ref.resolve(NameMapping(namespaceMap={self.ns: "missingNs"})))

    def test_node_ref_type_and_ambiguity(self):
        ref = NodeRef.capture(self.joint)
        full = cmds.ls(self.joint, long=True)[0]
        wrong_type = NodeRef(ref.name, ref.path, "transform")
        self.assertIsNone(wrong_type.resolve())
        twin = cmds.createNode("joint", name=self.name("arm"), parent=cmds.createNode("transform", name=self.name("g")))
        self.assertEqual(ref.resolve().getFullName(), full)
        self.assertIsNone(NodeRef(ref.name, None, "joint").resolve())
        self.assertTrue(cmds.objExists(twin))

    def test_plug_ref(self):
        node = mlib.getNode(self.joint)
        ref = PlugRef.capture(node.getPlug("tx"))
        self.assertEqual(ref.attribute, "translateX")
        self.assertEqual(PlugRef.capture(self.joint + ".worldMatrix[0]").attribute, "worldMatrix[0]")
        self.assertEqual(PlugRef.fromData(ref.toData()), ref)
        plug = ref.resolve(NameMapping(namespaceMap={self.ns: self.other}))
        self.assertEqual(plug.getNode(), mlib.getNode(self.joint_b))
        self.assertEqual(plug.getShortName(), "tx")
        self.assertIsNone(PlugRef(ref.node, "noSuchAttr").resolve())

    def test_component_ref(self):
        cube = cmds.polyCube(name=self.name("cube"), constructionHistory=False)[0]
        shape = mlib.getNode(cube).getShape()
        ref = ComponentRef.capture(shape.getVertices([5, 1, 3]))
        self.assertEqual(ref.type, "vtx")
        self.assertEqual(ref.indices, (5, 1, 3))
        self.assertEqual(ComponentRef.fromData(ref.toData()), ref)
        resolved = ref.resolve()
        self.assertEqual(resolved.indices, (5, 1, 3))
        self.assertEqual(ComponentRef.capture(shape.getVertices([2])[0]).indices, (2,))
        self.assertIsNone(ComponentRef(ref.node, "vtx", [100]).resolve())
        with self.assertRaises(ValueError):
            ComponentRef(ref.node, "pt", [1])


class _OffsetSnapshot(Snapshot):
    """テスト用: ノードの translateX を書く最小の種類。"""

    FORMAT = "mlib.test.offset"
    VERSION = 1

    @classmethod
    def capture(cls, nodes):
        return cls({"items": [{"node": NodeRef.capture(node).toData(),
                               "value": cmds.getAttr(str(node) + ".tx")} for node in nodes]})

    def apply(self, *, nameMap=None, replace=None, namespaceMap=None, fail=False):
        return self._run_apply({"nameMap": nameMap, "replace": replace, "namespaceMap": namespaceMap},
                               {"fail": fail})

    def _validate(self, mapping, report, options):
        for item in self._data["items"]:
            ref = NodeRef.fromData(item["node"])
            if ref.resolve(mapping) is None:
                report.addMissing(ref.mappedName(mapping))
            if item["value"] < 0:
                report.addError("negative value")

    def _apply(self, mapping, report, options, fast):
        for item in self._data["items"]:
            node = NodeRef.fromData(item["node"]).resolve(mapping)
            if node is not None:
                cmds.setAttr(node.getFullName() + ".tx", item["value"])
        if options["fail"]:
            raise RuntimeError("fail on purpose")


class SnapshotBaseTest(NamespaceCase):
    """Snapshot 基底の保存・検査・適用・巻き戻し。"""

    PREFIX = "mlibSpecJsonSnap_"

    def setUp(self):
        super().setUp()
        self.a = cmds.createNode("transform", name=self.name("a"))
        self.b = cmds.createNode("transform", name=self.name("b"))
        cmds.setAttr(self.a + ".tx", 3.0)
        cmds.setAttr(self.b + ".tx", 4.0)
        self.folder = tempfile.mkdtemp(prefix="mlibJsonSnap")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)
        super().tearDown()

    def test_save_load_apply(self):
        snap = _OffsetSnapshot.capture([self.a, self.b])
        self.assertIsNone(snap.header)
        path = snap.save(os.path.join(self.folder, "offset.json"))
        loaded = _OffsetSnapshot.load(path)
        self.assertIsInstance(loaded.header, Header)
        self.assertEqual(loaded.toData(), snap.toData())
        cmds.setAttr(self.a + ".tx", 0.0)
        cmds.delete(self.b)
        report = loaded.validate()
        self.assertTrue(report.valid)
        self.assertEqual(report.missing, [self.name("b")])
        self.assertEqual(cmds.getAttr(self.a + ".tx"), 0.0)
        cmds.flushUndo()
        result = loaded.apply()
        self.assertIsInstance(result, ValidationReport)
        self.assertEqual(cmds.getAttr(self.a + ".tx"), 3.0)
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.a + ".tx"), 0.0)

    def test_errors_change_nothing_and_failure_rolls_back(self):
        cmds.setAttr(self.a + ".tx", -1.0)
        snap = _OffsetSnapshot.capture([self.a])
        cmds.setAttr(self.a + ".tx", 7.0)
        with self.assertRaises(ValueError):
            snap.apply()
        self.assertEqual(cmds.getAttr(self.a + ".tx"), 7.0)
        snap = _OffsetSnapshot.capture([self.b])
        cmds.setAttr(self.b + ".tx", 9.0)
        with self.assertRaises(RuntimeError):
            snap.apply(fail=True)
        self.assertEqual(cmds.getAttr(self.b + ".tx"), 9.0)

    def test_load_rejects_other_format(self):
        path = os.path.join(self.folder, "x.json")
        dump({"items": []}, path, "mlib.other", 1)
        with self.assertRaises(ValueError):
            _OffsetSnapshot.load(path)

    def test_data_is_copied(self):
        snap = _OffsetSnapshot({"items": [], "v": Vector(1, 2, 3)})
        data = snap.toData()
        data["v"].x = 99
        self.assertEqual(snap.toData()["v"].x, 1)
        with self.assertRaises(TypeError):
            _OffsetSnapshot([])
        with self.assertRaises(NotImplementedError):
            Snapshot.capture()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
