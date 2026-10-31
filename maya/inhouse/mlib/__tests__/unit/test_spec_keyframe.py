"""9.0.0 のキー操作の約束を固定する。

Keyframe/Keyframes(作成時の「カーブ + 番号」を保つ参照)、選択キーの取得(Selection.getKeyframes・
mlib.ls(selectedKeyframes=True))、AnimCurve.moveKey/scaleKey の index・time の絞り込み、replaceKeys、
removeKey の keepCurve、setKey の接線の既定(既存は保つ・新規は Maya の設定)、Plug/Node.moveKey、
Plug/Node.setKey の値の単位(get() と同じ)、getDefault の数値、getDrivenPlugs、getPlugs(writable=True)、
undoChunk の open/close を、cmds の結果と突き合わせて確かめる。
"""

import math
import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common import Keyframe, Keyframes, Selection
from mlib.decorator import undoChunk
from support.specCase import NamespaceCase


class _KeyCase(NamespaceCase):
    """translateX・rotateY にキーを打った transform を用意する。"""

    PREFIX = "mlibSpecKeyframe_"

    def setUp(self):
        super().setUp()
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))
        self.tangents = cmds.keyTangent(query=True, g=True, inTangentType=True, outTangentType=True)
        self.time = (cmds.currentUnit(query=True, time=True), cmds.currentTime(query=True))
        self.node = mlib.getNode(self.make("transform", "node"))
        self.name_ = self.node.getFullName()
        for time, value in ((1, 0.0), (5, 2.0), (10, 4.0)):
            cmds.setKeyframe(self.name_, attribute="translateX", time=time, value=value)
        cmds.setKeyframe(self.name_, attribute="rotateY", time=1, value=90.0)
        self.curve = self.node.getPlug("tx").getAnimCurve()
        selected = cmds.keyframe(query=True, selected=True, name=True)
        if selected:
            cmds.selectKey(selected, clear=True)

    def tearDown(self):
        cmds.currentUnit(linear=self.units[0], angle=self.units[1])
        cmds.keyTangent(g=True, inTangentType=self.tangents[0], outTangentType=self.tangents[1])
        cmds.currentUnit(time=self.time[0])
        cmds.currentTime(self.time[1])
        super().tearDown()

    def times(self, curve=None):
        return cmds.keyframe((curve or self.curve).getFullName(), query=True, timeChange=True) or []

    def values(self, curve=None):
        return cmds.keyframe((curve or self.curve).getFullName(), query=True, valueChange=True) or []


