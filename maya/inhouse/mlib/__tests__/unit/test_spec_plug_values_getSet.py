"""Plugの型別の値の取得・設定(単位・safe・fast・setIfChanged・reset)の約束を固定する。

期待値はmaya.cmdsで独立に求めた値と比べる。
"""

import math
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib
from mlib import plugs
from mlib.maths import Matrix


class _PlugSpecCase(unittest.TestCase):
    """専用の名前空間・Undo・単位・時刻を用意し、終了時に元へ戻す。"""

    def setUp(self):
        self.namespace = ":specBValues_" + uuid.uuid4().hex
        self.before = set(cmds.ls(long=True) or [])
        cmds.namespace(add=self.namespace)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True),
                      cmds.currentUnit(query=True, time=True))
        self.time = cmds.currentTime(query=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        self.node = self.make("transform")
        self.name = self.node.getFullName()

    def tearDown(self):
        cmds.currentUnit(linear=self.units[0], angle=self.units[1], time=self.units[2])
        cmds.currentTime(self.time)
        for name in sorted(set(cmds.ls(long=True) or []) - self.before, key=len, reverse=True):
            if cmds.objExists(name):
                try:
                    cmds.lockNode(name, lock=False)
                    cmds.delete(name)
                except RuntimeError:
                    pass  # Mayaが自動で作る削除できないノードは残す。
        if cmds.namespace(exists=self.namespace):
            cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_state)

    def make(self, kind="network"):
        """Mayaコマンドで作成したノードを取得する。"""
        return mlib.getNode(cmds.createNode(kind, name=self.namespace + ":n#", skipSelect=True))

    def add(self, name, **flags):
        """cmds.addAttrでアトリビュートを追加し、そのPlugを返す。"""
        cmds.addAttr(self.name, longName=name, **flags)
        return self.node.getPlug(name)

    def assertUndoEmpty(self):
        """Undoの記録が追加されていないことを確かめる。"""
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))


class PlugTypeSelectionSpecTest(_PlugSpecCase):
    """アトリビュート定義から選ばれるラッパー型とgetType(Mayaの型名)の対応。"""

    def test_registered_types_follow_cmds_type_names(self):
        """登録型はcmds.getAttr(type=True)の型名に対応するクラスになる。"""
        cases = (
            ("bool", dict(attributeType="bool"), plugs.BoolPlug),
            ("double", dict(attributeType="double"), plugs.DoublePlug),
            ("doubleLinear", dict(attributeType="doubleLinear"), plugs.DoubleLinearPlug),
            ("doubleAngle", dict(attributeType="doubleAngle"), plugs.DoubleAnglePlug),
            ("float", dict(attributeType="float"), plugs.FloatPlug),
            ("long", dict(attributeType="long"), plugs.LongPlug),
            ("short", dict(attributeType="short"), plugs.ShortPlug),
            ("enum", dict(attributeType="enum", enumName="a:b"), plugs.EnumPlug),
            ("time", dict(attributeType="time"), plugs.TimePlug),
            ("string", dict(dataType="string"), plugs.StringPlug),
            ("matrix", dict(attributeType="matrix"), plugs.MatrixPlug),
            ("message", dict(attributeType="message"), plugs.MessagePlug),
        )
        for index, (type_name, flags, cls) in enumerate(cases):
            with self.subTest(type_name=type_name):
                plug = self.add("a%d" % index, **flags)
                self.assertIs(type(plug), cls)
                self.assertEqual(plug.getType(), type_name)
                if type_name != "message":
                    self.assertEqual(cmds.getAttr(plug.getFullName(), type=True), type_name)

    def test_unregistered_types_use_base_plug(self):
        """byte・char・型付き配列は基底Plugのままで、型名は定義から返す。"""
        for index, (type_name, flags) in enumerate((
                ("byte", dict(attributeType="byte")), ("char", dict(attributeType="char")),
                ("doubleArray", dict(dataType="doubleArray")), ("stringArray", dict(dataType="stringArray")))):
            with self.subTest(type_name=type_name):
                plug = self.add("b%d" % index, **flags)
                self.assertIs(type(plug), plugs.Plug)
                self.assertEqual(plug.getType(), type_name)

    def test_typed_matrix_and_double3_and_compound(self):
        """dataType=matrixもMatrixPlug、double3はDouble3Plug、それ以外のコンパウンドアトリビュートはCompoundPlug。"""
        self.assertIs(type(self.add("dm", dataType="matrix")), plugs.MatrixPlug)
        self.assertIs(type(self.node.getPlug("translate")), plugs.Double3Plug)
        self.assertIs(type(self.node.getPlug("boundingBox")), plugs.CompoundPlug)
        cmds.addAttr(self.name, longName="f3", attributeType="float3")
        for axis in "xyz":
            cmds.addAttr(self.name, longName="f3" + axis, attributeType="float", parent="f3")
        f3 = self.node.getPlug("f3")
        self.assertIs(type(f3), plugs.CompoundPlug)
        self.assertEqual(f3.getType(), "float3")

    def test_multi_reports_element_type_and_is_multi_plug(self):
        """マルチアトリビュート全体はMultiPlugで、getTypeは要素の型名を返す。"""
        values = self.add("values", attributeType="long", multi=True)
        self.assertIs(type(values), plugs.MultiPlug)
        self.assertEqual(values.getType(), "long")
        self.assertIs(type(values[3]), plugs.LongPlug)
        self.assertIs(type(self.node.getPlug("worldMatrix")[0]), plugs.MatrixPlug)


