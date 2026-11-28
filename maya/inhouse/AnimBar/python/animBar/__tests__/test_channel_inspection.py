"""選択チャンネルの参照とアニメーションレイヤーの分類を検証する。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import maya.cmds as cmds
import mlib

from animBar.core import animCopy, keys, timing


class ChannelInspectionTest(unittest.TestCase):
    """同じリグを2回参照する専用シーンを使う。"""

    def test_published_export_scope(self):
        """公開種別と実入力の両方を検査し、未宣言のキーを除外する。"""
        from mlrig import publishedChannels

        cmds.file(new=True, force=True)
        root = cmds.createNode("transform", name="rig")
        ctrl = cmds.createNode("transform", name="ctrl", parent=root)
        kinds = ("default", "static", "constraint", "deformer", "externalRig", "irregular")
        ports = {kind: dict(path="ctrl", attribute=attr, kind=kind)
                 for kind, attr in zip(kinds, ("tx", "ty", "rx", "ry", "rz", "sz"))}
        ports["override"] = dict(path="ctrl", attribute="rotateX", kind="default")
        publishedChannels.setPorts(root, ports)
        cmds.setKeyframe(ctrl, at="tx", time=3, value=7)
        cmds.setKeyframe(ctrl, at="tz", time=3, value=13)
        cmds.select(root)
        clip, excluded = animCopy.previewPublishedExport((1, 5))
        self.assertEqual(set(clip["channels"]), {"|rig|ctrl.translateX", "|rig|ctrl.translateY"})
        self.assertEqual(len(excluded), 4)
        for kind, attr in zip(kinds[2:], ("rotateX", "rotateY", "rotateZ", "scaleZ")):
            self.assertIn(kind, excluded["|rig|ctrl." + attr])
        cmds.setKeyframe(ctrl, at="ty", time=3, value=2)
        self.assertIn("Static port has an input", animCopy.previewPublishedExport((1, 5))[1]["|rig|ctrl.translateY"])

    def test_published_reset_defaults(self):
        """例外宣言の既定値とロックを監査し、欠損した役割を報告する。"""
        from mlrig import publishedChannels

        cmds.file(new=True, force=True)
        root = cmds.createNode("transform", name="rig")
        cmds.addAttr(root, longName="gain", attributeType="double", defaultValue=2.5, keyable=True)
        cmds.setAttr(root + ".gain", 7, lock=True)
        lost = cmds.createNode("transform", name="lost", parent=root)
        publishedChannels.setPorts(root, {
            "special": dict(path="", attribute="gain", kind="irregular"),
            "missing": dict(path="lost", attribute="tx", kind="static"),
        })
        cmds.delete(lost)
        cmds.select(root)
        before = cmds.undoInfo(query=True, undoName=True)
        rows, unavailable = timing.inspectPublishedDefaults()
        self.assertEqual(rows, [("|rig.gain", 2.5, "Static", "", True, "special (irregular)")])
        self.assertIn("Missing static port", unavailable["|rig [missing]"])
        self.assertEqual(cmds.getAttr(root + ".gain"), 7)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), before)

    def test_captured_defaults_are_scoped_per_rig(self):
        """同名役割の初期値をリグごとに読み出す。"""
        from mlrig import publishedChannels

        cmds.file(new=True, force=True)
        roots = [cmds.createNode("transform", name=name) for name in ("first", "second")]
        for root, value in zip(roots, (3.0, 5.0)):
            publishedChannels.setPorts(root, {"lift": dict(path="", attribute="translateY", kind="default")})
            cmds.setAttr(root + ".translateY", value)
            publishedChannels.captureDefaults(root, ["lift"])
            cmds.setAttr(root + ".translateY", 0)
        cmds.select(roots, replace=True)
        rows, missing = timing.inspectPublishedDefaults()
        self.assertFalse(missing)
        self.assertEqual({row[0]: row[1] for row in rows}, {"|first.translateY": 3.0, "|second.translateY": 5.0})

    def test_selected_reset_key_scope(self):
        """飛び選択の監査結果を実際のリセットとUndoに照合する。"""
        cmds.file(new=True, force=True)
        node = cmds.createNode("transform", name="auditCtrl")
        for frame in (1, 3, 9):
            cmds.setKeyframe(node, attribute="scaleX", time=frame, value=frame + 2)
        cmds.selectKey(clear=True)
        self.assertEqual(timing.inspectResetKeys(), [])
        for frame in (1, 9):
            cmds.selectKey(node, attribute="scaleX", time=(frame, frame), add=True)
        before = cmds.undoInfo(query=True, undoName=True)
        rows = timing.inspectResetKeys()
        self.assertEqual([row[1:] for row in rows], [("|auditCtrl.scaleX", [1, 9], 1)])
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), before)
        self.assertEqual(timing.resetValues(), 2)
        self.assertEqual(cmds.keyframe(node, attribute="scaleX", query=True, valueChange=True), [1, 5, 1])
        cmds.undo()
        self.assertEqual(cmds.keyframe(node, attribute="scaleX", query=True, valueChange=True), [3, 5, 11])

    def test_channel_box_export_scope(self):
        """同名の2体を選択し、指定したPlugだけを書き出す。"""
        cmds.file(new=True, force=True)
        with tempfile.TemporaryDirectory() as folder:
            self.addCleanup(cmds.file, new=True, force=True)
            for group in ("a", "b"):
                cmds.createNode("transform", name=group)
                cmds.createNode("transform", name="ctrl", parent=group)
            path = str(Path(folder) / "shot.ma")
            cmds.file(rename=path)
            cmds.file(save=True, type="mayaAscii")
            for reopen in (False, True):
                if reopen:
                    cmds.file(path, open=True, force=True)
                cmds.select("|a|ctrl", "|b|ctrl")
                plug = mlib.getPlug("|b|ctrl.ty")
                for selected, expected in (([], set()), ([plug], {"|b|ctrl.translateY"})):
                    with patch.object(keys, "_channel_box_plugs", return_value=selected):
                        clip, excluded = animCopy.previewClipExport((1, 5), channelBoxOnly=True)
                        defaults = timing.inspectResetDefaults(channelBoxOnly=True)
                    self.assertEqual(defaults, [(path, 0.0, "Static", "", False) for path in expected])
                    self.assertEqual(set(clip["channels"]), expected)
                    self.assertFalse(excluded)

    def test_layer_on_one_reference(self):
        """同名の参照先の片方だけに加えたレイヤーを保存後も区別できる。"""
        cmds.file(new=True, force=True)
        with tempfile.TemporaryDirectory() as folder:
            self.addCleanup(cmds.file, new=True, force=True)
            rig = str(Path(folder) / "rig.ma")
            node = cmds.createNode("transform", name="ctrl")
            cmds.setKeyframe(node, attribute="translateX", time=1, value=2)
            cmds.setAttr(node + ".scaleZ", lock=True)
            cmds.file(rename=rig)
            cmds.file(save=True, type="mayaAscii")
            cmds.file(new=True, force=True)
            for namespace in ("first", "second"):
                cmds.file(rig, reference=True, namespace=namespace)
            layer = cmds.animLayer("Offset", attribute="first:ctrl.translateX")
            cmds.setKeyframe("first:ctrl.translateX", animLayer=layer, time=5, value=3)
            shot = str(Path(folder) / "shot.ma")
            cmds.file(rename=shot)
            cmds.file(save=True, type="mayaAscii")
            for reopen in (False, True):
                if reopen:
                    cmds.file(shot, open=True, force=True)
                for namespace, expected in (("first", "Animation layer"), ("second", "Time keys")):
                    node = "|" + namespace + ":ctrl"
                    cmds.select(node)
                    rows = keys.inspectChannels()
                    self.assertEqual({row[1].split(".")[0] for row in rows}, {node})
                    channels = {plug: (kind, locked) for kind, plug, _, locked in rows}
                    self.assertEqual(channels[node + ".translateX"], (expected, False))
                    self.assertEqual(channels[node + ".scaleZ"], ("Static", True))

    def test_copy_preview_matches_clip(self):
        """静的・範囲外・ロックを含むシーンで、プレビューを実際のコピーと比較する。"""
        cmds.file(new=True, force=True)
        node = cmds.createNode("transform", name="clipCtrl")
        cmds.setKeyframe(node, at="tx", time=1, value=7)
        cmds.setKeyframe(node, at="ty", time=10, value=8)
        mesh = cmds.polyCube()[0]
        deformer = cmds.cluster(mesh + ".vtx[0]")[0]
        cmds.connectAttr(deformer + ".envelope", node + ".scaleY")
        cmds.setAttr(node + ".sz", lock=True)
        cmds.select(node)
        animCopy.copyAnimation(timeRange=(10, 10))
        before = animCopy._clipboard.copy()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "clip.ma")
            cmds.file(rename=path)
            cmds.file(save=True, type="mayaAscii")
            for reopen in (False, True):
                if reopen:
                    cmds.file(path, open=True, force=True)
                    cmds.select(node)
                rows = {plug: (kind, count) for plug, kind, count in animCopy.previewCopy((1, 5))}
                self.assertEqual(rows["|clipCtrl.translateX"], ("Time keys", 1))
                self.assertEqual(rows["|clipCtrl.translateY"], ("Time keys", 0))
                self.assertEqual(rows["|clipCtrl.scaleX"], ("Static", 0))
                self.assertEqual(rows["|clipCtrl.scaleY"], ("Deformer", 0))
                self.assertEqual(rows["|clipCtrl.scaleZ"], ("Static [locked]", 0))
                self.assertEqual(animCopy._clipboard, before)
            self.assertEqual(animCopy.copyAnimation(timeRange=(1, 5)), 1)
            self.assertEqual(set(animCopy._clipboard["data"][node]), {"translateX"})
            cmds.file(new=True, force=True)

    def test_mixed_clip_export(self):
        """保存再読込の前後で静的値とキーの出力、ロックの除外とUndo履歴を照合する。"""
        cmds.file(new=True, force=True)
        with tempfile.TemporaryDirectory() as folder:
            self.addCleanup(cmds.file, new=True, force=True)
            node = cmds.createNode("transform", name="exportCtrl")
            cmds.setKeyframe(node, at="tx", time=3, value=7, outTangentType="step")
            cmds.setAttr(node + ".ty", 2.5)
            cmds.setAttr(node + ".sx", lock=True)
            scene = str(Path(folder) / "export.ma")
            cmds.file(rename=scene)
            cmds.file(save=True, type="mayaAscii")
            for reopen in (False, True):
                if reopen:
                    cmds.file(scene, open=True, force=True)
                cmds.select(node)
                before = cmds.undoInfo(query=True, undoName=True)
                clip, excluded = animCopy.previewClipExport()
                path = Path(folder) / "clip.json"
                animCopy.writeClip(path, clip)
                saved = json.loads(path.read_text(encoding="utf-8"))
                channels = saved["channels"]
                self.assertEqual(channels, clip["channels"])
                self.assertEqual(channels["|exportCtrl.translateX"]["curve"]["keys"][0][:2], [3, 7])
                self.assertEqual(channels["|exportCtrl.translateY"]["value"], 2.5)
                self.assertNotIn("|exportCtrl.scaleX", channels)
                self.assertEqual(excluded["|exportCtrl.scaleX"], "Static [locked]")
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), before)

    def test_shot_export_range(self):
        """別の名前空間にある同名チャンネルの境界キーと時間単位を書き出す。"""
        cmds.file(new=True, force=True)
        self.addCleanup(cmds.file, new=True, force=True)
        self.assertFalse(animCopy.previewClipExport((1, 25))[0]["channels"])
        nodes = []
        for namespace, offset in (("actorA", 0), ("actorB", 10)):
            cmds.namespace(add=namespace)
            node = cmds.createNode("transform", name=namespace + ":ctrl")
            nodes.append(node)
            for frame, value in ((0, 8), (1, 0), (13, 2), (25, 0), (26, 8)):
                cmds.setKeyframe(node, at="tx", time=frame, value=value + offset)
        cmds.select(nodes)
        with tempfile.TemporaryDirectory() as folder:
            scene = str(Path(folder) / "shot.ma")
            cmds.file(rename=scene)
            cmds.file(save=True, type="mayaAscii")
            for reopen in (False, True):
                if reopen:
                    cmds.file(scene, open=True, force=True)
                    cmds.select(nodes)
                clip, _ = animCopy.previewClipExport((1, 25))
                path = Path(folder) / "shot.json"
                animCopy.writeClip(path, clip)
                saved = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(saved["range"], [1, 25])
                self.assertEqual(saved["units"]["time"], cmds.currentUnit(q=True, time=True))
                for node, offset in zip(nodes, (0, 10)):
                    entries = saved["channels"]["|" + node + ".translateX"]["curve"]["keys"]
                    self.assertEqual([entry[:2] for entry in entries], [[1, offset], [13, 2 + offset], [25, offset]])

    def test_named_paste_between_references(self):
        """同じリグの2参照で、指定した名前空間の同名チャンネルだけを更新する。"""
        cmds.file(new=True, force=True)
        with tempfile.TemporaryDirectory() as folder:
            self.addCleanup(cmds.file, new=True, force=True)
            rig = str(Path(folder) / "rig.ma")
            cmds.createNode("transform", name="ctrl")
            cmds.file(rename=rig)
            cmds.file(save=True, type="mayaAscii")
            cmds.file(new=True, force=True)
            for namespace in ("first", "second"):
                cmds.file(rig, reference=True, namespace=namespace)
            cmds.setKeyframe("first:ctrl.tx", time=5, value=11)
            cmds.select("first:ctrl")
            self.assertEqual(animCopy.copyAnimation(), 1)
            self.assertEqual(animCopy.pasteAnimation(mode="name", namespace="missing"), 0)
            self.assertEqual(animCopy.pasteAnimation(mode="name", namespace="second"), 1)
            cmds.undo()
            self.assertFalse(cmds.keyframe("second:ctrl.tx", query=True, timeChange=True))
            self.assertEqual(cmds.keyframe("first:ctrl.tx", query=True, valueChange=True), [11])
            cmds.redo()
            shot = str(Path(folder) / "shot.ma")
            cmds.file(rename=shot)
            cmds.file(save=True, type="mayaAscii")
            cmds.file(shot, open=True, force=True)
            self.assertEqual(cmds.keyframe("second:ctrl.tx", query=True, valueChange=True), [11])
            cmds.file(new=True, force=True)
