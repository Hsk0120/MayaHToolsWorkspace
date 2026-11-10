"""SkinCluster のスキンウェイトの JSON 保存・復元(getWeightsData・setWeightsData・exportWeights・importWeights)と、
bindSkin のウェイトのファイルからの作成を確かめる。

ngSkinTools2 のレイヤーは、同梱のプラグインがある Maya の版だけで確かめる。
"""

import json as std_json
import os
import shutil
import sys
import tempfile
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.json import ValidationReport, dump
from mlib.nodes import SkinCluster
from support.specCase import NamespaceCase

CONTENTS = r"C:\ProgramData\Autodesk\ApplicationPlugins\ngskintools2\Contents"
VERSION = cmds.about(version=True).split()[0][:4]
NGSKIN_PLUGIN = os.path.join(CONTENTS, "plug-ins", VERSION, "ngSkinTools2.mll")


class SkinWeightsCase(NamespaceCase):
    """名前空間に joint 4 本と 5x5 頂点の板を作り、決まったウェイトでバインドする。"""

    PREFIX = "mlibSpecJsonSkin_"

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp(prefix="mlibSkinWeights")
        self.path = os.path.join(self.folder, "weights.json")
        self.joints = self.makeJoints(self.ns)
        self.mesh = self.makePlane(self.ns, "mesh", 4)
        self.skin = mlib.bindSkin(self.joints, self.mesh, maximumInfluences=4)
        self.count = cmds.polyEvaluate(self.mesh, vertex=True)
        self.skin.setWeights(self.joints, self.pattern(self.count, len(self.joints)), rows=True)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)
        super().tearDown()

    @staticmethod
    def makeJoints(namespace, names=("j0", "j1", "j2", "j3")):
        """名前空間に X 方向へ並ぶ joint の連鎖を作り、フルパスを返す。"""
        cmds.select(clear=True)
        joints = [cmds.joint(name=f"{namespace}:{name}", position=(-4.0 + 2.5 * index, 0, 0))
                  for index, name in enumerate(names)]
        cmds.select(clear=True)
        return [cmds.ls(joint, long=True)[0] for joint in joints]

    @staticmethod
    def makePlane(namespace, name, divisions):
        """名前空間に 10x10 の板(XZ 平面)を作る。"""
        return cmds.polyPlane(name=f"{namespace}:{name}", width=10, height=10, subdivisionsX=divisions,
                              subdivisionsY=divisions, constructionHistory=False)[0]

    @staticmethod
    def pattern(count, width):
        """頂点ごとに違う、合計 1 の行を返す。"""
        rows = []
        for vertex in range(count):
            row = [float(1 + (vertex + column) % 3) for column in range(width)]
            total = sum(row)
            rows.append([value / total for value in row])
        return rows

    def allWeights(self, skin=None, joints=None):
        """joint ごとの全頂点のウェイトを頂点ごとの行で返す。"""
        skin = skin or self.skin
        return skin.getWeights(joints or self.joints, rows=True)

    def scramble(self, skin=None, joints=None):
        """全頂点を先頭の joint に 1.0 にする。"""
        skin = skin or self.skin
        joints = joints or self.joints
        rows = [[1.0] + [0.0] * (len(joints) - 1) for _ in range(cmds.polyEvaluate(skin.mesh, vertex=True))]
        skin.setWeights(joints, rows, rows=True)

    def assertRowsAlmostEqual(self, actual, expected, places=9):
        self.assertEqual(len(actual), len(expected))
        for a, e in zip(actual, expected):
            self.assertSequenceAlmostEqual(a, e, places)


