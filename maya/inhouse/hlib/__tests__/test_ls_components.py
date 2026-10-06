"""lsの正式名称フィルタ・混合選択・範囲展開を実Mayaで検証する。"""

import sys
import unittest
import uuid

import hlib
import maya.cmds as cmds


class LsComponentsTest(unittest.TestCase):
    def setUp(self):
        self.selection = cmds.ls(sl=True, long=True) or []
        self.ns = "lsComponents_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.mesh = cmds.polyCube(name=self.ns + ":mesh", ch=False)[0]
        self.other = cmds.polyCube(name=self.ns + ":other", ch=False)[0]
        self.joint = cmds.createNode("joint", name=self.ns + ":joint")

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        cmds.select(self.selection, replace=True) if self.selection else cmds.select(clear=True)

    def test_mixed_selection_and_multiple_meshes(self):
        cmds.select([self.joint, self.mesh + ".vtx[1:3]", self.other + ".vtx[0]"], r=True)
        items = hlib.ls(sl=True)
        self.assertEqual(len(items), 5)
        self.assertIsInstance(items[0], hlib.nodes.Joint)
        vertices = hlib.ls(sl=True, type="vertex")
        self.assertEqual([v.index for v in vertices], [1, 2, 3, 0])
        self.assertTrue(all(isinstance(v, hlib.components.Vertex) for v in vertices))
        self.assertEqual(len({v.shape.getFullName() for v in vertices}), 2)
        self.assertEqual(hlib.ls(sl=True, type="face"), [])

    def test_component_names_ranges_and_no_conversion(self):
        curve = cmds.curve(name=self.ns + ":curve", d=1, p=[(0, 0, 0), (1, 0, 0)])
        for name, path, kind in (
            ("vertex", self.mesh + ".vtx[0:1]", hlib.components.Vertex),
            ("edge", self.mesh + ".e[0:1]", hlib.components.Edge),
            ("face", self.mesh + ".f[0:1]", hlib.components.Face),
            ("uv", self.mesh + ".map[0:1]", hlib.components.UV),
            ("controlVertex", curve + ".cv[0:1]", hlib.components.CV),
        ):
            for flatten in (False, True):
                result = hlib.ls(path, type=name, fl=flatten)
                self.assertEqual([v.index for v in result], [0, 1])
                self.assertTrue(all(isinstance(v, kind) for v in result))
        self.assertEqual(hlib.ls(self.mesh, type="vertex"), [])
        self.assertEqual(hlib.ls(self.mesh + ".f[0]", type="vertex"), [])

    def test_invalid_names_empty_and_existing_returns(self):
        cmds.select(self.mesh + ".vtx[0]", r=True)
        self.assertEqual(len(hlib.ls(sl=True, typ="vertex")), 1)
        for value in (None, []):
            self.assertEqual(hlib.ls(value, type="vertex"), [])
        self.assertIsInstance(hlib.ls(self.joint, typ="joint"), hlib.nodes.Joints)
        self.assertIsInstance(hlib.ls(type="skinCluster"), hlib.nodes.SkinClusters)
        self.assertIsInstance(hlib.ls(self.mesh + ".translateX")[0], hlib.plugs.Plug)
        cmds.addAttr(self.joint, ln="values", at="double", multi=True)
        self.assertIsInstance(hlib.ls(self.joint + ".values")[0], hlib.plugs.ArrayPlug)
        with self.assertRaises(TypeError):
            hlib.ls(sl=True, selection=True, type="vertex")

    def test_instance_path_and_direct_delta_removal(self):
        instance = cmds.instance(self.mesh, name=self.ns + ":instance")[0]
        vertex = hlib.ls(instance + ".vtx[0]", type="vertex")[0]
        self.assertIn(instance, vertex.getFullName())
        target = cmds.duplicate(self.other, name=self.ns + ":target")[0]
        bs = hlib.getNode(cmds.blendShape(target, self.other)[0])
        try:
            bs.setTargetDeltas(0, {0: (0, 1, 0), 1: (0, 2, 0)}, disconnect=True)
            cmds.select(self.other + ".vtx[0]", r=True)
            bs.resetTargetVertices(0, hlib.ls(sl=True, type="vertex"))
            self.assertEqual(set(bs.getTargetDeltas(0)), {1})
            cmds.undo()
            self.assertEqual(set(bs.getTargetDeltas(0)), {0, 1})
        finally:
            cmds.delete(bs.getName())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
