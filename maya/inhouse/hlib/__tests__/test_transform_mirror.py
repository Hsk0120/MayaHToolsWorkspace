"""ノードミラーの空間・回転・UndoをMaya内で検証する。"""
from maya.api.OpenMaya import MSpace
import sys
import unittest

import maya.cmds as cmds
import hlib
from hlib.nodes import Node, Joints
from hlib.maths import Matrix


class TransformMirrorTest(unittest.TestCase):
    """テスト用階層のみを作成・破棄する。"""

    def setUp(self):
        self.parent = cmds.createNode("transform")
        cmds.setAttr(self.parent + ".translate", 3, 4, 5)
        cmds.setAttr(self.parent + ".rotate", 20, 30, 40)
        cmds.setAttr(self.parent + ".scale", 2, 3, 4)

    def tearDown(self):
        cmds.delete(self.parent)

    def test_spaces_types_axes_and_undo(self):
        for node_type in ("transform", "joint"):
            for fast in (False, True):
                for ws in (False, True):
                    for axis in ("x", "y", "z", "xy", "xz", "yz", "xyz"):
                        name = cmds.createNode(node_type, parent=self.parent)
                        node = Node(name)
                        cmds.setAttr(name + ".translate", 1, 2, 3)
                        cmds.setAttr(name + ".rotate", 12, 23, 34)
                        if node_type == "joint":
                            cmds.setAttr(name + ".jointOrient", 5, 10, 15)
                        original = node.getMatrix(space=MSpace.kWorld)
                        parent = Node(self.parent).getMatrix(space=MSpace.kWorld)
                        source = original if ws else original * parent.inverse()
                        expected = source.mirrored(axis, (4, 5, 6))
                        if not ws:
                            expected = expected * parent
                        self.assertIs(node.mirrorTransform(axis, MSpace.kWorld if ws else MSpace.kObject, (4, 5, 6), fast=fast), node)
                        self.assertTrue(node.getMatrix(space=MSpace.kWorld).isEquivalent(expected, 1e-7),
                                        (node_type, fast, ws, axis))
                        if not fast:
                            cmds.undo()
                            self.assertTrue(node.getMatrix(space=MSpace.kWorld).isEquivalent(original, 1e-7))
                            cmds.redo()
                        node.mirrorTransform(axis, MSpace.kWorld if ws else MSpace.kObject, (4, 5, 6), fast=fast)
                        self.assertTrue(node.getMatrix(space=MSpace.kWorld).isEquivalent(original, 1e-7))
                        cmds.delete(name)

    def test_offset_pivot_units_and_bulk(self):
        name = cmds.createNode("transform", parent=self.parent)
        node = Node(name)
        cmds.setAttr(name + ".offsetParentMatrix", *Matrix(translate=(4, 2, 1)), type="matrix")
        original = node.getMatrix(space=MSpace.kWorld)
        unit = cmds.currentUnit(query=True, linear=True)
        try:
            cmds.currentUnit(linear="m")
            node.mirrorTransform("x", space=MSpace.kWorld, pivot=(1, 0, 0))
            self.assertTrue(node.getMatrix(space=MSpace.kWorld).isEquivalent(
                original.mirrored("x", (1, 0, 0)), 1e-7))
        finally:
            cmds.currentUnit(linear=unit)
        cmds.xform(name, pivots=(1, 2, 3))
        with self.assertRaises(ValueError):
            node.mirrorTransform(fast=True)
        joints = Joints([Node(cmds.createNode("joint", parent=self.parent)) for _ in range(2)])
        before = joints.getMatrix(space=MSpace.kWorld)
        joints.mirrorTransform("z", space=MSpace.kWorld)
        cmds.undo()
        for node, matrix in zip(joints, before):
            self.assertTrue(node.getMatrix(space=MSpace.kWorld).isEquivalent(matrix, 1e-7))

    def test_invalid_inputs_and_inherits_transform(self):
        node = Node(cmds.createNode("transform", parent=self.parent))
        node.plug("inheritsTransform").set(False)
        node.setTranslation((1, 2, 3))
        original = node.getMatrix(space=MSpace.kWorld)
        node.mirrorTransform("x")
        self.assertTrue(node.getMatrix(space=MSpace.kWorld).isEquivalent(original.mirrored("x"), 1e-7))
        original = node.getMatrix(space=MSpace.kWorld)
        for kwargs in ({"axis": "xx"}, {"pivot": (float("nan"), 0, 0)}, {"ws": 1}):
            with self.assertRaises((ValueError, TypeError)):
                node.mirrorTransform(**kwargs)
            self.assertTrue(node.getMatrix(space=MSpace.kWorld).isEquivalent(original, 1e-7))
        node.plug("inheritsTransform").set(True)
        cmds.setAttr(self.parent + ".scaleX", 0)
        with self.assertRaises(ValueError):
            node.mirrorTransform(space=MSpace.kWorld)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
