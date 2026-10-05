"""明示的なOpenMaya編集の値・Undo・エラー時のコンテキストを検証する。"""
from maya.api.OpenMaya import MSpace
import sys
import unittest
from unittest.mock import patch
from contextlib import ExitStack
import maya.cmds as cmds
import hlib

hlib.reload()


class FastEditTest(unittest.TestCase):
    def setUp(self):
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def api_only(self):
        stack = ExitStack()
        for name in ('setAttr', 'xform', 'polyEditUV', 'undoInfo'):
            stack.enter_context(patch.object(cmds, name, side_effect=AssertionError(name)))
        return stack

    def test_plug_and_undo(self):
        node = hlib.getNode(cmds.createNode('transform'))
        sentinel = cmds.createNode('transform')
        cmds.setAttr(sentinel + '.tx', 5)
        undo_name = cmds.undoInfo(query=True, undoName=True)
        with self.api_only():
            node.plug('tx').set(12, fast=True)
            node.plug('visibility').set(False, fast=True)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        cmds.undo()
        self.assertEqual(cmds.getAttr(sentinel + '.tx'), 0)
        self.assertEqual(cmds.getAttr(node.fullName() + '.tx'), 12)
        node.plug('tx').set(24)
        cmds.undo()
        self.assertEqual(node.plug('tx').get(), 12)
        with self.assertRaises(TypeError):
            node.plug('tx').set(0, fast=1)
        cmds.setAttr(node.fullName() + '.tx', lock=True)
        with self.assertRaises(RuntimeError):
            node.plug('tx').set(0, fast=True)
        cmds.setAttr(node.fullName() + '.tx', lock=False)
        node.plug('tx').set(33)
        cmds.undo()
        self.assertEqual(node.plug('tx').get(), 12)

    def test_transform_and_joint(self):
        for kind in ('transform', 'joint'):
            node = hlib.getNode(cmds.createNode(kind))
            node.setTranslation((2, 3, 4), at=4)
            node.setRotation((15, 20, 30), unit='deg')
            expected = list(node.getMatrix())
            node.setTranslation((0, 0, 0), at=4)
            node.setRotation((0, 0, 0))
            with self.api_only():
                node.setTranslation((2, 3, 4), fast=True, at=4)
                node.setRotation((15, 20, 30), unit='deg', fast=True)
                if kind == 'joint':
                    node.freezeRotation(fast=True)
                    node.jointOrientToRotate(fast=True)
            for a, b in zip(node.getMatrix(), expected):
                self.assertAlmostEqual(a, b, places=7)

    def test_geometry(self):
        mesh = hlib.getNode(cmds.listRelatives(cmds.polyCube(ch=False)[0], shapes=True)[0])
        curve = hlib.getNode(cmds.listRelatives(cmds.curve(d=1, p=[(0, 0, 0), (1, 2, 3), (4, 2, 1)]), shapes=True)[0])
        for points in (mesh.vertices(), curve.cvs()):
            before = points.getPosition()
            rows = [(x + .2, y * 2, z - .3) for x, y, z in before]
            points.setPositions(rows)
            expected = points.getPosition()
            points.setPositions(before)
            with self.api_only():
                points.setPositions(rows, fast=True)
            for actual, wanted in zip(points.getPosition(), expected):
                for a, b in zip(actual, wanted):
                    self.assertAlmostEqual(a, b, places=6)
        uvs = mesh.uvs()
        with self.api_only():
            uvs.setPosition((.2, .3), fast=True)
        for uv in uvs:
            for a, b in zip(uv.getPosition(), (.2, .3)):
                self.assertAlmostEqual(a, b, places=6)
        history = hlib.getNode(cmds.listRelatives(cmds.polyCube()[0], shapes=True)[0])
        with self.assertRaises(NotImplementedError):
            history.vertices().setPosition((1, 2, 3), fast=True)
        periodic = hlib.getNode(cmds.listRelatives(cmds.circle(ch=False)[0], shapes=True)[0])
        with self.assertRaises(NotImplementedError):
            periodic.cvs().mirror(fast=True)

    def test_skin(self):
        mesh = cmds.polyPlane(ch=False, sx=2, sy=2)[0]
        joints = [cmds.createNode('joint') for _ in range(3)]
        skin = hlib.getNode(cmds.skinCluster(joints, mesh, toSelectedBones=True)[0])
        for normalize in (0, 1, 2):
            cmds.setAttr(skin.fullName() + '.normalizeWeights', normalize)
            skin.setWeights(joints, [.2, .3, .5])
            expected = list(skin.getWeights(joints))
            skin.setWeights(joints, [1, 0, 0])
            with self.api_only():
                skin.setWeights(joints, [.2, .3, .5], fast=True)
            self.assertEqual(list(skin.getWeights(joints)), expected)

    def test_units_flags_and_bulk(self):
        node = hlib.getNode(cmds.createNode('transform'))
        old_angle = cmds.currentUnit(query=True, angle=True)
        old_linear = cmds.currentUnit(query=True, linear=True)
        try:
            for angle in ('deg', 'rad'):
                for linear in ('cm', 'm'):
                    cmds.currentUnit(angle=angle, linear=linear)
                    with self.api_only():
                        node.plug('rx').set(.4, fast=True)
                        node.plug('tx').set(.6, fast=True)
                    self.assertAlmostEqual(node.plug('rx').mplug().asMAngle().asRadians(), .4)
                    self.assertAlmostEqual(node.plug('tx').mplug().asMDistance().asCentimeters(), .6)
        finally:
            cmds.currentUnit(angle=old_angle, linear=old_linear)
        joints = [cmds.createNode('joint') for _ in range(2)]
        collection = hlib.ls(joints, type='joint')
        with self.api_only():
            collection.setTranslation((1, 2, 3), fast=True, at=4)
            node.setOutlinerColor((.1, .2, .3), fast=True)
            node.setOverrideColor(6, fast=True)
            node.setAttributeFlags(['tx'], locked=True, keyable=False, channelBox=True, fast=True)
        self.assertTrue(cmds.getAttr(node.fullName() + '.tx', lock=True))
        for joint in joints:
            self.assertEqual(cmds.getAttr(joint + '.translate')[0], (1, 2, 3))

    def test_skin_sparse_subset_and_limits(self):
        mesh = cmds.polyPlane(ch=False, sx=1, sy=1)[0]
        joints = [cmds.createNode('joint') for _ in range(4)]
        skin = hlib.getNode(cmds.skinCluster(joints, mesh, toSelectedBones=True)[0])
        cmds.skinCluster(skin.fullName(), edit=True, removeInfluence=joints[1])
        joints.pop(1)
        for maintain in (False, True):
            cmds.setAttr(skin.fullName() + '.maxInfluences', 1)
            cmds.setAttr(skin.fullName() + '.maintainMaxInfluences', maintain)
            cmds.setAttr(joints[2] + '.liw', True)
            skin.setWeights(joints, [.2, .3, .5])
            skin.setWeights([joints[2]], [.4, .3, .2, .1])
            expected = list(skin.getWeights(joints))
            skin.setWeights(joints, [.2, .3, .5])
            with self.api_only():
                skin.setWeights([joints[2]], [.4, .3, .2, .1], fast=True)
            self.assertEqual(list(skin.getWeights(joints)), expected)

    def test_data_types_and_connections(self):
        node = hlib.getNode(cmds.createNode('network'))
        for name, kind in [('text', 'string'), ('numbers', 'doubleArray'), ('matrixValue', 'matrix')]:
            cmds.addAttr(node.fullName(), longName=name, dataType=kind)
        cmds.addAttr(node.fullName(), longName='timeValue', attributeType='time')
        cmds.addAttr(node.fullName(), longName='choice', attributeType='enum', enumName='a:b:c')
        cmds.addAttr(node.fullName(), longName='limited', attributeType='double', minValue=0, maxValue=1)
        for value in (-1, 2):
            with self.assertRaises(RuntimeError):
                node.plug('limited').set(value, fast=True)
        self.assertEqual(cmds.getAttr(node.fullName() + '.limited'), 0)
        with self.api_only():
            node.plug('text').set('hello', fast=True)
            node.plug('numbers').set([1., 2., 3.], fast=True)
            node.plug('matrixValue').set([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 2, 3, 4, 1], fast=True)
            node.plug('timeValue').set(12, fast=True)
            node.plug('choice').set(2, fast=True)
        self.assertEqual(cmds.getAttr(node.fullName() + '.text'), 'hello')
        self.assertEqual(list(cmds.getAttr(node.fullName() + '.numbers')), [1, 2, 3])
        self.assertEqual(node.plug('timeValue').mplug().asMTime().asUnits(__import__('maya.api.OpenMaya', fromlist=['MTime']).MTime.kSeconds), 12)
        self.assertEqual(cmds.getAttr(node.fullName() + '.choice'), 2)
        a, b = [cmds.createNode('transform') for _ in range(2)]
        cmds.connectAttr(a + '.tx', b + '.tx')
        with self.assertRaises(RuntimeError):
            hlib.getNode(b).plug('tx').set(10, fast=True)

    def test_geometry_world_space_and_units(self):
        transform = cmds.polyCube(ch=False)[0]
        cmds.setAttr(transform + '.translate', 10, 20, 30)
        cmds.setAttr(transform + '.rotate', 20, 30, 40)
        cmds.setAttr(transform + '.scale', 2, 3, 4)
        shape = hlib.getNode(cmds.listRelatives(transform, shapes=True)[0])
        points = shape.vertices([1, 3, 5])
        old = cmds.currentUnit(query=True, linear=True)
        try:
            for unit in ('cm', 'm'):
                cmds.currentUnit(linear=unit)
                rows = [(1, 2, 3), (2, 4, 6), (3, 6, 9)]
                with self.api_only():
                    points.setPositions(rows, ws=True, fast=True)
                for actual, expected in zip(points.getPosition(ws=True), rows):
                    for a, b in zip(actual, expected):
                        # Mesh内部のfloat座標を非一様スケールで変換した丸め誤差。
                        self.assertAlmostEqual(a, b, delta=1e-5)
        finally:
            cmds.currentUnit(linear=old)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
