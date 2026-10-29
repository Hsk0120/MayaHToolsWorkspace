"""5.0.0 で追加・変更したアトリビュート編集の仕様テスト。

- ``setFlags/setAttrFlags(children=)``・``lock/hide/show``: コンパウンドアトリビュートの子への状態の設定。
- ``EnumPlug.set("name")``・``addAttr(defaultValue="name")``: enumのフィールド名。
- ``setMin/setMax/setSoftMin/setSoftMax``・``Transform.setLimits``: 範囲の編集(cmdsとの突き合わせ)。
- 再実行向けの ``safe=True``(``addAttr``・``connect/connectTo``・``setAlias``)。
各項目で通常経路のUndo1回、fastのUndoなし、不正入力の例外型を確かめる。
"""

import math
import sys
import unittest

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common import DrivenKey
from support.specCase import NamespaceCase


class _Case(NamespaceCase):
    PREFIX = "mlibSpecEdit_"

    def setUp(self):
        super().setUp()
        self.node = mlib.getNode(self.make("transform", "node"))
        self.other = mlib.getNode(self.make("transform", "other"))
        self.full = self.node.getFullName()

    def flags(self, attribute):
        """(keyable, channelBox, locked) をcmdsで読む。"""
        name = self.full + "." + attribute
        return (cmds.getAttr(name, keyable=True), cmds.getAttr(name, channelBox=True), cmds.getAttr(name, lock=True))