class PlugScalarValueSpecTest(_PlugSpecCase):
    """数値・単位付きスカラーの往復、範囲、safe・fastの違い。"""

    def test_get_returns_python_types(self):
        """getは型に応じたPythonの値を返し、cmds.getAttrと一致する。"""
        cases = (("bo", dict(attributeType="bool"), True, bool), ("lo", dict(attributeType="long"), -7, int),
                 ("sh", dict(attributeType="short"), 12, int), ("do", dict(attributeType="double"), 2.25, float),
                 ("fl", dict(attributeType="float"), 0.5, float), ("en", dict(attributeType="enum", enumName="a:b:c"), 2, int))
        for attr, flags, value, kind in cases:
            with self.subTest(attr=attr):
                plug = self.add(attr + "V", **flags)
                cmds.setAttr(plug.getFullName(), value)
                self.assertIs(type(plug.get()), kind)
                self.assertEqual(plug.get(), cmds.getAttr(plug.getFullName()))

    def test_float_keeps_single_precision(self):
        """floatは単精度で保存され、getはその値をdoubleで返す(通常・fastとも)。"""
        plug = self.add("fl", attributeType="float")
        expected = float(om2.MFloatArray([0.1])[0])
        for fast in (False, True):
            with self.subTest(fast=fast):
                plug.set(0.1, fast=fast)
                self.assertEqual(plug.get(), expected)
                self.assertNotEqual(plug.get(), 0.1)

    def test_distance_internal_and_ui_units_in_mm_and_m(self):
        """距離は内部cm。uiUnits=TrueはUI単位(mm・m)で読み書きし、fastも同じ意味。"""
        tx = self.node.getPlug("tx")
        for unit, factor in (("mm", 10.0), ("m", 0.01)):
            with self.subTest(unit=unit):
                cmds.currentUnit(linear=unit)
                tx.set(5)
                self.assertAlmostEqual(cmds.getAttr(self.name + ".tx"), 5 * factor)
                self.assertAlmostEqual(tx.get(), 5.0)
                self.assertAlmostEqual(tx.get(uiUnits=True), 5 * factor)
                tx.set(3, uiUnits=True)
                self.assertAlmostEqual(cmds.getAttr(self.name + ".tx"), 3.0)
                self.assertAlmostEqual(tx.get(), 3.0 / factor)
                tx.set(7, fast=True)
                self.assertAlmostEqual(cmds.getAttr(self.name + ".tx"), 7 * factor)
                tx.set(2, uiUnits=True, fast=True)
                self.assertAlmostEqual(tx.get(), 2.0 / factor)

    def test_angle_degrees_and_ui_units(self):
        """角度の数値は既定で度、unit="rad"でラジアン。uiUnits=TrueはUIの角度単位(deg・rad)。"""
        rx = self.node.getPlug("rx")
        rx.set(90)
        self.assertAlmostEqual(cmds.getAttr(self.name + ".rx"), 90.0)
        self.assertAlmostEqual(rx.get(uiUnits=True), 90.0)
        rx.set(math.pi / 2, unit="rad")
        self.assertAlmostEqual(cmds.getAttr(self.name + ".rx"), 90.0)
        rx.set(45, uiUnits=True)
        self.assertAlmostEqual(rx.get(), 45.0)
        self.assertAlmostEqual(rx.get(unit="rad"), math.pi / 4)
        cmds.currentUnit(angle="rad")
        rx.set(1.0, uiUnits=True)
        self.assertAlmostEqual(rx.get(unit="rad"), 1.0)
        self.assertAlmostEqual(rx.get(), math.degrees(1.0))
        self.assertAlmostEqual(cmds.getAttr(self.name + ".rx"), 1.0)

    def test_time_default_frames_and_seconds(self):
        """時間の数値は既定で現在のUI時間単位(film・ntsc)のフレーム、timeUnit="sec"で秒。"""
        ti = self.add("ti", attributeType="time")
        for frame, fps in (("film", 24), ("ntsc", 30)):
            cmds.currentUnit(time=frame)
            for fast in (False, True):
                with self.subTest(frame=frame, fast=fast):
                    cmds.setAttr(ti.getFullName(), 2 * fps)
                    self.assertAlmostEqual(ti.get(), 2.0 * fps)
                    self.assertAlmostEqual(ti.get(timeUnit="sec"), 2.0)
                    for alias in ("seconds", "second"):
                        self.assertAlmostEqual(ti.get(timeUnit=alias), 2.0)
                    self.assertAlmostEqual(ti.get(timeUnit="frames"), 2.0 * fps)
                    self.assertAlmostEqual(ti.get(uiUnits=True), 2.0 * fps)
                    ti.set(12, fast=fast)
                    self.assertAlmostEqual(cmds.getAttr(ti.getFullName()), 12.0)
                    self.assertAlmostEqual(ti.mplug().asMTime().asUnits(om2.MTime.kSeconds), 12.0 / fps)
                    ti.set(0.5, timeUnit="sec", fast=fast)
                    self.assertAlmostEqual(cmds.getAttr(ti.getFullName()), 0.5 * fps)
                    ti.set(15, uiUnits=True, fast=fast)
                    self.assertAlmostEqual(ti.get(), 15.0)
                    self.assertAlmostEqual(ti.get(timeUnit="sec"), 15.0 / fps)
                    if not fast:
                        # MTimeは自身の単位を持つため、timeUnitに関係なく換算しない(fastは数値のみ)。
                        ti.set(om2.MTime(1.0, om2.MTime.kSeconds), timeUnit="frame")
                        self.assertAlmostEqual(ti.get(), 1.0 * fps)
        self.assertAlmostEqual(mlib.getPlug("time1.outTime").get(), cmds.currentTime(query=True))

    def test_time_unit_errors(self):
        """timeUnitの型・名前の誤り、uiUnitsとの同時指定、角度とのunit取り違えを型付きの例外にする。"""
        ti = self.add("ti", attributeType="time")
        rx = self.node.getPlug("rx")
        with self.assertRaises(TypeError):
            ti.get(timeUnit=1)
        with self.assertRaises(ValueError):
            ti.get(timeUnit="minute")
        with self.assertRaises(ValueError):
            ti.get(timeUnit="sec", uiUnits=True)
        with self.assertRaisesRegex(ValueError, "timeUnit"):
            ti.get(unit="sec")
        with self.assertRaisesRegex(ValueError, "unit for angle"):
            rx.get(timeUnit="deg")
        with self.assertRaises(ValueError):
            ti.set(1, timeUnit="minute")
        self.assertEqual(ti.set(1, timeUnit="minute", safe=True), 1)
        self.assertEqual(ti.set(1, timeUnit="sec", uiUnits=True, safe=True), 1)

    def test_time_children_of_compound_and_multi(self):
        """時間の子を持つコンパウンドアトリビュートと、時間のマルチアトリビュートも子ごとに換算する。"""
        name = self.node.getFullName()
        cmds.addAttr(name, longName="span", attributeType="compound", numberOfChildren=2)
        cmds.addAttr(name, longName="spanTime", attributeType="time", parent="span")
        cmds.addAttr(name, longName="spanAngle", attributeType="doubleAngle", parent="span")
        cmds.addAttr(name, longName="times", attributeType="time", multi=True)
        cmds.currentUnit(time="ntsc")
        span = self.node.getPlug("span")
        for fast in (False, True):
            with self.subTest(fast=fast):
                span.set((30, 90), fast=fast)
                self.assertAlmostEqual(cmds.getAttr(name + ".spanTime"), 30.0)
                self.assertAlmostEqual(cmds.getAttr(name + ".spanAngle"), 90.0)
                values = span.get()
                self.assertAlmostEqual(values[0], 30.0)
                self.assertAlmostEqual(values[1], 90.0)
                values = span.get(unit="rad", timeUnit="sec")
                self.assertAlmostEqual(values[0], 1.0)
                self.assertAlmostEqual(values[1], math.pi / 2)
                span.set((0.5, math.pi), unit="rad", timeUnit="sec", fast=fast)
                self.assertAlmostEqual(cmds.getAttr(name + ".spanTime"), 15.0)
                self.assertAlmostEqual(cmds.getAttr(name + ".spanAngle"), 180.0)
        times = self.node.getPlug("times")
        times[0].set(30)
        times[3].set(2, timeUnit="sec")
        self.assertEqual(sorted(times.get()), [0, 3])
        self.assertAlmostEqual(times.get()[0], 30.0)
        self.assertAlmostEqual(times.get()[3], 60.0)
        self.assertAlmostEqual(times.get(timeUnit="sec")[0], 1.0)

    def test_ui_units_flag_must_be_bool(self):
        """uiUnitsがbool以外ならgetはTypeError。setはsafe=Falseで例外、safe=Trueで1。"""
        tx = self.node.getPlug("tx")
        for bad in (1, None, "yes"):
            with self.subTest(bad=bad):
                with self.assertRaises(TypeError):
                    tx.get(uiUnits=bad)
                with self.assertRaises(TypeError):
                    tx.set(1, uiUnits=bad)
                self.assertEqual(tx.set(1, uiUnits=bad, safe=True), 1)
        self.assertEqual(cmds.getAttr(self.name + ".tx"), 0.0)

    def test_fast_flag_must_be_bool_even_with_safe(self):
        """fastがbool以外ならsafe=Trueでも値を変えずTypeError。"""
        tx = self.node.getPlug("tx")
        for bad in (1, None, "True"):
            with self.subTest(bad=bad):
                with self.assertRaises(TypeError):
                    tx.set(1, fast=bad)
                with self.assertRaises(TypeError):
                    tx.set(1, fast=bad, safe=True)
        self.assertEqual(cmds.getAttr(self.name + ".tx"), 0.0)

    def test_hard_range_rejected_by_all_paths(self):
        """ハード範囲外は通常・fastともRuntimeError、safeは1で、値は変わらない。"""
        plug = self.add("rng", attributeType="double", minValue=-1, maxValue=2)
        for kwargs in (dict(), dict(fast=True)):
            with self.subTest(**kwargs):
                with self.assertRaises(RuntimeError):
                    plug.set(5, **kwargs)
                with self.assertRaises(RuntimeError):
                    plug.set(-3, **kwargs)
                self.assertEqual(plug.set(5, safe=True, **kwargs), 1)
                self.assertEqual(plug.get(), 0.0)
        self.assertIs(plug.set(2), plug)
        self.assertEqual(plug.set(-1, fast=True), plug)
        self.assertEqual(plug.get(), -1.0)

    def test_soft_range_does_not_limit_values(self):
        """ソフト範囲は入力を制限しない。"""
        plug = self.add("soft", attributeType="double", softMinValue=-5, softMaxValue=5)
        plug.set(100)
        self.assertEqual(plug.get(), 100.0)
        plug.set(-100, fast=True)
        self.assertEqual(plug.get(), -100.0)

    def test_distance_range_is_checked_in_internal_units(self):
        """距離の範囲はcmの内部単位で判定し、UI単位がmmでも同じ境界になる。"""
        plug = self.add("lim", attributeType="doubleLinear", minValue=-1, maxValue=1)
        cmds.currentUnit(linear="mm")
        with self.assertRaises(RuntimeError):
            plug.set(5)
        with self.assertRaises(RuntimeError):
            plug.set(2, fast=True)
        with self.assertRaises(RuntimeError):
            plug.set(30, uiUnits=True)
        plug.set(0.5)
        self.assertAlmostEqual(cmds.getAttr(plug.getFullName()), 5.0)
        plug.set(0.25, fast=True)
        self.assertAlmostEqual(cmds.getAttr(plug.getFullName()), 2.5)
        plug.set(3, uiUnits=True)
        self.assertAlmostEqual(plug.get(), 0.3)

    def test_byte_range(self):
        """byteは0〜255の範囲外を通常・fastとも拒否する。"""
        plug = self.add("by", attributeType="byte")
        with self.assertRaises(RuntimeError):
            plug.set(300)
        with self.assertRaises(RuntimeError):
            plug.set(300, fast=True)
        plug.set(7, fast=True)
        self.assertEqual(plug.get(), 7)

    def test_bool_set_two(self):
        """boolへの2は通常・fastともRuntimeError(最大値1)で、値は変わらない。"""
        plug = self.node.getPlug("visibility")
        with self.assertRaises(RuntimeError):
            plug.set(2)
        with self.assertRaises(RuntimeError):
            plug.set(2, fast=True)
        self.assertIs(plug.get(), True)
        plug.set(0, fast=True)
        self.assertIs(plug.get(), False)

    def test_float_to_integer_rounding_matches_between_paths(self):
        """long・short・enum・boolへの小数は通常・fastとも0から遠い側へ四捨五入する。"""
        long_plug = self.add("lg", attributeType="long")
        short_plug = self.add("st", attributeType="short")
        for plug in (long_plug, short_plug):
            for value, expected in ((2.9, 3), (2.5, 3), (-2.5, -3), (2.4999, 2), (-2.6, -3), (1.5, 2)):
                for fast in (False, True):
                    with self.subTest(plug=plug.getAttrName(), value=value, fast=fast):
                        plug.set(0)
                        plug.set(value, fast=fast)
                        self.assertEqual(cmds.getAttr(plug.getFullName()), expected)
        enum_plug = self.add("en", attributeType="enum", enumName="a:b:c:d")
        for value, expected in ((1.7, 2), (1.5, 2), (2.4, 2)):
            for fast in (False, True):
                with self.subTest(enum=value, fast=fast):
                    enum_plug.set(0)
                    enum_plug.set(value, fast=fast)
                    self.assertEqual(enum_plug.get(), expected)
        flag = self.add("bo", attributeType="bool")
        for value, expected in ((0.4, False), (0.6, True)):
            for fast in (False, True):
                with self.subTest(bool=value, fast=fast):
                    flag.set(not expected)
                    flag.set(value, fast=fast)
                    self.assertIs(flag.get(), expected)

    def test_range_is_checked_before_rounding(self):
        """範囲は四捨五入前の値で比べる(cmds.setAttrと同じ)。通常・fastともRuntimeErrorで値は変えない。"""
        flag = self.add("bo", attributeType="bool")
        limited = self.add("lm", attributeType="long", minValue=0, maxValue=5)
        enum_plug = self.add("en", attributeType="enum", enumName="a=1:b=5:c=10")
        enum_plug.set(5)
        for plug, value in ((flag, 1.4), (flag, -0.4), (limited, 5.4), (limited, -0.4),
                            (enum_plug, 0.6), (enum_plug, 10.4), (enum_plug, 11), (enum_plug, 0)):
            for fast in (False, True):
                with self.subTest(plug=plug.getAttrName(), value=value, fast=fast):
                    before = cmds.getAttr(plug.getFullName())
                    with self.assertRaises(RuntimeError):
                        plug.set(value, fast=fast)
                    self.assertEqual(plug.set(value, safe=True, fast=fast), 1)
                    self.assertEqual(cmds.getAttr(plug.getFullName()), before)

    def test_string_and_number_cross_input_rejected_by_both_paths(self):
        """数値へ文字列・Noneや文字列へ数値は拒否され、値を変えない。

        fastと単位アトリビュートの事前換算はTypeError(型違い)。通常経路の他の型は ``cmds.setAttr`` 自身の
        RuntimeErrorがそのまま伝わるため、通常経路はどちらも許す。
        """
        long_plug = self.add("lg", attributeType="long")
        double_plug = self.add("db", attributeType="double")
        enum_plug = self.add("en", attributeType="enum", enumName="a:b:c")
        angle = self.node.getPlug("rx")
        for plug, value in ((long_plug, "5"), (double_plug, "1.5"), (double_plug, None), (angle, "1")):
            for fast in (False, True):
                with self.subTest(plug=plug.getAttrName(), value=value, fast=fast):
                    with self.assertRaises(TypeError if fast else (TypeError, RuntimeError)):
                        plug.set(value, fast=fast)
                    self.assertEqual(plug.set(value, safe=True, fast=fast), 1)
                    self.assertEqual(cmds.getAttr(plug.getFullName()), 0)
        # 5.0.0: enumへの文字列はフィールド名として解釈し、無い名前はValueError。
        for fast in (False, True):
            with self.subTest(plug="en", fast=fast):
                with self.assertRaises(ValueError):
                    enum_plug.set("1", fast=fast)
                self.assertEqual(enum_plug.set("1", safe=True, fast=fast), 1)
                self.assertEqual(cmds.getAttr(enum_plug.getFullName()), 0)
        text = self.add("txt", dataType="string")
        text.set("keep")
        for value in (5, 7.0, None, True):
            for fast in (False, True):
                with self.subTest(text=value, fast=fast):
                    with self.assertRaises(TypeError if fast else (TypeError, RuntimeError)):
                        text.set(value, fast=fast)
                    self.assertEqual(text.set(value, safe=True, fast=fast), 1)
                    self.assertEqual(text.get(), "keep")
        # boolは数値として受け付ける(cmds.setAttrと同じ)。
        double_plug.set(True, fast=True)
        self.assertEqual(double_plug.get(), 1.0)

    def test_invalid_input_types(self):
        """Noneや反復できない値はsafe=Falseで例外、safe=Trueで1を返す。"""
        long_plug = self.add("lg", attributeType="long")
        with self.assertRaises(RuntimeError):
            long_plug.set(None)
        self.assertEqual(long_plug.set(None, safe=True), 1)
        self.assertEqual(long_plug.get(), 0)

    def test_non_finite_values_are_accepted_by_scalars(self):
        """スカラーのdoubleはnan・infを拒否せず、そのまま書く(通常・fast)。"""
        tx = self.node.getPlug("tx")
        tx.set(float("nan"))
        self.assertTrue(math.isnan(tx.get()))
        tx.set(float("inf"), fast=True)
        self.assertEqual(tx.get(), float("inf"))

    def test_locked_parent_locked_and_connected_are_rejected(self):
        """自身・親のロック、入力接続は通常・fastともRuntimeErrorで、safeは1。"""
        tx = self.node.getPlug("tx")
        for flag in ("self", "parent", "connected"):
            with self.subTest(flag=flag):
                if flag == "self":
                    cmds.setAttr(self.name + ".tx", lock=True)
                elif flag == "parent":
                    cmds.setAttr(self.name + ".t", lock=True)
                else:
                    other = self.make("transform")
                    cmds.connectAttr(other.getFullName() + ".ty", self.name + ".tx")
                try:
                    with self.assertRaises(RuntimeError):
                        tx.set(1)
                    with self.assertRaises(RuntimeError):
                        tx.set(1, fast=True)
                    self.assertEqual(tx.set(1, safe=True), 1)
                    self.assertEqual(tx.set(1, safe=True, fast=True), 1)
                    self.assertFalse(tx.isSettable())
                    self.assertTrue(tx.isWritable())
                finally:
                    cmds.setAttr(self.name + ".tx", lock=False)
                    cmds.setAttr(self.name + ".t", lock=False)
                    for source in cmds.listConnections(self.name + ".tx", source=True, destination=False,
                                                       plugs=True) or []:
                        cmds.disconnectAttr(source, self.name + ".tx")
                self.assertEqual(cmds.getAttr(self.name + ".tx"), 0.0)

    def test_set_undo_redo_and_fast_leaves_queue_empty(self):
        """通常のsetは1回のUndoで戻り、fastはUndoへ記録しない。"""
        tx = self.node.getPlug("tx")
        cmds.flushUndo()
        tx.set(4)
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.name + ".tx"), 0.0)
        self.assertUndoEmpty()
        cmds.redo()
        self.assertEqual(cmds.getAttr(self.name + ".tx"), 4.0)
        cmds.flushUndo()
        tx.set(9, fast=True)
        self.assertEqual(cmds.getAttr(self.name + ".tx"), 9.0)
        self.assertUndoEmpty()
        self.assertTrue(cmds.undoInfo(query=True, state=True))

    def test_set_returns_self_or_zero(self):
        """setは通常自身、safe=Trueの成功は0を返す。"""
        tx = self.node.getPlug("tx")
        self.assertIs(tx.set(1), tx)
        self.assertIs(tx.set(2, fast=True), tx)
        self.assertEqual(tx.set(3, safe=True), 0)
        self.assertEqual(tx.set(4, safe=True, fast=True), 0)

    def test_bool_toggle_and_undo(self):
        """toggleは反転して自身を返し、1回のUndoで戻る。"""
        visibility = self.node.getPlug("visibility")
        cmds.flushUndo()
        self.assertIs(visibility.toggle(), visibility)
        self.assertFalse(cmds.getAttr(self.name + ".v"))
        visibility.toggle()
        self.assertTrue(cmds.getAttr(self.name + ".v"))
        cmds.undo()
        self.assertFalse(cmds.getAttr(self.name + ".v"))