class KeyframeReferenceTest(_KeyCase):
    """Keyframe/Keyframes の取得・読取り・書込み。"""

    def test_read_matches_cmds(self):
        """getTime/getValue は cmds.keyframe の照会と一致し、repr・等価・ハッシュはカーブと番号で決まる。"""
        keys = self.curve.getKeyframes()
        self.assertIsInstance(keys, Keyframes)
        self.assertEqual(len(keys), 3)
        self.assertEqual([key.getTime() for key in keys], self.times())
        self.assertEqual(keys.getTimes(), self.times())
        self.assertEqual(keys.getValues(), self.values())
        key = self.curve.getKeyframe(1)
        self.assertIsInstance(key, Keyframe)
        self.assertEqual((key.getCurve(), key.getIndex()), (self.curve, 1))
        self.assertEqual(key, Keyframe(self.curve, 1))
        self.assertEqual(len({key, Keyframe(self.curve, 1), Keyframe(self.curve, 2)}), 2)
        self.assertIn(key, keys)
        self.assertIn("Keyframe(", repr(key))
        self.assertEqual(key.getTangent(), self.curve.getTangent(1))
        self.assertTrue(key.isValid())

    def test_invalid_input(self):
        """番号の範囲外は IndexError、AnimCurve 以外・Keyframe 以外は TypeError。"""
        for index in (-1, 3, True, 1.0):
            with self.subTest(index=index):
                with self.assertRaises(IndexError):
                    self.curve.getKeyframe(index)
        with self.assertRaises(IndexError):
            self.curve.getKeyframes([0, 9])
        with self.assertRaises(TypeError):
            Keyframe(self.node, 0)
        with self.assertRaises(TypeError):
            Keyframes([self.curve])

    def test_set_value_keeps_tangents_and_undoes_once(self):
        """setValue は接線型を保って値だけを変え、Undo 1 回で戻る。fast は Undo に残さない。"""
        self.curve.setTangent(1, inTangentType="linear", outTangentType="step")
        before = self.values()
        self.flushUndo()
        self.curve.getKeyframe(1).setValue(7.5)
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.values(), before),
                                   lambda: self.assertEqual(self.values(), [0.0, 7.5, 4.0]))
        tangent = self.curve.getTangent(1)
        self.assertEqual((tangent["inTangentType"], tangent["outTangentType"]), ("linear", "step"))
        self.flushUndo()
        self.curve.getKeyframe(2).setValue(1.0, fast=True)
        self.assertEqual(self.values()[2], 1.0)
        self.assertUndoEmpty()

    def test_set_value_units(self):
        """角度は度(unit="rad" でラジアン)、距離は UI 単位によらず cm。"""
        cmds.currentUnit(linear="mm")
        self.curve.getKeyframe(0).setValue(1.5)
        self.assertAlmostEqual(self.values()[0], 15.0)
        self.assertAlmostEqual(self.curve.getKeyframe(0).getValue(), 1.5)
        rotate = self.node.getPlug("ry").getAnimCurve()
        rotate.getKeyframe(0).setValue(math.pi / 2, unit="rad")
        self.assertAlmostEqual(self.values(rotate)[0], 90.0)
        self.assertAlmostEqual(rotate.getKeyframe(0).getValue(unit="rad"), math.pi / 2)

    def test_keyframes_across_curves(self):
        """複数のカーブのキーをカーブごとにまとめ、setValue・move・remove を1回の Undo にする。"""
        rotate = self.node.getPlug("ry").getAnimCurve()
        keys = Keyframes([self.curve.getKeyframe(2), rotate.getKeyframe(0), self.curve.getKeyframe(0),
                          self.curve.getKeyframe(0)])
        self.assertEqual(len(keys), 3)
        self.assertEqual(keys.getCurves(), [self.curve, rotate])
        self.assertEqual(keys.getIndices(self.curve), [0, 2])
        self.assertEqual([(curve, len(group)) for curve, group in keys.iterCurves()], [(self.curve, 2), (rotate, 1)])
        self.flushUndo()
        keys.setValue(3.0)
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.values(), [0.0, 2.0, 4.0]),
                                   lambda: self.assertEqual(self.values(), [3.0, 2.0, 3.0]))
        self.flushUndo()
        keys.move(timeOffset=0, valueOffset=1)
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.values(rotate), [90.0]),
                                   lambda: self.assertEqual(self.values(rotate), [91.0]))
        self.flushUndo()
        keys.remove()
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.times(), [1.0, 5.0, 10.0]),
                                   lambda: self.assertEqual(self.times(), [5.0]))
        # keepCurve=True(既定)なので、全キーを消した rotateY のカーブも残る。
        self.assertTrue(rotate.isValid())

    def test_move_keeps_neighbor_order(self):
        """1つのキーを動かすと隣を越えない(Maya と同じ)。まとめて動かすキー同士は一緒に動く。"""
        self.curve.getKeyframe(0).move(timeOffset=20)
        self.assertLess(self.times()[0], 5.0)
        cmds.undo()
        self.curve.getKeyframes([1, 2]).move(timeOffset=3, valueOffset=-1)
        self.assertEqual(self.times(), [1.0, 8.0, 13.0])
        self.assertEqual(self.values(), [0.0, 1.0, 3.0])

    def test_driven_key_curve(self):
        """入力が時間でないカーブ(ドリブンキー)でも、時刻は入力値を指す。"""
        driven = mlib.createNode("animCurveUL", name=self.name("driven"))
        driven.setKey(0.25, 1.0).setKey(0.75, 3.0)
        key = driven.getKeyframe(1)
        self.assertEqual(key.getTime(), 0.75)
        key.move(timeOffset=0.1)
        self.assertAlmostEqual(key.getTime(), 0.85)
        key.setValue(2.0)
        self.assertEqual(driven.getKeyValues(), [1.0, 2.0])


