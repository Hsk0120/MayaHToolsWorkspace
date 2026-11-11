"""Node.duplicate が複製した自身を同じ種類のラッパーで返すことを確かめる。

各種ノード(transform・joint・DGノード・shape)の戻り型、名前・suffix・Mayaフラグの受け渡し、
Undo 1 回で戻ること、無効なノード・不正なフラグの例外を確かめる。
"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from support.specCase import NamespaceCase


def _short(node):
    """名前空間とDAGパスを除いたノード名を返す。"""
    return node.getNodeName().rpartition(":")[2]


class NodeDuplicateTest(NamespaceCase):
    """Node.duplicate の戻り型・引数・Undo・例外。"""

    PREFIX = "mlibNodeDuplicate_"
    CLEAR_SELECTION = True

    def setUp(self):
        super().setUp()
        # 複製はカレントの名前空間に作られるため、テストの名前空間へ切り替えて後始末の対象にする。
        self.current_namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        cmds.namespace(setNamespace=":" + self.ns)
        cmds.select(clear=True)
        self.root = cmds.joint(name=self.ns + ":root", position=(0, 0, 0))
        self.tip = cmds.joint(name=self.ns + ":tip", position=(0, 1, 0))
        cmds.select(clear=True)
        self.cube = cmds.polyCube(name=self.ns + ":cube")[0]

    def tearDown(self):
        cmds.namespace(setNamespace=self.current_namespace)
        super().tearDown()

    def test_returns_same_wrapper_type(self):
        cases = (
            ("transform", mlib.createNode("transform", name=self.ns + ":xform"), "transform"),
            ("joint", mlib.getNode(self.root), "joint"),
            ("dg", mlib.createNode("multiplyDivide", name=self.ns + ":md"), "multiplyDivide"),
            ("locator transform", mlib.createLocator(name=self.ns + ":loc").getParent(), "transform"),
        )
        for label, node, node_type in cases:
            with self.subTest(label):
                copied = node.duplicate()
                self.assertIs(type(copied), type(node))
                self.assertEqual(copied.getType(), node_type)
                self.assertNotEqual(copied.getFullName(), node.getFullName())
                self.assertTrue(cmds.objExists(copied.getFullName()))

    def test_shape_returns_duplicated_shape(self):
        cmds.cluster(self.cube)
        shapes = cmds.listRelatives(self.cube, shapes=True, fullPath=True)
        for index, shape_name in enumerate(shapes):
            with self.subTest(shape_name):
                shape = mlib.getNode(shape_name)
                copied = shape.duplicate()
                self.assertIs(type(copied), type(shape))
                self.assertNotEqual(copied.getFullName(), shape.getFullName())
                parent = cmds.listRelatives(copied.getFullName(), parent=True, fullPath=True)[0]
                self.assertNotEqual(parent, cmds.ls(self.cube, long=True)[0])
                children = cmds.listRelatives(parent, shapes=True, fullPath=True)
                self.assertEqual(children[index], copied.getFullName())

    def test_name_suffix_and_flags(self):
        root = mlib.getNode(self.root)
        named = root.duplicate(self.ns + ":copy")
        self.assertEqual(_short(named), "copy")
        suffixed = root.duplicate(suffix="_FK")
        self.assertEqual(_short(suffixed), "root_FK")
        self.assertEqual([_short(child) for child in suffixed.getChildren()], ["tip_FK"])
        parent_only = root.duplicate(parentOnly=True)
        self.assertEqual(parent_only.getChildren(), [])
        short = root.duplicate(po=True)
        self.assertEqual(short.getChildren(), [])

    def test_undo_once(self):
        node = mlib.getNode(self.root)
        before = set(cmds.ls(long=True))
        self.flushUndo()
        copied = node.duplicate(suffix="_copy")
        self.assertIn(copied.getFullName(), set(cmds.ls(long=True)) - before)
        cmds.undo()
        self.assertEqual(set(cmds.ls(long=True)), before)

    def test_invalid_inputs(self):
        node = mlib.createNode("transform", name=self.ns + ":gone")
        cmds.delete(node.getFullName())
        with self.assertRaisesRegex(RuntimeError, "Cannot duplicate an invalid"):
            node.duplicate()
        root = mlib.getNode(self.root)
        before = set(cmds.ls(long=True))
        with self.assertRaises(TypeError):
            root.duplicate(parentOnly=True, po=True)
        with self.assertRaises(TypeError):
            root.duplicate(suffix=1)
        with self.assertRaises(ValueError):
            root.duplicate(suffix="a b")
        self.assertEqual(set(cmds.ls(long=True)), before)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
