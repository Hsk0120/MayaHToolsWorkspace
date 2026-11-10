"""mlib.json のポーズ・アトリビュート・選択のスナップショットを確かめる。"""

import json as std_json
import os
import shutil
import sys
import tempfile
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.json import ValidationReport
from mlib.json.attributesSnapshot import AttributesSnapshot
from mlib.json.poseSnapshot import PoseSnapshot
from mlib.json.selectionSnapshot import SelectionSnapshot
from mlib.maths import Matrix
from support.specCase import NamespaceCase


class _SnapshotCase(NamespaceCase):
    """2つの名前空間(元・先)と一時フォルダを用意する。"""

    def setUp(self):
        super().setUp()
        self.other = self.ns + "B"
        cmds.namespace(add=self.other)
        self.extra_namespaces.append(self.other)
        self.folder = tempfile.mkdtemp(prefix="mlibJsonSnapshots")
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))

    def tearDown(self):
        self.set_units(*self.units)
        shutil.rmtree(self.folder, ignore_errors=True)
        super().tearDown()

    @staticmethod
    def set_units(linear, angle):
        # currentUnitはUndoに記録されるため、適用のUndoの確認を妨げないよう記録せずに切り替える。
        cmds.undoInfo(stateWithoutFlush=False)
        try:
            cmds.currentUnit(linear=linear, angle=angle)
        finally:
            cmds.undoInfo(stateWithoutFlush=True)

    def other_name(self, text):
        return self.other + ":" + text

    def round_trip(self, snapshot):
        path = snapshot.save(os.path.join(self.folder, "snap.json"))
        with open(str(path), encoding="utf-8") as stream:
            raw = std_json.load(stream)
        self.assertEqual(raw["header"]["format"], snapshot.FORMAT)
        return type(snapshot).load(path)


