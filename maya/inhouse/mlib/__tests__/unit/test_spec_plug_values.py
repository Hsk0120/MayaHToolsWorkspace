"""Plugの型照会・範囲と既定値の単位・enum名・エイリアス・マルチアトリビュートの要素の情報(mlib 2.0 の新しい約束)を固定する。

対象: ``getType()`` がMayaの型名を返すこと(旧 ``getDataType`` の契約)、
``getMin/getMax/getSoftMin/getSoftMax/getDefault(uiUnits=)``、``getEnumName(value=None)``・``getEnumNames()``、
``getAlias()``・``getMulti()``・``getIndex()``、``unlock(below, *, fast)``(``undoable`` の廃止)、
廃止した名前(``getDataType``・``getPlugName``・``lock``・``getEnumFieldName``・``getNextAvailable`` 等)が
無いこと。期待値は maya.cmds / OpenMaya で独立に求める。
"""

import math
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib
from mlib import plugs


class _ValueSpecCase(unittest.TestCase):
    """専用の名前空間・Undo・単位を用意し、終了時に元へ戻す。"""

    def setUp(self):
        self.namespace = ":specPlugValues_" + uuid.uuid4().hex
        self.before = set(cmds.ls(long=True) or [])
        cmds.namespace(add=self.namespace)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True),
                      cmds.currentUnit(query=True, time=True))
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        self.node = self.make("transform")
        # Plug.getFullName() はノードの一意名(ルートの "|" 無し)で始まるので、同じ形で期待値を作る。
        self.name = self.node.getName()

    def tearDown(self):
        cmds.currentUnit(linear=self.units[0], angle=self.units[1], time=self.units[2])
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


class GetTypeSpecTest(_ValueSpecCase):
    """getType()はMayaの型名(cmds.getAttr type=True)を返し、Pythonクラスはtype(plug)で調べる。"""

    def test_get_type_matches_cmds_type_name(self):
        """登録型・未登録型とも、getType()はcmds.getAttr(type=True)の型名と一致する。"""
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
            ("byte", dict(attributeType="byte"), plugs.Plug),
            ("doubleArray", dict(dataType="doubleArray"), plugs.Plug),
        )
        for type_name, flags, cls in cases:
            with self.subTest(type=type_name):
                plug = self.add("attr_" + type_name, **flags)
                self.assertEqual(plug.getType(), type_name)
                self.assertEqual(plug.getType(), cmds.getAttr(plug.getFullName(), type=True))
                self.assertIs(type(plug), cls)
                self.assertNotIsInstance(plug.getType(), type)

    def test_builtin_attributes(self):
        """組込みアトリビュートもcmdsと同じ型名。コンパウンドアトリビュート全体はコンパウンドアトリビュートの型名、子は子の型名。"""
        for attr in ("translate", "translateX", "rotateX", "rotateOrder", "visibility", "worldMatrix[0]"):
            with self.subTest(attr=attr):
                plug = self.node.getPlug(attr)
                self.assertEqual(plug.getType(), cmds.getAttr(self.name + "." + attr, type=True))
        self.assertEqual(self.node.getPlug("translate").getType(), "double3")
        self.assertEqual(self.node.getPlug("translateX").getType(), "doubleLinear")

    def test_multi_whole_returns_element_type_and_generic_is_none(self):
        """マルチアトリビュート全体は要素の型名、generic(値で型が決まる)はNone。値を読んでも変わらない。"""
        values = self.add("vals", attributeType="long", multi=True)
        self.assertIsInstance(values, plugs.MultiPlug)
        self.assertEqual(values.getType(), "long")
        self.assertEqual(values[3].getType(), "long")
        choice = mlib.getNode(cmds.createNode("choice", name=self.namespace + ":c#", skipSelect=True))
        element = choice.getPlug("input")[0]
        self.assertIsNone(element.getType())
        cmds.setAttr(choice.getFullName() + ".input[0]", 1.5)
        self.assertIsNone(element.getType())
        self.assertIsNone(choice.getPlug("output").getType())

    def test_invalid_plug_raises(self):
        """削除済みのアトリビュート・ノードではRuntimeError。"""
        plug = self.add("gone", attributeType="double")
        cmds.deleteAttr(self.name, attribute="gone")
        with self.assertRaises(RuntimeError):
            plug.getType()
        tx = self.node.getPlug("tx")
        cmds.delete(self.name)
        with self.assertRaises(RuntimeError):
            tx.getType()