class DataTest(SkinWeightsCase):
    """データの形と往復。"""

    def test_data_layout(self):
        data = self.skin.getWeightsData()
        self.assertEqual(data["vertexCount"], self.count)
        self.assertEqual([item["name"] for item in data["influences"]],
                         [joint.rpartition("|")[2] for joint in self.joints])
        self.assertEqual(data["influences"][0]["type"], "joint")
        self.assertEqual(data["geometry"]["type"], "mesh")
        self.assertEqual(len(data["weights"]["indices"]), self.count)
        self.assertEqual(data["weights"]["indices"][0], [0, 1, 2, 3])
        self.assertEqual(len(data["positions"]), self.count)
        self.assertEqual(data["influenceLocks"], [False] * 4)
        self.assertEqual(data["settings"], {"skinningMethod": "classicLinear", "maxInfluences": 4,
                                            "maintainMaxInfluences": False, "normalizeWeights": "interactive"})
        self.assertIsNone(data["ngSkinLayers"])
        std_json.dumps(data, allow_nan=False)

    def test_sparse_weights(self):
        rows = [[1.0, 0.0, 0.0, 0.0]] * self.count
        self.skin.setWeights(self.joints, rows, rows=True)
        data = self.skin.getWeightsData()
        self.assertEqual(data["weights"]["indices"], [[0]] * self.count)
        self.assertEqual(data["weights"]["values"], [[1.0]] * self.count)

    def test_round_trip_exact(self):
        expected = self.allWeights()
        written = self.skin.exportWeights(self.path)
        self.assertEqual(str(written), os.path.realpath(self.path))
        with open(self.path, encoding="utf-8") as stream:
            raw = std_json.load(stream)
        self.assertEqual(raw["header"]["format"], "mlib.skinWeights")
        self.assertEqual(raw["header"]["version"], 1)
        self.scramble()
        report = self.skin.importWeights(self.path)
        self.assertIsInstance(report, ValidationReport)
        self.assertEqual((report.missing, report.skipped, report.errors), ([], [], []))
        self.assertRowsAlmostEqual(self.allWeights(), expected, places=12)

    def test_set_weights_data_round_trip(self):
        data = self.skin.getWeightsData()
        self.scramble()
        self.skin.setWeightsData(data)
        self.assertEqual(self.skin.getWeightsData()["weights"], data["weights"])

    def test_wrong_format_and_bad_data(self):
        dump({"a": 1}, self.path, "mlib.pose", 1)
        with self.assertRaises(ValueError):
            self.skin.importWeights(self.path)
        data = self.skin.getWeightsData()
        broken = dict(data, weights={"indices": data["weights"]["indices"][:-1], "values": data["weights"]["values"]})
        with self.assertRaises(ValueError):
            self.skin.setWeightsData(broken)
        with self.assertRaises(TypeError):
            self.skin.setWeightsData([])
        with self.assertRaises(ValueError):
            self.skin.setWeightsData(data, method="nearest")
        with self.assertRaises(TypeError):
            self.skin.setWeightsData(data, fast=1)


