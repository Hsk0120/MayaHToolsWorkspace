"""マルチアトリビュートの列挙と範囲照会の責務を共通化しても既存契約が変わらないことを検証する。"""

import sys
import unittest
from unittest.mock import patch

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
from mlib.nodes import BlendWeighted
from mlib.plugs import MultiPlug


class MaintenanceDelegationTest(unittest.TestCase):
    """専用シーンで番号・評価・例外・単位型を確認する。"""

    def setUp(self):
        """ユーザーのシーンを使わない専用テストの初期状態を用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")

    def test_sparse_indices_are_listed_without_values_or_wrappers(self):
        """番号照会は疎な論理番号だけを返し、値評価や要素ラッパー生成を要求しない。"""
        nodes = ((mlib.createNode("blendWeighted"), 1),
                 (mlib.createNode("plusMinusAverage"), 1),
                 (mlib.createNode("plusMinusAverage"), 2),
                 (mlib.createNode("plusMinusAverage"), 3))
        for node, dimension in nodes:
            with self.subTest(node=node.getType(), dimension=dimension):
                name = "input" if isinstance(node, BlendWeighted) else f"input{dimension}D"
                array = node.getPlug(name)
                value = 2.5 if dimension == 1 else tuple(range(dimension))
                array[9].set(value)
                array[2].set(value)
                array[7]
                cmds.flushUndo()
                with patch.object(cmds, "getAttr", side_effect=AssertionError("value evaluated")), \
                        patch.object(MultiPlug, "getElements", side_effect=AssertionError("wrappers created")):
                    self.assertEqual(array.getIndices(), [2, 9])
                indices = array.getIndices()
                indices.append(99)
                self.assertEqual(array.getIndices(), [2, 9])
                self.assertEqual([plug.mplug().logicalIndex() for plug in array.getElements()], [2, 9])
                self.assertTrue(cmds.undoInfo(q=True, undoQueueEmpty=True))

    def test_world_indices_do_not_change_stored_element_operations(self):
        """仮想インスタンス番号の列挙と、削除・空き番号探索の実データ判定を混同しない。"""
        transform = mlib.getNode(cmds.polyCube(constructionHistory=False)[0])
        cmds.instance(transform.getFullName())
        array = transform.getShape().getPlug("worldMesh")
        stored = list(array.mplug().getExistingArrayAttributeIndices())
        cmds.flushUndo()
        with patch.object(cmds, "getAttr", side_effect=AssertionError("world value evaluated")):
            self.assertEqual(array.getIndices(), sorted(set(stored).union((0, 1))))
            for index in (0, 1):
                self.assertEqual(array.getElement(index).mplug().logicalIndex(), index)
        self.assertEqual(list(array.mplug().getExistingArrayAttributeIndices()), stored)
        next_index = next(index for index in range(len(stored) + 1) if index not in stored)
        self.assertEqual(array.getNextAvailable(vacant=True), next_index)
        for index in set((0, 1)).difference(stored):
            with self.assertRaises(IndexError):
                array.removeElement(index)
        self.assertEqual(list(array.mplug().getExistingArrayAttributeIndices()), stored)
        self.assertTrue(cmds.undoInfo(q=True, undoQueueEmpty=True))

    def test_multi_index_validation_and_missing_errors_are_preserved(self):
        """MultiPlugの番号検証と未存在要素拒否を維持する。"""
        for kind, name in (("blendWeighted", "input"), ("plusMinusAverage", "input1D")):
            array = mlib.createNode(kind).getPlug(name)
            for value in (True, 1.5, -1, 2147483648):
                with self.subTest(node=kind, index=value):
                    error = TypeError if isinstance(value, (bool, float)) else IndexError
                    with self.assertRaises(error):
                        array.getElement(value)
            self.assertEqual(array.getElement(7).getIndex(), 7)
            self.assertEqual(array.getIndices(), [])


    def test_range_queries_preserve_native_values_and_unit_types(self):
        """数値・単位型はネイティブAPIの値、型、対応しない照会の例外を維持する。"""
        node = mlib.createNode("network")
        for kind in ("double", "doubleAngle", "doubleLinear", "time"):
            cmds.addAttr(node.getFullName(), longName=kind, attributeType=kind, minValue=-2, maxValue=5)
        cmds.addAttr(node.getFullName(), longName="soft", attributeType="double",
                     softMinValue=-1, softMaxValue=4)
        cmds.currentUnit(linear="m", angle="rad", time="ntsc")
        cmds.flushUndo()
        for name in ("double", "doubleAngle", "doubleLinear", "time", "soft"):
            plug = node.getPlug(name)
            attribute = plug.mplug().attribute()
            fn = (om2.MFnNumericAttribute(attribute) if attribute.hasFn(om2.MFn.kNumericAttribute)
                  else om2.MFnUnitAttribute(attribute))
            for suffix in ("Min", "Max", "SoftMin", "SoftMax"):
                with self.subTest(attribute=name, limit=suffix):
                    has_name, get_name = f"has{suffix}", f"get{suffix}"
                    if not hasattr(fn, has_name):
                        with self.assertRaises(AttributeError):
                            getattr(plug, has_name)()
                        with self.assertRaises(AttributeError):
                            getattr(plug, get_name)()
                        continue
                    present = getattr(fn, has_name)()
                    expected = getattr(fn, get_name)() if present else None
                    self.assertEqual(getattr(plug, has_name)(), present)
                    actual = getattr(plug, get_name)()
                    self.assertIs(type(actual), type(expected))
                    if isinstance(expected, om2.MAngle):
                        self.assertEqual(actual.asRadians(), expected.asRadians())
                    elif isinstance(expected, om2.MDistance):
                        self.assertEqual(actual.asCentimeters(), expected.asCentimeters())
                    elif isinstance(expected, om2.MTime):
                        self.assertEqual(actual.asUnits(om2.MTime.kSeconds), expected.asUnits(om2.MTime.kSeconds))
                    else:
                        self.assertEqual(actual, expected)
        self.assertTrue(cmds.undoInfo(q=True, undoQueueEmpty=True))

    def test_range_queries_preserve_unsupported_and_deleted_guards(self):
        """非対応型ではFalse/None、削除済み参照では全8照会が寿命エラーになる。"""
        node = mlib.createNode("network")
        for suffix in ("Min", "Max", "SoftMin", "SoftMax"):
            self.assertIs(getattr(node.getPlug("message"), f"has{suffix}")(), False)
            self.assertIsNone(getattr(node.getPlug("message"), f"get{suffix}")())
        removed_attribute = node.addAttr("removed", "double")
        removed_node = node.getPlug("message")
        cmds.deleteAttr(removed_attribute.getFullName())
        node.delete()
        for plug in (removed_attribute, removed_node):
            for suffix in ("Min", "Max", "SoftMin", "SoftMax"):
                for prefix in ("has", "get"):
                    with self.subTest(method=prefix + suffix), self.assertRaises(RuntimeError):
                        getattr(plug, prefix + suffix)()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
