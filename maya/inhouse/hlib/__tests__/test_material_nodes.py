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
        self.assertEqual(material.shading_engines(), [group])
        self.assertTrue(material.assigned_objects())
        cmds.undo()
        self.assertEqual(mesh.face(0).material(), material)

    def test_instance_assignments(self):
        transform = Node(cmds.polyCube()[0])
        instance = Node(cmds.instance(transform.full_name())[0])
        a = hlib.createShadingGroup(hlib.createShader("lambert"))
        b = hlib.createShadingGroup(hlib.createShader("blinn"))
        a.assign(transform)
        b.assign(instance)
        self.assertEqual(transform.shape().shading_engines(), [a])
        self.assertEqual(instance.shape().shading_engines(), [b])

    def test_texture_connections(self):
        texture = hlib.createNode("file")
        place = hlib.createNode("place2dTexture")
        self.assertIsInstance(texture, File)
        texture.set_file_path("test.<UDIM>.exr")
        self.assertEqual(texture.get_file_path(), "test.<UDIM>.exr")
        place.connect_texture(texture)
        self.assertEqual(texture.get_placement(), place)
        place.connect_texture(texture)

    def test_shader_ports_and_aliases(self):
        material = hlib.createShader("surfaceShader", n="surface")
        group = hlib.createShadingGroup(n="surfaceSG")
        self.assertIsNone(group.get_shader())
        group.set_shader(material.plug("outColor"))
        self.assertEqual(group.get_shader_plug(), material.plug("outColor"))
        replacement = hlib.createShader("lambert")
        group.set_shader(replacement)
        self.assertEqual(group.get_shader(), replacement)
        cmds.undo()
        self.assertEqual(group.get_shader(), material)
        group.set_shader(material, kind="volume")
        self.assertEqual(group.get_shader("volume"), material)
        with self.assertRaises(ValueError):
            group.get_shader("invalid")
        with self.assertRaises(TypeError):
            hlib.createShader("lambert", name="one", n="two")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
