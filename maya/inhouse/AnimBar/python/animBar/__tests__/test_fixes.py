"""aTools と挙動を比べて直した点を mayapy で確かめる。

キーをそろえてもカーブの形を変えない・貼付けは範囲の外のキーを残す・接線(fixed の角度とウェイト・ロック)と
インフィニティをコピーと退避で保つ・繰り返しの反転は半周期ずらす・連続して選んだキーのツイーンが平らにならない・
ツイーンで打つキーが前のキーの接線型を引き継ぐ・何も動かさない nudge は時刻を進めない・ease は時刻の比率を使う・
退避ファイルは別フォルダの同名シーンと混ざらない。
"""

import json
import os
import tempfile
import unittest

import maya.cmds as cmds

import mlib
from mlib.common import Time

from animBar.core import (animCopy, crashRecovery, keyTransform, mirror, selectSets, spaceTools, tangents,
                          timeline, timing, tween, viewTools)


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

    def setUp(self):
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True, infinity=True)
        Time.setPlaybackRange(1, 20)


class ShareKeysTest(_Case):

    def test_share_keeps_curve_shape(self):
        """足したキーは、その時刻のカーブの値のまま(現在の値で打たない)。"""
        a = _keyed("a", {"tx": [(1, 0), (7, 5)]})
        b = _keyed("b", {"ty": [(3, 1), (9, 2)]})
        cmds.keyTangent(b + ".ty", edit=True, inTangentType="linear", outTangentType="linear")
        cmds.select(a, b)
        Time.setCurrent(4)
        expected = cmds.getAttr(b + ".ty", time=7)
        timing.shareKeys()
        self.assertAlmostEqual(dict(_values(b, "ty"))[7], expected, places=5)
        self.assertAlmostEqual(cmds.getAttr(b + ".ty", time=5), 1 + 2 / 6.0, places=5)
        self.assertEqual([time for time, _ in _values(a, "tx")], [1, 3, 7, 9])


class PasteTest(_Case):

    def test_paste_keeps_outside_keys_and_handles(self):
        """範囲の外のキーを残し、fixed の角度・ウェイト・ロックとインフィニティを保つ。"""
        source = _keyed("src", {"tx": [(1, 0), (5, 10)]})
        name = source + ".tx"
        cmds.keyTangent(name, edit=True, weightedTangents=True)
        cmds.keyTangent(name, edit=True, index=(0, 0), lock=False)
        cmds.keyTangent(name, edit=True, index=(0, 0), outAngle=30, outWeight=3)
        cmds.setInfinity(name, preInfinite="cycle", postInfinite="linear")
        target = _keyed("dst", {"tx": [(20, 7), (40, 9)]})
        animCopy.copyAnimation([mlib.getNode(source)])
        animCopy.pasteAnimation([mlib.getNode(target)])
        self.assertEqual([time for time, _ in _values(target, "tx")], [1, 5, 20, 40])
        pasted = target + ".tx"
        self.assertTrue(cmds.keyTangent(pasted, query=True, weightedTangents=True)[0])
        self.assertEqual(cmds.keyTangent(pasted, query=True, index=(0, 0), outTangentType=True), ["fixed"])
        self.assertAlmostEqual(cmds.keyTangent(pasted, query=True, index=(0, 0), outAngle=True)[0], 30, places=3)
        self.assertAlmostEqual(cmds.keyTangent(pasted, query=True, index=(0, 0), outWeight=True)[0], 3, places=3)
        self.assertFalse(cmds.keyTangent(pasted, query=True, index=(0, 0), lock=True)[0])
        self.assertEqual(cmds.setInfinity(pasted, query=True, preInfinite=True), ["cycle"])
        self.assertEqual(cmds.setInfinity(pasted, query=True, postInfinite=True), ["linear"])

    def test_paste_creates_curve_and_undoes_once(self):
        """キーの無いアトリビュートにも貼れ、全体が1回の Undo で戻る。"""
        source = _keyed("src", {"tx": [(1, 0), (5, 10)], "rx": [(1, 0), (5, 45)]})
        target = cmds.createNode("transform", name="dst", skipSelect=True)
        animCopy.copyAnimation([mlib.getNode(source)])
        cmds.flushUndo()
        animCopy.pasteAnimation([mlib.getNode(target)])
        self.assertEqual(_values(target, "rx"), [(1, 0), (5, 45)])
        cmds.undo()
        self.assertFalse(cmds.keyframe(target + ".tx", query=True))

    def test_invert_cycle_shifts_half(self):
        """繰り返しの反転は、反対側へ値を反転し、範囲の半分だけずらして範囲を越えた分を先頭へ回す。"""
        left = _keyed("L_leg_ctrl", {"tx": [(1, 0), (5, 4), (9, 0)]})
        right = cmds.createNode("transform", name="R_leg_ctrl", skipSelect=True)
        animCopy.copyAnimation([mlib.getNode(left)])
        animCopy.pasteAnimation([mlib.getNode(left)], invertCycle=True)
        self.assertEqual(_values(right, "tx"), [(1, -4), (5, 0), (9, -4)])
        self.assertEqual(_values(left, "tx"), [(1, 0), (5, 4), (9, 0)])


