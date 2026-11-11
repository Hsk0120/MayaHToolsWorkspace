"""複数形のコレクション(Nodes・Joints・コンポーネント)から単数のメソッドを呼べることと、
Node.select・Nodes.getNames/select/callEach を確かめる。

転送は各要素の同名メソッドを同じ引数で呼び、戻り値を保持順のリストで返す。書込みは Undo 1 回で戻り、
メソッドを持たない要素を含む場合は何も変えずに TypeError、どの要素も持たない名前は AttributeError になる。
"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from support.specCase import NamespaceCase


class _Case(NamespaceCase):
    """transform 2つ・joint 2つ・polyCube を用意する。"""

    PREFIX = "mlibCollectionForward_"
    CLEAR_SELECTION = True

    def setUp(self):
        super().setUp()
        self.a = cmds.createNode("transform", name=self.ns + ":a")
        self.b = cmds.createNode("transform", name=self.ns + ":b")
        cmds.select(clear=True)
        self.j1 = cmds.joint(name=self.ns + ":j1", position=(0, 0, 0))
        self.j2 = cmds.joint(name=self.ns + ":j2", position=(1, 0, 0))
        cmds.select(clear=True)
        self.cube = cmds.polyCube(name=self.ns + ":cube")[0]

    def nodes(self, *names):
        return mlib.Nodes([cmds.ls(name, long=True)[0] for name in names])


class NodesForwardingTest(_Case):
    """Nodes・Joints から単数のメソッドを呼ぶ。"""

    def test_query_and_write_return_lists(self):
        nodes = self.nodes(self.a, self.b)
        result = nodes.setTranslation((1, 2, 3))
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        positions = nodes.getTranslation()
        self.assertEqual([tuple(p) for p in positions], [(1, 2, 3), (1, 2, 3)])
        self.assertEqual(nodes.getTranslation(ws=True), nodes.getTranslation(worldSpace=True))

    def test_joints_forward_joint_methods(self):
        joints = mlib.Joints([self.j1, self.j2])
        self.assertEqual(joints.getRadius(), [cmds.getAttr(self.j1 + ".radius"), cmds.getAttr(self.j2 + ".radius")])
        self.assertEqual(len(joints.getTranslation(worldSpace=True)), 2)

    def test_existing_collection_methods_keep_priority(self):
        nodes = self.nodes(self.a, self.b)
        self.assertIs(nodes.setOverrideColor(13), nodes)
        self.assertEqual(nodes.getOverrideColor(), [13, 13])

    def test_undo_once(self):
        nodes = self.nodes(self.a, self.b)
        self.flushUndo()
        nodes.setTranslation((5, 0, 0))
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.a + ".tx"), 0)
        self.assertEqual(cmds.getAttr(self.b + ".tx"), 0)

    def test_missing_methods(self):
        nodes = self.nodes(self.a, self.b)
        with self.assertRaises(AttributeError):
            nodes.noSuchMethod
        with self.assertRaises(AttributeError):
            nodes._items_missing
        mixed = mlib.Nodes([cmds.ls(self.a, long=True)[0], cmds.createNode("multiplyDivide", name=self.ns + ":md")])
        with self.assertRaises(TypeError):
            mixed.setTranslation((9, 0, 0))
        self.assertEqual(cmds.getAttr(self.a + ".tx"), 0)

    def test_empty_collection(self):
        self.assertEqual(mlib.Nodes().getName(), [])
        with self.assertRaises(AttributeError):
            mlib.Joints().noSuchMethod


class ComponentForwardingTest(_Case):
    """コンポーネントの複数形から単数のメソッドを呼ぶ。"""

    def test_vertices_forward(self):
        mesh = mlib.getNode(self.cube).getShape()
        vertices = mesh.getVertices([0, 1])
        names = vertices.getFullName()
        self.assertEqual(names, [vertex.getFullName() for vertex in vertices])
        with self.assertRaises(AttributeError):
            vertices.noSuchMethod

    def test_component_write_undo_once(self):
        mesh = mlib.getNode(self.cube).getShape()
        vertices = mesh.getVertices([0, 1])
        before = vertices.getPosition()
        self.flushUndo()
        vertices.setPositionY(5.0)
        self.assertEqual([p[1] for p in vertices.getPosition()], [5.0, 5.0])
        cmds.undo()
        self.assertEqual(vertices.getPosition(), before)


class SelectNamesCallEachTest(_Case):
    """Node.select・Nodes.getNames/select/callEach。"""

    def test_node_select(self):
        node = mlib.getNode(self.a)
        node.select()
        self.assertEqual(cmds.ls(selection=True, long=True), cmds.ls(self.a, long=True))
        mlib.getNode(self.b).select(add=True)
        self.assertEqual(len(cmds.ls(selection=True)), 2)
        mlib.getNode(self.a).select(deselect=True)
        self.assertEqual(cmds.ls(selection=True, long=True), cmds.ls(self.b, long=True))

    def test_nodes_select_and_names(self):
        nodes = self.nodes(self.a, self.b)
        self.assertEqual(nodes.getNames(), [node.getName() for node in nodes])
        nodes.select()
        self.assertEqual(cmds.ls(selection=True, long=True), cmds.ls([self.a, self.b], long=True))
        mlib.Nodes().select()
        self.assertEqual(cmds.ls(selection=True), [])

    def test_select_undo_and_invalid(self):
        cmds.select(self.a, replace=True)
        self.flushUndo()
        mlib.getNode(self.b).select()
        cmds.undo()
        self.assertEqual(cmds.ls(selection=True, long=True), cmds.ls(self.a, long=True))
        self.flushUndo()
        self.nodes(self.a, self.b).select(deselect=True)
        cmds.undo()
        self.assertEqual(cmds.ls(selection=True, long=True), cmds.ls(self.a, long=True))
        node = mlib.createNode("transform", name=self.ns + ":gone")
        cmds.delete(node.getFullName())
        with self.assertRaisesRegex(RuntimeError, "Cannot select an invalid"):
            node.select()
        with self.assertRaises(TypeError):
            mlib.getNode(self.a).select(add=True, af=True, addFirst=True)

    def test_call_each(self):
        nodes = self.nodes(self.a, self.b)
        self.flushUndo()
        nodes.callEach("setTranslation", (0, 4, 0))
        self.assertEqual(nodes.callEach("getTranslation"), nodes.getTranslation())
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.b + ".ty"), 0)
        with self.assertRaises(TypeError):
            nodes.callEach(1)
        for name in ("", "_forward", "__init__"):
            with self.assertRaises(ValueError):
                nodes.callEach(name)
        with self.assertRaises(TypeError):
            nodes.callEach("noSuchMethod")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