class RemovedNamesSpecTest(_ValueSpecCase):
    """mlib 2.0 で廃止した名前は属性として存在しない(別名も残さない)。"""

    def test_removed_methods_are_absent(self):
        """旧名はAttributeError。クラス辞書にも無い。"""
        tx = self.node.getPlug("tx")
        values = self.add("vals", attributeType="double", multi=True)
        for name in ("getDataType", "getPlugName", "lock", "getEnumFieldName", "getNextAvailable",
                     "getNextAvailableIndex"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(tx, name))
                self.assertFalse(hasattr(plugs.Plug, name))
                with self.assertRaises(AttributeError):
                    getattr(tx, name)
        for name in ("getNextAvailableIndex", "getDataType", "lock", "getPlugName"):
            with self.subTest(array=name):
                self.assertFalse(hasattr(values, name))
                self.assertFalse(hasattr(plugs.MultiPlug, name))
        self.assertTrue(hasattr(values, "getNextAvailable"))
        self.assertTrue(hasattr(plugs.MultiPlug, "getNextAvailable"))
        self.assertIs(plugs.Plug.setLocked, plugs.Plug.__dict__["setLocked"])

    def test_removed_keyword_arguments(self):
        """unlock(undoable=)とgetConnections(pcls=)は受け付けない。"""
        tx = self.node.getPlug("tx")
        with self.assertRaises(TypeError):
            tx.unlock(undoable=False)
        with self.assertRaises(TypeError):
            tx.unlock(False, True)
        with self.assertRaises(TypeError):
            tx.getConnections(pcls=plugs.Plug)