class RecoveryTest(_Case):

    def test_restore_keeps_handles_and_recreates_curve(self):
        """退避と復元で fixed の角度を保ち、退避後にキーを消したアトリビュートも戻す。"""
        node = _keyed("ctrl", {"tx": [(1, 0), (5, 10)], "ty": [(1, 2), (5, 3)]})
        cmds.keyTangent(node + ".tx", edit=True, index=(1, 1), inAngle=-20)
        path = os.path.join(tempfile.mkdtemp(), "backup.json")
        crashRecovery.backup(path)
        cmds.cutKey(node + ".ty", clear=True)
        cmds.keyframe(node + ".tx", edit=True, time=(5, 5), valueChange=99)
        cmds.setKeyframe(node, attribute="tx", time=9, value=1)
        crashRecovery.restore(path)
        self.assertEqual(_values(node, "tx"), [(1, 0), (5, 10)])
        self.assertAlmostEqual(cmds.keyTangent(node + ".tx", query=True, index=(1, 1), inAngle=True)[0], -20, places=3)
        self.assertEqual(_values(node, "ty"), [(1, 2), (5, 3)])

    def test_restore_reads_old_format(self):
        """1.0.0 の退避(時刻・値・接線型の並び)も読める。"""
        node = _keyed("ctrl", {"tx": [(1, 0), (5, 10)]})
        path = os.path.join(tempfile.mkdtemp(), "old.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"time": 0, "curves": {"ctrl.tx": [[2, 1, "linear", "linear"], [4, 3, "auto", "step"]]}},
                      handle)
        self.assertEqual(crashRecovery.restore(path), 1)
        self.assertEqual(_values(node, "tx"), [(2, 1), (4, 3)])
        self.assertEqual(cmds.keyTangent(node + ".tx", query=True, index=(1, 1), outTangentType=True), ["step"])

    def test_backup_path_separates_folders(self):
        """別フォルダの同じ名前のシーンは別の退避ファイルになる。"""
        one = crashRecovery.backupPath("C:/projA/shot.ma")
        two = crashRecovery.backupPath("C:/projB/shot.ma")
        self.assertNotEqual(one, two)
        self.assertTrue(os.path.basename(one).startswith("shot_"))
        self.assertEqual(one, crashRecovery.backupPath("C:/projA/shot.ma"))


class TweenFixTest(_Case):

    def test_consecutive_selected_keys_are_not_flat(self):
        """連続して選んだキーは、前から順に直前のキーと後ろのキーの間にする。"""
        node = _keyed("ctrl", {"tx": [(1, 0), (3, 7), (5, 7), (7, 7), (9, 8)]})
        cmds.selectKey(node + ".tx", time=(3, 7))
        self.assertEqual(tween.tween(0.5), 3)
        values = [value for _, value in _values(node, "tx")]
        self.assertEqual(values, [0, 4, 6, 7, 8])

    def test_linear_from_previous_and_next_keys(self):
        """前・後ろの2キーを結ぶ直線を延ばした値にし、2キーが無ければ変えない。"""
        node = _keyed("ctrl", {"tx": [(1, 0), (3, 2), (9, 10), (11, 14)], "ty": [(1, 5)]})
        cmds.select(node)
        Time.setCurrent(6)
        self.assertEqual(tween.tweenLinear(-1), 1)
        self.assertAlmostEqual(dict(_values(node, "tx"))[6], 5)
        self.assertEqual(tween.tweenLinear(1), 1)
        self.assertAlmostEqual(dict(_values(node, "tx"))[6], 4)
        self.assertEqual(_values(node, "ty"), [(1, 5)])

    def test_new_key_follows_previous_tangent(self):
        """step のブロッキング中に打つキーは step のまま(入力側は auto)。"""
        node = _keyed("ctrl", {"tx": [(1, 0), (11, 10)]})
        cmds.keyTangent(node + ".tx", edit=True, outTangentType="step")
        cmds.select(node)
        Time.setCurrent(6)
        tween.tween(0.5)
        self.assertEqual(cmds.keyTangent(node + ".tx", query=True, index=(1, 1), outTangentType=True), ["step"])
        self.assertEqual(cmds.keyTangent(node + ".tx", query=True, index=(1, 1), inTangentType=True), ["auto"])