class CompoundFlagsTest(_Case):
    """children=True はコンパウンドアトリビュートの子へも状態を設定する。既定は従来どおり親だけ。"""

    def test_default_keeps_children(self):
        """既定(children=False)はMayaのsetAttrと同じく、親のkeyable・channelBoxが子へ及ばない。"""
        self.node.setAttrFlags("t", keyable=False, channelBox=False)
        self.assertEqual([self.flags(axis)[0] for axis in ("tx", "ty", "tz")], [True, True, True])
        cmds.setAttr(self.full + ".r", keyable=False)
        self.assertEqual([self.flags(axis)[0] for axis in ("rx", "ry", "rz")], [True, True, True])

    def test_children_flag_matrix(self):
        """keyable・channelBox・lockの各組み合わせを、子の状態をcmdsで突き合わせて確かめる。"""
        cases = (
            ({"keyable": False, "channelBox": False}, (False, False, False)),
            ({"keyable": False, "channelBox": True}, (False, True, False)),
            ({"keyable": True}, (True, False, False)),
            ({"locked": True}, (True, False, True)),
        )
        for fast in (False, True):
            for kwargs, expected in cases:
                with self.subTest(fast=fast, flags=kwargs):
                    cmds.setAttr(self.full + ".s", lock=False)
                    for axis in ("sx", "sy", "sz"):
                        cmds.setAttr(self.full + "." + axis, lock=False, keyable=True, channelBox=False)
                    self.node.getPlug("s").setFlags(children=True, fast=fast, **kwargs)
                    for axis in ("sx", "sy", "sz"):
                        self.assertEqual(self.flags(axis), expected)

    def test_set_attr_flags_children_undo_once(self):
        """Node.setAttrFlags(children=True) は全子の変更を1回のUndoで戻す。fastはUndoに積まない。"""
        self.flushUndo()
        self.node.setAttrFlags(["t", "r"], keyable=False, channelBox=False, children=True)
        names = ("tx", "ty", "tz", "rx", "ry", "rz")
        self.assertUndoesInOneStep(
            lambda: self.assertTrue(all(self.flags(name)[0] for name in names)),
            lambda: self.assertFalse(any(self.flags(name)[0] or self.flags(name)[1] for name in names)))
        self.flushUndo()
        self.node.setAttrFlags("t", keyable=False, children=True, fast=True)
        self.assertUndoEmpty()
        self.assertFalse(self.flags("tx")[0])

    def test_children_type_error(self):
        """childrenがbool以外ならTypeError(変更しない)。"""
        with self.assertRaises(TypeError):
            self.node.getPlug("t").setFlags(keyable=False, children=1)
        with self.assertRaises(TypeError):
            self.node.setAttrFlags("t", keyable=False, children="yes")
        self.assertTrue(self.flags("t")[0] or self.flags("tx")[0])

    def test_lock_hide_show(self):
        """lockは自身をロックし、hide/showは子へ広げる。各1回のUndoで戻る。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                plug = self.node.getPlug("sx")
                self.assertIs(plug.lock(fast=fast), plug)
                self.assertTrue(plug.isLocked())
                self.assertEqual([p.getFullName() for p in plug.unlock(fast=fast)], [plug.getFullName()])
                rotate = self.node.getPlug("r")
                self.assertIs(rotate.hide(fast=fast), rotate)
                self.assertEqual([self.flags(axis)[:2] for axis in ("rx", "ry", "rz")], [(False, False)] * 3)
                rotate.show(keyable=False, fast=fast)
                self.assertEqual([self.flags(axis)[:2] for axis in ("rx", "ry", "rz")], [(False, True)] * 3)
                rotate.show(fast=fast)
                self.assertEqual([self.flags(axis)[:2] for axis in ("rx", "ry", "rz")], [(True, False)] * 3)
        self.flushUndo()
        self.node.getPlug("t").hide()
        self.assertUndoesInOneStep(lambda: self.assertTrue(self.flags("ty")[0]),
                                   lambda: self.assertFalse(self.flags("ty")[0]))
        with self.assertRaises(TypeError):
            self.node.getPlug("t").show(keyable=None)


class EnumNameTest(_Case):
    """EnumPlug.set はフィールド名も受け付ける。"""

    def setUp(self):
        super().setUp()
        self.enum = self.node.addAttr("mode", "enum", enumName="body:head=3:tail")

    def test_set_by_name_matches_cmds(self):
        """名前で設定した値は、同じ名前のcmdsのenum値と一致する(通常・fast)。整数も従来どおり。"""
        for fast in (False, True):
            for name, value in (("head", 3), ("tail", 4), ("body", 0)):
                with self.subTest(fast=fast, name=name):
                    self.assertIs(self.enum.set(name, fast=fast), self.enum)
                    self.assertEqual(cmds.getAttr(self.full + ".mode"), value)
                    self.assertEqual(cmds.getAttr(self.full + ".mode", asString=True), name)
            self.enum.set(3, fast=fast)
            self.assertEqual(self.enum.get(), 3)

    def test_undo_and_fast(self):
        """通常は1回のUndoで戻り、fastはUndoに積まない。"""
        self.flushUndo()
        self.enum.set("tail")
        self.assertUndoesInOneStep(lambda: self.assertEqual(self.enum.get(), 0),
                                   lambda: self.assertEqual(self.enum.get(), 4))
        self.flushUndo()
        self.enum.set("head", fast=True)
        self.assertUndoEmpty()
        self.assertEqual(self.enum.get(), 3)

    def test_unknown_name(self):
        """大文字・小文字の違う名前・無い名前はValueError(有効な名前を文言に含む)。safeは失敗数1。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaises(ValueError) as caught:
                    self.enum.set("Head", fast=fast)
                self.assertIn("'body', 'head', 'tail'", str(caught.exception))
                self.assertEqual(self.enum.set("nope", safe=True, fast=fast), 1)
                self.assertEqual(self.enum.set("head", safe=True, fast=fast), 0)
        with self.assertRaises(ValueError):
            self.enum.getEnumValue("missing")

    def test_add_attr_default_by_name(self):
        """addAttr(defaultValue="名前") はenumNameから値を求める(通常・fast)。無い名前はValueErrorで追加しない。"""
        for fast in (False, True):
            name = "fastMode" if fast else "slowMode"
            plug = self.node.addAttr(name, "enum", enumName="a=2:b:c=7", defaultValue="b", fast=fast)
            self.assertEqual(plug.getDefault(), 3)
            self.assertEqual(plug.get(), 3)
            with self.assertRaises(ValueError):
                self.node.addAttr(name + "Bad", "enum", enumName="a:b", defaultValue="z", fast=fast)
            self.assertFalse(self.node.hasAttr(name + "Bad"))


