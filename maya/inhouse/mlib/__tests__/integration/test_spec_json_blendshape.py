"""BlendShape のターゲットの JSON 保存・復元(getTargetsData・setTargetsData・exportTargets・importTargets)。

- 別のメッシュの空の blendShape へ書き出し→読み込み: デルタ・in-between(相対・絶対)・頂点マスク・baseWeights・
  ウェイトの値・ドライバーの再接続(namespaceMap)・Shape Editor のフォルダ。変形結果も一致する。
- mode="replace"(同名の置き換えと追加)・mode="empty" の拒否・頂点数の違いのエラー・見つからないドライバー・Undo 1回。
"""

import json as std_json
import os
import shutil
import sys
import tempfile
import unittest

import maya.cmds as cmds
import maya.mel as mel

import mlib
mlib.reload()
from mlib.json import ValidationReport
from mlib.nodes import BlendShape
from support.specCase import NamespaceCase


class _JsonBlendCase(NamespaceCase):
    """2つの名前空間に同じ平面とコントローラーを作り、片方にターゲット一式を持つ blendShape を作る。"""

    PREFIX = "mlibSpecJsonBs_"

    def setUp(self):
        super().setUp()
        self.other = self.ns + "B"
        cmds.namespace(add=self.other)
        self.extra_namespaces.append(self.other)
        self.folder = tempfile.mkdtemp(prefix="mlibJsonBs")
        self.path = os.path.join(self.folder, "targets.json")
        self.base = self.plane(self.name("base"))
        self.ctrl = cmds.createNode("transform", name=self.name("ctrl"))
        self.ctrl_b = cmds.createNode("transform", name=self.other + ":ctrl")
        smile = self.lifted(self.name("smileGeo"), 1.0, 1.0)
        frown = self.lifted(self.name("frownGeo"), -1.0, -1.0)
        half = self.lifted(self.name("halfGeo"), 1.0, 0.4)
        rel = self.lifted(self.name("relGeo"), -1.0, 0.2)
        self.bs = BlendShape(cmds.blendShape(smile, frown, self.base, name=self.name("bs"))[0])
        cmds.aliasAttr("smile", f"{self.bs}.weight[0]")
        cmds.aliasAttr("frown", f"{self.bs}.weight[1]")
        self.bs.addInBetween("smile", half, 0.4)
        self.bs.addInBetween("smile", rel, 0.7, relative=True)
        self.bs.addTarget(self.lifted(self.name("extraGeo"), 1.0, 0.3), name="extra")
        cmds.delete(frown, half, rel)
        self.bs.setTargetWeights("frown", {0: 0.5, 5: 0.25})
        # Maya 2022 は要素0の無い疎な baseWeights を変形に使わないため、全頂点を書く。
        cmds.setAttr(f"{self.bs}.inputTarget[0].baseWeights[0:14]", *([1.0] * 3 + [0.75] + [1.0] * 11))
        cmds.setAttr(f"{self.bs}.frown", 0.6)
        cmds.connectAttr(self.ctrl + ".translateX", f"{self.bs}.smile")
        cmds.setAttr(self.ctrl + ".translateX", 0.7)
        # frown と extra をフォルダへまとめ、extra を先にする。
        mel.eval(f'blendShapeCreateTargetGroup({{"{self.bs.getName()}.1", "{self.bs.getName()}.2"}})')
        self.group = cmds.getAttr(f"{self.bs}.parentDirectory[1]")
        cmds.setAttr(f"{self.bs}.targetDirectory[{self.group}].childIndices", [2, 1], type="Int32Array")
        cmds.setAttr(f"{self.bs}.targetDirectory[{self.group}].directoryName", "mouth", type="string")
        cmds.setAttr(f"{self.bs}.targetDirectory[{self.group}].directoryWeight", 0.5)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)
        super().tearDown()

    @staticmethod
    def plane(name):
        return cmds.polyPlane(name=name, width=4, height=2, subdivisionsX=4, subdivisionsY=2,
                              constructionHistory=False)[0]

    def lifted(self, name, side, amount):
        mesh = self.plane(name)
        for index in range(15):
            point = cmds.xform(f"{mesh}.vtx[{index}]", query=True, translation=True, objectSpace=True)
            if point[0] * side > 0.1:
                cmds.xform(f"{mesh}.vtx[{index}]", translation=(point[0], amount + index * 0.01, point[2]),
                           objectSpace=True)
        return mesh

    def fresh(self, namespace=None, subdivisions=4):
        """別の名前空間に同じ平面と、ターゲットの無い blendShape を作る。"""
        namespace = namespace or self.other
        mesh = cmds.polyPlane(name=namespace + ":base", width=4, height=2, subdivisionsX=subdivisions,
                              subdivisionsY=2, constructionHistory=False)[0]
        return mesh, BlendShape(cmds.blendShape(mesh, name=namespace + ":bs")[0])

    @staticmethod
    def points(mesh):
        count = cmds.polyEvaluate(mesh, vertex=True)
        return [tuple(round(v, 5) for v in cmds.xform(f"{mesh}.vtx[{i}]", query=True, translation=True,
                                                         objectSpace=True)) for i in range(count)]

    @staticmethod
    def deltas(bs, target, weight=1.0):
        return {k: tuple(round(v, 6) for v in d) for k, d in bs.getTargetDeltas(target, fullWeight=weight).items()}

    def folders(self, bs):
        return bs.getTargetsData()["folders"]