class NudgeEaseTest(_Case):

    def test_nudge_without_keys_keeps_time(self):
        """動かすキーが無ければ現在時刻も変えない。"""
        node = cmds.createNode("transform", name="empty", skipSelect=True)
        cmds.select(node)
        Time.setCurrent(4)
        self.assertEqual(timing.nudgeKeys(2), 0)
        self.assertEqual(Time.getCurrent(), 4)
        keyed = _keyed("ctrl", {"tx": [(4, 1), (9, 2)]})
        cmds.select(keyed)
        self.assertEqual(timing.nudgeKeys(2), 1)
        self.assertEqual(Time.getCurrent(), 6)
        self.assertEqual([time for time, _ in _values(keyed, "tx")], [6, 9])

    def test_nudge_does_not_collide(self):
        """隣のキーにぶつかる量は動かさず、端数の時刻を作らない。"""
        node = _keyed("ctrl", {"tx": [(1, 0), (5, 1), (6, 2)], "ty": [(5, 0), (9, 1)]})
        cmds.selectKey(node + ".tx", time=(5, 5))
        cmds.selectKey(node + ".ty", time=(5, 5), add=True)
        self.assertEqual(timing.nudgeKeys(2), 1)
        self.assertEqual([time for time, _ in _values(node, "tx")], [1, 5, 6])
        self.assertEqual([time for time, _ in _values(node, "ty")], [7, 9])
        cmds.selectKey(node + ".tx", time=(5, 6))
        self.assertEqual(timing.nudgeKeys(2), 2)
        self.assertEqual([time for time, _ in _values(node, "tx")], [1, 7, 8])

    def test_key_transform_creates_key_at_current_time(self):
        """現在時刻にキーが無いアニメーションは、その時刻のカーブの値でキーを足してから変える。"""
        node = _keyed("ctrl", {"tx": [(1, 2), (9, 2)]})
        still = cmds.createNode("transform", name="still", skipSelect=True)
        cmds.select(node, still)
        Time.setCurrent(5)
        self.assertEqual(keyTransform.applyKeyTransform("blendToDefault", 0.5), 1)
        self.assertEqual(_values(node, "tx"), [(1, 2), (5, 1), (9, 2)])
        self.assertFalse(cmds.keyframe(still, query=True))

    def test_reset_selected_keys(self):
        """Graph Editor で選んだキーは既定値にし、選んでいないキーは変えない。"""
        node = _keyed("ctrl", {"sx": [(1, 3), (5, 4), (9, 5)], "tx": [(1, 7)]})
        cmds.selectKey(node + ".sx", time=(5, 9))
        self.assertEqual(timing.resetValues(), 2)
        self.assertEqual(_values(node, "sx"), [(1, 3), (5, 1), (9, 1)])
        self.assertEqual(_values(node, "tx"), [(1, 7)])

    def test_jump_to_selected_keys_average(self):
        """選んだキーの平均の時刻へ移り、選んでいなければ選んだノードの最初のキーへ移る。"""
        node = _keyed("ctrl", {"tx": [(2, 0), (6, 1), (12, 2)], "ty": [(8, 0)]})
        cmds.selectKey(node + ".tx", time=(2, 6))
        cmds.selectKey(node + ".ty", time=(8, 8), add=True)
        self.assertAlmostEqual(timeline.jumpToKey(0), (2 + 6 + 8) / 3.0)
        cmds.selectKey(node + ".tx", clear=True)
        cmds.selectKey(node + ".ty", clear=True)
        cmds.select(node)
        self.assertEqual(timeline.jumpToKey(0), 2)

    def test_ease_uses_time_ratio(self):
        """キーの間隔が不均等でも、時刻の比率でイーズの曲線に沿わせる。"""
        node = _keyed("ctrl", {"tx": [(0, 0), (1, 0), (8, 0), (10, 10)]})
        cmds.selectKey(node + ".tx", time=(0, 10))
        keyTransform.applyKeyTransform("easeInOut", 1)
        values = [value for _, value in _values(node, "tx")]
        self.assertAlmostEqual(values[1], 10 * 0.1 ** 3, places=5)
        self.assertAlmostEqual(values[2], 10 * 0.8 ** 3, places=5)



