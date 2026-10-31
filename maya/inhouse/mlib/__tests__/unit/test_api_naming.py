"""命名整理後の共通API・旧入口拒否・公開境界を検証する。"""

import importlib
import inspect
import sys
import types
import unittest
import uuid

import maya.cmds as cmds
import mlib


class ApiNamingTest(unittest.TestCase):
    def setUp(self):
        self.previous_namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.selection = cmds.ls(selection=True, long=True) or []
        self.namespace = ':mlibNaming_' + uuid.uuid4().hex
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
        driver = mlib.createNode('transform')
        cmds.addAttr(driver.getFullName(), longName='driver', attributeType='double')
        source = driver.getPlug('driver')
        curve = mlib.createNode('animCurveUU')
        source.connectTo(curve.getPlug('input'))
        curve.setKey(0, 2)
        curve.setKey(3, 5)
        blend = mlib.createNode('blendWeighted')
        source.connectTo(blend.getPlug("input")[0])
        for node in (curve, blend):
            self.assertEqual([p.getFullName() for p in node.getConnections(True, False, type='transform', skipConversionNodes=True)], [source.getFullName()])
            self.assertEqual(node.getConnections(True, False, type='mesh', skipConversionNodes=True), [])
        self.assertEqual(curve.getKeyInputs(), [0, 3])
        self.assertEqual(blend.getPlug("input").getElement(0).getNode(), blend)

    def test_live_queries_and_stored_properties(self):
        node = mlib.createNode('joint')
        plug = node.getPlug('translateX')
        self.assertTrue(callable(node.getFullName))
        self.assertTrue(callable(node.isLocked))
        self.assertTrue(callable(plug.getName))
        self.assertTrue(inspect.isfunction(inspect.getattr_static(type(plug), 'getNode')))
        before = node.getFullName()
        node.rename('renamed')
        self.assertNotEqual(node.getFullName(), before)
        self.assertTrue(plug.getFullName().startswith(node.getName() + '.'))
        self.assertEqual([joint.getUuid() for joint in mlib.nodes.Joints([node])], [node.getUuid()])

    def test_public_collection_has_no_deletion_workflow(self):
        for name in ('gather', 'apply', 'finalize'):
            self.assertFalse(hasattr(mlib.nodes.SkinClusters, name))
        joint = mlib.createNode('joint')
        child = mlib.createNode('joint', parent=joint.getFullName())
        self.assertEqual(child.getParent(), joint)
        self.assertEqual(joint.getChildren(type="joint"), [child])

    def test_math_type_names(self):
        """数学型の正式名と値を保ち、旧名を再公開しない。"""
        from mlib.maths import Translate, EulerRotate
        self.assertIs(mlib.maths.Translate, Translate)
        self.assertIs(mlib.maths.EulerRotate, EulerRotate)
        for old in ("Translation", "EulerRotation", "Rotate"):
            self.assertFalse(hasattr(mlib.maths, old))
        self.assertEqual(tuple(Translate(1, 2, 3)), (1, 2, 3))
        self.assertEqual(tuple(EulerRotate(1, 2, 3)), (1, 2, 3))

    def test_matrix_has_no_compatibility_entries(self):
        from mlib.maths import Matrix
        with self.assertRaises(TypeError):
            Matrix(rotation=(0, 0, 0))
        for name in ('rotation', '_wrap_copy', 'to_mmatrix'):
            self.assertFalse(hasattr(Matrix, name), name)
        matrix = Matrix(rotate=(0.1, 0.2, 0.3))
        self.assertEqual(set(matrix.decompose()), {'translate', 'euler', 'quaternion', 'scale', 'shear'})

    def test_module_paths(self):
        for module, cls in (("common.drivenKey", "DrivenKey"),
                            ("maths.eulerRotate", "EulerRotate"),
                            ("maths.translate", "Translate")):
            self.assertTrue(inspect.isclass(getattr(importlib.import_module("mlib." + module), cls)))
        self.assertTrue(callable(mlib.getNode))
        self.assertTrue(callable(mlib.getPlug))

    def test_reload_removes_old_module_and_class_exports(self):
        old_module = types.ModuleType('mlib.maths.eulerRotation')
        sys.modules[old_module.__name__] = old_module
        mlib.maths.eulerRotation = old_module
        mlib.maths.Rotate = object
        mlib.maths.Translation = object
        mlib.maths.EulerRotation = object
        mlib.reload()
        self.assertNotIn(old_module.__name__, sys.modules)
        self.assertFalse(hasattr(mlib.maths, 'eulerRotation'))
        self.assertFalse(hasattr(mlib.maths, 'Rotate'))
        self.assertFalse(hasattr(mlib.maths, 'Translation'))
        self.assertFalse(hasattr(mlib.maths, 'EulerRotation'))
        self.assertEqual(tuple(mlib.maths.Translate(1, 2, 3)), (1, 2, 3))
        self.assertEqual(tuple(mlib.maths.EulerRotate(1, 2, 3)), (1, 2, 3))


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
