"""Anim Bar の処理(animBar.core)を mayapy で確かめる。

各テストは新しいシーンで、キーを打った簡単なコントロールを作り、操作の結果を cmds で読んで確かめる。
"""

import json
import os
import tempfile
import unittest

import maya.cmds as cmds

import mlib
from mlib.common import Time

from animBar.core import (animCopy, crashRecovery, keyTransform, mirror, selectSets, spaceTools,
                          tangents, timeline, timing, tween)


def _keyed(name, keysByAttribute):
    """transformを作り、アトリビュートごとに (時刻, 値) のキーを打つ。"""
    node = cmds.createNode("transform", name=name, skipSelect=True)
    for attribute, pairs in keysByAttribute.items():
        for time, value in pairs:
            cmds.setKeyframe(node, attribute=attribute, time=time, value=value)
    return node


def _values(node, attribute):
    """キーの (時刻, 値) を返す。"""
    times = cmds.keyframe(node + "." + attribute, query=True, timeChange=True) or []
    values = cmds.keyframe(node + "." + attribute, query=True, valueChange=True) or []
    return list(zip(times, values))


class _Case(unittest.TestCase):
    """新しいシーンと単位をそろえる。"""

    def assert_values(self, actual, expected):
        """数値の列が成分ごとに近いことを確かめる。"""
        self.assertEqual(len(actual), len(expected))
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=6)

    def setUp(self):
        """新しいシーンにしてcm・度・filmにする。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True, infinity=True)
        Time.setPlaybackRange(1, 20)


class TweenTest(_Case):
    """前後のキーの間の値。"""

    def test_tween_at_current_time_and_selected_keys(self):
        """現在時刻にキーを作って中間の値にし、選んだキーにも効き、1回のUndoで戻る。"""
        node = _keyed("ctrl", {"tx": [(1, 0), (11, 10)], "ry": [(1, 0), (11, 90)]})
        cmds.select(node)
        Time.setCurrent(6)
        cmds.flushUndo()
        self.assertEqual(tween.tween(0.5), 2)
        self.assertEqual(_values(node, "tx"), [(1, 0), (6, 5), (11, 10)])
        self.assertAlmostEqual(dict(_values(node, "ry"))[6], 45)
        tween.tween(1.2)
        self.assertAlmostEqual(dict(_values(node, "tx"))[6], 12)
        cmds.undo()
        self.assertAlmostEqual(dict(_values(node, "tx"))[6], 5)
        tween.copyNeighborKey(-1)
        self.assertAlmostEqual(dict(_values(node, "tx"))[6], 0)
        cmds.selectKey(node + ".tx", time=(6, 6))
        tween.tween(0.25)
        self.assertAlmostEqual(dict(_values(node, "tx"))[6], 2.5)
        self.assertAlmostEqual(dict(_values(node, "ry"))[6], 0)

    def test_no_neighbor_keys_does_nothing(self):
        """前後どちらかのキーが無ければ変えない。"""
        node = _keyed("ctrl", {"tx": [(5, 3)]})
        cmds.select(node)
        Time.setCurrent(10)
        self.assertEqual(tween.tween(0.5), 0)
        self.assertEqual(_values(node, "tx"), [(5, 3)])


class KeyTransformTest(_Case):
    """スライダーの各モード。"""

    def setUp(self):
        """3つのキーのカーブを作り、真ん中を選ぶ。"""
        super().setUp()
        self.node = _keyed("L_arm_ctrl", {"tx": [(1, 0), (5, 4), (9, 10)]})
        cmds.selectKey(self.node + ".tx", time=(5, 5))

    def middle(self):
        """真ん中のキーの値。"""
        return dict(_values(self.node, "tx"))[5]

    def test_modes(self):
        """各モードの量に応じた値と、ドラッグの間は開始時の値を基準にすること。"""
        session = keyTransform.KeySession("blendToNeighbors")
        session.apply(0.5)
        self.assertAlmostEqual(self.middle(), 7)
        session.apply(-0.5)
        self.assertAlmostEqual(self.middle(), 2)
        session.apply(0)
        self.assertAlmostEqual(self.middle(), 4)
        keyTransform.applyKeyTransform("blendToDefault", 1)
        self.assertAlmostEqual(self.middle(), 0)
        cmds.undo()
        keyTransform.applyKeyTransform("pushPull", 1)
        # 直線上(1→9で0→10)の5フレームは5。4から1だけ離れているので、量1で3になる。
        self.assertAlmostEqual(self.middle(), 3)
        cmds.undo()
        keyTransform.setBlendFrame("right", 9)
        keyTransform.applyKeyTransform("blendToFrame", 1)
        self.assertAlmostEqual(self.middle(), 10)
        cmds.undo()
        other = _keyed("R_arm_ctrl", {"tx": [(1, 0), (5, -6), (9, 0)]})
        keyTransform.applyKeyTransform("blendToMirror", 1)
        self.assertAlmostEqual(self.middle(), 6)
        cmds.undo()
        before = self.middle()
        keyTransform.applyKeyTransform("noise", 1, seed=3)
        self.assertNotAlmostEqual(self.middle(), before)
        self.assertTrue(cmds.objExists(other))

    def test_ease_and_nudge(self):
        """easeInOutは両端を保ち、nudgeValueは一定量を足す。"""
        node = _keyed("ease", {"tx": [(1, 0), (2, 2), (3, 4), (4, 6), (5, 8)]})
        cmds.selectKey(node + ".tx", time=(1, 5))
        keyTransform.applyKeyTransform("easeInOut", 1)
        values = [value for _, value in _values(node, "tx")]
        self.assertAlmostEqual(values[0], 0)
        self.assertAlmostEqual(values[-1], 8)
        self.assertLess(values[1], 2)
        keyTransform.nudgeValue(1.5)
        self.assertAlmostEqual(_values(node, "tx")[-1][1], 9.5)


class TangentTimingTest(_Case):
    """接線・キーの時間・リセット・全体への反映。"""

    def test_tangents(self):
        """Mayaの接線型とflow・bounce。"""
        node = _keyed("ctrl", {"tx": [(1, 0), (5, 10), (9, 0), (13, 5)]})
        cmds.selectKey(node + ".tx", time=(1, 13))
        tangents.setTangent("linear")
        self.assertEqual(set(cmds.keyTangent(node + ".tx", query=True, outTangentType=True)), {"linear"})
        tangents.setTangent("step")
        self.assertEqual(set(cmds.keyTangent(node + ".tx", query=True, outTangentType=True)), {"step"})
        tangents.setTangent("bounce")
        angles = cmds.keyTangent(node + ".tx", query=True, outAngle=True)
        self.assertAlmostEqual(angles[1], 0, places=5)
        tangents.setTangent("flow")
        curve = mlib.getNode(cmds.listConnections(node + ".tx", source=True)[0])
        self.assertAlmostEqual(cmds.keyTangent(node + ".tx", query=True, index=(2, 2), outAngle=True)[0],
                               tangents.flowAngle(curve, 2), places=4)
        with self.assertRaises(ValueError):
            tangents.setTangent("wobbly")

    def test_nudge_insert_share_reset_transform_all(self):
        """キーを動かす・間を空ける・そろえる・リセット・全体への反映。"""
        a = _keyed("a", {"tx": [(1, 0), (5, 5), (9, 0)]})
        b = _keyed("b", {"ty": [(3, 1), (9, 2)]})
        cmds.selectKey(a + ".tx", time=(5, 5))
        timing.nudgeKeys(2)
        self.assertEqual([time for time, _ in _values(a, "tx")], [1, 7, 9])
        cmds.selectKey(clear=True)
        cmds.select(a, b)
        Time.setCurrent(4)
        timing.insertFrames(3)
        self.assertEqual([time for time, _ in _values(a, "tx")], [1, 10, 12])
        self.assertEqual([time for time, _ in _values(b, "ty")], [3, 12])
        with self.assertRaises(ValueError):
            timing.insertFrames(-20)
        timing.insertFrames(-3)
        self.assertEqual([time for time, _ in _values(b, "ty")], [3, 9])
        timing.shareKeys()
        self.assertEqual([time for time, _ in _values(b, "ty")], [1, 3, 7, 9])
        cmds.setAttr(a + ".rz", 30)
        timing.resetValues(attributes=["rotate"])
        self.assertEqual(cmds.getAttr(a + ".rz"), 0)
        Time.setCurrent(7)
        before = [value for _, value in _values(a, "tx")]
        cmds.setAttr(a + ".tx", cmds.getAttr(a + ".tx") + 2)
        timing.transformAll([mlib.getNode(a)])
        self.assert_values([value for _, value in _values(a, "tx")], [value + 2 for value in before])


class MirrorTest(_Case):
    """左右の対応とポーズの反転。"""

    def test_mirror_flip_and_center(self):
        """反対側へ写す・入れ替える・中心は符号だけ反転。"""
        left = cmds.createNode("transform", name="L_hand_ctrl", skipSelect=True)
        right = cmds.createNode("transform", name="R_hand_ctrl", skipSelect=True)
        center = cmds.createNode("transform", name="spine_ctrl", skipSelect=True)
        cmds.setAttr(left + ".translate", 1, 2, 3)
        cmds.setAttr(left + ".rotate", 10, 20, 30)
        mirror.mirrorPose([mlib.getNode(left)], mode="mirror")
        # 左右のコントロールは既定で translateX だけを反転する(aTools と同じ)。
        self.assert_values(cmds.getAttr(right + ".translate")[0], (-1, 2, 3))
        self.assert_values(cmds.getAttr(right + ".rotate")[0], (10, 20, 30))
        mirror.setInvertRules(side=("translateX", "rotateY", "rotateZ"))
        try:
            mirror.mirrorPose([mlib.getNode(left)], mode="mirror")
            self.assert_values(cmds.getAttr(right + ".rotate")[0], (10, -20, -30))
        finally:
            mirror.resetInvertRules()
        cmds.setAttr(right + ".tx", 5)
        mirror.mirrorPose([mlib.getNode(left)], mode="flip")
        self.assertEqual(cmds.getAttr(left + ".tx"), -5)
        self.assertEqual(cmds.getAttr(right + ".tx"), -1)
        cmds.setAttr(center + ".rotate", 5, 6, 7)
        mirror.mirrorPose([mlib.getNode(center)], mode="mirror")
        self.assert_values(cmds.getAttr(center + ".rotate")[0], (5, -6, -7))
        mlib.getNode(center).addAttr(longName=mirror.INVERT_ATTRIBUTE, dataType="string").set("rotateX")
        mirror.mirrorPose([mlib.getNode(center)], mode="mirror")
        self.assert_values(cmds.getAttr(center + ".rotate")[0], (-5, -6, -7))
        self.assertIsNone(mirror.oppositeName("pelvis"))


class SelectSetTest(_Case):
    """選択セットの作成・選択・書出し・読込み。"""

    def test_create_select_export_import(self):
        """作ったセットで選び、JSONへ書き出して読み込み直せる。"""
        a = cmds.createNode("transform", name="a", skipSelect=True)
        b = cmds.createNode("transform", name="b", skipSelect=True)
        node = selectSets.createSet("Arms", [a, b], colorIndex=3)
        self.assertEqual([item.getName() for item in selectSets.sets()], [node.getName()])
        self.assertEqual((selectSets.label(node), selectSets.color(node)), ("Arms", 3))
        cmds.select(clear=True)
        selectSets.selectSet(node)
        self.assertEqual(sorted(cmds.ls(selection=True)), ["a", "b"])
        selectSets.editSet(node, remove=[b], name="Arm", colorIndex=1)
        self.assertEqual((selectSets.label(node), selectSets.color(node)), ("Arm", 1))
        path = os.path.join(tempfile.mkdtemp(), "sets.json")
        self.assertEqual(selectSets.exportSets(path), 1)
        selectSets.deleteSet(node)
        self.assertEqual(selectSets.sets(), [])
        created = selectSets.importSets(path)
        self.assertEqual([selectSets.label(item) for item in created], ["Arm"])
        with self.assertRaises(ValueError):
            selectSets.createSet(" ", [a])


class SpaceToolsTest(_Case):
    """位置合わせ・スペース切替・仮のピボット・仮のコンストレイント。"""

    def test_align_switch_pivot_and_follow(self):
        """ワールドの位置を保つ操作をcmdsで読んで確かめる。"""
        master = _keyed("master", {"tx": [(1, 0), (10, 9)]})
        slave = cmds.createNode("transform", name="slave", skipSelect=True)
        cmds.select(slave, master)
        Time.setCurrent(10)
        spaceTools.align()
        self.assertAlmostEqual(cmds.xform(slave, query=True, worldSpace=True, translation=True)[0], 9)
        parent_a = cmds.createNode("transform", name="spaceA", skipSelect=True)
        parent_b = cmds.createNode("transform", name="spaceB", skipSelect=True)
        cmds.setAttr(parent_b + ".translate", 5, 0, 0)
        ctrl = cmds.createNode("transform", name="ctrl", skipSelect=True)
        cmds.addAttr(ctrl, longName="space", attributeType="enum", enumName="a:b", keyable=True)
        constraint = cmds.parentConstraint(parent_a, parent_b, ctrl, maintainOffset=False)[0]
        offset = cmds.createNode("transform", name="ctrlOffset", skipSelect=True)
        cmds.delete(constraint)
        cmds.parent(ctrl, offset)
        condition = cmds.createNode("condition", skipSelect=True)
        cmds.connectAttr(ctrl + ".space", condition + ".firstTerm")
        cmds.setAttr(condition + ".colorIfTrueR", 0)
        cmds.setAttr(condition + ".colorIfFalseR", 5)
        cmds.connectAttr(condition + ".outColorR", offset + ".tx")
        cmds.setAttr(ctrl + ".tx", 2)
        before = cmds.xform(ctrl, query=True, worldSpace=True, translation=True)
        spaceTools.switchSpace(mlib.getNode(ctrl), "space", 1)
        self.assertEqual(cmds.getAttr(ctrl + ".space"), 1)
        for actual, expected in zip(cmds.xform(ctrl, query=True, worldSpace=True, translation=True), before):
            self.assertAlmostEqual(actual, expected)
        pivot = spaceTools.createTempPivot([mlib.getNode(slave)], position=(0, 0, 0))
        cmds.setAttr(pivot.getFullName() + ".rz", 90)
        moved = cmds.xform(slave, query=True, worldSpace=True, translation=True)
        self.assertEqual(spaceTools.clearTempPivots(), 1)
        for actual, expected in zip(cmds.xform(slave, query=True, worldSpace=True, translation=True), moved):
            self.assertAlmostEqual(actual, expected, places=5)
        follower = cmds.createNode("transform", name="follower", skipSelect=True)
        cmds.setAttr(follower + ".ty", 3)
        Time.setCurrent(1)
        spaceTools.fakeConstraint([mlib.getNode(follower)], mlib.getNode(master), rangeMode="keys")
        Time.setCurrent(10)
        self.assertAlmostEqual(cmds.getAttr(follower + ".tx"), 9)
        self.assertAlmostEqual(cmds.getAttr(follower + ".ty"), 3)


class CopyTimelineRecoveryTest(_Case):
    """アニメーションのコピー・再生範囲・退避。"""

    def test_copy_paste_ranges_and_recovery(self):
        """貼付け・現在時刻へずらす・範囲の保存・退避と復元。"""
        source = _keyed("ns_src", {"tx": [(1, 0), (5, 10)], "rx": [(1, 0), (5, 45)]})
        target = cmds.createNode("transform", name="dst", skipSelect=True)
        animCopy.copyAnimation([mlib.getNode(source)])
        animCopy.pasteAnimation([mlib.getNode(target)])
        self.assertEqual(_values(target, "tx"), [(1, 0), (5, 10)])
        self.assertEqual(_values(target, "rx"), [(1, 0), (5, 45)])
        Time.setCurrent(11)
        animCopy.pasteAnimation([mlib.getNode(target)], inPlace=True)
        # 貼った範囲(11〜15)だけを置き換え、範囲の外のキー(1・5)は残す。
        self.assertEqual([time for time, _ in _values(target, "tx")], [1, 5, 11, 15])
        cmds.select(source)
        self.assertEqual(timeline.frameSelectedKeys(), (1.0, 5.0))
        timeline.saveRange("shot")
        Time.setPlaybackRange(1, 100)
        self.assertEqual(timeline.useRange("shot"), (1.0, 5.0))
        timeline.removeRange("shot")
        self.assertNotIn("shot", timeline.savedRanges())
        Time.setCurrent(1)
        self.assertEqual(timeline.jumpToKey(1), 5.0)
        path = os.path.join(tempfile.mkdtemp(), "backup.json")
        self.assertGreaterEqual(crashRecovery.backup(path), 2)
        cmds.keyframe(source + ".tx", edit=True, time=(5, 5), valueChange=99)
        self.assertGreaterEqual(crashRecovery.restore(path), 1)
        self.assertEqual(dict(_values(source, "tx"))[5], 10)
        with open(path, encoding="utf-8") as handle:
            self.assertIn("ns_src.tx", json.load(handle)["curves"])
        crashRecovery.discard(path)
        self.assertFalse(crashRecovery.hasBackup(path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