class MappingTest(SkinWeightsCase):
    """influence の対応付け・欠け・追加。"""

    def test_namespace_mapping(self):
        expected = self.allWeights()
        self.skin.exportWeights(self.path)
        other = self.ns + "B"
        cmds.namespace(add=other)
        self.extra_namespaces.append(other)
        joints = self.makeJoints(other)
        mesh = self.makePlane(other, "mesh", 4)
        skin = mlib.bindSkin(joints, mesh)
        report = skin.importWeights(self.path, namespaceMap={self.ns: other})
        self.assertEqual(report.missing, [])
        self.assertRowsAlmostEqual(self.allWeights(skin, joints), expected, places=12)

    def test_missing_influence_is_reported_and_renormalized(self):
        expected = self.allWeights()
        self.skin.exportWeights(self.path)
        renamed = cmds.rename(self.joints[3], "renamedJ3")
        joints = self.joints[:3] + [cmds.ls(renamed, long=True)[0]]
        self.scramble(joints=joints)
        report = self.skin.importWeights(self.path)
        self.assertEqual(report.missing, [self.name("j3")])
        actual = self.allWeights(joints=joints)
        for row, saved in zip(actual, expected):
            self.assertAlmostEqual(row[3], 0.0, places=12)
            scale = 1.0 / sum(saved[:3])
            self.assertSequenceAlmostEqual(row[:3], [value * scale for value in saved[:3]], places=12)

    def test_vertex_only_on_missing_influence_is_skipped(self):
        rows = self.pattern(self.count, 4)
        rows[0] = [0.0, 0.0, 0.0, 1.0]
        self.skin.setWeights(self.joints, rows, rows=True)
        self.skin.exportWeights(self.path)
        renamed = cmds.ls(cmds.rename(self.joints[3], "renamedJ3"), long=True)[0]
        joints = self.joints[:3] + [renamed]
        self.scramble(joints=joints)
        report = self.skin.importWeights(self.path)
        self.assertEqual(len(report.skipped), 1)
        self.assertIn(".vtx[0]", report.skipped[0])
        self.assertSequenceAlmostEqual(self.allWeights(joints=joints)[0], [1.0, 0.0, 0.0, 0.0])

    def test_extra_influence_is_added(self):
        expected = self.allWeights()
        self.skin.exportWeights(self.path)
        mesh = self.makePlane(self.ns, "partial", 4)
        skin = mlib.bindSkin(self.joints[:2], mesh)
        self.assertEqual(len(skin.getInfluences()), 2)
        skin.importWeights(self.path)
        self.assertEqual(sorted(node.getFullName() for node in skin.getInfluences()), sorted(self.joints))
        self.assertRowsAlmostEqual(self.allWeights(skin), expected, places=12)

    def test_target_only_influence_is_zeroed(self):
        cmds.select(clear=True)
        extra = cmds.ls(cmds.joint(name=self.name("extra"), position=(0, 3, 0)), long=True)[0]
        cmds.select(clear=True)
        expected = self.allWeights()
        self.skin.exportWeights(self.path)
        self.skin.addInfluences([extra])
        self.skin.setWeights([extra], [0.5], broadcast=True)
        self.skin.importWeights(self.path)
        self.assertRowsAlmostEqual(self.allWeights(), expected, places=12)
        self.assertTrue(all(value == 0.0 for value in self.skin.getWeights([extra])))

    def test_no_influence_found_raises(self):
        self.skin.exportWeights(self.path)
        before = self.allWeights()
        with self.assertRaises(ValueError):
            self.skin.importWeights(self.path, namespaceMap={self.ns: "missingNamespace"})
        self.assertRowsAlmostEqual(self.allWeights(), before)


class VertexMethodTest(SkinWeightsCase):
    """頂点の対応(index・position)。"""

    def test_index_mismatch_raises_without_change(self):
        self.skin.exportWeights(self.path)
        mesh = self.makePlane(self.ns, "dense", 8)
        skin = mlib.bindSkin(self.joints, mesh)
        before = self.allWeights(skin)
        with self.assertRaises(ValueError) as caught:
            skin.importWeights(self.path)
        self.assertIn("vertex count", str(caught.exception))
        self.assertRowsAlmostEqual(self.allWeights(skin), before)

    def test_position_on_different_resolution(self):
        expected = self.allWeights()
        source_points = [tuple(round(value, 6) for value in point)
                         for point in self.skin.getWeightsData()["positions"]]
        self.skin.exportWeights(self.path)
        mesh = self.makePlane(self.ns, "dense", 8)
        skin = mlib.bindSkin(self.joints, mesh)
        skin.importWeights(self.path, method="position")
        target = self.allWeights(skin)
        positions = skin.getWeightsData()["positions"]
        matched = 0
        for vertex, point in enumerate(positions):
            key = tuple(round(value, 6) for value in point)
            if key in source_points:
                self.assertSequenceAlmostEqual(target[vertex], expected[source_points.index(key)], places=12)
                matched += 1
        self.assertEqual(matched, self.count)
        for row in target:
            self.assertAlmostEqual(sum(row), 1.0, places=9)


