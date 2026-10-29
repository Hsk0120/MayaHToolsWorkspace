"""5.0.0 で変更したマルチアトリビュート・名前・genericの仕様テスト。

- 「次に使える要素」は ``cmds.connectAttr(nextAvailable=True)`` と同じ規則(``connectTo(nextAvailable=True)`` と
  ``MultiPlug.getNextAvailable()`` の既定)。同じ初期状態をcmdsとmlibで作り、選ばれた番号を突き合わせる。
- ``MultiPlug.getElement(i)`` は未作成の要素も参照を返す。
- ``Plug.getName()``・``getAttrName()`` は論理番号を省かず、getAttrNameは先頭ドットを持たない。
- generic のアトリビュートへの定数のマトリクス。
"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.maths import Matrix
from support.specCase import NamespaceCase


class _Case(NamespaceCase):
    PREFIX = "mlibSpecMulti_"

    def setUp(self):
        super().setUp()
        self.node = mlib.getNode(self.make("transform", "node"))
        self.source = mlib.getNode(self.make("transform", "source"))
        self.feeder = mlib.getNode(self.make("transform", "feeder"))


class NextAvailableParityTest(_Case):
    """cmds.connectAttr(nextAvailable=True) と同じ要素を選ぶ。"""

    #: (名前, 準備)。準備は (マルチアトリビュートの名前, 接続元のノード名) を受け取ってシーンを作る。
    SETUPS = (
        ("empty", lambda attr, src: None),
        ("value0", lambda attr, src: cmds.setAttr(attr + "[0]", 5)),
        ("values01", lambda attr, src: (cmds.setAttr(attr + "[0]", 5), cmds.setAttr(attr + "[1]", 5))),
        ("conn0_2", lambda attr, src: (cmds.connectAttr(src + ".tx", attr + "[0]"),
                                       cmds.connectAttr(src + ".ty", attr + "[2]"))),
        ("conn2", lambda attr, src: cmds.connectAttr(src + ".ty", attr + "[2]")),
        ("conn2_value0", lambda attr, src: (cmds.connectAttr(src + ".ty", attr + "[2]"),
                                            cmds.setAttr(attr + "[0]", 4))),
        ("locked0", lambda attr, src: (cmds.setAttr(attr + "[0]", 1), cmds.setAttr(attr + "[0]", lock=True))),
        ("conn0_locked1", lambda attr, src: (cmds.connectAttr(src + ".tx", attr + "[0]"),
                                             cmds.setAttr(attr + "[1]", 1), cmds.setAttr(attr + "[1]", lock=True))),
    )

    def add_multi(self, node, name):
        cmds.addAttr(node.getFullName(), longName=name, attributeType="double", multi=True, indexMatters=False)
        return node.getFullName() + "." + name

    def chosen_by_cmds(self, attr):
        connected = {plug for plug in cmds.listConnections(attr, source=True, destination=False, plugs=True,
                                                           connections=True) or []}
        cmds.connectAttr(self.source.getFullName() + ".sx", attr, nextAvailable=True)
        pairs = cmds.listConnections(attr, source=True, destination=False, plugs=True, connections=True) or []
        for destination, source in zip(pairs[::2], pairs[1::2]):
            if source.endswith(".scaleX") and destination not in connected:
                return int(destination.rsplit("[", 1)[1].rstrip("]"))
        self.fail("cmds did not connect: %s" % attr)

    def test_matches_cmds(self):
        """connectTo(nextAvailable=True)・getNextAvailable()は各初期状態でcmdsと同じ番号を選ぶ。"""
        for index, (label, setup) in enumerate(self.SETUPS):
            for fast in (False, True):
                with self.subTest(case=label, fast=fast):
                    reference = self.add_multi(self.node, "ref%d%d" % (index, fast))
                    ours = self.add_multi(self.node, "our%d%d" % (index, fast))
                    setup(reference, self.feeder.getFullName())
                    setup(ours, self.feeder.getFullName())
                    expected = self.chosen_by_cmds(reference)
                    multi = mlib.getPlug(ours)
                    self.assertEqual(multi.getNextAvailable(), expected)
                    element = self.source.getPlug("sx").connectTo(multi, nextAvailable=True, fast=fast)
                    self.assertEqual(element.getIndex(), expected)

    def test_compound_children_count(self):
        """子の接続を持つ要素は使われている扱いで、その次から選ぶ(cmdsと同じ)。"""
        results = []
        for prefix in ("ref", "our"):
            name = self.node.getFullName()
            cmds.addAttr(name, longName=prefix + "Pair", attributeType="double2", multi=True, indexMatters=False)
            for axis in "XY":
                cmds.addAttr(name, longName=prefix + "Pair" + axis, attributeType="double", parent=prefix + "Pair")
            cmds.connectAttr(self.feeder.getFullName() + ".tx", "%s.%sPair[1].%sPairX" % (name, prefix, prefix))
        cmds.addAttr(self.source.getFullName(), longName="pair", attributeType="double2")
        for axis in "XY":
            cmds.addAttr(self.source.getFullName(), longName="pair" + axis, attributeType="double", parent="pair")
        cmds.connectAttr(self.source.getFullName() + ".pair", self.node.getFullName() + ".refPair", nextAvailable=True)
        results.append(cmds.getAttr(self.node.getFullName() + ".refPair", multiIndices=True))
        element = self.source.getPlug("pair").connectTo(self.node.getPlug("ourPair"), nextAvailable=True)
        results.append(cmds.getAttr(self.node.getFullName() + ".ourPair", multiIndices=True))
        self.assertEqual(results[0], results[1])
        self.assertEqual(element.getIndex(), 2)

    def test_vacant_is_separate_rule(self):
        """vacant=Trueは値を持つ要素も避ける別の探索(Mayaの規則ではない)。"""
        attr = self.add_multi(self.node, "values")
        cmds.setAttr(attr + "[0]", 1)
        multi = mlib.getPlug(attr)
        self.assertEqual(multi.getNextAvailable(), 0)
        self.assertEqual(multi.getNextAvailable(vacant=True), 1)

    def test_undo_once(self):
        """nextAvailableの接続は1回のUndoで戻る。fastはUndoに積まない。"""
        multi = mlib.getPlug(self.add_multi(self.node, "values"))

        def inputs():
            return cmds.listConnections(multi.getFullName(), source=True, destination=False) or []
        self.flushUndo()
        self.source.getPlug("sx").connectTo(multi, nextAvailable=True)
        self.assertUndoesInOneStep(lambda: self.assertEqual(inputs(), []),
                                   lambda: self.assertEqual(len(inputs()), 1))
        self.flushUndo()
        self.source.getPlug("sy").connectTo(multi, nextAvailable=True, fast=True)
        self.assertUndoEmpty()


class GetElementTest(_Case):
    """getElementは未作成の要素も参照し、getElementsは既存要素だけを返す。"""

    def test_missing_element_reference(self):
        cmds.addAttr(self.node.getFullName(), longName="values", attributeType="double", multi=True)
        multi = self.node.getPlug("values")
        element = multi.getElement(4)
        self.assertEqual(element, multi[4])
        self.assertEqual(element.getFullName(), multi.getFullName() + "[4]")
        self.assertNotIn(4, multi)
        self.assertEqual(multi.getElements(), [])
        element.set(2.0)
        self.assertEqual(multi.getElements(), [element])
        self.assertEqual(cmds.getAttr(self.node.getFullName() + ".values", multiIndices=True), [4])

    def test_errors(self):
        multi = self.node.getPlug("worldMatrix")
        for index, error in ((-1, IndexError), (2147483648, IndexError), (True, TypeError), ("1", TypeError)):
            with self.subTest(index=index):
                with self.assertRaises(error):
                    multi.getElement(index)


class PlugNamesTest(_Case):
    """getName・getAttrNameは論理番号を省かず、getAttrNameはgetPlugへ戻せる。"""

    def test_names(self):
        name = self.node.getName()
        cmds.addAttr(self.node.getFullName(), longName="items", shortName="its", attributeType="compound",
                     numberOfChildren=1, multi=True)
        cmds.addAttr(self.node.getFullName(), longName="weight", shortName="wt", attributeType="double",
                     parent="items")
        for path, short in (("worldMatrix[0]", "wm[0]"), ("worldMatrix", "wm"), ("translateX", "tx"),
                            ("items[3].weight", "its[3].wt"), ("parentInverseMatrix[0]", "pim[0]")):
            with self.subTest(path=path):
                plug = self.node.getPlug(path)
                self.assertEqual(plug.getAttrName(), short)
                self.assertEqual(plug.getName(), name + "." + short)
                self.assertEqual(self.node.getPlug(plug.getAttrName()), plug)
                self.assertTrue(cmds.objExists(plug.getName()))


class GenericMatrixTest(_Case):
    """genericのアトリビュートへの定数のマトリクス。"""

    def test_dynamic_generic_accepts_matrix(self):
        """matrixを受け付ける動的genericは通常・fastとも書け、cmdsで同じ値を読める。"""
        cmds.addAttr(self.node.getFullName(), longName="anything", dataType=["matrix", "string"])
        plug = self.node.getPlug("anything")
        value = Matrix()
        value.setElement(3, 0, 5.0)
        for fast in (False, True):
            with self.subTest(fast=fast):
                plug.set(Matrix(), fast=fast)
                plug.set(value, fast=fast)
                self.assertEqual(plug.get(), value)
                self.assertEqual(cmds.getAttr(plug.getFullName())[12], 5.0)
        self.flushUndo()
        plug.set(Matrix())
        self.assertUndoesInOneStep(lambda: self.assertEqual(plug.get(), value),
                                   lambda: self.assertEqual(plug.get(), Matrix()))
        self.flushUndo()
        plug.set(value, fast=True)
        self.assertUndoEmpty()

    def test_choice_input_raises_type_error(self):
        """choice.inputはMayaが定数のマトリクスを保存・復元できないため、通常・fastともTypeErrorで変更しない。"""
        choice = mlib.getNode(self.make("choice", "pick"))
        element = choice.getPlug("input")[0]
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaisesRegex(TypeError, "holdMatrix"):
                    element.set(Matrix(), fast=fast)
                self.assertEqual(element.set(Matrix(), safe=True, fast=fast), 1)
        self.assertEqual(cmds.getAttr(choice.getFullName() + ".input", multiIndices=True) or [], [])

    def test_locked_generic_fast(self):
        """fastでもロック中のgenericはRuntimeError。"""
        cmds.addAttr(self.node.getFullName(), longName="anything", dataType=["matrix", "string"])
        plug = self.node.getPlug("anything")
        plug.setLocked(True)
        with self.assertRaises(RuntimeError):
            plug.set(Matrix(), fast=True)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
