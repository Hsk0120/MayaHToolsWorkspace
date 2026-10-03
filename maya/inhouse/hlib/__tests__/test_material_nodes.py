"""Mayaの継承・シェーダー接続・面割り当てを検証する。"""
import sys
import unittest
import maya.cmds as cmds
import hlib
hlib.reload()
from hlib.nodes import Node, Lambert, Reflect, Blinn, StandardSurface, ShadingEngine, File


class MaterialNodesTest(unittest.TestCase):
    """専用namespace内で割り当てを検証する。"""

    def setUp(self):
        self.old = cmds.namespaceInfo(currentNamespace=True)
        self.ns = cmds.namespace(add="hlibMaterialTest")
        cmds.namespace(set=self.ns)

    def tearDown(self):
        cmds.namespace(set=self.old)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_maya_inheritance(self):
        for kind in ("lambert", "blinn", "phong", "phongE", "standardSurface", "surfaceShader",
                     "file", "place2dTexture", "place3dTexture"):
            node = hlib.createNode(kind)
            native = cmds.nodeType(kind, isTypeName=True, inherited=True)
            for cls in type(node).__mro__:
                key = cls.__dict__.get("__hlib_node_type__")
                if key and key != "dependNode":
                    self.assertIn(key, native)
        self.assertTrue(issubclass(Blinn, Reflect))
        self.assertTrue(issubclass(Reflect, Lambert))
        self.assertFalse(issubclass(StandardSurface, Lambert))

    def test_assignment_faces_and_undo(self):
        mesh = Node(cmds.polyCube()[0]).shape()
        material = hlib.createShader("lambert")
        second = hlib.createShader("standardSurface")
        group = hlib.createShadingGroup(material)
        other = hlib.createShadingGroup(second)
        self.assertIsInstance(group, ShadingEngine)
        group.assign(mesh)
        self.assertEqual(mesh.materials(), [material])
        other.assign(mesh.faces([0, 1]))
        self.assertEqual(mesh.face(0).material(), second)
        self.assertEqual(mesh.face(2).material(), material)
        self.assertEqual(mesh.faces([0, 1]).materials(), [second])
        self.assertTrue(all(member.shape == mesh for member in other.members()))
        self.assertEqual(material.shadingEngines(), [group])
        self.assertTrue(material.assignedObjects())
        cmds.undo()
        self.assertEqual(mesh.face(0).material(), material)

    def test_instance_assignments(self):
        transform = Node(cmds.polyCube()[0])
        instance = Node(cmds.instance(transform.fullName())[0])
        a = hlib.createShadingGroup(hlib.createShader("lambert"))
        b = hlib.createShadingGroup(hlib.createShader("blinn"))
        a.assign(transform)
        b.assign(instance)
        self.assertEqual(transform.shape().shadingEngines(), [a])
        self.assertEqual(instance.shape().shadingEngines(), [b])

    def test_texture_connections(self):
        texture = hlib.createNode("file")
        place = hlib.createNode("place2dTexture")
        self.assertIsInstance(texture, File)
        texture.setFilePath("test.<UDIM>.exr")
        self.assertEqual(texture.getFilePath(), "test.<UDIM>.exr")
        place.connectTexture(texture)
        self.assertEqual(texture.getPlacement(), place)
        place.connectTexture(texture)

    def test_shader_ports_and_aliases(self):
        material = hlib.createShader("surfaceShader", n="surface")
        group = hlib.createShadingGroup(n="surfaceSG")
        self.assertIsNone(group.getShader())
        group.setShader(material.plug("outColor"))
        self.assertEqual(group.getShaderPlug(), material.plug("outColor"))
        replacement = hlib.createShader("lambert")
        group.setShader(replacement)
        self.assertEqual(group.getShader(), replacement)
        cmds.undo()
        self.assertEqual(group.getShader(), material)
        group.setShader(material, kind="volume")
        self.assertEqual(group.getShader("volume"), material)
        with self.assertRaises(ValueError):
            group.getShader("invalid")
        with self.assertRaises(TypeError):
            hlib.createShader("lambert", name="one", n="two")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
