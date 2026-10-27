"""CompoundPlug・Double3Plug・ArrayPlugの子・要素・値の約束を固定する。

期待値はmaya.cmdsで独立に求めた値と比べる。
"""

import math
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib
from mlib import plugs
from mlib.maths import EulerRotate, Scale, Shear, Translate, Vector


class _PlugSpecCase(unittest.TestCase):
    """専用の名前空間・Undo・単位を用意し、終了時に元へ戻す。"""

    def setUp(self):
        self.namespace = ":specBCompound_" + uuid.uuid4().hex
        self.before = set(cmds.ls(long=True) or [])
        cmds.namespace(add=self.namespace)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg")
        self.node = self.make("transform")
        self.name = self.node.getFullName()

    def tearDown(self):
        cmds.currentUnit(linear=self.units[0], angle=self.units[1])
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

    def indices(self, plug_name):
        """cmdsで既存の論理番号を取得する。"""
        return cmds.getAttr(plug_name, multiIndices=True) or []


class CompoundPlugSpecTest(_PlugSpecCase):
    """複合アトリビュートの子の参照と値。"""

    def setUp(self):
        super().setUp()
        cmds.addAttr(self.name, longName="pair", shortName="pr", attributeType="compound", numberOfChildren=2)
        cmds.addAttr(self.name, longName="first", shortName="fi", attributeType="double", parent="pair")
        cmds.addAttr(self.name, longName="second", shortName="se", attributeType="doubleLinear", parent="pair")
        self.pair = self.node.getPlug("pair")

    def test_child_access_by_index_name_short_name_and_attribute(self):
        """子は定義順の番号・ロング名・ショート名・Pythonアトリビュートで参照する。"""
        self.assertIs(type(self.pair), plugs.CompoundPlug)
        children = self.pair.getChildren()
        self.assertEqual([c.getLongName() for c in children], ["first", "second"])
        self.assertEqual([c.getLongName() for c in self.pair], ["first", "second"])
        self.assertEqual(self.pair[0], children[0])
        self.assertEqual(self.pair["second"], children[1])
        self.assertEqual(self.pair["se"], children[1])
        self.assertEqual(self.pair.first, children[0])
        self.assertIs(type(self.pair[1]), plugs.DoubleLinearPlug)
        self.assertEqual(self.pair[0].getParent(), self.pair)
        self.assertTrue(self.pair[0].isChild())
        self.assertTrue(self.pair.isCompound())
        self.assertFalse(self.pair.isChild())

    def test_child_access_errors(self):
        """範囲外はIndexError、無い名前はAttributeError、bool・float・sliceはTypeError。"""
        with self.assertRaises(IndexError):
            self.pair[2]
        with self.assertRaises(IndexError):
            self.pair[-1]
        with self.assertRaises(AttributeError):
            self.pair["missing"]
        with self.assertRaises(AttributeError):
            self.pair.missing
        self.assertFalse(hasattr(self.pair, "missing"))
        for bad in (True, 1.0, slice(0, 1)):
            with self.subTest(bad=bad):
                with self.assertRaises(TypeError):
                    self.pair[bad]
        with self.assertRaises(AttributeError):
            self.pair._private

    def test_get_set_internal_and_ui_units(self):
        """getは子の定義順のtuple。距離の子はUI単位がmmでも内部cmで扱う。"""
        cmds.currentUnit(linear="mm")
        self.assertIs(self.pair.set((1.5, 2.0)), self.pair)
        self.assertEqual(cmds.getAttr(self.name + ".first"), 1.5)
        self.assertAlmostEqual(cmds.getAttr(self.name + ".second"), 20.0)
        self.assertEqual(self.pair.get(), (1.5, 2.0))
        self.assertEqual(self.pair.get(uiUnits=True), (1.5, 20.0))
        self.pair.set((3, 40), uiUnits=True)
        self.assertEqual(self.pair.get(), (3.0, 4.0))
        self.pair.set((5, 6), fast=True)
        self.assertEqual(self.pair.get(), (5.0, 6.0))
        self.pair.set((7, 80), uiUnits=True, fast=True)
        self.assertEqual(self.pair.get(), (7.0, 8.0))

    def test_length_and_type_errors(self):
        """子数と異なる長さはValueError、反復できない値はTypeError。safeは1で値を変えない。"""
        with self.assertRaises(ValueError):
            self.pair.set((1,))
        with self.assertRaises(ValueError):
            self.pair.set((1, 2, 3), fast=True)
        with self.assertRaises(TypeError):
            self.pair.set(5)
        self.assertEqual(self.pair.set((1,), safe=True), 1)
        self.assertEqual(self.pair.set(5, safe=True), 1)
        self.assertEqual(self.pair.get(), (0.0, 0.0))

    def test_safe_updates_writable_children_and_counts_failures(self):
        """safeはロックされた子を失敗数に数え、書ける子は更新する。"""
        cmds.setAttr(self.name + ".second", lock=True)
        # 汎用の複合もDouble3Plugと同じく事前に全子の書込み可否を検査し、
        # safe=Falseでは何も書かずに例外にする。
        cmds.flushUndo()
        for ui_units in (False, True):
            with self.subTest(uiUnits=ui_units):
                with self.assertRaises(RuntimeError):
                    self.pair.set((1, 2), uiUnits=ui_units)
                self.assertEqual(self.pair.get(), (0.0, 0.0))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        # 入力接続のある子も同じ。
        cmds.setAttr(self.name + ".second", lock=False)
        other = cmds.createNode("transform", name=self.namespace + ":src#", skipSelect=True)
        cmds.connectAttr(other + ".tx", self.name + ".second")
        with self.assertRaises(RuntimeError):
            self.pair.set((1, 2))
        self.assertEqual(cmds.getAttr(self.name + ".first"), 0.0)
        cmds.disconnectAttr(other + ".tx", self.name + ".second")
        cmds.setAttr(self.name + ".second", lock=True)
        self.assertEqual(self.pair.set((1, 2), safe=True), 1)
        self.assertEqual(self.pair.get(), (1.0, 0.0))
        self.pair[0].set(0)
        with self.assertRaises(RuntimeError):
            self.pair.set((3, 4), fast=True)
        self.assertEqual(self.pair.get(), (0.0, 0.0))
        self.assertEqual(self.pair.set((3, 4), safe=True, fast=True), 1)
        self.assertEqual(self.pair.get(), (3.0, 0.0))

    def test_set_undo_is_one_step_and_fast_is_not_recorded(self):
        """通常の複合setは1回のUndoで全子が戻り、fastは記録しない。"""
        cmds.flushUndo()
        self.pair.set((1, 2))
        cmds.undo()
        self.assertEqual(self.pair.get(), (0.0, 0.0))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.pair.set((1, 2), fast=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_numeric_compound_float3(self):
        """float3は1回の型付き設定で書き、単精度の値を返す。"""
        cmds.addAttr(self.name, longName="col", attributeType="float3")
        for axis in "rgb":
            cmds.addAttr(self.name, longName="col" + axis, attributeType="float", parent="col")
        col = self.node.getPlug("col")
        col.set((0.5, 0.25, 1))
        self.assertEqual(cmds.getAttr(self.name + ".col"), [(0.5, 0.25, 1.0)])
        self.assertEqual(col.get(), (0.5, 0.25, 1.0))
        cmds.setAttr(self.name + ".colb", lock=True)
        with self.assertRaises(RuntimeError):
            col.set((1, 1, 1))
        self.assertEqual(col.get(), (0.5, 0.25, 1.0))


class Double3PlugSpecTest(_PlugSpecCase):
    """3成分値の数学型、回転順序と角度単位、UI単位。"""

    def test_value_types_by_attribute_name(self):
        """translate・rotate・scale・shearは専用の数学型、他のdouble3はVector。"""
        cases = (("translate", Translate), ("rotate", EulerRotate), ("scale", Scale), ("shear", Shear),
                 ("rotatePivot", Vector))
        for attr, kind in cases:
            with self.subTest(attr=attr):
                value = self.node.getPlug(attr).get()
                self.assertIs(type(value), kind)
        self.assertEqual(tuple(self.node.getPlug("scale").get()), (1.0, 1.0, 1.0))

    def test_rotate_get_uses_node_rotate_order_and_radians(self):
        """rotateのgetはノードのrotateOrderを持つEulerRotateで、UIの角度単位に依存しない。"""
        cmds.setAttr(self.name + ".rotateOrder", 3)
        cmds.setAttr(self.name + ".r", 90, 0, 0)
        for angle in ("deg", "rad"):
            with self.subTest(angle=angle):
                cmds.currentUnit(angle=angle)
                value = self.node.getPlug("rotate").get()
                self.assertEqual(value.order, 3)
                self.assertAlmostEqual(value.x, math.pi / 2)
        cmds.currentUnit(angle="deg")
        self.assertEqual(self.node.getPlug("rotate").get(uiUnits=True), (90.0, 0.0, 0.0))

    def test_rotate_set_units(self):
        """数値列は既定rad、unit='deg'で度。uiUnits=TrueはUI単位。不正な単位はValueError。"""
        rotate = self.node.getPlug("rotate")
        rotate.set((math.pi / 2, 0, 0))
        self.assertAlmostEqual(cmds.getAttr(self.name + ".rx"), 90.0)
        rotate.set((0, 45, 0), unit="deg")
        self.assertAlmostEqual(cmds.getAttr(self.name + ".ry"), 45.0)
        rotate.set((0, 0, 30), uiUnits=True)
        self.assertAlmostEqual(cmds.getAttr(self.name + ".rz"), 30.0)
        rotate.set((0, 0, 60), unit="deg", fast=True)
        self.assertAlmostEqual(cmds.getAttr(self.name + ".rz"), 60.0)
        with self.assertRaises(ValueError):
            rotate.set((0, 0, 0), unit="grad")
        with self.assertRaises(ValueError):
            rotate.set((0, 0, 0), unit="deg", uiUnits=True)
        self.assertEqual(rotate.set((0, 0, 0), unit="grad", safe=True), 1)
        self.assertAlmostEqual(cmds.getAttr(self.name + ".rz"), 60.0)

    def test_rotate_set_math_values_reorder(self):
        """MEulerRotation・MQuaternionはノードのrotateOrderへ並べ替えて設定する。"""
        cmds.setAttr(self.name + ".rotateOrder", 3)
        rotate = self.node.getPlug("rotate")
        euler = om2.MEulerRotation(0.1, 0.2, 0.3, om2.MEulerRotation.kXYZ)
        rotate.set(euler)
        expected = euler.reorder(3)
        actual = [math.radians(v) for v in cmds.getAttr(self.name + ".r")[0]]
        for a, e in zip(actual, (expected.x, expected.y, expected.z)):
            self.assertAlmostEqual(a, e)
        quaternion = om2.MQuaternion(0, math.sqrt(0.5), 0, math.sqrt(0.5))
        cmds.setAttr(self.name + ".rotateOrder", 0)
        rotate.set(quaternion)
        self.assertAlmostEqual(cmds.getAttr(self.name + ".ry"), 90.0)
        with self.assertRaises(ValueError):
            rotate.set(euler, unit="deg")
        with self.assertRaises(TypeError):
            rotate.set(euler, uiUnits=True)

    def test_translate_units_and_validation(self):
        """translateはUI単位mmでも内部cm。成分数・非有限値はValueError、数学値のUI指定はTypeError。"""
        cmds.currentUnit(linear="mm")
        translate = self.node.getPlug("translate")
        translate.set((1, 2, 3))
        self.assertEqual(cmds.getAttr(self.name + ".t"), [(10.0, 20.0, 30.0)])
        self.assertEqual(translate.get(uiUnits=True), (10.0, 20.0, 30.0))
        translate.set((10, 10, 10), uiUnits=True, fast=True)
        self.assertEqual(tuple(translate.get()), (1.0, 1.0, 1.0))
        translate.set((1, 2, 3), unit="deg")
        self.assertEqual(tuple(translate.get()), (1.0, 2.0, 3.0))
        for bad in ((1, 2), (1, 2, float("nan")), (1, 2, float("inf"))):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    translate.set(bad)
                self.assertEqual(translate.set(bad, safe=True), 1)
        with self.assertRaises(TypeError):
            translate.set(5)
        with self.assertRaises(TypeError):
            translate.set(om2.MVector(1, 2, 3), uiUnits=True)
        self.assertEqual(tuple(translate.get()), (1.0, 2.0, 3.0))

    def test_connected_child_strict_and_safe(self):
        """入力接続された子があると通常・fastは全体を拒否し、safeは他の子を更新して1を返す。"""
        other = self.make("transform")
        cmds.connectAttr(other.getFullName() + ".ty", self.name + ".ty")
        translate = self.node.getPlug("translate")
        with self.assertRaises(RuntimeError):
            translate.set((1, 2, 3))
        with self.assertRaises(RuntimeError):
            translate.set((1, 2, 3), fast=True)
        self.assertEqual(tuple(translate.get()), (0.0, 0.0, 0.0))
        self.assertEqual(translate.set((5, 6, 7), safe=True), 1)
        self.assertEqual(tuple(translate.get()), (5.0, 0.0, 7.0))
        self.assertEqual(translate.set((8, 8, 8), safe=True, fast=True), 1)
        self.assertEqual(tuple(translate.get()), (8.0, 0.0, 8.0))

    def test_double3_undo(self):
        """通常のsetは1回のUndoで3成分とも戻る。"""
        translate = self.node.getPlug("translate")
        cmds.flushUndo()
        translate.set((1, 2, 3))
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.name + ".t"), [(0.0, 0.0, 0.0)])


