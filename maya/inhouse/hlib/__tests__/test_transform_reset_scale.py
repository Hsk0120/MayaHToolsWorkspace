"""リセット・ピボット・形状拡縮をMayaで検証する。"""
from maya.api.OpenMaya import MSpace
import sys
import unittest
import maya.cmds as cmds
from hlib.nodes import Node, Transforms


class TransformResetScaleTest(unittest.TestCase):
    """専用階層だけを編集する。"""

    def setUp(self):
        self.root = cmds.createNode("transform")

    def tearDown(self):
        cmds.delete(self.root)

    def test_reset_and_bulk(self):
        nodes = Transforms([Node(cmds.createNode("transform", parent=self.root)) for _ in range(2)])
        for node in nodes:
            cmds.setAttr(node.getFullName() + ".translate", 1, 2, 3)
            cmds.setAttr(node.getFullName() + ".scale", 2, 3, 4)
        nodes.reset(["tx", "scale"])
        for node in nodes:
            self.assertEqual(tuple(node.getTranslation(at=4)), (0, 2, 3))
            self.assertEqual(tuple(node.getScaling()), (1, 1, 1))
        cmds.undo()
        self.assertEqual(tuple(nodes[0].getTranslation(at=4)), (1, 2, 3))
        nodes[0].reset(fast=True)
        self.assertEqual(tuple(nodes[0].getTranslation(at=4)), (0, 0, 0))
        cmds.addAttr(nodes[0].getFullName(), longName="customValue", attributeType="double", defaultValue=7)
        nodes[0].getPlug("customValue").set(12)
        nodes[0].reset("customValue")
        self.assertEqual(nodes[0].getPlug("customValue").get(), 7)

    def test_reset_pivot_preserves_matrix(self):
        node = Node(cmds.createNode("transform", parent=self.root))
        cmds.setAttr(self.root + ".rotate", 20, 30, 40)
        cmds.setAttr(node.getFullName() + ".translate", 3, 4, 5)
        cmds.setAttr(node.getFullName() + ".rotate", 10, 25, 35)
        cmds.setAttr(node.getFullName() + ".scale", 2, 3, 4)
        before = node.getMatrix(ws=True)
        for ws in (True, False):
            node.resetPivot(ws=ws)
            self.assertTrue(before.isEquivalent(node.getMatrix(ws=True), 1e-8))
            for kind in ("rotate", "scale"):
                for value in node.getPivot(ws=ws, kind=kind):
                    self.assertAlmostEqual(value, 0)
            cmds.undo()
            self.assertTrue(before.isEquivalent(node.getMatrix(ws=True), 1e-8))

    def test_scale_shapes_in_each_space(self):
        factories = (
            lambda: cmds.polyCube(constructionHistory=False)[0],
            lambda: cmds.curve(degree=1, point=[(1, 2, 3), (3, 4, 5), (2, 4, 1)]),
            lambda: cmds.nurbsPlane(constructionHistory=False)[0],
        )
        for factory in factories:
            transform = cmds.parent(factory(), self.root)[0]
            node = Node(transform)
            shape = node.getShape()
            cmds.setAttr(transform + ".translate", 2, 3, 4)
            cmds.setAttr(transform + ".rotate", 20, 30, 40)
            cmds.setAttr(transform + ".scale", 2, 3, 4)
            token = ".vtx[*]" if shape.isType("mesh") else ".cv[*][*]" if shape.isType("nurbsSurface") else ".cv[*]"
            components = cmds.ls(shape.getFullName() + token, flatten=True)
            for ws in (False, True):
                before = [cmds.xform(c, query=True, translation=True, worldSpace=ws, objectSpace=not ws) for c in components]
                matrix = node.getMatrix(ws=True)
                node.scaleGeometry((2, .5, -1), ws=ws, pivot=(1, 2, 3))
                after = [cmds.xform(c, query=True, translation=True, worldSpace=ws, objectSpace=not ws) for c in components]
                for src, dst in zip(before, after):
                    for i, factor in enumerate((2, .5, -1)):
                        self.assertAlmostEqual(dst[i], (i + 1) + (src[i] - (i + 1)) * factor, places=5)
                self.assertTrue(matrix.isEquivalent(node.getMatrix(ws=True), 1e-8))
                cmds.undo()
                restored = cmds.xform(components[0], query=True, translation=True, worldSpace=ws, objectSpace=not ws)
                for a, b in zip(before[0], restored):
                    self.assertAlmostEqual(a, b, places=5)
            with self.assertRaises(ValueError):
                shape.scaleGeometry(float("nan"))
            shape.scaleGeometry(2, indices=[])
            index = (0, 0) if shape.isType("nurbsSurface") else 0
            shape.scaleGeometry(2, indices=[index])

    def test_periodic_curve_and_unit_scale(self):
        transform = cmds.parent(cmds.circle(constructionHistory=False)[0], self.root)[0]
        shape = Node(transform).getShape()
        unit = cmds.currentUnit(query=True, linear=True)
        try:
            cmds.currentUnit(linear="m")
            before = shape.cvs().getPosition()
            shape.scaleGeometry((2, 3, 1), pivot=(1, 0, 0))
            after = shape.cvs().getPosition()
            for src, dst in zip(before, after):
                self.assertAlmostEqual(dst[0], 1 + (src[0] - 1) * 2)
                self.assertAlmostEqual(dst[1], src[1] * 3)
                self.assertAlmostEqual(dst[2], src[2])
        finally:
            cmds.currentUnit(linear=unit)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
