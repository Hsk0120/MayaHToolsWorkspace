"""aTools にあって未対応だった機能を mayapy で確かめる。

アニメーションレイヤー・pairBlend を介したカーブの扱い・キー変形の scaleFrom 系のモード・接線の対象の選び方
(最初・最後・全キー)・アニメーションのミラーと反対側の選択・transformAll のトグル方式・プレイブラストの設定・
退避を戻すかの確認。
"""

import json
import os
import tempfile
import unittest

import maya.cmds as cmds

import mlib
from mlib.common import Time

from animBar.core import crashRecovery, keys, keyTransform, mirror, tangents, timeline, timing, tween


def _keyed(name, keysByAttribute):
    """transformを作り、アトリビュートごとに (時刻, 値) のキーを打つ。"""
    node = cmds.createNode("transform", name=name, skipSelect=True)
    for attribute, pairs in keysByAttribute.items():
        for time, value in pairs:
            cmds.setKeyframe(node, attribute=attribute, time=time, value=value)
    return node


def _values(curve):
    """カーブのキーの (時刻, 値) を返す。"""
    times = cmds.keyframe(curve, query=True, timeChange=True) or []
    values = cmds.keyframe(curve, query=True, valueChange=True) or []
    return list(zip(times, values))


class _Case(unittest.TestCase):
    """新しいシーンと単位をそろえる。"""

    def setUp(self):
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True, infinity=True)
        Time.setPlaybackRange(1, 20)
        mirror.resetInvertRules()


def _layered():
    """tx・rx にキーのある transform をレイヤー L1 へ入れ、L1 にもキーを打つ。"""
    node = _keyed("layered", {"tx": [(1, 0), (10, 10)], "rx": [(1, 0), (10, 90)]})
    cmds.select(node)
    cmds.animLayer("L1", addSelectedObjects=True)
    cmds.animLayer("L1", edit=True, selected=True, preferred=True)
    for time, value in ((1, 0), (5, 2), (10, 0)):
        cmds.setKeyframe(node, attribute="tx", time=time, value=value, animLayer="L1")
        cmds.setKeyframe(node, attribute="rx", time=time, value=value * 10, animLayer="L1")
    return node


class LayerTest(_Case):

    def test_layer_curve_is_found(self):
        """レイヤーを介したアトリビュートでも、選んだレイヤーのカーブとアトリビュートを探せる。"""
        node = mlib.getNode(_layered())
        plugs = [plug.getLongName() for plug in keys.animatedPlugs(node, channelBox=False)]
        self.assertIn("translateX", plugs)
        self.assertIn("rotateX", plugs)
        curve = keys.animCurveOf(node.getPlug("tx"))
        self.assertEqual(curve.getName(), cmds.animLayer("L1", query=True, findCurveForPlug="layered.tx")[0])
        self.assertTrue(keys.isEditable(node.getPlug("tx")))

    def test_driven_plug_follows_blend_nodes(self):
        """レイヤーのカーブの駆動先は、ブレンドのノードの先のアトリビュート。"""
        node = mlib.getNode(_layered())
        for name in ("tx", "rx"):
            with self.subTest(name=name):
                curve = keys.animCurveOf(node.getPlug(name))
                self.assertEqual(keys.drivenPlug(curve), node.getPlug(name))
                base = mlib.getNode(cmds.animLayer("BaseAnimation", query=True, findCurveForPlug="layered." + name)[0])
                self.assertEqual(keys.drivenPlug(base), node.getPlug(name))

    def test_tween_on_layer(self):
        """レイヤーのカーブでもツイーンでキーを打てる(前後のレイヤーのキーの間の値)。"""
        node = _layered()
        cmds.select(node)
        Time.setCurrent(3)
        curve = cmds.animLayer("L1", query=True, findCurveForPlug=node + ".tx")[0]
        before = dict(_values(curve))
        tween.tween(0.5)
        # レイヤーのキーの値(レイヤーの差分)の中間になる。
        self.assertAlmostEqual(dict(_values(curve))[3], (before[1] + before[5]) / 2.0, places=4)

    def test_pair_blend(self):
        """コンストレイントとキーを切り替える pairBlend を介したアトリビュートのカーブも探せる。"""
        node = _keyed("blended", {"tx": [(1, 0), (10, 3)]})
        target = cmds.createNode("transform", name="target", skipSelect=True)
        cmds.parentConstraint(target, node)
        self.assertTrue(cmds.ls(type="pairBlend"))
        plug = mlib.getNode(node).getPlug("tx")
        curve = keys.animCurveOf(plug)
        self.assertEqual(curve.getName(), "blended_translateX")
        self.assertEqual(keys.drivenPlug(curve), plug)
        self.assertIn("translateX", [p.getLongName() for p in keys.keyablePlugs(mlib.getNode(node), channelBox=False)])

    def test_plain_connection_is_not_editable(self):
        """アニメーション以外から入力のあるアトリビュートは対象にしない。"""
        node = cmds.createNode("transform", name="driven", skipSelect=True)
        driver = cmds.createNode("transform", name="driver", skipSelect=True)
        cmds.connectAttr(driver + ".tx", node + ".tx")
        self.assertFalse(keys.isEditable(mlib.getNode(node).getPlug("tx")))
        self.assertNotIn("translateX", [p.getLongName() for p in keys.keyablePlugs(mlib.getNode(node), False)])