class StateTest(SkinWeightsCase):
    """ロック・DQ ブレンドウェイト・設定。"""

    def test_lock_state_restored(self):
        cmds.setAttr(self.joints[1] + ".liw", True)
        expected = self.allWeights()
        self.skin.exportWeights(self.path)
        cmds.setAttr(self.joints[1] + ".liw", False)
        cmds.setAttr(self.joints[2] + ".liw", True)
        self.scramble()
        self.skin.importWeights(self.path)
        self.assertEqual([cmds.getAttr(joint + ".liw") for joint in self.joints], [False, True, False, False])
        self.assertRowsAlmostEqual(self.allWeights(), expected, places=12)

    def test_dq_blend_weights(self):
        self.skin.setSkinningMethod("weightBlended")
        blend = [vertex / float(self.count) for vertex in range(self.count)]
        cmds.setAttr(f"{self.skin.getFullName()}.blendWeights[0:{self.count - 1}]", *blend)
        data = self.skin.getWeightsData()
        self.assertSequenceAlmostEqual(data["blendWeights"], blend)
        self.skin.exportWeights(self.path)
        cmds.setAttr(f"{self.skin.getFullName()}.blendWeights[0:{self.count - 1}]", *([0.0] * self.count))
        self.skin.setSkinningMethod("classicLinear")
        self.skin.importWeights(self.path)
        self.assertEqual(self.skin.getSkinningMethod(), "weightBlended")
        self.assertSequenceAlmostEqual(self.skin.getWeightsData()["blendWeights"], blend)

    def test_settings(self):
        self.skin.setSkinningMethod("dualQuaternion")
        self.skin.setMaxInfluences(3, maintain=False)
        self.skin.setNormalizeMode("post")
        self.skin.exportWeights(self.path)
        self.skin.setSkinningMethod("classicLinear")
        self.skin.setMaxInfluences(5, maintain=True)
        self.skin.setNormalizeMode("interactive")
        self.skin.importWeights(self.path)
        self.assertEqual(self.skin.getSkinningMethod(), "dualQuaternion")
        self.assertEqual(self.skin.getMaxInfluences(), 3)
        self.assertFalse(self.skin.isMaintainingMaxInfluences())
        self.assertEqual(self.skin.getNormalizeMode(), "post")

    def test_locked_setting_is_skipped(self):
        self.skin.setMaxInfluences(3)
        self.skin.exportWeights(self.path)
        self.skin.setMaxInfluences(5)
        cmds.setAttr(self.skin.getFullName() + ".maxInfluences", lock=True)
        try:
            report = self.skin.importWeights(self.path)
        finally:
            cmds.setAttr(self.skin.getFullName() + ".maxInfluences", lock=False)
        self.assertEqual(len(report.skipped), 1)
        self.assertIn("maxInfluences", report.skipped[0])
        self.assertEqual(self.skin.getMaxInfluences(), 5)


