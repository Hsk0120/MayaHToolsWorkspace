"""Mayaの継承・シェーダー接続・面割り当てを検証する。"""
import sys
import unittest
import maya.cmds as cmds
import mlib
mlib.reload()
from mlib.nodes import Node, Lambert, Reflect, Blinn, StandardSurface, ShadingEngine, File


class MaterialNodesTest(unittest.TestCase):
    """専用namespace内で割り当てを検証する。"""

    def setUp(self):
        self.old = cmds.namespaceInfo(currentNamespace=True)
        self.ns = cmds.namespace(add="mlibMaterialTest")
        cmds.namespace(set=self.ns)

    def tearDown(self):
        cmds.namespace(set=self.old)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_maya_inheritance(self):
        for kind in ("lambert", "blinn", "phong", "phongE", "standardSurface", "surfaceShader",
                     "file", "place2dTexture", "place3dTexture"):
            node = mlib.createNode(kind)
            native = cmds.nodeType(kind, isTypeName=True, inherited=True)
            declared = {cls: name for name, cls in mlib.nodes._WRAPPER_CLASSES.items()}
            for cls in type(node).__mro__:
                key = declared.get(cls)
                if key and key != "dependNode":
                    self.assertIn(key, native)
        self.assertTrue(issubclass(Blinn, Reflect))
        self.assertTrue(issubclass(Reflect, Lambert))
        self.assertFalse(issubclass(StandardSurface, Lambert))

    def test_assignment_faces_and_undo(self):
        mesh = Node(cmds.polyCube()[0]).getShape()
        material = mlib.getNode(cmds.shadingNode("lambert", asShader=True))
        second = mlib.getNode(cmds.shadingNode("standardSurface", asShader=True))
        group = mlib.getNode(cmds.sets(renderable=True, noSurfaceShader=True, empty=True))
        group.setShader(material)
        other = mlib.getNode(cmds.sets(renderable=True, noSurfaceShader=True, empty=True))
        other.setShader(second)
        self.assertIsInstance(group, ShadingEngine)
        group.assign(mesh)
        self.assertEqual(mesh.getMaterials(), [material])
        other.assign(mesh.getFaces([0, 1]))
        self.assertEqual(mesh.getFace(0).getMaterial(), second)
        self.assertEqual(mesh.getFace(2).getMaterial(), material)
        self.assertEqual(mesh.getFaces([0, 1]).getMaterials(), [second])
        self.assertTrue(all(member.shape == mesh for member in other.getMembers()))
        self.assertEqual(material.getShadingEngines(), [group])
        self.assertTrue(material.getAssignedObjects())
        cmds.undo()
        self.assertEqual(mesh.getFace(0).getMaterial(), material)

    def test_instance_assignments(self):
        transform = Node(cmds.polyCube()[0])
        instance = Node(cmds.instance(transform.getFullName())[0])
        a = mlib.getNode(cmds.sets(renderable=True, noSurfaceShader=True, empty=True))
        a.setShader(mlib.getNode(cmds.shadingNode("lambert", asShader=True)))
        b = mlib.getNode(cmds.sets(renderable=True, noSurfaceShader=True, empty=True))
        b.setShader(mlib.getNode(cmds.shadingNode("blinn", asShader=True)))
        a.assign(transform)
        b.assign(instance)
        self.assertEqual(transform.getShape().getShadingEngines(), [a])
        self.assertEqual(instance.getShape().getShadingEngines(), [b])

    def test_texture_connections(self):
        texture = mlib.createNode("file")
        place = mlib.createNode("place2dTexture")
        self.assertIsInstance(texture, File)
        texture.setFilePath("test.<UDIM>.exr")
        self.assertEqual(texture.getFilePath(), "test.<UDIM>.exr")
        place.connectTexture(texture)
        self.assertEqual(texture.getPlacement(), place)
        place.connectTexture(texture)

    def test_shader_ports_and_aliases(self):
        material = mlib.getNode(cmds.shadingNode("surfaceShader", n="surface", asShader=True))
        group = mlib.getNode(cmds.sets(renderable=True, noSurfaceShader=True, empty=True, n="surfaceSG"))
        self.assertIsNone(group.getShader())
        group.setShader(material.getPlug("outColor"))
        self.assertEqual(group.getShaderPlug(), material.getPlug("outColor"))
        replacement = mlib.getNode(cmds.shadingNode("lambert", asShader=True))
        group.setShader(replacement)
        self.assertEqual(group.getShader(), replacement)
        cmds.undo()
        self.assertEqual(group.getShader(), material)
        group.setShader(material, kind="volume")
        self.assertEqual(group.getShader("volume"), material)
        with self.assertRaises(ValueError):
            group.getShader("invalid")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