class ExportImportTest(_JsonBlendCase):

    def test_export_import_into_fresh_blendshape(self):
        written = self.bs.exportTargets(self.path)
        self.assertEqual(str(written), os.path.realpath(self.path))
        with open(self.path, encoding="utf-8") as stream:
            raw = std_json.load(stream)
        self.assertEqual(raw["header"]["format"], "mlib.blendShapeTargets")
        self.assertEqual(raw["header"]["version"], 1)
        mesh, bs = self.fresh()
        report = bs.importTargets(self.path, namespaceMap={self.ns: self.other}, mode="empty")
        self.assertIsInstance(report, ValidationReport)
        self.assertEqual((report.missing, report.skipped, report.errors), ([], [], []))
        self.assertEqual(bs.getTargetNames(), ["smile", "frown", "extra"])
        for name in ("smile", "frown", "extra"):
            with self.subTest(name=name):
                self.assertEqual(self.deltas(bs, name), self.deltas(self.bs, name))
                self.assertEqual(bs.getTargetWeights(name), self.bs.getTargetWeights(name))
                self.assertEqual(bs.getInBetweenWeights(name), self.bs.getInBetweenWeights(name))
        for weight in (0.4, 0.7):
            self.assertEqual(self.deltas(bs, "smile", weight), self.deltas(self.bs, "smile", weight))
        info = "inbetweenInfoGroup[0].inbetweenInfo[{}].inbetweenTargetType"
        self.assertEqual(cmds.getAttr(f"{bs}." + info.format(5700)), 1)
        self.assertEqual(cmds.getAttr(f"{bs}." + info.format(5400)), 0)
        self.assertAlmostEqual(cmds.getAttr(f"{bs}.inputTarget[0].baseWeights[3]"), 0.75)
        self.assertAlmostEqual(cmds.getAttr(f"{bs}.frown"), 0.6, places=6)
        self.assertEqual(cmds.listConnections(f"{bs}.smile", source=True, destination=False, plugs=True),
                         [self.ctrl_b + ".translateX"])
        self.assertEqual(self.folders(bs), self.folders(self.bs))
        group = cmds.getAttr(f"{bs}.parentDirectory[{bs.getTargetIndex('frown')}]")
        self.assertEqual(cmds.getAttr(f"{bs}.targetDirectory[{group}].directoryName"), "mouth")
        self.assertAlmostEqual(cmds.getAttr(f"{bs}.targetDirectory[{group}].directoryWeight"), 0.5)
        # 変形結果も同じになる(相対 in-between を通る値を含む)。
        for value in (0.25, 0.55, 0.7, 1.0):
            cmds.setAttr(self.ctrl + ".translateX", value)
            cmds.setAttr(self.ctrl_b + ".translateX", value)
            with self.subTest(value=value):
                self.assertEqual(self.points(mesh), self.points(self.base))

    def test_data_round_trip_is_json_compatible(self):
        data = self.bs.getTargetsData()
        text = std_json.dumps(data, allow_nan=False)
        self.assertEqual([target["name"] for target in data["targets"]], ["smile", "frown", "extra"])
        self.assertEqual(data["targets"][0]["driver"]["attr"], "translateX")
        self.assertEqual(data["bases"][0]["vertexCount"], 15)
        _mesh, bs = self.fresh()
        bs.setTargetsData(std_json.loads(text), namespaceMap={self.ns: self.other})
        self.assertEqual(bs.getTargetsData()["folders"], data["folders"])

    def test_connected_target_is_baked(self):
        geo = self.lifted(self.name("liveGeo"), 1.0, 2.0)
        live = self.bs.addTarget(geo, name="live")
        cmds.xform(f"{geo}.vtx[0]", translation=(0, 5, 0), relative=True)
        data = self.bs.getTargetsData()
        record = next(target for target in data["targets"] if target["name"] == "live")
        item = record["bases"][0]["items"][0]
        offsets = dict(zip(item["indices"], zip(*[iter(item["offsets"])] * 3)))
        self.assertAlmostEqual(offsets[0][1], 5.0, places=5)
        _mesh, bs = self.fresh()
        bs.setTargetsData(data, namespaceMap={self.ns: self.other})
        self.assertEqual(self.deltas(bs, "live"), self.deltas(self.bs, live))
        self.assertFalse(cmds.listConnections(f"{bs}.inputTarget[0].inputTargetGroup[{bs.getTargetIndex('live')}]"
                                              ".inputTargetItem[6000].inputGeomTarget"))

    def test_one_undo(self):
        _mesh, bs = self.fresh()
        self.flushUndo()
        bs.importTargets(self.bs.exportTargets(self.path), namespaceMap={self.ns: self.other})
        self.assertUndoesInOneStep(lambda: self.assertEqual(bs.getTargetNames(), []),
                                   lambda: self.assertEqual(bs.getTargetNames(), ["smile", "frown", "extra"]))
        self.assertFalse(cmds.listConnections(f"{bs}.weight", source=True, destination=False))