class MicroTransformTest(_Case):

    def test_scales_change_and_rebaselines(self):
        """操作による変化は倍率に縮め、フレームの移動・Undo・Redo では基準を取り直す scriptJob を持つ。"""
        node = cmds.createNode("transform", name="ctrl")
        cmds.select(node)
        viewTools.setMicroFactor(0.1)
        # scriptJob は GUI でしか作れないため、ここでは縮める処理と基準の取り直しだけを確かめる
        # (scriptJob の登録は guiCheck.py が確かめる)。
        viewTools._snapshot_micro()
        cmds.setAttr(node + ".tx", 10)
        viewTools._scale_micro()
        self.assertAlmostEqual(cmds.getAttr(node + ".tx"), 1.0)
        cmds.setAttr(node + ".ty", 5)
        viewTools._snapshot_micro()
        viewTools._scale_micro()
        self.assertAlmostEqual(cmds.getAttr(node + ".ty"), 5.0)
        viewTools.setMicroTransform(False)
        self.assertFalse(viewTools.isMicroTransform())



class SpaceRangeTest(_Case):

    def test_align_range_has_no_rotation_flips(self):
        """範囲の位置合わせは、回転が180度を越えても反転しないつながったカーブになる。"""
        master = _keyed("master", {"ry": [(1, 0), (9, 360)]})
        cmds.keyTangent(master + ".ry", edit=True, inTangentType="linear", outTangentType="linear")
        slave = cmds.createNode("transform", name="slave", skipSelect=True)
        Time.setPlaybackRange(1, 9)
        spaceTools.align([mlib.getNode(slave)], mlib.getNode(master), rangeMode="range")
        values = [value for _, value in _values(slave, "ry")]
        self.assertEqual(len(values), 9)
        for before, after in zip(values, values[1:]):
            self.assertLess(abs(after - before), 90)
        for frame in (3, 7):
            self.assertAlmostEqual(abs(cmds.getAttr(slave + ".ry", time=frame) - cmds.getAttr(master + ".ry", time=frame))
                                   % 360, 0, places=3)

    def test_fake_constraint_uses_current_frame_offset(self):
        """仮のコンストレイントは、呼んだときの現在時刻の相対位置を保つ。"""
        master = _keyed("master", {"tx": [(1, 0), (9, 8)]})
        cmds.keyTangent(master + ".tx", edit=True, inTangentType="linear", outTangentType="linear")
        slave = cmds.createNode("transform", name="slave", skipSelect=True)
        cmds.setAttr(slave + ".tx", 10)
        Time.setPlaybackRange(1, 9)
        Time.setCurrent(5)
        spaceTools.fakeConstraint([mlib.getNode(slave)], mlib.getNode(master), rangeMode="range")
        # 5フレームでマスターは4、スレーブは10なので、相対は+6。
        self.assertAlmostEqual(cmds.getAttr(slave + ".tx", time=1), 6, places=4)
        self.assertAlmostEqual(cmds.getAttr(slave + ".tx", time=9), 14, places=4)



class FlowTangentTest(_Case):

    def test_flow_slope_follows_neighbors(self):
        """flow の接線の傾きは、前後のキーを結ぶ直線の傾き(UI単位の値 / フレーム)と同じになる。"""
        for unit in ("film", "ntsc"):
            cmds.currentUnit(time=unit)
            for attribute in ("tx", "ry"):
                with self.subTest(unit=unit, attribute=attribute):
                    node = _keyed("flow#", {attribute: [(1, 0), (5, 40), (9, 100)]})
                    cmds.selectKey(node + "." + attribute, time=(5, 5))
                    tangents.setTangent("flow")
                    step = 1e-3
                    slope = (cmds.getAttr(node + "." + attribute, time=5 + step) -
                             cmds.getAttr(node + "." + attribute, time=5 - step)) / (2 * step)
                    self.assertAlmostEqual(slope, 100 / 8.0, places=2)
                    cmds.selectKey(node + "." + attribute, clear=True)