class RangeUnitsSpecTest(_ValueSpecCase):
    """getMin/getMax/getSoftMin/getSoftMax/getDefaultのuiUnits。既定は内部単位のオブジェクト。"""

    def expected_ui(self, value, unit_class):
        """内部単位の単位付きオブジェクトを、現在のUI単位の数値へ変換した期待値。"""
        return value.asUnits(unit_class.uiUnit())

    def test_distance_range_in_ui_units(self):
        """doubleLinearの範囲はMDistance。uiUnits=TrueはUI単位(cm→m切替に追従)の数値。"""
        plug = self.add("dist", attributeType="doubleLinear", minValue=-10, maxValue=20,
                        softMinValue=-5, softMaxValue=15, defaultValue=2.5)
        getters = (("getMin", -10.0), ("getMax", 20.0), ("getSoftMin", -5.0), ("getSoftMax", 15.0),
                   ("getDefault", 2.5))
        for name, cm_value in getters:
            with self.subTest(getter=name, unit="cm"):
                internal = getattr(plug, name)()
                self.assertIsInstance(internal, om2.MDistance)
                self.assertAlmostEqual(internal.asUnits(om2.MDistance.kCentimeters), cm_value)
                ui = getattr(plug, name)(uiUnits=True)
                self.assertIsInstance(ui, float)
                self.assertAlmostEqual(ui, cm_value)
        cmds.currentUnit(linear="m")
        for name, cm_value in getters:
            with self.subTest(getter=name, unit="m"):
                internal = getattr(plug, name)()
                self.assertAlmostEqual(getattr(plug, name)(uiUnits=True), cm_value / 100.0)
                self.assertAlmostEqual(getattr(plug, name)(uiUnits=True), self.expected_ui(internal, om2.MDistance))
        # cmds.attributeQuery の範囲も UI 単位で返るので突き合わせる。
        self.assertAlmostEqual(plug.getMin(uiUnits=True),
                               cmds.attributeQuery("dist", node=self.name, minimum=True)[0])
        self.assertAlmostEqual(plug.getMax(uiUnits=True),
                               cmds.attributeQuery("dist", node=self.name, maximum=True)[0])

    def test_angle_range_in_ui_units(self):
        """doubleAngleの範囲・既定値はMAngle。uiUnits=TrueはUI単位の数値でcmds.attributeQueryと一致。

        cmds.addAttrのminValue/maxValue/defaultValueは内部単位(radian)の生の数値として保存される
        (-90 は -90 radian)ので、uiUnits=True の値は度に換算した値になる。unitを指定すると数値で返す。
        """
        angle = self.add("ang", attributeType="doubleAngle", minValue=-90, maxValue=180, defaultValue=45)
        self.assertIsInstance(angle.getMin(), om2.MAngle)
        self.assertAlmostEqual(angle.getMin().asUnits(om2.MAngle.kRadians), -90.0)
        self.assertAlmostEqual(angle.getMin(unit="rad"), -90.0)
        self.assertAlmostEqual(angle.getMax(unit="deg"), math.degrees(180.0))
        self.assertAlmostEqual(angle.getMin(uiUnits=True), math.degrees(-90.0))
        self.assertAlmostEqual(angle.getMax(uiUnits=True), math.degrees(180.0))
        self.assertAlmostEqual(angle.getDefault(uiUnits=True), math.degrees(45.0))
        self.assertAlmostEqual(angle.getDefault(unit="degrees"), math.degrees(45.0))
        with self.assertRaises(ValueError):
            angle.getMin(unit="deg", uiUnits=True)
        self.assertAlmostEqual(angle.getMin(uiUnits=True),
                               cmds.attributeQuery("ang", node=self.name, minimum=True)[0])
        self.assertAlmostEqual(angle.getDefault(uiUnits=True),
                               cmds.attributeQuery("ang", node=self.name, listDefault=True)[0])
        self.assertAlmostEqual(angle.getDefault(uiUnits=True), cmds.getAttr(angle.getFullName()))
        self.assertAlmostEqual(angle.getDefault(uiUnits=True), angle.get(uiUnits=True))
        self.assertAlmostEqual(angle.getDefault().asUnits(om2.MAngle.kDegrees), angle.get())
        cmds.currentUnit(angle="rad")
        self.assertAlmostEqual(angle.getMin(uiUnits=True), -90.0)
        self.assertAlmostEqual(angle.getMin(uiUnits=True), self.expected_ui(angle.getMin(), om2.MAngle))
        self.assertAlmostEqual(angle.getMin(uiUnits=True),
                               cmds.attributeQuery("ang", node=self.name, minimum=True)[0])

    def test_time_range_in_ui_units(self):
        """timeの範囲・既定値はMTime。uiUnits=Trueは現在のUI時間単位の数値でcmds.attributeQueryと一致。"""
        time = self.add("tm", attributeType="time", minValue=0, maxValue=48, defaultValue=24)
        for unit in ("film", "ntsc"):
            with self.subTest(unit=unit):
                cmds.currentUnit(time=unit)
                self.assertIsInstance(time.getMax(), om2.MTime)
                self.assertIsInstance(time.getMax(uiUnits=True), float)
                self.assertAlmostEqual(time.getMax(uiUnits=True), self.expected_ui(time.getMax(), om2.MTime))
                self.assertAlmostEqual(time.getMax(uiUnits=True),
                                       cmds.attributeQuery("tm", node=self.name, maximum=True)[0])
                self.assertAlmostEqual(time.getDefault(uiUnits=True), self.expected_ui(time.getDefault(), om2.MTime))
                self.assertAlmostEqual(time.getDefault(uiUnits=True),
                                       cmds.attributeQuery("tm", node=self.name, listDefault=True)[0])

    def test_plain_numbers_and_compounds(self):
        """単位の無い数値はuiUnitsで変わらず、数値のコンパウンドアトリビュートは子ごとに換算したtuple。"""
        plain = self.add("num", attributeType="double", minValue=-1, maxValue=1, defaultValue=0.5)
        for name in ("getMin", "getMax", "getDefault"):
            with self.subTest(getter=name):
                self.assertEqual(getattr(plain, name)(), getattr(plain, name)(uiUnits=True))
                self.assertIsInstance(getattr(plain, name)(uiUnits=True), float)
        self.assertEqual(self.node.getPlug("scale").getDefault(), (1.0, 1.0, 1.0))
        self.assertEqual(self.node.getPlug("scale").getDefault(uiUnits=True), (1.0, 1.0, 1.0))
        cmds.currentUnit(angle="rad")
        rotate = self.node.getPlug("rotate").getDefault(uiUnits=True)
        self.assertEqual(rotate, (0.0, 0.0, 0.0))
        self.assertIsNone(self.node.getPlug("message").getDefault())
        self.assertIsNone(self.node.getPlug("message").getDefault(uiUnits=True))
        self.assertIsNone(plain.getSoftMin())
        self.assertIsNone(plain.getSoftMin(uiUnits=True))
        self.assertEqual(self.node.getPlug("rotateOrder").getDefault(uiUnits=True), 0)

    def test_ui_units_argument_errors(self):
        """uiUnitsはbool限定のキーワード引数。"""
        tx = self.node.getPlug("tx")
        for name in ("getMin", "getMax", "getSoftMin", "getSoftMax", "getDefault"):
            with self.subTest(getter=name):
                with self.assertRaises(TypeError):
                    getattr(tx, name)(uiUnits=1)
                with self.assertRaises(TypeError):
                    getattr(tx, name)(True)