class KeySelectionTest(_KeyCase):
    """Graph Editor・Dope Sheet のキーの選択。"""

    def test_select_and_query(self):
        """Keyframes.select の結果を Selection.getKeyframes・mlib.ls(selectedKeyframes=True) で取れる。"""
        self.assertEqual(len(Selection.getKeyframes()), 0)
        rotate = self.node.getPlug("ry").getAnimCurve()
        self.flushUndo()
        Keyframes([self.curve.getKeyframe(0), self.curve.getKeyframe(2), rotate.getKeyframe(0)]).select()
        self.assertEqual(sorted(cmds.keyframe(self.curve.getFullName(), query=True, selected=True,
                                              indexValue=True)), [0, 2])
        selected = Selection.getKeyframes()
        self.assertEqual(len(selected), 3)
        self.assertEqual(set(selected.getCurves()), {self.curve, rotate})
        self.assertEqual(selected.getIndices(self.curve), [0, 2])
        self.assertEqual(mlib.ls(selectedKeyframes=True), selected)
        self.curve.getKeyframe(1).select(add=True)
        self.assertEqual(Selection.getKeyframes().getIndices(self.curve), [0, 1, 2])
        self.curve.getKeyframe(1).select()
        self.assertEqual(len(Selection.getKeyframes()), 1)
        cmds.undo()
        self.assertEqual(Selection.getKeyframes().getIndices(self.curve), [0, 1, 2])
        Keyframes().select()
        self.assertEqual(len(Selection.getKeyframes()), 0)

    def test_ls_rejects_mixed_arguments(self):
        """selectedKeyframes=True は他の引数と併用できず、bool 以外は TypeError。False は通常の ls。"""
        for call in (lambda: mlib.ls(self.name_, selectedKeyframes=True),
                     lambda: mlib.ls(selectedKeyframes=True, type="transform"),
                     lambda: mlib.ls(selectedKeyframes=1)):
            with self.assertRaises(TypeError):
                call()
        self.assertEqual(list(mlib.ls(self.name_, selectedKeyframes=False)), [self.node])