class RangeEditTest(_Case):
    """setMin等は動的アトリビュートの定義をcmds.addAttr(edit=True)で編集する。"""

    def test_double_matches_cmds(self):
        """数値の範囲はcmds.attributeQueryと一致し、setMin/setMax(None)で外れる。"""
        plug = self.node.addAttr("amount", "double")
        node = self.full

        def query(**flags):
            return cmds.attributeQuery("amount", node=node, **flags)
        plug.setMin(-1.5).setMax(4.0).setSoftMin(0.0).setSoftMax(2.0)
        self.assertEqual((query(minimum=True), query(maximum=True), query(softMin=True), query(softMax=True)),
                         ([-1.5], [4.0], [0.0], [2.0]))
        self.assertEqual((plug.getMin(), plug.getMax(), plug.getSoftMin(), plug.getSoftMax()), (-1.5, 4.0, 0.0, 2.0))
        plug.setMin(None)
        self.assertFalse(query(minExists=True))
        self.assertFalse(plug.hasMin())
        self.assertTrue(plug.hasMax())
        plug.setMax(None)
        self.assertFalse(query(maxExists=True))
        for call in (plug.setSoftMin, plug.setSoftMax):
            with self.subTest(call=call):
                with self.assertRaises(NotImplementedError):
                    call(None)
        self.assertEqual((plug.getSoftMin(), plug.getSoftMax()), (0.0, 2.0))

    def test_angle_units(self):
        """角度は既定で度、unit="rad"はラジアン、MAngleはそのまま。getMinと往復する。"""
        plug = self.node.addAttr("bend", "doubleAngle")
        plug.setMin(-45).setMax(math.pi, unit="rad").setSoftMax(om2.MAngle(30, om2.MAngle.kDegrees))
        self.assertAlmostEqual(plug.getMin(unit="deg"), -45.0)
        self.assertAlmostEqual(plug.getMax(unit="deg"), 180.0)
        self.assertAlmostEqual(plug.getSoftMax(unit="deg"), 30.0)
        self.assertAlmostEqual(cmds.addAttr(self.full + ".bend", query=True, minValue=True), math.radians(-45))

    def test_undo_once(self):
        """1回のUndoで元の範囲へ戻る。"""
        plug = self.node.addAttr("amount", "double", minValue=0.0)
        self.flushUndo()
        plug.setMin(5.0)
        self.assertUndoesInOneStep(lambda: self.assertEqual(plug.getMin(), 0.0),
                                   lambda: self.assertEqual(plug.getMin(), 5.0))

    def test_errors(self):
        """静的アトリビュート・数値以外の型・不正な値・単位はTypeError/ValueError。"""
        text = self.node.addAttr("label", "string")
        amount = self.node.addAttr("amount", "double")
        for call, error in ((lambda: self.node.getPlug("tx").setMin(0), TypeError),
                            (lambda: text.setMax(1), TypeError),
                            (lambda: amount.setMin("1"), TypeError),
                            (lambda: amount.setMin(True), TypeError),
                            (lambda: amount.setSoftMin(1, unit=3), TypeError),
                            (lambda: amount.setSoftMin(1, unit="turn"), ValueError)):
            with self.subTest(call=call):
                with self.assertRaises(error):
                    call()
        self.assertFalse(amount.hasMin())