class UndoFastTest(SkinWeightsCase):
    """1 回の Undo と fast。"""

    def test_one_undo_restores(self):
        expected = self.allWeights()
        cmds.setAttr(self.joints[0] + ".liw", True)
        self.skin.setSkinningMethod("dualQuaternion")
        self.skin.exportWeights(self.path)
        cmds.setAttr(self.joints[0] + ".liw", False)
        self.skin.setSkinningMethod("classicLinear")
        self.scramble()
        scrambled = self.allWeights()
        self.flushUndo()
        self.skin.importWeights(self.path)

        def before():
            self.assertRowsAlmostEqual(self.allWeights(), scrambled)
            self.assertFalse(cmds.getAttr(self.joints[0] + ".liw"))
            self.assertEqual(self.skin.getSkinningMethod(), "classicLinear")

        def after():
            self.assertRowsAlmostEqual(self.allWeights(), expected, places=12)
            self.assertTrue(cmds.getAttr(self.joints[0] + ".liw"))
            self.assertEqual(self.skin.getSkinningMethod(), "dualQuaternion")

        self.assertUndoesInOneStep(before, after)

    def test_undo_restores_added_influence(self):
        self.skin.exportWeights(self.path)
        mesh = self.makePlane(self.ns, "partial", 4)
        skin = mlib.bindSkin(self.joints[:2], mesh)
        self.flushUndo()
        skin.importWeights(self.path)
        self.assertEqual(len(skin.getInfluences()), 4)
        cmds.undo()
        self.assertEqual(len(skin.getInfluences()), 2)

    def test_fast_has_no_undo_and_same_result(self):
        self.skin.setSkinningMethod("weightBlended")
        cmds.setAttr(self.joints[2] + ".liw", True)
        blend = [vertex / float(self.count) for vertex in range(self.count)]
        cmds.setAttr(f"{self.skin.getFullName()}.blendWeights[0:{self.count - 1}]", *blend)
        expected = self.skin.getWeightsData()
        self.skin.exportWeights(self.path)
        self.skin.setSkinningMethod("classicLinear")
        cmds.setAttr(self.joints[2] + ".liw", False)
        cmds.setAttr(f"{self.skin.getFullName()}.blendWeights[0:{self.count - 1}]", *([0.0] * self.count))
        self.scramble()
        self.flushUndo()
        self.skin.importWeights(self.path, fast=True)
        self.assertUndoEmpty()
        actual = self.skin.getWeightsData()
        for key in ("weights", "influenceLocks", "settings", "blendWeights"):
            self.assertEqual(actual[key], expected[key], key)


class BindSkinTest(SkinWeightsCase):
    """bindSkin のファイルからの作成。"""

    def test_bind_from_file(self):
        self.skin.setSkinningMethod("dualQuaternion")
        self.skin.setMaxInfluences(3, maintain=False)
        cmds.setAttr(self.joints[1] + ".liw", True)
        expected = self.skin.getWeightsData()
        self.skin.exportWeights(self.path)
        mesh = self.makePlane(self.ns, "fresh", 4)
        self.flushUndo()
        skin = mlib.bindSkin(None, mesh, weights=self.path)
        self.assertIsInstance(skin, SkinCluster)
        self.assertEqual([node.getFullName() for node in skin.getInfluences()], self.joints)
        actual = skin.getWeightsData()
        for key in ("weights", "influenceLocks", "settings", "blendWeights"):
            self.assertEqual(actual[key], expected[key], key)
        cmds.undo()
        self.assertFalse(cmds.ls(cmds.listHistory(mesh) or [], type="skinCluster"))

    def test_bind_from_file_with_namespace_and_position(self):
        expected = self.allWeights()
        self.skin.exportWeights(self.path)
        other = self.ns + "B"
        cmds.namespace(add=other)
        self.extra_namespaces.append(other)
        joints = self.makeJoints(other)
        mesh = self.makePlane(other, "mesh", 4)
        skin = mlib.bindSkin(None, mesh, weights=self.path, namespaceMap={self.ns: other}, method="position")
        self.assertEqual([node.getFullName() for node in skin.getInfluences()], joints)
        self.assertRowsAlmostEqual(self.allWeights(skin, joints), expected, places=12)

    def test_bind_from_file_rejects_before_binding(self):
        self.skin.exportWeights(self.path)
        mesh = self.makePlane(self.ns, "dense", 8)
        with self.assertRaises(ValueError):
            mlib.bindSkin(None, mesh, weights=self.path)
        self.assertFalse(cmds.ls(cmds.listHistory(mesh) or [], type="skinCluster"))
        with self.assertRaises(ValueError):
            mlib.bindSkin(None, mesh)
        with self.assertRaises(TypeError):
            mlib.bindSkin(self.joints, mesh, namespaceMap={"a": "b"})

    def test_bind_without_file_is_unchanged(self):
        mesh = self.makePlane(self.ns, "plain", 2)
        skin = mlib.bindSkin(self.joints[:2], mesh)
        self.assertEqual(skin.getMaxInfluences(), 4)
        self.assertEqual(skin.getNormalizeMode(), "interactive")


