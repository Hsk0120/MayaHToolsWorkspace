"""DecomposeMatrix.setRotateOrder が回転順序の名前と番号の両方を受け付けることを検証する。"""

import sys
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import hlib

hlib.reload()


class DecomposeMatrixRotateOrderTest(unittest.TestCase):
    def setUp(self):
        self.namespace = "hlibDecomposeOrder_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        self.node = hlib.createNode("decomposeMatrix", name=self.namespace + ":decompose")

    def tearDown(self):
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def rotate_order(self):
        return cmds.getAttr(self.node.fullName() + ".inputRotateOrder")

    def test_accepts_names_and_order_numbers(self):
        names = hlib.maths.eulerRotation.ORDER_NAMES
        for index, name in enumerate(names):
            self.assertIs(self.node.setRotateOrder(name), self.node)
            self.assertEqual(self.rotate_order(), index)
            self.node.setRotateOrder(0)
            self.assertIs(self.node.setRotateOrder(index), self.node)
            self.assertEqual(self.rotate_order(), index)
            self.node.setRotateOrder(0)
            self.node.setRotateOrder(name.upper())
            self.assertEqual(self.rotate_order(), index)
        # EulerRotation.order(om2 の番号)や om2 の定数をそのまま渡せる。
        euler = hlib.maths.EulerRotation(0.1, 0.2, 0.3, "yxz")
        self.node.setRotateOrder(euler.order)
        self.assertEqual(self.rotate_order(), om2.MEulerRotation.kYXZ)
        self.node.setRotateOrder(om2.MEulerRotation.kZXY)
        self.assertEqual(self.rotate_order(), 2)

    def test_invalid_orders_raise_without_editing(self):
        self.node.setRotateOrder("zyx")
        for invalid in ("bad", "", 6, -1, True, 1.0, None):
            with self.assertRaises(ValueError, msg=repr(invalid)):
                self.node.setRotateOrder(invalid)
            self.assertEqual(self.rotate_order(), 5)

    def test_number_is_undoable_and_fast_mode_writes_directly(self):
        self.node.setRotateOrder(4)
        self.assertEqual(self.rotate_order(), 4)
        cmds.undo()
        self.assertEqual(self.rotate_order(), 0)
        cmds.redo()
        self.assertEqual(self.rotate_order(), 4)
        self.node.setRotateOrder(3, fast=True)
        self.assertEqual(self.rotate_order(), 3)
        with self.assertRaises(ValueError):
            self.node.setRotateOrder(7, fast=True)
        self.assertEqual(self.rotate_order(), 3)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
