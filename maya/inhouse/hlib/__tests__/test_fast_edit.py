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
            node.getPlug('tx').set(12, fast=True)
            node.getPlug('visibility').set(False, fast=True)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        cmds.undo()
        self.assertEqual(cmds.getAttr(sentinel + '.tx'), 0)
        self.assertEqual(cmds.getAttr(node.getFullName() + '.tx'), 12)
        node.getPlug('tx').set(24)
        cmds.undo()
        self.assertEqual(node.getPlug('tx').get(), 12)
        with self.assertRaises(TypeError):
            node.getPlug('tx').set(0, fast=1)
        cmds.setAttr(node.getFullName() + '.tx', lock=True)
        with self.assertRaises(RuntimeError):
            node.getPlug('tx').set(0, fast=True)
        cmds.setAttr(node.getFullName() + '.tx', lock=False)
        node.getPlug('tx').set(33)
        cmds.undo()
        self.assertEqual(node.getPlug('tx').get(), 12)

    def test_transform_and_joint(self):
        for kind in ('transform', 'joint'):
            node = hlib.getNode(cmds.createNode(kind))
            node.setTranslate((2, 3, 4), at=4)
            node.setRotate((15, 20, 30), unit='deg')
            expected = list(node.getMatrix())
            node.setTranslate((0, 0, 0), at=4)
            node.setRotate((0, 0, 0))
            with self.api_only():
                node.setTranslate((2, 3, 4), fast=True, at=4)
                node.setRotate((15, 20, 30), unit='deg', fast=True)
                if kind == 'joint':
                    node.freezeRotate(fast=True)
                    node.jointOrientToRotate(fast=True)
            for a, b in zip(node.getMatrix(), expected):
                self.assertAlmostEqual(a, b, places=7)

    def test_geometry(self):
        mesh = hlib.getNode(cmds.listRelatives(cmds.polyCube(ch=False)[0], shapes=True)[0])
        curve = hlib.getNode(cmds.listRelatives(cmds.curve(d=1, p=[(0, 0, 0), (1, 2, 3), (4, 2, 1)]), shapes=True)[0])
        for points in (mesh.getVertices(), curve.cvs()):
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
            history.getVertices().setPosition((1, 2, 3), fast=True)
        periodic = hlib.getNode(cmds.listRelatives(cmds.circle(ch=False)[0], shapes=True)[0])
        with self.assertRaises(NotImplementedError):
            periodic.cvs().mirror(fast=True)

    def test_skin(self):
        mesh = cmds.polyPlane(ch=False, sx=2, sy=2)[0]
        joints = [cmds.createNode('joint') for _ in range(3)]
        skin = hlib.getNode(cmds.skinCluster(joints, mesh, toSelectedBones=True)[0])
        for normalize in (0, 1, 2):
            cmds.setAttr(skin.getFullName() + '.normalizeWeights', normalize)
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
                        node.getPlug('rx').set(.4, fast=True)
                        node.getPlug('tx').set(.6, fast=True)
                    self.assertAlmostEqual(node.getPlug('rx').mplug().asMAngle().asRadians(), .4)
                    self.assertAlmostEqual(node.getPlug('tx').mplug().asMDistance().asCentimeters(), .6)
        finally:
            cmds.currentUnit(angle=old_angle, linear=old_linear)
        joints = [cmds.createNode('joint') for _ in range(2)]
        collection = hlib.ls(joints, type='joint')
        with self.api_only():
            collection.setTranslate((1, 2, 3), fast=True, at=4)
            node.setOutlinerColor((.1, .2, .3), fast=True)
            node.setOverrideColor(6, fast=True)
            node.setAttrFlags(['tx'], locked=True, keyable=False, channelBox=True, fast=True)
        self.assertTrue(cmds.getAttr(node.getFullName() + '.tx', lock=True))
        for joint in joints:
            self.assertEqual(cmds.getAttr(joint + '.translate')[0], (1, 2, 3))

    def test_skin_sparse_subset_and_limits(self):
        mesh = cmds.polyPlane(ch=False, sx=1, sy=1)[0]
        joints = [cmds.createNode('joint') for _ in range(4)]
        skin = hlib.getNode(cmds.skinCluster(joints, mesh, toSelectedBones=True)[0])
        cmds.skinCluster(skin.getFullName(), edit=True, removeInfluence=joints[1])
        joints.pop(1)
        for maintain in (False, True):
            cmds.setAttr(skin.getFullName() + '.maxInfluences', 1)
            cmds.setAttr(skin.getFullName() + '.maintainMaxInfluences', maintain)
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
            cmds.addAttr(node.getFullName(), longName=name, dataType=kind)
        cmds.addAttr(node.getFullName(), longName='timeValue', attributeType='time')
        cmds.addAttr(node.getFullName(), longName='choice', attributeType='enum', enumName='a:b:c')
        cmds.addAttr(node.getFullName(), longName='limited', attributeType='double', minValue=0, maxValue=1)
        for value in (-1, 2):
            with self.assertRaises(RuntimeError):
                node.getPlug('limited').set(value, fast=True)
        self.assertEqual(cmds.getAttr(node.getFullName() + '.limited'), 0)
        with self.api_only():
            node.getPlug('text').set('hello', fast=True)
            node.getPlug('numbers').set([1., 2., 3.], fast=True)
            node.getPlug('matrixValue').set([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 2, 3, 4, 1], fast=True)
            node.getPlug('timeValue').set(12, fast=True)
            node.getPlug('choice').set(2, fast=True)
        self.assertEqual(cmds.getAttr(node.getFullName() + '.text'), 'hello')
        self.assertEqual(list(cmds.getAttr(node.getFullName() + '.numbers')), [1, 2, 3])
        self.assertEqual(node.getPlug('timeValue').mplug().asMTime().asUnits(__import__('maya.api.OpenMaya', fromlist=['MTime']).MTime.kSeconds), 12)
        self.assertEqual(cmds.getAttr(node.getFullName() + '.choice'), 2)
        a, b = [cmds.createNode('transform') for _ in range(2)]
        cmds.connectAttr(a + '.tx', b + '.tx')
        with self.assertRaises(RuntimeError):
            hlib.getNode(b).getPlug('tx').set(10, fast=True)

    def test_geometry_world_space_and_units(self):
        transform = cmds.polyCube(ch=False)[0]
        cmds.setAttr(transform + '.translate', 10, 20, 30)
        cmds.setAttr(transform + '.rotate', 20, 30, 40)
        cmds.setAttr(transform + '.scale', 2, 3, 4)
        shape = hlib.getNode(cmds.listRelatives(transform, shapes=True)[0])
        points = shape.getVertices([1, 3, 5])
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