class PlugSetIfChangedSpecTest(_PlugSpecCase):
    """setIfChangedの比較・ロック一時解除・Undo。"""

    def test_same_value_returns_false_without_checks(self):
        """同値なら書込み可否を確かめずFalse。ロックや接続があっても例外にしない。"""
        tx = self.node.getPlug("tx")
        cmds.setAttr(self.name + ".tx", lock=True)
        self.assertFalse(tx.setIfChanged(0.0))
        self.assertFalse(tx.setIfChanged(0))
        with self.assertRaises(RuntimeError):
            tx.setIfChanged(2.0)

    def test_comparison_uses_internal_units(self):
        """比較と設定はcm/radの内部単位で行う(UI単位がmでも)。"""
        cmds.currentUnit(linear="m")
        tx = self.node.getPlug("tx")
        tx.set(150)
        self.assertFalse(tx.setIfChanged(150))
        self.assertTrue(tx.setIfChanged(1.5))
        self.assertAlmostEqual(tx.get(), 1.5)

    def test_unlock_relocks_and_single_undo(self):
        """unlock=Trueは自身のロックを一時解除して再ロックし、値とロックを1回のUndoで戻す。"""
        tx = self.node.getPlug("tx")
        cmds.setAttr(self.name + ".tx", 2.0)
        cmds.setAttr(self.name + ".tx", lock=True)
        cmds.flushUndo()
        self.assertTrue(tx.setIfChanged(3.0, unlock=True))
        self.assertEqual(cmds.getAttr(self.name + ".tx"), 3.0)
        self.assertTrue(cmds.getAttr(self.name + ".tx", lock=True))
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.name + ".tx"), 2.0)
        self.assertTrue(cmds.getAttr(self.name + ".tx", lock=True))
        self.assertUndoEmpty()

    def test_unlock_does_not_unlock_parent(self):
        """親のロックは解除せず、RuntimeErrorにする。"""
        tx = self.node.getPlug("tx")
        cmds.setAttr(self.name + ".t", lock=True)
        with self.assertRaises(RuntimeError):
            tx.setIfChanged(1.0, unlock=True)
        self.assertTrue(cmds.getAttr(self.name + ".t", lock=True))
        self.assertEqual(cmds.getAttr(self.name + ".tx"), 0.0)

    def test_fast_unlock_leaves_queue_empty(self):
        """fastは値・ロックの変更をUndoへ記録しない。"""
        tx = self.node.getPlug("tx")
        cmds.setAttr(self.name + ".tx", lock=True)
        cmds.flushUndo()
        self.assertTrue(tx.setIfChanged(4.0, unlock=True, fast=True))
        self.assertEqual(cmds.getAttr(self.name + ".tx"), 4.0)
        self.assertTrue(cmds.getAttr(self.name + ".tx", lock=True))
        self.assertUndoEmpty()

    def test_scalar_only_and_flag_type(self):
        """スカラー以外とbool以外のfastはTypeError。文字列・enumも比較できる。"""
        tx = self.node.getPlug("tx")
        for value in ([1.0], (1.0,), None, om2.MVector()):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    tx.setIfChanged(value)
        with self.assertRaises(TypeError):
            tx.setIfChanged(1.0, fast=1)
        with self.assertRaises(TypeError):
            self.node.getPlug("worldMatrix")[0].setIfChanged(Matrix())
        text = self.add("txt", dataType="string")
        self.assertTrue(text.setIfChanged("a"))
        self.assertFalse(text.setIfChanged("a"))
        enum_plug = self.add("en", attributeType="enum", enumName="a:b")
        self.assertFalse(enum_plug.setIfChanged(0))
        self.assertTrue(enum_plug.setIfChanged(1))
        self.assertEqual(cmds.getAttr(enum_plug.getFullName()), 1)