class AnimCurveEditTest(_KeyCase):
    """AnimCurve の moveKey・scaleKey・replaceKeys・removeKey(keepCurve)・setKey の接線の既定。"""

    def test_move_key_ranges(self):
        """index(単数・並び)・time(時刻・範囲)で絞り、省略は全キー。index と time の同時指定は TypeError。"""
        self.curve.moveKey(timeOffset=1)
        self.assertEqual(self.times(), [2.0, 6.0, 11.0])
        self.curve.moveKey(0, valueOffset=1)
        self.assertEqual(self.values(), [1.0, 2.0, 4.0])
        self.curve.moveKey([1, 2], timeOffset=2)
        self.assertEqual(self.times(), [2.0, 8.0, 13.0])
        self.curve.moveKey(time=(7, 20), timeOffset=-1, valueOffset=1)
        self.assertEqual(self.times(), [2.0, 7.0, 12.0])
        self.assertEqual(self.values(), [1.0, 3.0, 5.0])
        self.curve.moveKey(time=(100, 200), timeOffset=5)
        self.assertEqual(self.times(), [2.0, 7.0, 12.0])
        with self.assertRaises(TypeError):
            self.curve.moveKey(0, time=2, timeOffset=1)
        with self.assertRaises(IndexError):
            self.curve.moveKey(5, timeOffset=1)
        self.flushUndo()
        self.curve.moveKey(timeOffset=1, valueOffset=1)
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.times(), [2.0, 7.0, 12.0]),
                                   lambda: self.assertEqual(self.times(), [3.0, 8.0, 13.0]))

    def test_move_key_seconds_and_degrees(self):
        """timeUnit="sec" は秒、角度の valueOffset は度(unit="rad" でラジアン)。"""
        cmds.currentUnit(time="film")
        self.curve.moveKey(timeOffset=1, timeUnit="sec")
        self.assertEqual(self.times(), [25.0, 29.0, 34.0])
        rotate = self.node.getPlug("ry").getAnimCurve()
        rotate.moveKey(valueOffset=math.pi, unit="rad")
        self.assertAlmostEqual(self.values(rotate)[0], 270.0)

    def test_scale_key_ranges(self):
        """scaleKey と mirror も index・time で絞れる。"""
        self.curve.scaleKey(1, 2, valuePivot=0, index=[1, 2])
        self.assertEqual(self.values(), [0.0, 4.0, 8.0])
        self.curve.scaleKey(2, 1, inputPivot=5, time=(5, 10))
        self.assertSequenceAlmostEqual(self.times(), [1.0, 5.0, 15.0], places=5)
        self.curve.mirror(value=True, valuePivot=4, index=1)
        self.assertEqual(self.values(), [0.0, 4.0, 8.0])
        self.curve.mirror(value=True, valuePivot=0, index=0)
        self.assertEqual(self.values(), [0.0, 4.0, 8.0])
        with self.assertRaises(TypeError):
            self.curve.scaleKey(2, index=0, time=1)
        with self.assertRaises(ValueError):
            self.curve.scaleKey(0, time=(1, 5))

    def test_remove_key_keep_curve(self):
        """既定(keepCurve=True)は全キーを消してもカーブと接続が残り、False は Maya と同じく消える。"""
        name = self.curve.getFullName()
        self.flushUndo()
        self.curve.removeKey([0, 1, 2])
        self.assertTrue(cmds.objExists(name))
        self.assertEqual(self.curve.getKeyCount(), 0)
        self.assertEqual(self.node.getPlug("tx").getAnimCurve(), self.curve)
        self.assertFalse(cmds.lockNode(name, query=True, lock=True)[0])
        cmds.undo()
        self.assertEqual(self.times(), [1.0, 5.0, 10.0])
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        cmds.redo()
        self.assertEqual(self.curve.getKeyCount(), 0)
        cmds.undo()
        # すでにロックしていたカーブはロックを保つ。
        cmds.lockNode(name, lock=True)
        self.curve.removeKey(time=(0, 20))
        self.assertTrue(cmds.objExists(name))
        self.assertTrue(cmds.lockNode(name, query=True, lock=True)[0])
        cmds.undo()
        cmds.lockNode(name, lock=False)
        self.curve.removeKey(time=(0, 20), keepCurve=False)
        self.assertFalse(cmds.objExists(name))
        cmds.undo()
        self.assertTrue(cmds.objExists(name))
        with self.assertRaises(TypeError):
            self.curve.removeKey(0, keepCurve=1)

    def test_remove_key_fast(self):
        """fast は Undo に残さず、keepCurve=False で空になったカーブを削除する。"""
        free = mlib.createNode("animCurveTL", name=self.name("free"))
        free.setKey(1, 1).setKey(2, 2)
        self.flushUndo()
        free.removeKey([0, 1], fast=True)
        self.assertTrue(free.isValid())
        self.assertEqual(free.getKeyCount(), 0)
        free.setKey(1, 1, fast=True)
        free.removeKey(0, keepCurve=False, fast=True)
        self.assertFalse(free.isValid())
        self.assertUndoEmpty()

    def test_replace_keys(self):
        """replaceKeys はカーブと接続を残して全キーを置き換え、Undo 1 回で戻る。不正な要素では何も変えない。"""
        self.flushUndo()
        self.curve.replaceKeys([(2, 1.0), (4, 3.0, "linear", "step"), (4, 5.0)])
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.times(), [1.0, 5.0, 10.0]),
                                   lambda: self.assertEqual((self.times(), self.values()), ([2.0, 4.0], [1.0, 5.0])))
        cmds.redo()
        self.assertEqual(self.node.getPlug("tx").getAnimCurve(), self.curve)
        self.assertEqual(self.curve.getTangent(1)["inTangentType"], "linear")
        cmds.currentTime(3)
        self.assertAlmostEqual(cmds.getAttr(self.name_ + ".tx"), self.curve.evaluate(3))
        before = (self.times(), self.values())
        for keys in ([(1, 2, "linear")], [(1, float("nan"))], [(1, 2, "bogus", "linear")], ["ab"]):
            with self.subTest(keys=keys):
                with self.assertRaises((TypeError, ValueError)):
                    self.curve.replaceKeys(keys)
                self.assertEqual((self.times(), self.values()), before)
        self.curve.replaceKeys([])
        self.assertTrue(self.curve.isValid())
        self.assertEqual(self.curve.getKeyCount(), 0)

    def test_set_key_default_tangents(self):
        """接線型を省くと、既存のキーは接線型を保ち、新しいキーは Maya の設定(keyTangent -g)に従う。"""
        cmds.keyTangent(g=True, inTangentType="flat", outTangentType="step")
        for fast in (False, True):
            with self.subTest(fast=fast):
                curve = mlib.createNode("animCurveTL", name=self.name("tangent#"))
                curve.setKey(1, 1, fast=fast)
                tangent = curve.getTangent(0)
                self.assertEqual((tangent["inTangentType"], tangent["outTangentType"]), ("flat", "step"))
                curve.setTangent(0, inTangentType="linear", outTangentType="linear")
                curve.setKey(1, 5, fast=fast)
                tangent = curve.getTangent(0)
                self.assertEqual((tangent["inTangentType"], tangent["outTangentType"]), ("linear", "linear"))
                self.assertEqual(curve.getKeyValues(), [5.0])
                curve.setKey(2, 1, "spline", fast=fast)
                self.assertEqual(curve.getTangent(1)["inTangentType"], "spline")
                self.assertEqual(curve.getTangent(1)["outTangentType"], "step")

    def test_driven_plugs(self):
        """getDrivenPlugs は unitConversion を飛ばした出力先を返す。つながっていなければ空。"""
        self.assertEqual(self.curve.getDrivenPlugs(), [self.node.getPlug("tx")])
        rotate = self.node.getPlug("ry").getAnimCurve()
        self.assertEqual(rotate.getDrivenPlugs(), [self.node.getPlug("ry")])
        other = mlib.getNode(self.make("transform", "other"))
        cmds.connectAttr(self.curve.getFullName() + ".output", other.getFullName() + ".ty")
        self.assertEqual(set(self.curve.getDrivenPlugs()), {self.node.getPlug("tx"), other.getPlug("ty")})
        self.assertEqual(mlib.createNode("animCurveTL", name=self.name("lonely")).getDrivenPlugs(), [])