@unittest.skipUnless(os.path.exists(NGSKIN_PLUGIN), "ngSkinTools2 is not available for this Maya version")
class NgSkinLayersTest(SkinWeightsCase):
    """ngSkinTools2 のレイヤーの保存と作り直し。"""

    @classmethod
    def setUpClass(cls):
        scripts = os.path.join(CONTENTS, "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        cmds.loadPlugin(NGSKIN_PLUGIN, quiet=True)

    def setUp(self):
        super().setUp()
        from ngSkinTools2 import api

        self.api = api
        self.layers = api.init_layers(self.skin.getName())
        base = self.layers.add("base")
        for index, value in enumerate((.5, .2, .2, .1)):
            base.set_weights(index, [value] * self.count)
        top = self.layers.add("top")
        top.set_weights(2, [.25] * self.count)
        top.set_weights(1, [.25] * self.count)
        top.set_weights("mask", [vertex / float(self.count) for vertex in range(self.count)])
        top.opacity = 0.7
        child = self.layers.add("child", parent=top)
        child.set_weights(3, [.3] * self.count)

    def tearDown(self):
        for layers in getattr(self, "cleanup", []):
            layers.clear()
        self.layers.clear()
        super().tearDown()

    def describe(self, layers):
        """レイヤーの名前・親・不透明度・使う influence の組を返す。"""
        items = layers.list()
        names = {layer.id: layer.name for layer in items}
        return sorted((layer.name, names.get(layer.parent_id), round(layer.opacity, 6),
                       sorted(layer.get_used_influences())) for layer in items)

    def test_layers_round_trip(self):
        expected = self.skin.getWeightsData()
        self.assertEqual([layer["name"] for layer in expected["ngSkinLayers"]], ["base", "top", "child"])
        layout = self.describe(self.layers)
        self.skin.exportWeights(self.path)
        self.layers.clear()
        self.scramble()
        self.flushUndo()
        report = self.skin.importWeights(self.path)
        self.assertEqual(report.skipped, [])
        self.assertEqual(self.describe(self.api.Layers(self.skin.getName())), layout)
        actual = self.skin.getWeightsData()
        self.assertEqual(actual["ngSkinLayers"], expected["ngSkinLayers"])
        indices, values = actual["weights"]["indices"], actual["weights"]["values"]
        self.assertEqual(indices, expected["weights"]["indices"])
        self.assertRowsAlmostEqual(values, expected["weights"]["values"], places=6)
        cmds.undo()
        self.assertEqual(self.api.Layers(self.skin.getName()).list(), [])

    def test_layers_into_another_skin(self):
        expected = self.skin.getWeightsData()
        self.skin.exportWeights(self.path)
        other = self.ns + "B"
        cmds.namespace(add=other)
        self.extra_namespaces.append(other)
        joints = self.makeJoints(other)
        skin = mlib.bindSkin(joints, self.makePlane(other, "mesh", 4))
        skin.importWeights(self.path, namespaceMap={self.ns: other})
        target = self.api.Layers(skin.getName())
        self.cleanup = [target]
        self.assertEqual(self.describe(target), self.describe(self.layers))
        self.assertRowsAlmostEqual(skin.getWeightsData()["weights"]["values"], expected["weights"]["values"],
                                   places=6)

    def test_existing_layers_are_kept_without_saved_layers(self):
        data = self.skin.getWeightsData()
        data["ngSkinLayers"] = None
        report = self.skin.setWeightsData(data)
        self.assertEqual(len(report.skipped), 1)
        self.assertIn("ngSkinTools layers", report.skipped[0])
        self.assertEqual(len(self.layers.list()), 3)


if __name__ == "__main__":
    unittest.main()