class PlugEnumSpecTest(_PlugSpecCase):
    """enumの名前と番号、欠番のある番号、setEnumNamesの検証。"""

    def setUp(self):
        super().setUp()
        self.enum_plug = self.add("en", attributeType="enum", enumName="a=1:b=5:c=10")

    def test_names_values_and_field_lookup(self):
        """番号とフィールド名の往復。getEnumValueは名前から番号、getEnumName(value)は番号から名前。"""
        plug = self.enum_plug
        plug.set(5)
        self.assertEqual(plug.getEnumName(), "b")
        self.assertEqual(plug.getEnumValue("c"), 10)
        self.assertEqual(plug.getEnumName(1), "a")
        self.assertEqual(plug.getEnumName(10), "c")
        self.assertEqual(cmds.getAttr(plug.getFullName(), asString=True), "b")
        rotate_order = self.node.getPlug("rotateOrder")
        self.assertEqual(rotate_order.getEnumName(5), "zyx")
        self.assertEqual(rotate_order.getEnumValue("zyx"), 5)

    def test_missing_field_errors(self):
        """名前・番号に対応するフィールドが無ければValueError。"""
        plug = self.enum_plug
        with self.assertRaises(ValueError):
            plug.getEnumValue("zz")
        for value in (3, 0, 11, -1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    plug.getEnumName(value)
        for value in (1.0, True, "1"):
            with self.subTest(bad=value):
                with self.assertRaises(TypeError):
                    plug.getEnumName(value)
        # 既定値0はフィールドの無い番号。getEnumNameもValueError。
        self.assertEqual(plug.get(), 0)
        with self.assertRaises(ValueError):
            plug.getEnumName()
        plug.set(3)
        with self.assertRaises(ValueError):
            plug.getEnumName()
        plug.set(10)
        self.assertEqual(plug.getEnumName(), "c")

    def test_values_without_fields_can_be_set(self):
        """フィールドの無い番号でも最小〜最大の範囲内なら書ける。最小未満はRuntimeError。"""
        plug = self.enum_plug
        plug.set(3)
        self.assertEqual(cmds.getAttr(plug.getFullName()), 3)
        plug.set(7, fast=True)
        self.assertEqual(cmds.getAttr(plug.getFullName()), 7)
        with self.assertRaises(RuntimeError):
            plug.set(-1)
        with self.assertRaises(ValueError):
            plug.set("C")

    def test_reset_to_default_outside_fields_fails(self):
        """既定値0が最小値1を下回るため、resetはMayaの設定どおりRuntimeErrorになる(docstringに記載)。"""
        plug = self.enum_plug
        plug.set(5)
        self.assertEqual(plug.getDefault(), 0)
        with self.assertRaises(RuntimeError):
            plug.reset()
        self.assertEqual(plug.get(), 5)
        with self.assertRaises(RuntimeError):
            plug.reset(fast=True)
        self.assertEqual(plug.get(), 5)

    def test_non_enum_errors(self):
        """enum以外ではgetEnumName・getEnumValue・getEnumName(value)・setEnumNamesがTypeError。"""
        for plug in (self.node.getPlug("tx"), self.add("txt", dataType="string"), self.node.getPlug("visibility")):
            for call in (plug.getEnumName, lambda: plug.getEnumValue("a"), lambda: plug.getEnumName(0),
                         lambda: plug.setEnumNames(["a"])):
                with self.subTest(plug=plug.getAttrName(), call=call):
                    with self.assertRaises(TypeError):
                        call()

    def test_set_enum_names_validation_and_undo(self):
        """setEnumNamesは0から順の名前へ更新し、1回のUndoで戻す。不正な入力は変更前に拒否する。"""
        plug = self.add("mode", attributeType="enum", enumName="off:on")
        cmds.flushUndo()
        self.assertIs(plug.setEnumNames(("x", "y", "z")), plug)
        self.assertEqual(cmds.attributeQuery("mode", node=self.name, listEnum=True), ["x:y:z"])
        self.assertEqual(plug.getEnumValue("z"), 2)
        cmds.undo()
        self.assertEqual(cmds.attributeQuery("mode", node=self.name, listEnum=True), ["off:on"])
        for names, error in (("x", TypeError), ([1], TypeError), ([], ValueError), ([""], ValueError),
                             (["a:b"], ValueError), (["a=1"], ValueError)):
            with self.subTest(names=names):
                with self.assertRaises(error):
                    plug.setEnumNames(names)
        with self.assertRaises(NotImplementedError):
            plug.setEnumNames(["x"], fast=True)
        with self.assertRaises(TypeError):
            plug.setEnumNames(["x"], fast=1)
        self.assertEqual(cmds.attributeQuery("mode", node=self.name, listEnum=True), ["off:on"])


class PlugDataValueSpecTest(_PlugSpecCase):
    """文字列・マトリクス・メッセージ・型付き配列の値。"""

    def test_string_values(self):
        """未設定の文字列は空文字列。日本語・空文字列を往復し、uiUnitsの影響を受けない。"""
        text = self.add("txt", dataType="string")
        self.assertEqual(text.get(), "")
        for fast in (False, True):
            for value in ("abc", "日本語", ""):
                with self.subTest(fast=fast, value=value):
                    text.set(value, fast=fast)
                    self.assertEqual(cmds.getAttr(text.getFullName()) or "", value)
                    self.assertEqual(text.get(uiUnits=True), value)
        with self.assertRaises(RuntimeError):
            text.set(None)

    def test_string_has_no_default_or_reset(self):
        """文字列のgetDefaultはNone、resetはTypeError。"""
        text = self.add("txt", dataType="string")
        self.assertIsNone(text.getDefault())
        with self.assertRaises(TypeError):
            text.reset()

    def test_matrix_attribute_round_trip(self):
        """matrixは16値・MMatrixを受け付け、Matrixを返す。uiUnitsで成分を換算しない。"""
        plug = self.add("mat", attributeType="matrix")
        values = [1, 0, 0, 0, 0, 2, 0, 0, 0, 0, 3, 0, 4, 5, 6, 1]
        cmds.currentUnit(linear="mm")
        self.assertIs(plug.set(values), plug)
        self.assertEqual(cmds.getAttr(plug.getFullName()), [float(v) for v in values])
        result = plug.get()
        self.assertIsInstance(result, Matrix)
        self.assertEqual(list(result), [float(v) for v in values])
        self.assertEqual(list(plug.get(uiUnits=True)), [float(v) for v in values])
        cmds.flushUndo()
        plug.set(om2.MMatrix(), fast=True)
        self.assertEqual(cmds.getAttr(plug.getFullName()), list(om2.MMatrix()))
        self.assertUndoEmpty()
        self.assertEqual(plug.set(values, safe=True), 0)

    def test_matrix_undo(self):
        """マトリクスの通常設定は1回のUndoで戻る。"""
        plug = self.add("mat", attributeType="matrix")
        cmds.flushUndo()
        plug.set([2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1])
        cmds.undo()
        self.assertEqual(cmds.getAttr(plug.getFullName()), list(om2.MMatrix()))

    def test_matrix_invalid_inputs(self):
        """16値でない入力はValueError、safeは1。worldMatrixはTypeError、resetとsetIfChangedは拒否。"""
        plug = self.add("mat", attributeType="matrix")
        with self.assertRaises(ValueError):
            plug.set([1, 2, 3])
        self.assertEqual(plug.set([1, 2, 3], safe=True), 1)
        world = self.node.getPlug("worldMatrix")[0]
        with self.assertRaises(TypeError):
            world.set(Matrix())
        self.assertEqual(world.set(Matrix(), safe=True), 1)
        with self.assertRaises(TypeError):
            plug.reset()
        with self.assertRaises(TypeError):
            plug.get(uiUnits=1)

    def test_typed_matrix_uninitialized_get_returns_none(self):
        """dataType=matrixの未初期化値のgetはNone。設定後は往復する。"""
        plug = self.add("dm", dataType="matrix")
        self.assertIsNone(plug.get())
        self.assertIsNone(plug.get(uiUnits=True))
        # attributeType=matrixは未設定でも単位行列。
        self.assertEqual(self.add("am", attributeType="matrix").get(), Matrix())
        values = [1, 0, 0, 0, 0, 2, 0, 0, 0, 0, 3, 0, 4, 5, 6, 1]
        plug.set(values)
        self.assertEqual(list(plug.get()), [float(v) for v in values])
        plug.set(om2.MMatrix(), fast=True)
        self.assertEqual(plug.get(), Matrix())

    def test_message_has_no_value(self):
        """messageのget・setはRuntimeError(fastも)、resetはTypeError、getDefaultはNone。"""
        message = self.node.getPlug("message")
        with self.assertRaises(RuntimeError):
            message.get()
        with self.assertRaises(RuntimeError):
            message.set(1)
        with self.assertRaises(NotImplementedError):
            message.set(1, fast=True)
        self.assertEqual(message.set(1, safe=True), 1)
        with self.assertRaises(TypeError):
            message.reset()
        self.assertIsNone(message.getDefault())

    def test_typed_arrays(self):
        """未初期化の型付き配列はNone、空配列は[]。通常・fastで往復する。"""
        cases = (("da", "doubleArray", [1.0, 2.5]), ("ia", "Int32Array", [1, -2]), ("sa", "stringArray", ["a", "b"]),
                 ("va", "vectorArray", [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)]))
        for attr, kind, value in cases:
            with self.subTest(kind=kind):
                plug = self.add(attr, dataType=kind)
                self.assertIsNone(plug.get())
                plug.set(value)
                self.assertEqual(plug.get(), value)
                plug.set([], fast=True)
                self.assertEqual(plug.get(), [])
                plug.set(value[:1], fast=True)
                self.assertEqual(plug.get(), value[:1])
        double_array = self.node.getPlug("da")
        self.assertEqual(cmds.getAttr(double_array.getFullName()), [1.0])