class PlugNodeKeyTest(_KeyCase):
    """Plug/Node の moveKey と setKey の値の単位。"""

    def test_plug_move_key(self):
        """Plug.moveKey は全キー(キーが1つでも)・時刻の範囲を動かし、値は get() と同じ単位。"""
        cmds.currentUnit(linear="mm")
        tx = self.node.getPlug("tx")
        self.flushUndo()
        tx.moveKey(timeOffset=2, valueOffset=1)
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.times(), [1.0, 5.0, 10.0]),
                                   lambda: self.assertEqual(self.times(), [3.0, 7.0, 12.0]))
        cmds.redo()
        self.assertEqual(self.values(), [10.0, 30.0, 50.0])
        tx.moveKey(time=(5, 20), timeOffset=-1)
        self.assertEqual(self.times(), [3.0, 6.0, 11.0])
        ry = self.node.getPlug("ry")
        ry.moveKey(timeOffset=4, valueOffset=10)
        self.assertEqual(self.times(ry.getAnimCurve()), [5.0])
        self.assertAlmostEqual(self.values(ry.getAnimCurve())[0], 100.0)
        self.node.getPlug("tz").moveKey(timeOffset=1)
        for bad in ({"timeOffset": "1"}, {"valueOffset": True}):
            with self.assertRaises(TypeError):
                tx.moveKey(**bad)
        with self.assertRaises(ValueError):
            tx.moveKey(timeOffset=float("inf"))

    def test_node_move_key(self):
        """Node.moveKey は指定した(省略はキー可能な全)アトリビュートを、1回の Undo で動かす。"""
        rotate = self.node.getPlug("ry").getAnimCurve()
        self.flushUndo()
        self.node.moveKey(timeOffset=1, valueOffset=1)
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.times(rotate), [1.0]),
                                   lambda: self.assertEqual(self.times(rotate), [2.0]))
        cmds.redo()
        self.assertEqual(self.values(), [1.0, 3.0, 5.0])
        self.assertAlmostEqual(self.values(rotate)[0], 91.0)
        self.node.moveKey(["tx"], time=(5, 20), timeOffset=1)
        self.assertEqual(self.times(), [2.0, 7.0, 12.0])
        self.assertEqual(self.times(rotate), [2.0])
        with self.assertRaises(ValueError):
            self.node.moveKey([], timeOffset=1)

    def test_node_set_key_units(self):
        """Node.setKey の value はアトリビュートごとに度・cm から換算し、uiUnits=True は UI 単位のまま。"""
        cmds.currentUnit(linear="mm")
        self.flushUndo()
        self.node.setKey(["tz", "rz"], time=3, value=2)
        self.assertUndoesInOneStep(lambda: self.assertFalse(cmds.keyframe(self.name_ + ".tz", query=True)),
                                   lambda: self.assertEqual(
                                       cmds.keyframe(self.name_ + ".tz", query=True, valueChange=True), [20.0]))
        cmds.redo()
        self.assertAlmostEqual(cmds.keyframe(self.name_ + ".rz", query=True, valueChange=True)[0], 2.0)
        self.node.setKey(["tz"], time=4, value=2, uiUnits=True)
        self.assertEqual(cmds.keyframe(self.name_ + ".tz", query=True, valueChange=True), [20.0, 2.0])
        self.node.setKey(["rz"], time=4, value=math.pi, unit="rad")
        self.assertAlmostEqual(cmds.getAttr(self.name_ + ".rz", time=4), 180.0)
        self.node.setKey(["sx"], time=6)
        self.assertEqual(cmds.keyframe(self.name_ + ".sx", query=True, timeChange=True), [6.0])
        with self.assertRaises(ValueError):
            self.node.setKey(["tz"], time=5, value=1, unit="deg", uiUnits=True)
        with self.assertRaises(TypeError):
            self.node.setKey(["tz"], time=5, value=1, uiUnits=1)

    def test_get_default_matches_get(self):
        """getDefault は get() と同じ規則の数値。"""
        cmds.currentUnit(linear="mm", angle="rad")
        plug = self.node.addAttr("lin", attributeType="doubleLinear", defaultValue=3)
        self.assertAlmostEqual(plug.getDefault(), 3.0)
        self.assertAlmostEqual(plug.getDefault(), plug.get())
        self.assertAlmostEqual(plug.getDefault(uiUnits=True), 30.0)
        self.node.getPlug("rx").set(10)
        self.node.getPlug("rx").reset()
        self.assertEqual(self.node.getPlug("rx").get(), 0.0)