class EnumNamesSpecTest(_ValueSpecCase):
    """getEnumName(value=None)とgetEnumNames()。"""

    def listed(self, attr):
        """cmds.attributeQuery(listEnum)の文字列を(名前, 値)の組へ展開する。"""
        result, value = [], 0
        for field in cmds.attributeQuery(attr, node=self.name, listEnum=True)[0].split(":"):
            if "=" in field:
                field, number = field.split("=")
                value = int(number)
            result.append((field, value))
            value += 1
        return result

    def test_enum_name_default_is_current_value(self):
        """valueを省くと現在値の名前、指定するとその値の名前(getEnumValueの逆引き)。"""
        plug = self.add("kind", attributeType="enum", enumName="a=1:b=5:c")
        # 既定値 0 にはフィールドが無いので現在値の名前は ValueError(getEnumName() は値を補正しない)。
        self.assertEqual(cmds.getAttr(plug.getFullName()), 0)
        with self.assertRaises(ValueError):
            plug.getEnumName()
        cmds.setAttr(plug.getFullName(), 1)
        self.assertEqual(plug.getEnumName(), "a")
        cmds.setAttr(plug.getFullName(), 5)
        self.assertEqual(plug.getEnumName(), "b")
        self.assertEqual(plug.getEnumName(None), "b")
        for value, name in ((1, "a"), (5, "b"), (6, "c")):
            with self.subTest(value=value):
                self.assertEqual(plug.getEnumName(value), name)
                self.assertEqual(plug.getEnumValue(name), value)
        rotate_order = self.node.getPlug("rotateOrder")
        self.assertEqual(rotate_order.getEnumName(5), "zyx")
        self.assertEqual(rotate_order.getEnumName(value=0), "xyz")

    def test_enum_name_errors(self):
        """欠番はValueError、bool・float・strはTypeError、enum以外はTypeError。"""
        plug = self.add("kind", attributeType="enum", enumName="a=1:b=5:c")
        for value in (0, 2, 3, 4, 7, -1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    plug.getEnumName(value)
        for value in (True, 1.0, "a"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(TypeError):
                    plug.getEnumName(value)
        cmds.setAttr(plug.getFullName(), 3)
        with self.assertRaises(ValueError):
            plug.getEnumName()
        tx = self.node.getPlug("tx")
        with self.assertRaises(TypeError):
            tx.getEnumName()
        with self.assertRaises(TypeError):
            tx.getEnumName(0)
        with self.assertRaises(TypeError):
            tx.getEnumNames()

    def test_enum_names_lists_fields_in_value_order(self):
        """getEnumNames()は(名前, 値)を値の昇順に返し、欠番は含まない。cmds.attributeQuery(listEnum)と一致。"""
        plug = self.add("kind", attributeType="enum", enumName="a=1:b=5:c")
        names = plug.getEnumNames()
        self.assertEqual(names, [("a", 1), ("b", 5), ("c", 6)])
        self.assertEqual(names, self.listed("kind"))
        self.assertIsInstance(names, list)
        self.assertIsNot(plug.getEnumNames(), names)
        rotate_order = self.node.getPlug("rotateOrder").getEnumNames()
        self.assertEqual([name for name, _ in rotate_order], ["xyz", "yzx", "zxy", "xzy", "yxz", "zyx"])
        self.assertEqual(rotate_order, self.listed("rotateOrder"))
        for name, value in rotate_order:
            self.assertEqual(self.node.getPlug("rotateOrder").getEnumName(value), name)
        cmds.setAttr(plug.getFullName(), 6)
        self.assertEqual(plug.getEnumNames(), names)

    def test_enum_names_follow_set_enum_names(self):
        """setEnumNamesの後は新しい一覧を返す。"""
        plug = self.add("kind", attributeType="enum", enumName="a:b")
        plug.setEnumNames(["x", "y", "z"])
        self.assertEqual(plug.getEnumNames(), [("x", 0), ("y", 1), ("z", 2)])
        self.assertEqual(plug.getEnumName(2), "z")


class AliasMultiIndexSpecTest(_ValueSpecCase):
    """getAlias/getMulti/getIndex。"""

    def test_get_alias(self):
        """エイリアス名を返し、無ければNone。cmds.aliasAttrと一致。"""
        tx = self.node.getPlug("tx")
        self.assertIsNone(tx.getAlias())
        cmds.aliasAttr("moveX", self.name + ".translateX")
        self.assertEqual(tx.getAlias(), "moveX")
        self.assertEqual(cmds.aliasAttr(self.name + ".translateX", query=True), "moveX")
        values = self.add("vals", attributeType="double", multi=True)
        cmds.aliasAttr("second", self.name + ".vals[2]")
        self.assertEqual(values[2].getAlias(), "second")
        self.assertIsNone(values[0].getAlias())
        self.assertIsNone(values.getAlias())
        cmds.aliasAttr(self.name + ".translateX", remove=True)
        self.assertIsNone(tx.getAlias())
        tx.setAlias("viaMlib")
        self.assertEqual(tx.getAlias(), "viaMlib")

    def test_get_multi_and_index_on_elements(self):
        """要素はgetMulti()でマルチアトリビュート全体(MultiPlug)、getIndex()で論理番号。"""
        values = self.add("vals", attributeType="double", multi=True)
        element = values[7]
        array = element.getMulti()
        self.assertIsInstance(array, plugs.MultiPlug)
        self.assertEqual(array.getFullName(), values.getFullName())
        self.assertEqual(element.getIndex(), 7)
        self.assertEqual(self.node.getPlug("vals[12]").getIndex(), 12)
        self.assertEqual(self.node.getPlug("worldMatrix")[0].getIndex(), 0)
        self.assertEqual(self.node.getPlug("worldMatrix")[0].getMulti().getFullName(), self.name + ".worldMatrix")
        # 要素の子はgetMulti()がNone(子であって要素ではない)。
        cmds.addAttr(self.name, longName="pairs", attributeType="compound", numberOfChildren=2, multi=True)
        cmds.addAttr(self.name, longName="px", attributeType="double", parent="pairs")
        cmds.addAttr(self.name, longName="py", attributeType="double", parent="pairs")
        child = self.node.getPlug("pairs")[3].px
        self.assertIsNone(child.getMulti())
        with self.assertRaises(TypeError):
            child.getIndex()
        self.assertEqual(child.getParent().getIndex(), 3)
        self.assertEqual(child.getParent().getMulti().getFullName(), self.name + ".pairs")
        # 参照を作っただけでは要素は作られない。
        self.assertIsNone(cmds.getAttr(self.name + ".vals", multiIndices=True))

    def test_get_multi_and_index_on_non_elements(self):
        """要素でないPlugはgetMulti()がNone、getIndex()はTypeError。削除済みはRuntimeError。"""
        values = self.add("vals", attributeType="double", multi=True)
        for plug in (self.node.getPlug("tx"), self.node.getPlug("t"), values):
            with self.subTest(plug=plug.getAttrName()):
                self.assertIsNone(plug.getMulti())
                with self.assertRaises(TypeError):
                    plug.getIndex()
        element = values[1]
        cmds.deleteAttr(self.name, attribute="vals")
        with self.assertRaises(RuntimeError):
            element.getMulti()
        with self.assertRaises(RuntimeError):
            element.getIndex()


class UnlockSpecTest(_ValueSpecCase):
    """unlock(below=False, *, fast=False)。undoableは廃止し、fastだけがUndoなし。"""

    def lock(self, *attrs):
        """cmdsでロックして記録を消す。"""
        for attr in attrs:
            cmds.setAttr(self.name + "." + attr, lock=True)
        cmds.flushUndo()

    def test_unlock_returns_unlocked_plugs_and_undo_once(self):
        """上位から順に解除したPlugのlistを返し、1回のUndoで全て戻る。"""
        self.assertEqual(self.node.getPlug("ty").unlock(), [])
        self.lock("t", "tx")
        tx = self.node.getPlug("tx")
        result = tx.unlock()
        self.assertEqual([p.getFullName() for p in result], [self.name + ".translate", self.name + ".translateX"])
        self.assertFalse(cmds.getAttr(self.name + ".t", lock=True))
        self.assertFalse(cmds.getAttr(self.name + ".tx", lock=True))
        cmds.undo()
        self.assertTrue(cmds.getAttr(self.name + ".t", lock=True))
        self.assertTrue(cmds.getAttr(self.name + ".tx", lock=True))
        self.assertUndoEmpty()
        # 親 t がロックされたままなので、兄弟 ty の解除は親だけを解除する。
        self.assertEqual([p.getLongName() for p in self.node.getPlug("ty").unlock()], ["translate"])

    def test_unlock_below_and_fast(self):
        """below=Trueは子も解除する。fastはUndoに記録しない。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                self.lock("t", "tx", "tz")
                result = self.node.getPlug("t").unlock(below=True, fast=fast)
                self.assertEqual([p.getLongName() for p in result], ["translate", "translateX", "translateZ"])
                for axis in "xyz":
                    self.assertFalse(cmds.getAttr(self.name + ".t" + axis, lock=True))
                if fast:
                    self.assertUndoEmpty()
                else:
                    cmds.undo()
                    self.assertTrue(cmds.getAttr(self.name + ".t", lock=True))
                    self.assertTrue(cmds.getAttr(self.name + ".tz", lock=True))
                    self.assertUndoEmpty()
                for axis in "xyz":
                    cmds.setAttr(self.name + ".t" + axis, lock=False)
                cmds.setAttr(self.name + ".t", lock=False)

    def test_unlock_argument_errors(self):
        """below・fastはbool限定。位置引数はbelowだけ。"""
        tx = self.node.getPlug("tx")
        with self.assertRaises(TypeError):
            tx.unlock(below=1)
        with self.assertRaises(TypeError):
            tx.unlock(fast=1)
        with self.assertRaises(TypeError):
            tx.unlock(False, False)


if __name__ == "__main__":
    unittest.main()