class PlugFastBackendSpecTest(_PlugSpecCase):
    """fastで書ける型の範囲(core.fastWrite)と、未対応型の更新前の拒否。"""

    def test_unsupported_child_rejected_before_partial_update(self):
        """未対応の子(message)を持つコンパウンドアトリビュートのfastはsafeでもNotImplementedErrorで、どの子も書かない。"""
        cmds.addAttr(self.name, longName="mix", attributeType="compound", numberOfChildren=2)
        cmds.addAttr(self.name, longName="mixA", attributeType="double", parent="mix")
        cmds.addAttr(self.name, longName="mixB", attributeType="message", parent="mix")
        mix = self.node.getPlug("mix")
        with self.assertRaises(NotImplementedError):
            mix.set((1, 2), fast=True, safe=True)
        with self.assertRaises(NotImplementedError):
            mix.set((1, 2), fast=True)
        self.assertEqual(cmds.getAttr(self.name + ".mixA"), 0.0)
        # 通常経路のsafeは書ける子を更新し、messageの子を失敗数に数える。
        self.assertEqual(mix.set((1, 2), safe=True), 1)
        self.assertEqual(cmds.getAttr(self.name + ".mixA"), 1.0)

    def test_unsupported_typed_data(self):
        """nurbsCurve等の型付きデータのfastはsafeでもNotImplementedError。"""
        plug = self.add("crv", dataType="nurbsCurve")
        with self.assertRaises(NotImplementedError):
            plug.set(1, fast=True)
        with self.assertRaises(NotImplementedError):
            plug.set(1, fast=True, safe=True)
        self.assertIsNone(plug.get())

    def test_scalar_message_fast_reports_unsupported_type_first(self):
        """スカラーのmessageのfastは型の対応を先に検査し、safeでもNotImplementedError。"""
        message = self.node.getPlug("message")
        with self.assertRaises(NotImplementedError):
            message.set(1, fast=True)
        with self.assertRaises(NotImplementedError):
            message.set(1, fast=True, safe=True)
        # ロックされていても、書込み可否より型の未対応を先に報告する。
        cmds.addAttr(self.name, longName="msgOut", attributeType="message")
        cmds.setAttr(self.name + ".msgOut", lock=True)
        with self.assertRaises(NotImplementedError):
            self.node.getPlug("msgOut").set(1, fast=True, safe=True)
        cmds.setAttr(self.name + ".msgOut", lock=False)

    def test_point_and_matrix_arrays_fast(self):
        """pointArray・matrixArrayはfastで書け、要素はtupleで返す。"""
        points = self.add("pa", dataType="pointArray")
        points.set([(1, 2, 3, 1)], fast=True)
        self.assertEqual(points.get(), [(1.0, 2.0, 3.0, 1.0)])
        points.set([(1, 2, 3, 1), (4, 5, 6, 1)])
        self.assertEqual(points.get(), [(1.0, 2.0, 3.0, 1.0), (4.0, 5.0, 6.0, 1.0)])
        matrices = self.add("ma", dataType="matrixArray")
        matrices.set([om2.MMatrix()], fast=True)
        self.assertEqual(matrices.get(), [tuple(om2.MMatrix())])

    def test_generic_attribute(self):
        """generic(choice.input)は基底Plugで型名None。数値を読み書きし、fastは未対応。"""
        choice = mlib.getNode(cmds.createNode("choice", name=self.namespace + ":choice#", skipSelect=True))
        element = choice.getPlug("input")[0]
        self.assertIs(type(element), plugs.Plug)
        self.assertIsNone(element.getType())
        element.set(2.5)
        self.assertEqual(element.get(), 2.5)
        with self.assertRaises(NotImplementedError):
            choice.getPlug("input")[1].set(1.0, fast=True)


