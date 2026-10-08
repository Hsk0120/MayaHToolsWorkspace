"""命名整理後の共通API・旧入口拒否・公開境界を検証する。"""

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
        cmds.addAttr(driver.getFullName(), longName='driver', attributeType='double')
        source = driver.getPlug('driver')
        curve = hlib.createNode('animCurveUU')
        source.connectTo(curve.getPlug('input'))
        curve.setKey(0, 2)
        curve.setKey(3, 5)
        blend = hlib.createNode('blendWeighted')
        blend.connectInput(0, source)
        for node in (curve, blend):
            self.assertEqual([p.getFullName() for p in node.getInputs(type='transform')], [source.getFullName()])
            self.assertEqual(node.getInputs(type='mesh'), [])
        self.assertEqual(curve.getKeyInputs(), [0, 3])
        self.assertEqual(blend.getInputPlugs()[0].getNode(), blend)

    def test_live_queries_and_stored_properties(self):
        node = hlib.createNode('joint')
        plug = node.getPlug('translateX')
        self.assertTrue(callable(node.getFullName))
        self.assertTrue(callable(node.isLocked))
        self.assertTrue(callable(plug.getName))
        self.assertTrue(inspect.isfunction(inspect.getattr_static(type(plug), 'getNode')))
        before = node.getFullName()
        node.rename('renamed')
        self.assertNotEqual(node.getFullName(), before)
        self.assertTrue(plug.getFullName().startswith(node.getName() + '.'))
        self.assertIsInstance(hlib.nodes.Joints([node]).getUuid(), list)

    def test_public_collection_has_no_deletion_workflow(self):
        for name in ('gather', 'apply', 'finalize'):
            self.assertFalse(hasattr(hlib.nodes.SkinClusters, name))
        joint = hlib.createNode('joint')
        child = hlib.createNode('joint', parent=joint.getFullName())
        self.assertEqual(child.getParentJointName(), joint.getName())
        self.assertEqual(joint.getChildJointNames(), [child.getName()])

    def test_math_types_and_old_json_records(self):
        from hlib.json.codec import encode, decode
        from hlib.maths import Translation, EulerRotation
        self.assertFalse(hasattr(hlib.maths, 'Translate'))
        self.assertFalse(hasattr(hlib.maths, 'Rotate'))
        for old, cls in (('Translate', Translation), ('Rotate', EulerRotation)):
            with self.assertRaises(ValueError):
                decode({'type': 'math:' + old, 'value': encode({'values': [1, 2, 3]})})
            value = decode(encode(cls(1, 2, 3)))
            self.assertIsInstance(value, cls)
            self.assertEqual(tuple(value), (1, 2, 3))

    def test_matrix_has_no_compatibility_entries(self):
        from hlib.maths import Matrix
        with self.assertRaises(TypeError):
            Matrix(rotation=(0, 0, 0))
        for name in ('rotation', '_wrap_copy', 'to_mmatrix'):
            self.assertFalse(hasattr(Matrix, name), name)
        matrix = Matrix(rotate=(0.1, 0.2, 0.3))
        self.assertEqual(set(matrix.decompose()), {'translate', 'euler', 'quaternion', 'scale', 'shear'})

    def test_module_paths(self):
        for module, cls in (('common.channelBox', 'ChannelBox'),
                            ('common.timeSlider', 'TimeSlider'),
                            ('common.drivenKey', 'DrivenKey'),
                            ('maths.eulerRotation', 'EulerRotation'),
                            ('maths.translation', 'Translation')):
            self.assertTrue(inspect.isclass(getattr(importlib.import_module('hlib.' + module), cls)))
        self.assertTrue(callable(hlib.getChannelBox))
        self.assertTrue(callable(hlib.getTimeSlider))
        self.assertTrue(callable(hlib.getDrivenKey))
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
