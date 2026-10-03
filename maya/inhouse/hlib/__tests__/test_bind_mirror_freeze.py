"""フリーズと作成コマンドの結果型・Undo・標準フラグを検証する。"""
from maya.api.OpenMaya import MSpace
import sys
import unittest
import maya.cmds as cmds
import hlib
hlib.reload()
from hlib.nodes import Node, Joint, Joints, Transforms, SkinCluster, SkinClusters


class BindMirrorFreezeTest(unittest.TestCase):
    """専用namespace内のノードだけを操作する。"""

    def setUp(self):
        self.old = cmds.namespaceInfo(currentNamespace=True)
        self.ns = cmds.namespace(add="hlibBindMirrorFreezeTest")
        cmds.namespace(set=self.ns)

    def tearDown(self):
        cmds.namespace(set=self.old)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_freeze_matches_maya(self):
        names = [cmds.polyCube()[0] for _ in range(2)]
        for name in names:
            cmds.setAttr(name + ".translate", 2, 3, 4)
            cmds.setAttr(name + ".rotate", 10, 20, 30)
            cmds.setAttr(name + ".scale", 2, 3, 4)
        Node(names[0]).freeze(t=True, r=True, s=True)
        cmds.makeIdentity(names[1], apply=True, translate=True, rotate=True, scale=True)
        for attr in ("translate", "rotate", "scale"):
            self.assertEqual(cmds.getAttr(names[0] + "." + attr), cmds.getAttr(names[1] + "." + attr))
        for i in range(8):
            a = cmds.pointPosition(names[0] + ".vtx[%d]" % i, world=True)
            b = cmds.pointPosition(names[1] + ".vtx[%d]" % i, world=True)
            for x, y in zip(a, b): self.assertAlmostEqual(x, y)
        nodes = Transforms([Node(name) for name in names])
        nodes.setTranslation((3, 2, 1))
        nodes.freeze()
        cmds.undo()
        self.assertEqual(tuple(nodes[0].getTranslation()), (3, 2, 1))

    def test_bind_single_multiple_and_undo(self):
        joint = Joint(cmds.createNode("joint"))
        meshes = [Node(cmds.polyCube()[0]) for _ in range(3)]
        single = hlib.bindSkin(meshes[0], [joint], tsb=True, mi=1, nw=1)
        self.assertIsInstance(single, SkinCluster)
        multiple = hlib.cmds.bindSkin(meshes[1:], [joint], toSelectedBones=True, maximumInfluences=1)
        self.assertIsInstance(multiple, SkinClusters)
        self.assertEqual(len(multiple), 2)
        names = [skin.fullName() for skin in multiple]
        self.assertTrue(all(skin.deforms(mesh) for skin, mesh in zip(multiple, meshes[1:])))
        cmds.undo()
        self.assertFalse(any(cmds.objExists(name) for name in names))
        cmds.redo()
        self.assertTrue(all(cmds.objExists(name) for name in names))
        with self.assertRaises(TypeError):
            hlib.bindSkin(meshes[0], [joint], mi=1, maximumInfluences=2)
        with self.assertRaises(ValueError):
            hlib.bindSkin([], [joint])
        with self.assertRaises(ValueError):
            hlib.bindSkin(meshes[0], [joint], q=True)

    def test_mirror_result_types_and_flags(self):
        root = Joint(cmds.createNode("joint", name="left_root"))
        cmds.setAttr(root.fullName() + ".translate", 2, 1, 0)
        mirrored = hlib.mirrorJoint(root, myz=True, mb=True, sr=("left", "right"))
        self.assertIsInstance(mirrored, Joint)
        self.assertAlmostEqual(mirrored.getTranslation(space=MSpace.kWorld).x, -2)
        cmds.createNode("joint", name="left_tip", parent=root.fullName())
        result = hlib.mirrorJoint(root, mirrorYZ=True, searchReplace=("left", "other"))
        self.assertIsInstance(result, Joints)
        self.assertEqual(len(result), 2)
        names = [node.fullName() for node in result]
        cmds.undo()
        self.assertFalse(any(cmds.objExists(name) for name in names))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
