"""blendShapeの新規接続・初期ターゲット・Undoと公開入口を検証する。"""

import sys
import unittest

import hlib
import maya.cmds as cmds


class CreateBlendShapeTest(unittest.TestCase):
    def setUp(self):
        self.before = set(cmds.ls(long=True))
        cmds.undoInfo(state=True)
        self.base = cmds.polyCube(ch=False)[0]
        self.target = cmds.duplicate(self.base)[0]
        cmds.move(0, 2, 0, self.target + ".vtx[0]", r=True)

    def tearDown(self):
        for name in sorted(set(cmds.ls(long=True)) - self.before, key=len, reverse=True):
            if cmds.objExists(name):
                cmds.delete(name)

    def test_empty_create_and_add_target(self):
        bs = hlib.createBlendShape(self.base, n="createdBlendShape")
        self.assertIsInstance(bs, hlib.nodes.BlendShape)
        self.assertEqual(bs.getTargetIndices(), [])
        self.assertEqual(bs.getGeometry(), [hlib.getNode(self.base).getShape()])
        bs.addTarget(self.target)
        self.assertAlmostEqual(bs.getTargetDeltas(0)[0].y, 2)

    def test_targets_flags_and_undo(self):
        second = cmds.duplicate(self.base)[0]
        bs = hlib.cmds.createBlendShape(hlib.getNode(self.base),
                                       [hlib.getNode(self.target), hlib.getNode(second)], o="local")
        name = bs.getName()
        self.assertEqual(bs.getTargetIndices(), [0, 1])
        cmds.undo()
        self.assertFalse(cmds.objExists(name))
        cmds.redo()
        bs = hlib.getNode(name)
        bs.getTargetPlug(0).set(1)
        actual = cmds.xform(self.base + ".vtx[0]", q=True, t=True, os=True)
        expected = cmds.xform(self.target + ".vtx[0]", q=True, t=True, os=True)
        self.assertEqual(actual, expected)

    def test_empty_targets_and_invalid_operations(self):
        bs = hlib.createBlendShape(self.base, targets=[])
        self.assertEqual(bs.getTargetIndices(), [])
        before = set(cmds.ls())
        for kwargs in ({"q": True}, {"e": True}, {"geometry": self.base}):
            with self.assertRaises(ValueError):
                hlib.createBlendShape(self.base, **kwargs)
        with self.assertRaises(TypeError):
            hlib.createBlendShape(self.base, name="a", n="b")
        with self.assertRaises(ValueError):
            hlib.createBlendShape(None)
        self.assertEqual(set(cmds.ls()), before)

    def test_single_target_and_reload(self):
        hlib.reload()
        self.assertIs(hlib.createBlendShape, hlib.cmds.createBlendShape)
        bs = hlib.createBlendShape(self.base, self.target)
        self.assertEqual(bs.getTargetIndices(), [0])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
