"""mlrigのControlHierarchyとmlibのTransformの連携を検証する。"""
import unittest
import maya.cmds as cmds
from mlib.nodes import Node
from mlib.maths import Translate
from mlrig.setups import ControlHierarchy

class ControlHierarchyTest(unittest.TestCase):
    namespace = ":mlibNodeApiTest"
    def setUp(self):
        self.created = []
        if cmds.namespace(exists=self.namespace):
            cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.namespace(add=self.namespace)

    def tearDown(self):
        for node in reversed(self.created):
            if cmds.objExists(node):
                cmds.delete(node)
        if cmds.namespace(exists=self.namespace):
            cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def create_transform(self, name):
        node = Node.create(type="transform", name=name)
        self.created.append(node.getName())
        return node

    def test_transform_unlock_and_disconnect_transform_channels_unlocks_and_disconnects(self):
        driver = self.create_transform("mlibNodeApiReleaseDriver")
        transform = self.create_transform("mlibNodeApiRelease")
        driver.getPlug("translateX").connectTo(transform.getPlug("translateX"))
        transform.getPlug("translate").setFlags(locked=True)
        transform.getPlug("rotateY").setFlags(locked=True)

        result = ControlHierarchy.unlockAndDisconnectTransformChannels(transform)
        self.assertIs(result, transform)
        self.assertFalse(transform.getPlug("translate").isLocked())
        self.assertFalse(transform.getPlug("translateX").isLocked())
        self.assertFalse(transform.getPlug("rotateY").isLocked())
        self.assertIsNone(transform.getPlug('translateX').getSource(skipConversionNodes=False))

    def test_transform_create_offset_groups_preserves_world_position(self):
        parent = self.create_transform("mlibNodeApiOffsetParent")
        parent.setTranslate((5.0, 0.0, 0.0), at=4)
        transform = self.create_transform("mlibNodeApiOffsetChild")
        transform.setParent(parent)
        transform.setTranslate((1.0, 2.0, 3.0), at=4)
        world_translate = transform.getTranslate(ws=True, at=4)

        zero, offset = ControlHierarchy.createOffsetGroups(transform, 'mlibNodeApiZero', 'mlibNodeApiOffset')
        self.created.extend([zero.getName(), offset.getName()])

        self.assertEqual(zero.getParent().getName(), parent.getName())
        self.assertEqual(offset.getParent().getName(), zero.getName())
        self.assertEqual(transform.getParent().getName(), offset.getName())
        self.assertEqual(zero.getTranslate(ws=True, at=4), world_translate)
        self.assertEqual(offset.getTranslate(ws=True, at=4), world_translate)
        self.assertEqual(transform.getTranslate(ws=True, at=4), world_translate)
        self.assertEqual(transform.getTranslate(at=4), Translate(0.0, 0.0, 0.0))

if __name__ == "__main__":
    unittest.main()