class TransformLimitsTest(_Case):
    """Transform.setLimitsはcmds.transformLimitsの入口。"""

    def query(self, flag):
        return cmds.transformLimits(self.full, query=True, **{flag: True})

    def test_limits_match_cmds(self):
        """値・片側の無効化・全体の無効化をcmds.transformLimitsの照会と突き合わせる。"""
        self.assertIs(self.node.setLimits(translateX=(-1, 2), rotateZ=(-45, 90), scaleY=(None, 3)), self.node)
        self.assertSequenceAlmostEqual(self.query("translationX"), (-1, 2))
        self.assertEqual(self.query("enableTranslationX"), [True, True])
        self.assertSequenceAlmostEqual(self.query("rotationZ"), (-45, 90))
        self.assertAlmostEqual(cmds.getAttr(self.full + ".minRotZLimit"), -45.0)
        self.assertEqual(self.query("enableScaleY"), [False, True])
        self.assertAlmostEqual(self.query("scaleY")[1], 3.0)
        self.node.setLimits(rotateZ=None)
        self.assertEqual(self.query("enableRotationZ"), [False, False])
        self.assertSequenceAlmostEqual(self.query("rotationZ"), (-45, 90))
        self.node.setLimits(rotateX=(0, math.pi / 2), unit="rad")
        self.assertSequenceAlmostEqual(self.query("rotationX"), (0, 90))

    def test_ui_units(self):
        """距離はcm・角度は度で受け取り、MayaのUI単位へ換算する。片側Noneでも値を保つ。"""
        cmds.currentUnit(linear="m", angle="rad")
        self.node.setLimits(translateY=(-50, 250), rotateY=(0, 90))
        self.assertAlmostEqual(cmds.getAttr(self.full + ".maxTransYLimit"), 2.5)
        self.assertAlmostEqual(cmds.getAttr(self.full + ".maxRotYLimit"), math.pi / 2)
        # transformLimitsの照会は移動だけcm、回転はUI単位で返る。
        self.assertSequenceAlmostEqual(self.query("translationY"), (-50, 250))
        self.assertSequenceAlmostEqual(self.query("rotationY"), (0, math.pi / 2))
        self.node.setLimits(translateY=(None, 300))
        self.assertSequenceAlmostEqual(self.query("translationY"), (-50, 300))
        self.assertEqual(self.query("enableTranslationY"), [False, True])

    def test_undo_once(self):
        self.flushUndo()
        self.node.setLimits(translateX=(0, 1), rotateY=(-10, 10))
        self.assertUndoesInOneStep(
            lambda: self.assertEqual(self.query("enableRotationY"), [False, False]),
            lambda: self.assertEqual(self.query("enableRotationY"), [True, True]))

    def test_errors(self):
        """未対応のチャンネル名・値の形・要素の型はTypeErrorで、何も変更しない。"""
        for kwargs in ({"tx": (0, 1)}, {"translateX": 1}, {"translateX": (0, 1, 2)}, {"translateX": "ab"},
                       {"translateX": (True, 1)}, {"translateX": ("0", 1)}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(TypeError):
                    self.node.setLimits(**kwargs)
        with self.assertRaises(ValueError):
            self.node.setLimits(rotateX=(0, 1), unit="turn")
        self.assertEqual(self.query("enableTranslationX"), [False, False])


class RerunSafeTest(_Case):
    """safe=True は既に目的の状態なら何も変更せず、成功時と同じ値を返す。"""

    def test_add_attr_safe(self):
        """既存のアトリビュートを返し、既定値・範囲を変えない。Undoに積まない。fast・getPlug=Falseも同じ。"""
        first = self.node.addAttr("amount", "double", defaultValue=1.0, minValue=0.0)
        first.set(5.0)
        self.flushUndo()
        for fast in (False, True):
            again = self.node.addAttr("amount", "double", defaultValue=2.0, minValue=3.0, safe=True, fast=fast)
            self.assertEqual(again, first)
            self.assertEqual((again.get(), again.getDefault(), again.getMin()), (5.0, 1.0, 0.0))
            self.assertIsNone(self.node.addAttr("amount", "double", getPlug=False, safe=True, fast=fast))
        self.assertUndoEmpty()
        created = self.node.addAttr("fresh", "double", safe=True)
        self.assertEqual(created.getType(), "double")

    def test_add_attr_safe_type_mismatch(self):
        """型・マルチアトリビュートかどうかが違えばsafeでもTypeError。safe=Falseは従来どおりRuntimeError。"""
        self.node.addAttr("amount", "double")
        self.node.addAttr("items", "double", multi=True)
        self.node.addAttr("vec", "double3")
        self.node.addAttr("mode", "enum", enumName="a:b")
        for args, kwargs in ((("amount", "string"), {}), (("amount", "doubleAngle"), {}),
                             (("items", "double"), {}), (("amount", "double"), {"multi": True}),
                             (("vec", "float3"), {})):
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(TypeError):
                    self.node.addAttr(*args, safe=True, **kwargs)
        self.assertEqual(self.node.addAttr("vec", "double3", safe=True).getType(), "double3")
        self.assertEqual(self.node.addAttr("items", "double", multi=True, safe=True).getType(), "double")
        self.assertEqual(self.node.addAttr("mode", "enum", enumName="x:y", safe=True).getEnumNames(),
                         [("a", 0), ("b", 1)])
        with self.assertRaises(RuntimeError):
            self.node.addAttr("amount", "double")
        with self.assertRaises(TypeError):
            self.node.addAttr("amount", "double", safe=1)

    def test_connect_safe(self):
        """同じ接続があれば何もせず接続先を返す。別の入力・ロックは従来どおりRuntimeError。"""
        source, destination = self.other.getPlug("tx"), self.node.getPlug("ty")
        result = source.connectTo(destination)
        self.flushUndo()
        for fast in (False, True):
            self.assertEqual(source.connectTo(destination, safe=True, fast=fast), result)
            self.assertEqual(destination.connect(source, safe=True, fast=fast), result)
        self.assertUndoEmpty()
        with self.assertRaises(RuntimeError):
            source.connectTo(destination)
        with self.assertRaises(RuntimeError):
            source >> destination
        with self.assertRaises(RuntimeError):
            self.other.getPlug("tz").connectTo(destination, safe=True)
        locked = self.node.getPlug("tz")
        locked.setLocked(True)
        with self.assertRaises(RuntimeError):
            source.connectTo(locked, safe=True)
        fresh = self.other.getPlug("ty").connectTo(self.node.getPlug("sx"), safe=True)
        self.assertEqual(cmds.listConnections(fresh.getFullName(), source=True, plugs=True),
                         [self.other.getName() + ".translateY"])

    def test_connect_safe_through_conversion(self):
        """unitConversion経由の同じ接続もsafeでは何もしない(safe=FalseはAlready connectedのRuntimeError)。"""
        source, destination = self.other.getPlug("rx"), self.node.getPlug("tx")
        source.connectTo(destination)
        self.assertEqual(source.connectTo(destination, safe=True), destination)
        with self.assertRaisesRegex(RuntimeError, "Already connected"):
            source.connectTo(destination)
        self.assertEqual(len(cmds.ls(cmds.listConnections(destination.getFullName(), source=True) or [],
                                     type="unitConversion")), 1)

    def test_connect_safe_next_available(self):
        """nextAvailableでも、接続元が既に接続された要素があればその要素を返す。"""
        cmds.addAttr(self.full, longName="links", attributeType="message", multi=True, indexMatters=False)
        multi = self.node.getPlug("links")
        first = self.other.getPlug("message").connectTo(multi, nextAvailable=True)
        self.assertEqual(self.other.getPlug("message").connectTo(multi, nextAvailable=True, safe=True), first)
        self.assertEqual(multi.getIndices(), [first.getIndex()])

    def test_set_alias_safe(self):
        """同じ別名の再設定はsafeで何もしない。別のアトリビュートの別名はRuntimeError。"""
        plug = self.node.getPlug("ty")
        plug.setAlias("height")
        self.flushUndo()
        self.assertIs(plug.setAlias("height", safe=True), plug)
        self.assertUndoEmpty()
        with self.assertRaises(RuntimeError):
            plug.setAlias("height")
        with self.assertRaises(RuntimeError):
            self.node.getPlug("tz").setAlias("height", safe=True)
        with self.assertRaises(TypeError):
            plug.setAlias("height", safe=None)

    def test_rerun_friendly_without_safe(self):
        """safeを足さなかった操作は再実行しても失敗しない(コンストレイントの再利用・ドリブンキーの置換)。"""
        first = self.node.addConstraint(self.other, type="point")
        second = self.node.addConstraint(self.other, type="point")
        self.assertEqual(first, second)
        driver = self.node.addAttr("drive", "double")
        key = DrivenKey(driver, self.node.getPlug("sy"))
        key.setKey(1.0, 2.0)
        key.setKey(1.0, 3.0)
        curves = cmds.listConnections(self.full + ".sy", source=True, type="animCurve")
        self.assertEqual(len(curves), 1)
        self.assertEqual(oma2.MFnAnimCurve(om2.MSelectionList().add(curves[0]).getDependNode(0)).numKeys, 1)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
