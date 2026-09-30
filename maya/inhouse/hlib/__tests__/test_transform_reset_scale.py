"""リセット・ピボット・形状拡縮をMayaで検証する。"""
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
            cmds.setAttr(node.full_name() + ".translate", 1, 2, 3)
            cmds.setAttr(node.full_name() + ".scale", 2, 3, 4)
        nodes.reset(["tx", "scale"])
        for node in nodes:
            self.assertEqual(tuple(node.get_translate()), (0, 2, 3))
            self.assertEqual(tuple(node.get_scale()), (1, 1, 1))
        cmds.undo()
        self.assertEqual(tuple(nodes[0].get_translate()), (1, 2, 3))
        nodes[0].reset(fast=True)
        self.assertEqual(tuple(nodes[0].get_translate()), (0, 0, 0))
        cmds.addAttr(nodes[0].full_name(), longName="customValue", attributeType="double", defaultValue=7)
        nodes[0].plug("customValue").set(12)
        nodes[0].reset("customValue")
        self.assertEqual(nodes[0].plug("customValue").get(), 7)

    def test_reset_pivot_preserves_matrix(self):
        node = Node(cmds.createNode("transform", parent=self.root))
        cmds.setAttr(self.root + ".rotate", 20, 30, 40)
        cmds.setAttr(node.full_name() + ".translate", 3, 4, 5)
        cmds.setAttr(node.full_name() + ".rotate", 10, 25, 35)
        cmds.setAttr(node.full_name() + ".scale", 2, 3, 4)
        before = node.get_matrix(ws=True)
        for ws in (True, False):
            node.reset_pivot(ws=ws)
            self.assertTrue(before.isEquivalent(node.get_matrix(ws=True), 1e-8))
            for kind in ("rotate", "scale"):
                for value in node.get_pivot(ws=ws, kind=kind):
                    self.assertAlmostEqual(value, 0)
            cmds.undo()
            self.assertTrue(before.isEquivalent(node.get_matrix(ws=True), 1e-8))

    def test_scale_shapes_in_each_space(self):
        factories = (
            lambda: cmds.polyCube(constructionHistory=False)[0],
            lambda: cmds.curve(degree=1, point=[(1, 2, 3), (3, 4, 5), (2, 4, 1)]),
            lambda: cmds.nurbsPlane(constructionHistory=False)[0],
        )
        for factory in factories:
            transform = cmds.parent(factory(), self.root)[0]
            node = Node(transform)
            shape = node.shape()
            cmds.setAttr(transform + ".translate", 2, 3, 4)
            cmds.setAttr(transform + ".rotate", 20, 30, 40)
            cmds.setAttr(transform + ".scale", 2, 3, 4)
            token = ".vtx[*]" if shape.is_type("mesh") else ".cv[*][*]" if shape.is_type("nurbsSurface") else ".cv[*]"
            components = cmds.ls(shape.full_name() + token, flatten=True)
            for ws in (False, True):
                before = [cmds.xform(c, query=True, translation=True, worldSpace=ws, objectSpace=not ws) for c in components]
                matrix = node.get_matrix(ws=True)
                node.scale_geometry((2, .5, -1), ws=ws, pivot=(1, 2, 3))
                after = [cmds.xform(c, query=True, translation=True, worldSpace=ws, objectSpace=not ws) for c in components]
                for src, dst in zip(before, after):
                    for i, factor in enumerate((2, .5, -1)):
                        self.assertAlmostEqual(dst[i], (i + 1) + (src[i] - (i + 1)) * factor, places=5)
                self.assertTrue(matrix.isEquivalent(node.get_matrix(ws=True), 1e-8))
                cmds.undo()
                restored = cmds.xform(components[0], query=True, translation=True, worldSpace=ws, objectSpace=not ws)
                for a, b in zip(before[0], restored):
                    self.assertAlmostEqual(a, b, places=5)
            with self.assertRaises(ValueError):
                shape.scale_geometry(float("nan"))
            shape.scale_geometry(2, indices=[])
            index = (0, 0) if shape.is_type("nurbsSurface") else 0
            shape.scale_geometry(2, indices=[index])

    def test_periodic_curve_and_unit_scale(self):
        transform = cmds.parent(cmds.circle(constructionHistory=False)[0], self.root)[0]
        shape = Node(transform).shape()
        unit = cmds.currentUnit(query=True, linear=True)
        try:
            cmds.currentUnit(linear="m")
            before = shape.cvs().get_position()
            shape.scale_geometry((2, 3, 1), pivot=(1, 0, 0))
            after = shape.cvs().get_position()
            for src, dst in zip(before, after):
                self.assertAlmostEqual(dst[0], 1 + (src[0] - 1) * 2)
                self.assertAlmostEqual(dst[1], src[1] * 3)
                self.assertAlmostEqual(dst[2], src[2])
        finally:
            cmds.currentUnit(linear=unit)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