class ScaleModeTest(_Case):

    def _scaled(self, mode, amount):
        node = _keyed("ctrl", {"tx": [(1, 0), (5, 4), (10, 8), (15, 2)]})
        cmds.selectKey(node + ".tx", time=(5, 10))
        keyTransform.applyKeyTransform(mode, amount)
        return [value for _, value in _values(node + ".tx")]

    def test_scale_modes(self):
        """選んだキー(4・8)の値の幅を、モードの中心から 1+量 倍にする。"""
        cases = {
            "scaleFromLeft": (1.0, [0, 8, 16, 2]),       # 中心は前のキーの 0
            "scaleFromRight": (1.0, [0, 6, 14, 2]),      # 中心は後ろのキーの 2
            "scaleFromAverage": (1.0, [0, 2, 10, 2]),    # 中心は平均の 6
            "scaleFromDefault": (-0.5, [0, 2, 4, 2]),    # 中心は既定値の 0
        }
        for mode, (amount, expected) in cases.items():
            with self.subTest(mode=mode):
                self.setUp()
                for value, wanted in zip(self._scaled(mode, amount), expected):
                    self.assertAlmostEqual(value, wanted, places=4)

    def test_modes_are_listed(self):
        """バーのモードの一覧に載る。"""
        names = [name for name, _ in keyTransform.MODES]
        for mode in keyTransform.SCALE_MODES:
            self.assertIn(mode, names)


class TangentScopeTest(_Case):

    def test_first_last_all(self):
        """最初・最後・全キーの接線だけを変える。"""
        for scope, expected in (("first", ["step", "auto", "auto"]), ("last", ["auto", "auto", "step"]),
                                ("all", ["step", "step", "step"])):
            with self.subTest(scope=scope):
                self.setUp()
                node = _keyed("ctrl", {"tx": [(1, 0), (5, 4), (10, 8)]})
                cmds.keyTangent(node + ".tx", edit=True, inTangentType="auto", outTangentType="auto")
                cmds.select(node)
                Time.setCurrent(5)
                tangents.setTangent("step", scope=scope)
                self.assertEqual(cmds.keyTangent(node + ".tx", query=True, outTangentType=True), expected)

    def test_bad_scope(self):
        """知らない選び方は ValueError。"""
        with self.assertRaises(ValueError):
            tangents.setTangent("flat", scope="middle")