class ArrayPlugSpecTest(_PlugSpecCase):
    """疎な論理番号、要素の作成と削除、message配列への追加。"""

    def setUp(self):
        super().setUp()
        self.net = self.make("network")
        self.net_name = self.net.getFullName()
        cmds.addAttr(self.net_name, longName="vals", attributeType="double", multi=True)
        self.array = self.net.getPlug("vals")

    def test_empty_array(self):
        """空の配列はget={}、getIndices=[]、反復しない。"""
        self.assertIs(type(self.array), plugs.ArrayPlug)
        self.assertEqual(self.array.get(), {})
        self.assertEqual(self.array.getIndices(), [])
        self.assertEqual(self.array.getElements(), [])
        self.assertEqual(list(self.array), [])
        self.assertEqual(self.array.getSourceNodes(), {})
        self.assertTrue(self.array.isArray())
        self.assertFalse(self.array.isElement())

    def test_reference_does_not_create_but_set_does(self):
        """参照だけでは要素を作らず、setが作る。番号は詰めずにキーへ残る。"""
        element = self.array[5]
        self.assertEqual(element.getFullName(), self.net_name + ".vals[5]")
        self.assertTrue(element.isElement())
        self.assertEqual(self.indices(self.net_name + ".vals"), [])
        element.set(1.5)
        self.array[2].set(0.5, fast=True)
        self.assertEqual(self.array.getIndices(), [2, 5])
        self.assertEqual(self.indices(self.net_name + ".vals"), [2, 5])
        self.assertEqual(self.array.get(), {2: 0.5, 5: 1.5})
        self.assertEqual([p.getFullName() for p in self.array],
                         [self.net_name + ".vals[2]", self.net_name + ".vals[5]"])

    def test_get_of_missing_element_creates_it(self):
        """未作成の要素のget()は要素を作る(cmds.getAttrと同じ)。"""
        self.assertEqual(self.array[9].get(), 0.0)
        self.assertEqual(self.array.getIndices(), [9])

    def test_logical_index_validation(self):
        """論理番号は0〜2147483647の整数。範囲外はIndexError、整数以外・boolはTypeError。"""
        self.assertEqual(self.array[2147483647].getFullName(), self.net_name + ".vals[2147483647]")
        for bad, error in ((-1, IndexError), (2147483648, IndexError), (1.0, TypeError), (True, TypeError),
                           (slice(0, 2), TypeError), ("0", TypeError)):
            with self.subTest(bad=bad):
                with self.assertRaises(error):
                    self.array[bad]

    def test_get_element(self):
        """getElementは既存要素だけを返し、欠番はIndexError。idx別名と同時指定の扱い。"""
        self.array[3].set(1.0)
        self.assertEqual(self.array.getElement(3).get(), 1.0)
        self.assertEqual(self.array.getElement(idx=3).getFullName(), self.net_name + ".vals[3]")
        with self.assertRaises(IndexError):
            self.array.getElement(4)
        with self.assertRaises(TypeError):
            self.array.getElement(3, idx=3)
        with self.assertRaises(TypeError):
            self.array.getElement()
        with self.assertRaises(TypeError):
            self.array.getElement(True)
        self.assertEqual(self.indices(self.net_name + ".vals"), [3])

    def test_get_next_available_index(self):
        """getNextAvailable(vacant=True)は既存番号に無い最初の番号。負数は0から。要素を作らない。"""
        self.array[0].set(1)
        self.array[1].set(1)
        self.array[3].set(1)
        self.assertEqual(self.array.getNextAvailable(vacant=True), 2)
        self.assertEqual(self.array.getNextAvailable(3, vacant=True), 4)
        self.assertEqual(self.array.getNextAvailable(10, vacant=True), 10)
        self.assertEqual(self.array.getNextAvailable(-1, vacant=True), 2)
        self.assertEqual(self.indices(self.net_name + ".vals"), [0, 1, 3])

    def test_get_next_available_for_connections(self):
        """getNextAvailableは入力接続とロックを避ける。既定は最後の接続要素の次から探す。"""
        source = self.make("transform").getFullName()
        self.assertEqual(self.array.getNextAvailable(), 0)
        cmds.connectAttr(source + ".tx", self.net_name + ".vals[2]")
        self.assertEqual(self.array.getNextAvailable(), 3)
        self.assertEqual(self.array.getNextAvailable(0), 0)
        cmds.setAttr(self.net_name + ".vals[0]", 1.0)
        cmds.setAttr(self.net_name + ".vals[0]", lock=True)
        self.assertEqual(self.array.getNextAvailable(0), 1)
        self.assertEqual(self.array.getNextAvailable(0, checkLocked=False), 0)
        element = self.array.getNextAvailable(asPlug=True)
        self.assertEqual(element.getFullName(), self.net_name + ".vals[3]")
        with self.assertRaises(AttributeError):
            self.array[2].getNextAvailable()
        cmds.setAttr(self.net_name + ".vals", lock=True)
        with self.assertRaises(RuntimeError):
            self.array.getNextAvailable()

    def test_remove_element_undo_and_fast(self):
        """removeElementは接続ごと要素を消して自身を返し、1回のUndoで戻る。fastは記録しない。"""
        source = self.make("transform").getFullName()
        self.array[0].set(1.0)
        cmds.connectAttr(source + ".tx", self.net_name + ".vals[1]")
        self.array[2].set(3.0)
        cmds.flushUndo()
        self.assertIs(self.array.removeElement(1), self.array)
        self.assertEqual(self.array.getIndices(), [0, 2])
        self.assertFalse(cmds.listConnections(source + ".tx", source=False, destination=True))
        cmds.undo()
        self.assertEqual(self.array.getIndices(), [0, 1, 2])
        self.assertTrue(cmds.isConnected(source + ".tx", self.net_name + ".vals[1]"))
        cmds.flushUndo()
        self.array.removeElement(idx=0, fast=True)
        self.assertEqual(self.array.getIndices(), [1, 2])
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        with self.assertRaises(IndexError):
            self.array.removeElement(0)
        with self.assertRaises(TypeError):
            self.array.removeElement()
        with self.assertRaises(TypeError):
            self.array.removeElement("1")
        with self.assertRaises(TypeError):
            self.array.removeElement(1, idx=1)
        with self.assertRaises(TypeError):
            self.array.removeElement(1, fast=1)

    def test_array_level_set_and_reset_rejected(self):
        """配列全体のset・resetはsafeでもTypeError。"""
        with self.assertRaises(TypeError):
            self.array.set({0: 1})
        with self.assertRaises(TypeError):
            self.array.set({0: 1}, safe=True)
        with self.assertRaises(TypeError):
            self.array.set({0: 1}, fast=1)
        with self.assertRaises(TypeError):
            self.array.reset()
        self.assertEqual(self.array.getIndices(), [])

    def test_ui_units_per_element(self):
        """角度配列のgetはuiUnitsを各要素へ渡す。"""
        cmds.addAttr(self.net_name, longName="angles", attributeType="doubleAngle", multi=True)
        angles = self.net.getPlug("angles")
        angles[0].set(math.pi)
        angles[3].set(90, uiUnits=True)
        result = angles.get()
        self.assertAlmostEqual(result[0], math.pi)
        self.assertAlmostEqual(result[3], math.pi / 2)
        self.assertEqual(sorted(angles.get(uiUnits=True).items()), [(0, 180.0), (3, 90.0)])
        with self.assertRaises(TypeError):
            angles.get(uiUnits=1)

    def test_compound_elements(self):
        """複合の配列要素はCompoundPlugで、子の番号は要素ごとに独立する。"""
        cmds.addAttr(self.net_name, longName="items", attributeType="compound", numberOfChildren=2, multi=True)
        cmds.addAttr(self.net_name, longName="ia", attributeType="double", parent="items")
        cmds.addAttr(self.net_name, longName="ib", attributeType="double", parent="items")
        items = self.net.getPlug("items")
        self.assertIs(type(items[1]), plugs.CompoundPlug)
        items[1].set((1, 2))
        items[4]["ib"].set(5)
        self.assertEqual(items.get(), {1: (1.0, 2.0), 4: (0.0, 5.0)})
        child = items[4]["ib"]
        self.assertEqual(child.getFullName(), self.net_name + ".items[4].ib")
        self.assertEqual(child.getParent().getFullName(), self.net_name + ".items[4]")
        self.assertTrue(child.getParent().isElement())

    def test_world_space_array_includes_instances(self):
        """worldMatrixはインスタンス番号の要素を評価前から含む。"""
        world = self.node.getPlug("worldMatrix")
        self.assertEqual(world.getIndices(), [0])
        cmds.instance(self.name)
        self.assertEqual(world.getIndices(), [0, 1])
        self.assertEqual(sorted(world.get()), [0, 1])
        self.assertTrue(world.getElement(1).getFullName().endswith(".worldMatrix[1]"))

    def test_source_nodes_keep_holes(self):
        """getSourceNodesは接続のある要素の番号と入力元ノードを返す。"""
        source = self.make("transform")
        cmds.connectAttr(source.getFullName() + ".tx", self.net_name + ".vals[4]")
        self.array[1].set(1.0)
        self.assertEqual(self.array.getSourceNodes(), {4: source})

    def test_append_message(self):
        """appendMessageは最大番号の次へ追加し、穴を再利用しない。通常はUndo、fastは記録なし。"""
        cmds.addAttr(self.net_name, longName="links", attributeType="message", multi=True)
        links = self.net.getPlug("links")
        target = self.make("transform")
        self.assertEqual(links.appendMessage(target), 0)
        self.assertEqual(links.appendMessage(target.getFullName()), 1)
        self.assertEqual(links.getSourceNodes(), {0: target, 1: target})
        links.removeElement(0)
        self.assertEqual(links.appendMessage(target), 2)
        self.assertEqual(links.getIndices(), [1, 2])
        cmds.flushUndo()
        self.assertEqual(links.appendMessage(target), 3)
        cmds.undo()
        self.assertEqual(links.getIndices(), [1, 2])
        cmds.flushUndo()
        self.assertEqual(links.appendMessage(target, fast=True), 3)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertTrue(cmds.isConnected(target.getFullName() + ".message", self.net_name + ".links[3]"))
        with self.assertRaises(TypeError):
            self.array.appendMessage(target)
        with self.assertRaises(RuntimeError):
            links.appendMessage(self.namespace + ":missing")
        with self.assertRaises(TypeError):
            links.appendMessage(target, fast=1)
        with self.assertRaises(RuntimeError):
            links.get()


if __name__ == "__main__":
    unittest.main()
