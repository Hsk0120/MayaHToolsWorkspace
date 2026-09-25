"""命名整理後の共通API・保存データ互換・公開境界を検証する。"""

import importlib
import inspect
import sys
import types
import unittest
import uuid

import maya.cmds as cmds
import hlib


class ApiNamingTest(unittest.TestCase):
    def setUp(self):
        self.previous_namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.selection = cmds.ls(selection=True, long=True) or []
        self.namespace = ':hlibNaming_' + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        cmds.namespace(set=self.previous_namespace)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        if self.selection:
            cmds.select(self.selection, replace=True)
        else:
            cmds.select(clear=True)

    def test_subclasses_keep_node_connection_queries(self):
        driver = hlib.createNode('transform')
        cmds.addAttr(driver.full_name(), longName='driver', attributeType='double')
        source = driver.plug('driver')
        curve = hlib.createNode('animCurveUU')
        source.connect(curve.plug('input'))
        curve.set_key(0, 2)
        curve.set_key(3, 5)
        blend = hlib.createNode('blendWeighted')
        blend.connect_input(0, source)
        for node in (curve, blend):
            self.assertEqual([p.full_name() for p in node.inputs(type='transform')], [source.full_name()])
            self.assertEqual(node.inputs(type='mesh'), [])
        self.assertEqual(curve.key_inputs(), [0, 3])
        self.assertEqual(blend.input_plugs()[0].node, blend)

    def test_live_queries_and_stored_properties(self):
        node = hlib.createNode('joint')
        plug = node.plug('translateX')
        self.assertTrue(callable(node.full_name))
        self.assertTrue(callable(node.is_locked))
        self.assertTrue(callable(plug.name))
        self.assertIsInstance(inspect.getattr_static(type(plug), 'node'), property)
        before = node.full_name()
        node.rename('renamed')
        self.assertNotEqual(node.full_name(), before)
        self.assertTrue(plug.full_name().startswith(node.name() + '.'))
        self.assertIsInstance(hlib.nodes.Joints([node]).uuid(), list)

    def test_public_collection_has_no_deletion_workflow(self):
        for name in ('gather', 'apply', 'finalize'):
            self.assertFalse(hasattr(hlib.nodes.SkinClusters, name))
        joint = hlib.createNode('joint')
        child = hlib.createNode('joint', parent=joint.full_name())
        self.assertEqual(child.parent_joint_name(), joint.name())
        self.assertEqual(joint.child_joint_names(), [child.name()])

    def test_math_types_and_old_json_records(self):
        from hlib.json.codec import encode, decode
        from hlib.maths import Translation, EulerRotation
        self.assertFalse(hasattr(hlib.maths, 'Translate'))
        self.assertFalse(hasattr(hlib.maths, 'Rotate'))
        for old, cls in (('Translate', Translation), ('Rotate', EulerRotation)):
            value = decode({'type': 'math:' + old, 'value': encode({'values': [1, 2, 3]})})
            self.assertIsInstance(value, cls)
            self.assertEqual(tuple(value), (1, 2, 3))

    def test_module_paths(self):
        for module, cls in (('editors.channel_box', 'ChannelBox'),
                            ('editors.time_slider', 'TimeSlider'),
                            ('animation.driven_key', 'DrivenKey'),
                            ('maths.euler_rotation', 'EulerRotation'),
                            ('maths.translation', 'Translation')):
            self.assertTrue(inspect.isclass(getattr(importlib.import_module('hlib.' + module), cls)))
        self.assertTrue(callable(hlib.channelBox))
        self.assertTrue(callable(hlib.timeSlider))
        self.assertTrue(callable(hlib.drivenKey))
        self.assertTrue(inspect.isclass(hlib.json.NurbsCurveSnapshot))

    def test_reload_removes_old_module_and_class_exports(self):
        old_module = types.ModuleType('hlib.maths.rotate')
        sys.modules[old_module.__name__] = old_module
        hlib.maths.rotate = old_module
        hlib.maths.Rotate = object
        hlib.maths.Translate = object
        hlib.json.CurveSnapshot = object
        snapshots = importlib.import_module('hlib.json.snapshots')
        snapshots.CurveSnapshot = object
        hlib.reload()
        self.assertNotIn(old_module.__name__, sys.modules)
        self.assertFalse(hasattr(hlib.maths, 'rotate'))
        self.assertFalse(hasattr(hlib.maths, 'Rotate'))
        self.assertFalse(hasattr(hlib.maths, 'Translate'))
        self.assertFalse(hasattr(hlib.json, 'CurveSnapshot'))
        self.assertFalse(hasattr(snapshots, 'CurveSnapshot'))
        self.assertEqual(tuple(hlib.maths.Translation(1, 2, 3)), (1, 2, 3))


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