class MirrorAnimationTest(_Case):

    def test_mirror_all_keys(self):
        """左の全キーを右へ写し、translateX だけ符号を反転する(右の元のキーは置き換える)。"""
        left = _keyed("L_arm", {"tx": [(1, 1), (10, 3)], "ty": [(1, 2), (10, 4)]})
        right = _keyed("R_arm", {"tx": [(4, 9)]})
        cmds.select(left)
        self.assertEqual(mirror.mirrorAnimation(), 2)
        self.assertEqual(_values(right + "_translateX"), [(1, -1), (10, -3)])
        self.assertEqual(_values(right + "_translateY"), [(1, 2), (10, 4)])
        self.assertEqual(_values(left + "_translateX"), [(1, 1), (10, 3)])

    def test_mirror_range_keeps_outside(self):
        """範囲を写すときは、先の範囲の外のキーを残す。"""
        left = _keyed("L_leg", {"ty": [(1, 1), (5, 5), (10, 10)]})
        right = _keyed("R_leg", {"ty": [(1, 0), (5, 0), (20, 7)]})
        cmds.select(left)
        mirror.mirrorAnimation(timeRange=(4, 10))
        self.assertEqual(_values(right + "_translateY"), [(1, 0), (5, 5), (10, 10), (20, 7)])

    def test_flip_and_center(self):
        """入れ替えは両側を読んでから書き、中心のものは反転するアトリビュートだけを反転する。"""
        left = _keyed("L_hand", {"ty": [(1, 1)]})
        right = _keyed("R_hand", {"ty": [(1, 2)]})
        center = _keyed("spine", {"tx": [(1, 3)], "ty": [(1, 4)]})
        cmds.select(left, center)
        mirror.mirrorAnimation(mode="flip")
        self.assertEqual(_values(left + "_translateY"), [(1, 2)])
        self.assertEqual(_values(right + "_translateY"), [(1, 1)])
        self.assertEqual(_values(center + "_translateX"), [(1, -3)])
        self.assertEqual(_values(center + "_translateY"), [(1, 4)])

    def test_select_opposite(self):
        """反対側を選ぶ・足す。中心のものは残す。"""
        left = cmds.createNode("transform", name="L_foot", skipSelect=True)
        right = cmds.createNode("transform", name="R_foot", skipSelect=True)
        center = cmds.createNode("transform", name="hips", skipSelect=True)
        cmds.select(left, center)
        mirror.selectOpposite()
        self.assertEqual(sorted(cmds.ls(selection=True)), sorted([right, center]))
        cmds.select(left)
        mirror.selectOpposite(add=True)
        self.assertEqual(sorted(cmds.ls(selection=True)), sorted([left, right]))


class TransformAllToggleTest(_Case):

    def test_without_key(self):
        """キーを打たずに値を変えたら、差を全キーへ足す。"""
        node = _keyed("ctrl", {"ty": [(1, 0), (5, 2), (10, 4)]})
        cmds.select(node)
        Time.setCurrent(5)
        self.assertEqual(timing.startTransformAll(), 1)
        cmds.setAttr(node + ".ty", 3)
        self.assertEqual(timing.finishTransformAll(), 1)
        self.assertEqual([round(value, 6) for _, value in _values(node + "_translateY")], [1, 3, 5])
        self.assertFalse(timing.isTransformAllActive())

    def test_after_auto_key(self):
        """変えた時刻に既にキーを打っていれば(自動キー)、そのキーには二重に足さない。"""
        node = _keyed("ctrl", {"ty": [(1, 0), (5, 2), (10, 4)]})
        cmds.select(node)
        Time.setCurrent(5)
        timing.startTransformAll()
        cmds.setKeyframe(node, attribute="ty", time=5, value=3)
        timing.finishTransformAll()
        self.assertEqual([round(value, 6) for _, value in _values(node + "_translateY")], [1, 3, 5])

    def test_new_key_between(self):
        """キーの無い時刻で打った(自動キーで増えた)キーにも二重に足さない。"""
        node = _keyed("ctrl", {"ty": [(1, 0), (9, 4)]})
        cmds.keyTangent(node + ".ty", edit=True, inTangentType="linear", outTangentType="linear")
        cmds.select(node)
        Time.setCurrent(5)
        timing.startTransformAll()
        cmds.setKeyframe(node, attribute="ty", time=5, value=3)
        timing.finishTransformAll()
        self.assertEqual([round(value, 6) for _, value in _values(node + "_translateY")], [1, 3, 5])

    def test_other_frame_and_cancel(self):
        """始めた時刻と違えば ValueError で何も変えず、やめれば何もしない。"""
        node = _keyed("ctrl", {"ty": [(1, 0), (5, 2)]})
        cmds.select(node)
        Time.setCurrent(5)
        timing.startTransformAll()
        Time.setCurrent(1)
        with self.assertRaises(ValueError):
            timing.finishTransformAll()
        self.assertTrue(timing.isTransformAllActive())
        timing.cancelTransformAll()
        with self.assertRaises(RuntimeError):
            timing.finishTransformAll()
        self.assertEqual([value for _, value in _values(node + "_translateY")], [0, 2])