class PlugResetDefaultSpecTest(_PlugSpecCase):
    """getDefaultの戻り値の型とresetのUndo・失敗時の扱い。"""

    def test_default_value_types(self):
        """数値はfloat・bool・int、単位付きはMAngle・MDistance・MTime、数値のコンパウンドアトリビュートはtuple。"""
        self.assertEqual(self.node.getPlug("sx").getDefault(), 1.0)
        self.assertIs(self.node.getPlug("visibility").getDefault(), True)
        self.assertEqual(self.node.getPlug("rotateOrder").getDefault(), 0)
        self.assertIsInstance(self.node.getPlug("rx").getDefault(), om2.MAngle)
        self.assertIsInstance(self.add("lin", attributeType="doubleLinear", defaultValue=2).getDefault(),
                              om2.MDistance)
        self.assertIsInstance(self.add("ti", attributeType="time").getDefault(), om2.MTime)
        self.assertEqual(self.node.getPlug("scale").getDefault(), (1.0, 1.0, 1.0))

    def test_reset_unit_attribute_independent_of_ui_units(self):
        """単位付きの既定値は内部単位へ換算して設定し、UI単位に依存しない。"""
        cmds.currentUnit(linear="mm")
        plug = self.add("lin", attributeType="doubleLinear", defaultValue=2)
        plug.set(5)
        plug.reset()
        self.assertAlmostEqual(plug.get(), 2.0)
        self.assertAlmostEqual(cmds.getAttr(plug.getFullName()), 20.0)

    def test_reset_compound_undo_and_fast(self):
        """コンパウンドアトリビュートは子を定義順に戻し、通常は1回のUndoで戻る。fastは記録しない。"""
        scale = self.node.getPlug("scale")
        scale.set((2, 3, 4))
        cmds.flushUndo()
        self.assertIs(scale.reset(), scale)
        self.assertEqual(tuple(scale.get()), (1.0, 1.0, 1.0))
        cmds.undo()
        self.assertEqual(tuple(scale.get()), (2.0, 3.0, 4.0))
        cmds.flushUndo()
        self.assertIs(scale.reset(fast=True), scale)
        self.assertEqual(tuple(scale.get()), (1.0, 1.0, 1.0))
        self.assertUndoEmpty()

    def test_reset_compound_stops_at_locked_child(self):
        """ロックされた子で例外にし、先に戻した子は残す。1回のUndoで先行分も戻る。"""
        scale = self.node.getPlug("scale")
        scale.set((2, 3, 4))
        cmds.setAttr(self.name + ".sy", lock=True)
        cmds.flushUndo()
        with self.assertRaises(RuntimeError):
            scale.reset()
        self.assertEqual(cmds.getAttr(self.name + ".s"), [(1.0, 3.0, 4.0)])
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.name + ".s"), [(2.0, 3.0, 4.0)])

    def test_reset_rejects_multi_and_bad_fast(self):
        """マルチアトリビュート全体とbool以外のfastはTypeError。"""
        with self.assertRaises(TypeError):
            self.node.getPlug("worldMatrix").reset()
        with self.assertRaises(TypeError):
            self.node.getPlug("tx").reset(fast=1)


if __name__ == "__main__":
    unittest.main()
