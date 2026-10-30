"""参照取得・値評価・要素作成を分離したPlugの契約を検証する。"""

import inspect
import unittest
from unittest.mock import patch

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import mlib


class PlugSimplificationTest(unittest.TestCase):
    """同じgeneric参照の型切替と、読み取りで更新しない境界を確認する。"""

    def setUp(self):
        """隔離シーンと内部値の比較条件を初期化する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg")

    def test_generic_reference_reads_current_value_after_type_switch(self):
        """generic参照は常にPlugで、再取得せず行列・数値・組を読み分ける。"""
        source = mlib.createNode("transform")
        source.setTranslation((2, 3, 4), at=4)
        number = mlib.createNode("network").addAttr("value", "double", defaultValue=7)
        choice = mlib.createNode("choice")
        choice.getPlug("input")[0].connect(source.getPlug("worldMatrix")[0])
        choice.getPlug("input")[1].connect(number)
        choice.getPlug("input")[2].connect(source.getPlug("translate"))
        output = choice.getPlug("output")
        self.assertIs(type(output), mlib.plugs.Plug)
        self.assertIsNone(output.getType())
        with patch.object(cmds, "getAttr", side_effect=AssertionError("matrix value used cmds")):
            first = output.get()
        self.assertIsInstance(first, mlib.maths.Matrix)
        self.assertEqual(tuple(first.translate), (2, 3, 4))
        choice.getPlug("selector").set(1)
        self.assertEqual(output.get(), 7)
        choice.getPlug("selector").set(2)
        self.assertIs(type(output.get()), tuple)
        self.assertEqual(output.get(), (2, 3, 4))
        choice.getPlug("selector").set(0)
        self.assertIsInstance(output.get(uiUnits=True), mlib.maths.Matrix)
        self.assertIs(type(output), mlib.plugs.Plug)

    def test_reference_and_existing_element_getters_do_not_create(self):
        """不存在参照・既存要素取得・拒否した旧引数は実体もUndoも増やさない。"""
        array = mlib.createNode("network").addAttr("values", "double", multi=True)
        cmds.flushUndo()
        with patch.object(cmds, "getAttr", side_effect=AssertionError("reference evaluated")):
            reference = array[9]
            self.assertEqual(reference.mplug().logicalIndex(), 9)
            self.assertEqual(array.getElement(9), reference)
            with self.assertRaises(TypeError):
                array.getElement(9, create=True)
        self.assertFalse(hasattr(array, "addElement"))
        self.assertEqual(array.getElements(), [])
        self.assertTrue(cmds.undoInfo(q=True, undoQueueEmpty=True))
        reference.set(4)
        self.assertEqual(array.getElement(index=9), reference)
        cmds.undo()
        self.assertEqual(array.getElements(), [])

    def test_generic_set_keeps_matrix_units_and_reads_repeated_type_changes(self):
        """genericへの行列書込みはUI距離に依存せず、同じ参照をUndoでも保つ。"""
        owner = mlib.createNode("network")
        attribute_fn = om2.MFnGenericAttribute()
        attribute = attribute_fn.create("value", "v")
        attribute_fn.addDataType(om2.MFnData.kMatrix)
        attribute_fn.addNumericType(om2.MFnNumericData.kDouble)
        om2.MFnDependencyNode(owner.mnode()).addAttribute(attribute)
        reference = owner.getPlug("value")
        matrix = mlib.maths.Matrix()
        matrix.translate = (2, 3, 4)
        cmds.currentUnit(linear="m", angle="rad")
        try:
            for ui_units in (False, True):
                with self.subTest(uiUnits=ui_units):
                    self.assertIs(reference.set(matrix, uiUnits=ui_units), reference)
                    value = reference.get(uiUnits=ui_units)
                    self.assertIsInstance(value, mlib.maths.Matrix)
                    self.assertEqual(tuple(value.translate), (2, 3, 4))
                    for actual, raw in zip(value, cmds.getAttr(reference.getFullName())):
                        self.assertAlmostEqual(actual, raw)
                    cmds.flushUndo()
                    self.assertIs(reference.set(7.5, uiUnits=ui_units), reference)
                    self.assertEqual(reference.get(), 7.5)
                    cmds.undo()
                    self.assertIsInstance(reference.get(), mlib.maths.Matrix)
                    self.assertEqual(tuple(reference.get().translate), (2, 3, 4))
                    cmds.redo()
                    self.assertEqual(reference.get(), 7.5)
                    self.assertIs(type(reference), mlib.plugs.Plug)
        finally:
            cmds.currentUnit(linear="cm", angle="deg")

    def test_message_multi_is_created_by_connection_and_undoable(self):
        """messageの参照取得では作成せず、接続で要素を作ってUndoする。"""
        source = mlib.createNode("network")
        array = mlib.createNode("network").addAttr("links", "message", multi=True)
        reference = array[12]
        self.assertEqual(array.getElement(12), reference)
        self.assertNotIn(12, array)
        cmds.flushUndo()
        reference.connect(source.getPlug("message"))
        self.assertEqual(array.getElement(12), reference)
        cmds.undo()
        self.assertEqual(array.getElements(), [])
        # messageの便利操作も同じ安全な参照経路を使い、接続だけで実体化する。
        for fast in (False, True):
            index = array.appendMessage(source, fast=fast)
            self.assertEqual(array[index].getSource(), source.getPlug("message"))
            if not fast:
                cmds.undo()
                self.assertEqual(array.getElements(), [])

    def test_logical_indices_remain_strict_without_materialization(self):
        """bool・範囲外の番号を拒否し、上限の未作成参照を別番号へ変換しない。"""
        array = mlib.createNode("network").addAttr("values", "double", multi=True)
        for index, error in ((True, TypeError), (1.5, TypeError), (-1, IndexError),
                             (2147483648, IndexError), (4294967296, IndexError)):
            with self.subTest(index=index):
                with self.assertRaises(error):
                    array[index]
                with self.assertRaises(error):
                    array.getElement(index)
        self.assertEqual(array[2147483647].mplug().logicalIndex(), 2147483647)
        self.assertEqual(array.getElements(), [])
        parameters = inspect.signature(type(array).getElement).parameters
        self.assertEqual(tuple(parameters), ("self", "index"))
        self.assertIs(parameters["index"].default, inspect.Parameter.empty)


if __name__ == "__main__":
    unittest.main()