class RangeTargetTest(_Case):

    def test_range_targets(self):
        """範囲を渡すと、その中のキーを対象にする。"""
        node = _keyed("ctrl", {"tx": [(1, 0), (5, 1), (8, 2), (12, 3)]})
        found = keys.rangeTargets([mlib.getNode(node)], (4, 8))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].indices, [1, 2])
        self.assertIsNone(keys.timelineRange())


class PlayblastSettingsTest(_Case):

    def setUp(self):
        super().setUp()
        timeline.resetPlayblastSettings()

    def tearDown(self):
        timeline.resetPlayblastSettings()

    def test_store_and_validate(self):
        """設定を覚え、範囲外・知らない鍵は受け付けない。"""
        self.assertEqual(timeline.playblastSettings(), timeline.PLAYBLAST_DEFAULTS)
        timeline.setPlayblastSettings(sound=False, overscan=1.2, percent=50)
        settings = timeline.playblastSettings()
        self.assertEqual((settings["sound"], settings["overscan"], settings["percent"]), (False, 1.2, 50))
        with self.assertRaises(ValueError):
            timeline.setPlayblastSettings(percent=0)
        with self.assertRaises(ValueError):
            timeline.setPlayblastSettings(overscan=0.5)
        with self.assertRaises(KeyError):
            timeline.setPlayblastSettings(quality=3)
        self.assertEqual(timeline.resetPlayblastSettings(), timeline.PLAYBLAST_DEFAULTS)


class RecoveryCheckTest(_Case):

    def setUp(self):
        super().setUp()
        folder = tempfile.mkdtemp()
        self.scene = os.path.join(folder, "shot.ma").replace("\\", "/")
        self.node = _keyed("ctrl", {"tx": [(1, 0), (10, 5)]})
        cmds.file(rename=self.scene)
        cmds.file(save=True, type="mayaAscii")

    def tearDown(self):
        crashRecovery.discard()

    def test_restore_newer_backup(self):
        """シーンより新しい退避があれば聞き、答えに合わせて戻す・消す・残す。"""
        self.assertFalse(crashRecovery.isBackupNewer())
        self.assertIsNone(crashRecovery.checkOnOpen(ask=lambda path: "restore"))
        crashRecovery.backup()
        # 保存より後に書いた退避として扱えるよう、シーンの更新時刻を前へずらす。
        os.utime(self.scene, (0, 0))
        self.assertTrue(crashRecovery.isBackupNewer())
        cmds.cutKey(self.node + ".tx", time=(10, 10))
        self.assertEqual(crashRecovery.checkOnOpen(ask=lambda path: "keep"), "keep")
        self.assertEqual(len(_values(self.node + "_translateX")), 1)
        self.assertEqual(crashRecovery.checkOnOpen(ask=lambda path: "restore"), "restore")
        self.assertEqual(_values(self.node + "_translateX"), [(1, 0), (10, 5)])
        self.assertEqual(crashRecovery.checkOnOpen(ask=lambda path: "discard"), "discard")
        self.assertFalse(crashRecovery.hasBackup())

    def test_old_backup_is_ignored(self):
        """シーンを保存した後に残った古い退避は聞かない。"""
        crashRecovery.backup()
        with open(crashRecovery.backupPath(), encoding="utf-8") as handle:
            data = json.load(handle)
        data["time"] = 0
        with open(crashRecovery.backupPath(), "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        self.assertFalse(crashRecovery.isBackupNewer())

    def test_remembered_state(self):
        """有効にしたかは optionVar に残る(GUI の無いバッチでは ScriptJob を作れないため値だけ確かめる)。"""
        previous = crashRecovery.wasEnabled()
        try:
            cmds.optionVar(intValue=(crashRecovery.ENABLED_OPTION, 1))
            self.assertTrue(crashRecovery.wasEnabled())
            cmds.optionVar(intValue=(crashRecovery.ENABLED_OPTION, 0))
            self.assertFalse(crashRecovery.wasEnabled())
        finally:
            cmds.optionVar(intValue=(crashRecovery.ENABLED_OPTION, int(previous)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
