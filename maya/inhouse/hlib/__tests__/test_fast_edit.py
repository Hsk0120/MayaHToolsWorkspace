"""明示的なOpenMaya編集の値・Undo・エラー時のコンテキストを検証する。"""
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
        node = hlib.node(cmds.createNode('transform'))
        sentinel = cmds.createNode('transform')
        cmds.setAttr(sentinel + '.tx', 5)
        undo_name = cmds.undoInfo(query=True, undoName=True)
        with self.api_only():
            node.plug('tx').set(12, fast=True)
            node.plug('visibility').set(False, fast=True)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        cmds.undo()
        self.assertEqual(cmds.getAttr(sentinel + '.tx'), 0)
        self.assertEqual(cmds.getAttr(node.full_name() + '.tx'), 12)
        node.plug('tx').set(24)
        cmds.undo()
        self.assertEqual(node.plug('tx').get(), 12)
        with self.assertRaises(TypeError):
            node.plug('tx').set(0, fast=1)
        cmds.setAttr(node.full_name() + '.tx', lock=True)
        with self.assertRaises(RuntimeError):
            node.plug('tx').set(0, fast=True)
        cmds.setAttr(node.full_name() + '.tx', lock=False)
        node.plug('tx').set(33)
        cmds.undo()
        self.assertEqual(node.plug('tx').get(), 12)

    def test_transform_and_joint(self):
        for kind in ('transform', 'joint'):
            node = hlib.node(cmds.createNode(kind))
            node.set_translate((2, 3, 4))
            node.set_rotate((15, 20, 30), unit='deg')
            expected = list(node.get_matrix())
            node.set_translate((0, 0, 0))
            node.set_rotate((0, 0, 0))
            with self.api_only():
                node.set_translate((2, 3, 4), fast=True)
                node.set_rotate((15, 20, 30), unit='deg', fast=True)
                if kind == 'joint':
                    node.freeze_rotation(fast=True)
                    node.joint_orient_to_rotate(fast=True)
            for a, b in zip(node.get_matrix(), expected):
                self.assertAlmostEqual(a, b, places=7)

    def test_geometry(self):
        mesh = hlib.node(cmds.listRelatives(cmds.polyCube(ch=False)[0], shapes=True)[0])
        curve = hlib.node(cmds.listRelatives(cmds.curve(d=1, p=[(0, 0, 0), (1, 2, 3), (4, 2, 1)]), shapes=True)[0])
        for points in (mesh.vertices(), curve.cvs()):
            before = points.get_positions()
            rows = [(x + .2, y * 2, z - .3) for x, y, z in before]
            points.set_positions(rows)
            expected = points.get_positions()
            points.set_positions(before)
            with self.api_only():
                points.set_positions(rows, fast=True)
            for actual, wanted in zip(points.get_positions(), expected):
                for a, b in zip(actual, wanted):
                    self.assertAlmostEqual(a, b, places=6)
        uvs = mesh.uvs()
        with self.api_only():
            uvs.set_position((.2, .3), fast=True)
        for uv in uvs:
            for a, b in zip(uv.get_position(), (.2, .3)):
                self.assertAlmostEqual(a, b, places=6)
        history = hlib.node(cmds.listRelatives(cmds.polyCube()[0], shapes=True)[0])
        with self.assertRaises(NotImplementedError):
            history.vertices().set_position((1, 2, 3), fast=True)
        periodic = hlib.node(cmds.listRelatives(cmds.circle(ch=False)[0], shapes=True)[0])
        with self.assertRaises(NotImplementedError):
            periodic.cvs().mirror(fast=True)

    def test_skin(self):
        mesh = cmds.polyPlane(ch=False, sx=2, sy=2)[0]
        joints = [cmds.createNode('joint') for _ in range(3)]
        skin = hlib.node(cmds.skinCluster(joints, mesh, toSelectedBones=True)[0])
        for normalize in (0, 1, 2):
            cmds.setAttr(skin.full_name() + '.normalizeWeights', normalize)
            skin.set_weights(joints, [.2, .3, .5])
            expected = list(skin.get_weights(joints))
            skin.set_weights(joints, [1, 0, 0])
            with self.api_only():
                skin.set_weights(joints, [.2, .3, .5], fast=True)
            self.assertEqual(list(skin.get_weights(joints)), expected)

    def test_units_flags_and_bulk(self):
        node = hlib.node(cmds.createNode('transform'))
        old_angle = cmds.currentUnit(query=True, angle=True)
        old_linear = cmds.currentUnit(query=True, linear=True)
        try:
            for angle in ('deg', 'rad'):
                for linear in ('cm', 'm'):
                    cmds.currentUnit(angle=angle, linear=linear)
                    with self.api_only():
                        node.plug('rx').set(.4, fast=True)
                        node.plug('tx').set(.6, fast=True)
                    self.assertAlmostEqual(cmds.getAttr(node.full_name() + '.rx'), .4)
                    self.assertAlmostEqual(cmds.getAttr(node.full_name() + '.tx'), .6)
        finally:
            cmds.currentUnit(angle=old_angle, linear=old_linear)
        joints = [cmds.createNode('joint') for _ in range(2)]
        collection = hlib.ls(joints, type='joint')
        with self.api_only():
            collection.set_translate((1, 2, 3), fast=True)
            node.set_outliner_color((.1, .2, .3), fast=True)
            node.set_override_color(6, fast=True)
            node.set_attr_flags(['tx'], locked=True, keyable=False, channel_box=True, fast=True)
        self.assertTrue(cmds.getAttr(node.full_name() + '.tx', lock=True))
        for joint in joints:
            self.assertEqual(cmds.getAttr(joint + '.translate')[0], (1, 2, 3))

    def test_skin_sparse_subset_and_limits(self):
        mesh = cmds.polyPlane(ch=False, sx=1, sy=1)[0]
        joints = [cmds.createNode('joint') for _ in range(4)]
        skin = hlib.node(cmds.skinCluster(joints, mesh, toSelectedBones=True)[0])
        cmds.skinCluster(skin.full_name(), edit=True, removeInfluence=joints[1])
        joints.pop(1)
        for maintain in (False, True):
            cmds.setAttr(skin.full_name() + '.maxInfluences', 1)
            cmds.setAttr(skin.full_name() + '.maintainMaxInfluences', maintain)
            cmds.setAttr(joints[2] + '.liw', True)
            skin.set_weights(joints, [.2, .3, .5])
            skin.set_weights([joints[2]], [.4, .3, .2, .1])
            expected = list(skin.get_weights(joints))
            skin.set_weights(joints, [.2, .3, .5])
            with self.api_only():
                skin.set_weights([joints[2]], [.4, .3, .2, .1], fast=True)
            self.assertEqual(list(skin.get_weights(joints)), expected)

    def test_data_types_and_connections(self):
        node = hlib.node(cmds.createNode('network'))
        for name, kind in [('text', 'string'), ('numbers', 'doubleArray'), ('matrixValue', 'matrix')]:
            cmds.addAttr(node.full_name(), longName=name, dataType=kind)
        cmds.addAttr(node.full_name(), longName='timeValue', attributeType='time')
        cmds.addAttr(node.full_name(), longName='choice', attributeType='enum', enumName='a:b:c')
        cmds.addAttr(node.full_name(), longName='limited', attributeType='double', minValue=0, maxValue=1)
        for value in (-1, 2):
            with self.assertRaises(RuntimeError):
                node.plug('limited').set(value, fast=True)
        self.assertEqual(cmds.getAttr(node.full_name() + '.limited'), 0)
        with self.api_only():
            node.plug('text').set('hello', fast=True)
            node.plug('numbers').set([1., 2., 3.], fast=True)
            node.plug('matrixValue').set([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 2, 3, 4, 1], fast=True)
            node.plug('timeValue').set(12, fast=True)
            node.plug('choice').set(2, fast=True)
        self.assertEqual(cmds.getAttr(node.full_name() + '.text'), 'hello')
        self.assertEqual(list(cmds.getAttr(node.full_name() + '.numbers')), [1, 2, 3])
        self.assertEqual(cmds.getAttr(node.full_name() + '.timeValue'), 12)
        self.assertEqual(cmds.getAttr(node.full_name() + '.choice'), 2)
        a, b = [cmds.createNode('transform') for _ in range(2)]
        cmds.connectAttr(a + '.tx', b + '.tx')
        with self.assertRaises(RuntimeError):
            hlib.node(b).plug('tx').set(10, fast=True)

    def test_geometry_world_space_and_units(self):
        transform = cmds.polyCube(ch=False)[0]
        cmds.setAttr(transform + '.translate', 10, 20, 30)
        cmds.setAttr(transform + '.rotate', 20, 30, 40)
        cmds.setAttr(transform + '.scale', 2, 3, 4)
        shape = hlib.node(cmds.listRelatives(transform, shapes=True)[0])
        points = shape.vertices([1, 3, 5])
        old = cmds.currentUnit(query=True, linear=True)
        try:
            for unit in ('cm', 'm'):
                cmds.currentUnit(linear=unit)
                rows = [(1, 2, 3), (2, 4, 6), (3, 6, 9)]
                with self.api_only():
                    points.set_positions(rows, ws=True, fast=True)
                for actual, expected in zip(points.get_positions(ws=True), rows):
                    for a, b in zip(actual, expected):
                        # Mesh内部のfloat座標を非一様スケールで変換した丸め誤差。
                        self.assertAlmostEqual(a, b, delta=1e-5)
        finally:
            cmds.currentUnit(linear=old)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