class ModeAndErrorTest(_JsonBlendCase):

    def test_replace_mode_replaces_same_name_and_adds_missing(self):
        self.bs.exportTargets(self.path)
        expected = {name: self.deltas(self.bs, name) for name in ("smile", "frown", "extra")}
        folders = self.folders(self.bs)
        self.bs.setTargetDeltas("smile", {0: (9, 9, 9)}, disconnect=True)
        self.bs.removeInBetween("smile", 0.4)
        self.bs.setTargetWeights("frown", [1.0] * 15)
        self.bs.removeTarget("extra")
        self.bs.addTarget(self.lifted(self.name("keepGeo"), 1.0, 0.1), name="keep")
        index = self.bs.getTargetIndex("smile")
        report = self.bs.importTargets(self.path)
        self.assertEqual(report.errors, [])
        self.assertEqual(self.bs.getTargetIndex("smile"), index)
        self.assertEqual(sorted(self.bs.getTargetNames()), ["extra", "frown", "keep", "smile"])
        for name, deltas in expected.items():
            with self.subTest(name=name):
                self.assertEqual(self.deltas(self.bs, name), deltas)
        self.assertEqual(self.bs.getInBetweenWeights("smile"), [0.4, 0.7])
        self.assertEqual(self.bs.getTargetWeights("frown")[5], 0.25)
        self.assertEqual(cmds.listConnections(f"{self.bs}.smile", source=True, destination=False, plugs=True),
                         [self.ctrl + ".translateX"])
        self.assertIn("keep", self.bs)
        # extra は空いた番号へ追加されるため、フォルダの中身は名前で比べる。
        mouth = [entry for entry in self.folders(self.bs) if "folder" in entry]
        self.assertEqual([entry["folder"] for entry in mouth], ["mouth"])
        self.assertEqual([entry["target"] for entry in mouth[0]["children"]],
                         [self.bs.getTargetIndex("extra"), self.bs.getTargetIndex("frown")])
        self.assertEqual(len([entry for entry in folders if "folder" in entry]), 1)

    def test_empty_mode_rejects_existing_targets(self):
        data = self.bs.getTargetsData()
        before = self.bs.getTargetsData()
        with self.assertRaises(ValueError):
            self.bs.setTargetsData(data, mode="empty")
        self.assertEqual(self.bs.getTargetsData(), before)
        for mode, error in (("merge", ValueError), (1, TypeError)):
            with self.subTest(mode=mode), self.assertRaises(error):
                self.bs.setTargetsData(data, mode=mode)
        with self.assertRaises(TypeError):
            self.bs.setTargetsData([])
        with self.assertRaises(ValueError):
            self.bs.setTargetsData({"bases": []})

    def test_topology_mismatch_changes_nothing(self):
        self.bs.exportTargets(self.path)
        _mesh, bs = self.fresh(subdivisions=3)
        self.flushUndo()
        with self.assertRaises(ValueError) as caught:
            bs.importTargets(self.path, namespaceMap={self.ns: self.other})
        self.assertIn("vertices", str(caught.exception))
        self.assertEqual(bs.getTargetNames(), [])
        self.assertUndoEmpty()

    def test_missing_driver_is_reported(self):
        self.bs.exportTargets(self.path)
        _mesh, bs = self.fresh()
        report = bs.importTargets(self.path, namespaceMap={self.ns: self.ns + "Missing"})
        self.assertEqual(report.missing, [self.ns + "Missing:ctrl.translateX"])
        self.assertFalse(cmds.listConnections(f"{bs}.smile", source=True, destination=False))
        self.assertAlmostEqual(cmds.getAttr(f"{bs}.smile"), 0.7, places=6)

    def test_rejects_other_format(self):
        from mlib.json import dump
        dump({"bases": []}, self.path, "mlib.other", 1)
        with self.assertRaises(ValueError):
            self.bs.importTargets(self.path)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