class WritablePlugsTest(_KeyCase):
    """getPlugs(writable=True) は今書ける(ロック・animCurve 以外の入力が無い)ものに絞る。"""

    def test_writable_filter(self):
        node = mlib.getNode(self.make("transform", "w"))
        name = node.getFullName()
        driver = mlib.getNode(self.make("transform", "driver"))
        cmds.setAttr(name + ".ty", lock=True)
        cmds.connectAttr(driver.getFullName() + ".tx", name + ".tz")
        cmds.setKeyframe(name, attribute="rx", time=1, value=5)
        cmds.connectAttr(driver.getFullName() + ".ty", name + ".sx")
        cmds.setAttr(name + ".scale", lock=True)
        keyable = [plug.getLongName() for plug in node.getPlugs(keyable=True)]
        writable = [plug.getLongName() for plug in node.getPlugs(keyable=True, writable=True)]
        self.assertEqual(writable, [plug for plug in keyable
                                    if plug not in ("translateY", "translateZ", "scaleX", "scaleY", "scaleZ")])
        self.assertIn("rotateX", writable)
        self.assertEqual(node.getPlugs(writable=False), node.getPlugs())
        with self.assertRaises(TypeError):
            node.getPlugs(writable=1)
        user = node.addAttr("free", attributeType="double", keyable=True)
        user.setLocked(True)
        self.assertNotIn(user, node.getPlugs(userDefined=True, writable=True))


class UndoChunkOpenCloseTest(NamespaceCase):
    """undoChunk の戻り値の open/close。"""

    PREFIX = "mlibSpecUndoOpen_"

    def test_open_close_spans_one_undo(self):
        """open から close までの変更が Undo 1 回にまとまり、二重の open・開かずの close は何もしない。"""
        node = self.make("transform", "n")
        self.flushUndo()
        chunk = undoChunk("drag")
        self.assertIs(chunk.open(), chunk)
        chunk.open()
        for value in (1, 2, 3):
            cmds.setAttr(node + ".tx", value)
        chunk.close()
        chunk.close()
        self.assertUndoesInOneStep(lambda: self.assertEqual(cmds.getAttr(node + ".tx"), 0.0),
                                   lambda: self.assertEqual(cmds.getAttr(node + ".tx"), 3.0))
        chunk.open()
        cmds.setAttr(node + ".ty", 5)
        chunk.close()
        cmds.undo()
        self.assertEqual(cmds.getAttr(node + ".ty"), 0.0)
        undoChunk("never").close()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