class DuplicateCameraTest(_Case):

    def test_duplicate_is_independent_and_bakes_shape(self):
        """複製はコンストレイントを持たず、ロックしたチャンネルも焼き、焦点距離のアニメーションも写す。"""
        camera, shape = cmds.camera(name="shotCam")
        driver = _keyed("driver", {"tx": [(1, 0), (5, 8)]})
        cmds.parentConstraint(driver, camera)
        cmds.setKeyframe(shape, attribute="focalLength", time=1, value=35)
        cmds.setKeyframe(shape, attribute="focalLength", time=5, value=50)
        cmds.setAttr(camera + ".sx", lock=True)
        Time.setPlaybackRange(1, 5)
        copy = timeline.duplicateCamera(camera)
        name = copy.getFullName()
        self.assertFalse(cmds.listRelatives(name, type="constraint"))
        for frame in (1, 3, 5):
            self.assertAlmostEqual(cmds.getAttr(name + ".tx", time=frame),
                                   cmds.getAttr(camera + ".tx", time=frame), places=4)
        copy_shape = cmds.listRelatives(name, shapes=True, fullPath=True)[0]
        self.assertAlmostEqual(cmds.getAttr(copy_shape + ".focalLength", time=5), 50, places=4)
        cmds.delete(driver)
        self.assertAlmostEqual(cmds.getAttr(name + ".tx", time=5), 8, places=4)



class UntestedPathsTest(_Case):
    """これまでテストの無かった経路。"""

    def test_copy_time_range_and_paste_by_name(self):
        """範囲を絞ったコピーと、名前空間で探す名前での貼付け。"""
        cmds.namespace(add="charA")
        cmds.namespace(add="charB")
        source = _keyed("charA:hand_ctrl", {"tx": [(1, 0), (5, 5), (9, 9)]})
        target = cmds.createNode("transform", name="charB:hand_ctrl", skipSelect=True)
        animCopy.copyAnimation([mlib.getNode(source)], timeRange=(4, 10))
        self.assertEqual(animCopy.pasteAnimation([mlib.getNode(target)], mode="name"), 1)
        self.assertEqual(_values(target, "tx"), [(5, 5), (9, 9)])
        with self.assertRaises(ValueError):
            animCopy.pasteAnimation([mlib.getNode(target)], mode="nearest")

    def test_mirror_keys_only_animated_by_default(self):
        """key=None はアニメーションのあるアトリビュートだけにキーを打ち、ロックした先は飛ばす。"""
        left = _keyed("L_arm_ctrl", {"tx": [(1, 1)]})
        right = _keyed("R_arm_ctrl", {"tx": [(1, 0)]})
        cmds.setAttr(left + ".ty", 3)
        cmds.setAttr(right + ".tz", lock=True)
        cmds.setAttr(left + ".tz", 4)
        Time.setCurrent(1)
        cmds.setAttr(left + ".tx", 2)
        mirror.mirrorPose([mlib.getNode(left)])
        self.assertEqual(_values(right, "tx"), [(1, -2)])
        self.assertEqual(cmds.getAttr(right + ".ty"), 3)
        self.assertFalse(cmds.keyframe(right + ".ty", query=True))
        self.assertEqual(cmds.getAttr(right + ".tz"), 0)

    def test_select_sets_namespace_import(self):
        """書き出した選択セットを、別の名前空間のメンバーで読み込む。"""
        cmds.namespace(add="rig1")
        cmds.namespace(add="rig2")
        a = cmds.createNode("transform", name="rig1:hand", skipSelect=True)
        cmds.createNode("transform", name="rig2:hand", skipSelect=True)
        created = selectSets.createSet("Hands", [mlib.getNode(a)], colorIndex=2)
        path = os.path.join(tempfile.mkdtemp(), "sets.json")
        selectSets.exportSets(path)
        selectSets.deleteSet(created)
        imported = selectSets.importSets(path, namespace="rig2")
        self.assertEqual(len(imported), 1)
        selectSets.selectSet(imported[0])
        self.assertEqual(cmds.ls(selection=True), ["rig2:hand"])

    def test_motion_trails_create_and_clear(self):
        """モーショントレイルを作って目印で全部消す。"""
        node = _keyed("ctrl", {"tx": [(1, 0), (9, 8)]})
        Time.setPlaybackRange(1, 9)
        trails = viewTools.createMotionTrails([mlib.getNode(node)])
        self.assertEqual(len(trails), 1)
        self.assertGreaterEqual(viewTools.clearMotionTrails(), 1)
        self.assertFalse([name for name in cmds.ls(type="motionTrail")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