class PoseSnapshotTest(_SnapshotCase):
    """ポーズの取得・保存・適用。"""

    PREFIX = "mlibSpecJsonPose_"

    def build(self, namespace):
        root = cmds.createNode("transform", name=namespace + ":root")
        joint = cmds.createNode("joint", name=namespace + ":arm", parent=root)
        cmds.addAttr(joint, longName="blend", attributeType="double", keyable=True)
        cmds.addAttr(joint, longName="mode", attributeType="enum", enumName="a:b:c")
        cmds.setAttr(joint + ".mode", channelBox=True)
        cmds.addAttr(joint, longName="hiddenValue", attributeType="double")
        return root, joint

    def setUp(self):
        super().setUp()
        self.root, self.joint = self.build(self.ns)
        self.root_b, self.joint_b = self.build(self.other)
        cmds.setAttr(self.root + ".translate", 1.0, 2.0, 3.0)
        cmds.setAttr(self.joint + ".rotate", 10.0, 20.0, 30.0)
        cmds.setAttr(self.joint + ".blend", 0.25)
        cmds.setAttr(self.joint + ".mode", 2)
        cmds.setAttr(self.joint + ".hiddenValue", 9.0)
        cmds.setAttr(self.joint + ".radius", 3.0)

    def test_capture_contents(self):
        snap = PoseSnapshot.capture([self.root, self.joint, self.root])
        data = snap.toData()
        self.assertEqual(len(data["nodes"]), 2)
        attrs = data["nodes"][1]["attrs"]
        self.assertAlmostEqual(attrs["rotateY"], 20.0)
        self.assertEqual(attrs["blend"], 0.25)
        self.assertEqual(attrs["mode"], 2)
        self.assertNotIn("hiddenValue", attrs)
        self.assertNotIn("rotate", attrs)
        self.assertIn("radius", attrs)
        self.assertIs(type(data["nodes"][0]["attrs"]["visibility"]), bool)

    def test_round_trip_into_other_namespace(self):
        self.set_units("mm", "rad")
        snap = self.round_trip(PoseSnapshot.capture([self.root, self.joint]))
        self.set_units("m", "deg")
        cmds.flushUndo()
        report = snap.apply(namespaceMap={self.ns: self.other})
        self.assertIsInstance(report, ValidationReport)
        self.assertEqual(report.missing, [])
        self.assertEqual(report.skipped, [])
        self.set_units("cm", "deg")
        self.assertSequenceAlmostEqual(cmds.getAttr(self.root_b + ".translate")[0], (1.0, 2.0, 3.0))
        self.assertSequenceAlmostEqual(cmds.getAttr(self.joint_b + ".rotate")[0], (10.0, 20.0, 30.0))
        self.assertEqual(cmds.getAttr(self.joint_b + ".mode"), 2)
        self.assertAlmostEqual(cmds.getAttr(self.joint_b + ".blend"), 0.25)
        self.assertEqual(cmds.getAttr(self.joint_b + ".hiddenValue"), 0.0)
        cmds.undo()
        self.assertSequenceAlmostEqual(cmds.getAttr(self.root_b + ".translate")[0], (0.0, 0.0, 0.0))
        self.assertSequenceAlmostEqual(cmds.getAttr(self.joint_b + ".rotate")[0], (0.0, 0.0, 0.0))
        self.assertEqual(cmds.getAttr(self.joint_b + ".mode"), 0)

    def test_locked_connected_and_missing(self):
        snap = PoseSnapshot.capture([self.root, self.joint])
        cmds.setAttr(self.root_b + ".tx", lock=True)
        cmds.setKeyframe(self.joint_b, attribute="rotateY", value=5.0, time=1)
        driver = cmds.createNode("transform", name=self.other_name("driver"))
        cmds.connectAttr(driver + ".tz", self.joint_b + ".blend")
        cmds.setAttr(self.joint_b + ".radius", lock=True)
        cmds.rename(self.root_b, self.other_name("renamed"))
        report = snap.validate(namespaceMap={self.ns: self.other})
        self.assertTrue(report.valid)
        self.assertEqual(report.missing, [self.other_name("root")])
        cmds.rename(self.other_name("renamed"), self.other_name("root"))
        report = snap.apply(namespaceMap={self.ns: self.other})
        skipped = "\n".join(report.skipped)
        self.assertIn("translateX: locked", skipped)
        self.assertIn("rotateY: connected", skipped)
        self.assertIn("blend: connected", skipped)
        self.assertIn("radius: locked", skipped)
        self.assertEqual(report.missing, [])
        self.assertEqual(cmds.getAttr(self.root_b + ".tx"), 0.0)
        self.assertAlmostEqual(cmds.getAttr(self.root_b + ".ty"), 2.0)
        self.assertAlmostEqual(cmds.getAttr(self.joint_b + ".rx"), 10.0)
        self.assertEqual(cmds.keyframe(self.joint_b + ".ry", query=True, keyframeCount=True), 1)
        self.assertEqual(cmds.keyframe(self.joint_b + ".rx", query=True, keyframeCount=True), 0)

    def test_missing_nodes_are_not_errors(self):
        snap = PoseSnapshot.capture([self.root, self.joint])
        report = snap.apply(namespaceMap={self.ns: "noSuchNs"})
        self.assertTrue(report.valid)
        self.assertEqual(sorted(report.missing), sorted(["noSuchNs:root", "noSuchNs:arm"]))

    def test_missing_attribute_is_skipped(self):
        snap = PoseSnapshot.capture([self.joint])
        cmds.deleteAttr(self.joint_b + ".blend")
        report = snap.apply(namespaceMap={self.ns: self.other})
        self.assertTrue(any(item.endswith("blend: missing attribute") for item in report.skipped))

    def test_invalid_data(self):
        node = {"name": "a", "path": None, "type": None}
        for data in ({}, {"nodes": {}}, {"nodes": [{"node": node}]},
                     {"nodes": [{"node": node, "attrs": {"tx": "1"}}]},
                     {"nodes": [{"node": {"path": "x"}, "attrs": {}}]}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                PoseSnapshot.fromData(data)
        with self.assertRaises(RuntimeError):
            PoseSnapshot.capture([self.name("noSuchNode")])
        with self.assertRaises(TypeError):
            PoseSnapshot.capture(5)


class AttributesSnapshotTest(_SnapshotCase):
    """任意の型のアトリビュートの取得・保存・適用。"""

    PREFIX = "mlibSpecJsonAttrs_"

    def build(self, namespace):
        node = cmds.createNode("transform", name=namespace + ":node")
        cmds.addAttr(node, longName="label", dataType="string")
        cmds.addAttr(node, longName="offsetMatrix", attributeType="matrix")
        cmds.addAttr(node, longName="choice", attributeType="enum", enumName="x:y:z")
        cmds.addAttr(node, longName="flag", attributeType="bool")
        cmds.addAttr(node, longName="dist", attributeType="doubleLinear")
        return node

    def setUp(self):
        super().setUp()
        self.node = self.build(self.ns)
        self.node_b = self.build(self.other)
        cmds.setAttr(self.node + ".label", "hello", type="string")
        self.matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 5, 6, 7, 1]
        cmds.setAttr(self.node + ".offsetMatrix", self.matrix, type="matrix")
        cmds.setAttr(self.node + ".choice", 1)
        cmds.setAttr(self.node + ".flag", True)
        cmds.setAttr(self.node + ".dist", 4.0)
        cmds.setAttr(self.node + ".translate", 1.0, 2.0, 3.0)
        cmds.setAttr(self.node + ".rotate", 0.0, 90.0, 0.0)
        cmds.setAttr(self.node + ".visibility", False)

    def names(self):
        return ["label", "offsetMatrix", "choice", "flag", "dist", "translate", "rotate", "visibility",
                "noSuchAttr"]

    def test_round_trip_with_units(self):
        self.set_units("mm", "rad")
        snap = AttributesSnapshot.capture([self.node], self.names())
        data = snap.toData()
        attrs = [entry["plug"]["attr"] for entry in data["plugs"]]
        self.assertEqual(attrs, ["label", "offsetMatrix", "choice", "flag", "dist", "translate", "rotate",
                                 "visibility"])
        values = {entry["plug"]["attr"]: entry["value"] for entry in data["plugs"]}
        self.assertIsInstance(values["offsetMatrix"], Matrix)
        self.assertAlmostEqual(values["dist"], 4.0)
        snap = self.round_trip(snap)
        self.set_units("m", "deg")
        cmds.flushUndo()
        report = snap.apply(namespaceMap={self.ns: self.other})
        self.assertEqual(report.skipped, [])
        self.set_units("cm", "deg")
        self.assertEqual(cmds.getAttr(self.node_b + ".label"), "hello")
        self.assertSequenceAlmostEqual(cmds.getAttr(self.node_b + ".offsetMatrix"), self.matrix)
        self.assertEqual(cmds.getAttr(self.node_b + ".choice"), 1)
        self.assertIs(cmds.getAttr(self.node_b + ".flag"), True)
        self.assertAlmostEqual(cmds.getAttr(self.node_b + ".dist"), 4.0)
        self.assertSequenceAlmostEqual(cmds.getAttr(self.node_b + ".translate")[0], (1.0, 2.0, 3.0))
        self.assertSequenceAlmostEqual(cmds.getAttr(self.node_b + ".rotate")[0], (0.0, 90.0, 0.0))
        self.assertIs(cmds.getAttr(self.node_b + ".visibility"), False)
        cmds.undo()
        self.assertIsNone(cmds.getAttr(self.node_b + ".label"))
        self.assertEqual(cmds.getAttr(self.node_b + ".choice"), 0)
        self.assertSequenceAlmostEqual(cmds.getAttr(self.node_b + ".translate")[0], (0.0, 0.0, 0.0))

    def test_plugs_and_strings(self):
        node = mlib.getNode(self.node)
        snap = AttributesSnapshot.capture([node.getPlug("tx"), self.node + ".label", node.getPlug("tx")])
        attrs = [entry["plug"]["attr"] for entry in snap.toData()["plugs"]]
        self.assertEqual(attrs, ["translateX", "label"])
        with self.assertRaises(ValueError):
            AttributesSnapshot.capture([self.node])
        with self.assertRaises(TypeError):
            AttributesSnapshot.capture([self.node], [1])

    def test_locked_connected_missing(self):
        snap = AttributesSnapshot.capture([self.node], self.names())
        cmds.setAttr(self.node_b + ".label", lock=True)
        cmds.setAttr(self.node_b + ".rz", lock=True)
        driver = cmds.createNode("transform", name=self.other_name("driver"))
        cmds.connectAttr(driver + ".tx", self.node_b + ".dist")
        cmds.deleteAttr(self.node_b + ".flag")
        report = snap.apply(namespaceMap={self.ns: self.other})
        skipped = "\n".join(report.skipped)
        self.assertIn("label: locked", skipped)
        self.assertIn("rotate: locked", skipped)
        self.assertIn("dist: connected", skipped)
        self.assertIn("flag: missing attribute", skipped)
        self.assertIsNone(cmds.getAttr(self.node_b + ".label"))
        self.assertSequenceAlmostEqual(cmds.getAttr(self.node_b + ".translate")[0], (1.0, 2.0, 3.0))
        report = snap.apply(namespaceMap={self.ns: "noSuchNs"})
        self.assertTrue(report.valid)
        self.assertEqual(report.missing, ["noSuchNs:node"])

    def test_invalid_data(self):
        plug = {"node": {"name": "a", "path": None, "type": None}, "attr": "tx"}
        for data in ({}, {"plugs": [{"plug": plug}]}, {"plugs": [{"plug": {"node": {}}, "value": 1}]},
                     {"plugs": [{"plug": plug, "value": object()}]}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                AttributesSnapshot.fromData(data)


class SelectionSnapshotTest(_SnapshotCase):
    """選択の順序とコンポーネント。"""

    PREFIX = "mlibSpecJsonSel_"

    def setUp(self):
        super().setUp()
        self.track = cmds.selectPref(query=True, trackSelectionOrder=True)
        cmds.selectPref(trackSelectionOrder=True)
        self.selection = cmds.ls(selection=True, long=True) or []
        for namespace in (self.ns, self.other):
            cmds.polyCube(name=namespace + ":cube", constructionHistory=False)
            cmds.createNode("transform", name=namespace + ":a")
            cmds.createNode("transform", name=namespace + ":b")
            curve = cmds.curve(name=namespace + ":crv", degree=1, point=[(0, 0, 0), (1, 0, 0), (2, 0, 0)])
            cmds.rename(cmds.listRelatives(curve, shapes=True, fullPath=True)[0], namespace + ":crvShape")
            cmds.createNode("multiplyDivide", name=namespace + ":md")

    def tearDown(self):
        cmds.select(self.selection, replace=True) if self.selection else cmds.select(clear=True)
        cmds.selectPref(trackSelectionOrder=self.track)
        super().tearDown()

    def test_order_and_components(self):
        cmds.select(clear=True)
        cmds.select(self.name("b"))
        cmds.select(self.name("cube") + ".vtx[5]", add=True)
        cmds.select(self.name("cube") + ".vtx[1]", add=True)
        cmds.select(self.name("md"), add=True)
        cmds.select(self.name("a"), add=True)
        cmds.select(self.name("cube") + ".f[2]", add=True)
        cmds.select(self.name("crv") + ".cv[2]", add=True)
        cmds.select(self.name("cube") + ".map[3]", add=True)
        cmds.select(self.name("cube") + ".e[0:1]", add=True)
        snap = self.round_trip(SelectionSnapshot.capture())
        items = snap.toData()["items"]
        summary = [("node", item["node"]["name"]) if "node" in item else
                   (item["components"]["type"], tuple(item["components"]["indices"])) for item in items]
        self.assertEqual(summary, [("node", self.name("b")), ("vtx", (5, 1)), ("node", self.name("md")),
                                   ("node", self.name("a")), ("f", (2,)), ("cv", (2,)), ("map", (3,)),
                                   ("e", (0, 1))])
        self.assertEqual(items[1]["components"]["node"]["type"], "mesh")
        cmds.select(clear=True)
        cmds.flushUndo()
        report = snap.apply(namespaceMap={self.ns: self.other})
        self.assertEqual(report.missing, [])
        selected = cmds.ls(orderedSelection=True)
        self.assertEqual([name for name in selected if "." not in name],
                         [self.other_name("b"), self.other_name("md"), self.other_name("a")])
        expected = cmds.ls([self.other_name(text) for text in (
            "cubeShape.vtx[5]", "cubeShape.vtx[1]", "cubeShape.f[2]", "crvShape.cv[2]", "cubeShape.map[3]",
            "cubeShape.e[0:1]")], flatten=True)
        self.assertEqual(len(expected), 7)
        self.assertEqual(set(name for name in cmds.ls(selection=True, flatten=True) if "." in name), set(expected))
        cmds.undo()
        self.assertEqual(cmds.ls(selection=True), [])

    def test_explicit_items_and_missing(self):
        cube = mlib.getNode(self.name("cube"))
        shape = cube.getShape()
        snap = SelectionSnapshot.capture([self.name("a"), shape.getVertices([7, 2]), cube])
        items = snap.toData()["items"]
        self.assertEqual(items[1]["components"]["indices"], [7, 2])
        cmds.delete(self.other_name("a"))
        cmds.select(self.other_name("b"))
        report = snap.apply(namespaceMap={self.ns: self.other})
        self.assertTrue(report.valid)
        self.assertEqual(report.missing, [self.other_name("a")])
        selected = cmds.ls(orderedSelection=True, long=True)
        self.assertNotIn(cmds.ls(self.other_name("b"), long=True)[0], selected)
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 3)
        report = snap.apply(namespaceMap={self.ns: "noSuchNs"})
        self.assertEqual(cmds.ls(selection=True), [])
        self.assertEqual(len(report.missing), 3)

    def test_out_of_range_components_are_skipped(self):
        cmds.select(self.name("cube") + ".vtx[7]")
        snap = SelectionSnapshot.capture()
        cmds.delete(self.other_name("cube"))
        cmds.polyPlane(name=self.other_name("cube"), subdivisionsX=1, subdivisionsY=1, constructionHistory=False)
        report = snap.apply(namespaceMap={self.ns: self.other})
        self.assertEqual(len(report.skipped), 1)
        self.assertIn("index out of range", report.skipped[0])

    def test_invalid_data(self):
        for data in ({}, {"items": [{}]}, {"items": [{"other": {}}]},
                     {"items": [{"components": {"node": {"name": "a"}, "type": "pt", "indices": [0]}}]}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                SelectionSnapshot.fromData(data)
        with self.assertRaises(RuntimeError):
            SelectionSnapshot.capture([self.name("noSuchNode")])
        with self.assertRaises(TypeError):
            SelectionSnapshot.capture([1.5])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
