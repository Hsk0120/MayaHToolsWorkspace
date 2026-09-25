"""jointOrient移送の姿勢保持、単位・回転順序・Undo・事前検証。"""
import unittest
import sys
import uuid
import maya.cmds as cmds
import hlib

hlib.reload()


class JointOrientToRotateTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibOrient_" + uuid.uuid4().hex
        self.unit = cmds.currentUnit(query=True, angle=True)
        cmds.currentUnit(angle="deg")
        cmds.namespace(add=self.ns)

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        cmds.currentUnit(angle=self.unit)

    def joint(self, parent=None):
        args = {"name": self.ns + ":joint_" + uuid.uuid4().hex}
        if parent:
            args["parent"] = parent
        node = cmds.createNode("joint", **args)
        cmds.setAttr(node + ".rotate", 31, -24, 58)
        cmds.setAttr(node + ".jointOrient", -17, 43, 26)
        return node

    def matrix(self, node):
        return cmds.xform(node, query=True, worldSpace=True, matrix=True)

    def assertMatrix(self, node, before):
        for a, b in zip(self.matrix(node), before):
            self.assertAlmostEqual(a, b, places=7)

    def test_all_orders_units_and_scale_compensation(self):
        for order in range(6):
            for unit in ("deg", "rad"):
                for ssc in (False, True):
                    with self.subTest(order=order, unit=unit, ssc=ssc):
                        cmds.currentUnit(angle="deg")
                        parent = self.joint()
                        node = self.joint(parent)
                        child = self.joint(node)
                        cmds.setAttr(parent + ".scale", -2, 1.5, 0.8)
                        cmds.setAttr(node + ".scale", 0.5, 1.8, 1.2)
                        cmds.setAttr(node + ".rotateAxis", 9, -23, 11)
                        cmds.setAttr(node + ".rotateOrder", order)
                        cmds.setAttr(node + ".segmentScaleCompensate", ssc)
                        cmds.setAttr(node + ".translate", 2, 3, -4)
                        cmds.setAttr(child + ".translateX", 5)
                        before, child_before = self.matrix(node), self.matrix(child)
                        cmds.currentUnit(angle=unit)
                        wrapper = hlib.node(node)
                        self.assertIs(wrapper.freeze_rotation(), wrapper)
                        self.assertEqual(cmds.getAttr(node + ".rotate")[0], (0, 0, 0))
                        self.assertMatrix(node, before)
                        self.assertMatrix(child, child_before)
                        self.assertIs(wrapper.joint_orient_to_rotate(), wrapper)
                        self.assertEqual(cmds.getAttr(node + ".jointOrient")[0], (0, 0, 0))
                        self.assertEqual(cmds.getAttr(node + ".rotateOrder"), order)
                        self.assertMatrix(node, before)
                        self.assertMatrix(child, child_before)

    def test_collection_undo_redo(self):
        root = self.joint()
        child = self.joint(root)
        nodes = [root, child]
        before = [(cmds.getAttr(n + ".rotate"), cmds.getAttr(n + ".jointOrient"), self.matrix(n)) for n in nodes]
        collection = hlib.nodes.Joints(nodes)
        self.assertIs(collection.joint_orient_to_rotate(), collection)
        for n, state in zip(nodes, before):
            self.assertMatrix(n, state[2])
        cmds.undo()
        for n, state in zip(nodes, before):
            self.assertEqual(cmds.getAttr(n + ".rotate"), state[0])
            self.assertEqual(cmds.getAttr(n + ".jointOrient"), state[1])
        cmds.redo()
        for n, state in zip(nodes, before):
            self.assertEqual(cmds.getAttr(n + ".jointOrient")[0], (0, 0, 0))
            self.assertMatrix(n, state[2])

    def test_preflight_rejects_lock_and_input_without_partial_edit(self):
        for attribute in ("rotateX", "jointOrient", "jointOrientY"):
            a, b = self.joint(), self.joint()
            before = cmds.getAttr(a + ".jointOrient")
            cmds.setAttr(b + "." + attribute, lock=True)
            try:
                with self.assertRaises(RuntimeError):
                    hlib.nodes.Joints([a, b]).joint_orient_to_rotate()
                with self.assertRaises(RuntimeError):
                    hlib.nodes.Joints([a, b]).freeze_rotation()
                self.assertEqual(cmds.getAttr(a + ".jointOrient"), before)
            finally:
                cmds.setAttr(b + "." + attribute, lock=False)
        a, b = self.joint(), self.joint()
        cmds.connectAttr(a + ".rotateX", b + ".rotateX")
        with self.assertRaises(RuntimeError):
            hlib.node(b).joint_orient_to_rotate()
        with self.assertRaises(RuntimeError):
            hlib.node(b).freeze_rotation()
        cmds.disconnectAttr(a + ".rotateX", b + ".rotateX")
        cmds.setKeyframe(b, attribute="rotateY", time=1)
        with self.assertRaises(RuntimeError):
            hlib.node(b).joint_orient_to_rotate()
        with self.assertRaises(RuntimeError):
            hlib.node(b).freeze_rotation()

    def test_zero_is_noop_and_invalid_raises(self):
        node = self.joint()
        cmds.setAttr(node + ".jointOrient", 0, 0, 0)
        cmds.setAttr(node + ".rotateX", 720)
        wrapper = hlib.node(node)
        wrapper.joint_orient_to_rotate()
        self.assertEqual(cmds.getAttr(node + ".rotateX"), 720)
        cmds.delete(node)
        with self.assertRaises(RuntimeError):
            wrapper.joint_orient_to_rotate()
        with self.assertRaises(RuntimeError):
            wrapper.freeze_rotation()
        empty = hlib.nodes.Joints()
        self.assertIs(empty.joint_orient_to_rotate(), empty)
        self.assertIs(empty.freeze_rotation(), empty)

    def test_freeze_skinned_joint_and_collection_undo_redo(self):
        for skinning_method in (0, 1, 2):
            for bulk in (False, True):
                with self.subTest(skinning_method=skinning_method, bulk=bulk):
                    root = self.joint()
                    child = self.joint(root)
                    cmds.setAttr(child + ".translateX", 3)
                    mesh = cmds.polyCube(name=self.ns + ":mesh", constructionHistory=False)[0]
                    skin = cmds.skinCluster(root, child, mesh, toSelectedBones=True,
                                            name=self.ns + ":skin")[0]
                    for pose in cmds.listConnections(skin + ".bindPose", source=True, destination=False) or []:
                        if not pose.startswith(self.ns + ":"):
                            cmds.rename(pose, self.ns + ":pose")
                    cmds.setAttr(skin + ".skinningMethod", skinning_method)
                    cmds.skinPercent(skin, mesh + ".vtx[*]", transformValue=[(root, 0.35), (child, 0.65)])
                    # バインド後に曲げた状態でフリーズする。
                    cmds.setAttr(root + ".rotate", 23, -18, 41)
                    cmds.setAttr(child + ".rotate", -27, 33, 12)
                    nodes = [root, child] if bulk else [child]
                    before = [(cmds.getAttr(n + ".rotate"), cmds.getAttr(n + ".jointOrient")) for n in nodes]
                    matrices = [self.matrix(root), self.matrix(child)]
                    vertices = cmds.xform(mesh + ".vtx[*]", query=True, worldSpace=True, translation=True)
                    binds = cmds.getAttr(skin + ".bindPreMatrix[*]")
                    weights = [cmds.skinPercent(skin, mesh + ".vtx[{}]".format(i), query=True, value=True) for i in range(8)]
                    target = hlib.nodes.Joints(nodes) if bulk else hlib.node(child)
                    self.assertIs(target.freeze_rotation(), target)

                    def assert_skin_unchanged():
                        self.assertMatrix(root, matrices[0])
                        self.assertMatrix(child, matrices[1])
                        actual = cmds.xform(mesh + ".vtx[*]", query=True, worldSpace=True, translation=True)
                        for a, b in zip(actual, vertices):
                            self.assertAlmostEqual(a, b, places=6)
                        self.assertEqual(cmds.getAttr(skin + ".bindPreMatrix[*]"), binds)
                        self.assertEqual([cmds.skinPercent(skin, mesh + ".vtx[{}]".format(i), query=True, value=True)
                                          for i in range(8)], weights)

                    assert_skin_unchanged()
                    for n in nodes:
                        self.assertEqual(cmds.getAttr(n + ".rotate")[0], (0, 0, 0))
                    cmds.undo()
                    for n, values in zip(nodes, before):
                        self.assertEqual(cmds.getAttr(n + ".rotate"), values[0])
                        self.assertEqual(cmds.getAttr(n + ".jointOrient"), values[1])
                    assert_skin_unchanged()
                    cmds.redo()
                    for n in nodes:
                        self.assertEqual(cmds.getAttr(n + ".rotate")[0], (0, 0, 0))
                    assert_skin_unchanged()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
