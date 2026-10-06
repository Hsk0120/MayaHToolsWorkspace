"""hlib.nodes.objectSet の ObjectSet ラッパーを検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.nodes import Node
from hlib.nodes.objectSet import ObjectSet


class ObjectSetTest(unittest.TestCase):
    """基本的なメンバー列挙・追加・除外・所属判定を検証する。"""

    def setUp(self):
        self.created = []
        self.a = Node.create(type="transform", name="hlibObjectSetA")
        self.b = Node.create(type="transform", name="hlibObjectSetB")
        self.created.extend([self.a.getName(), self.b.getName()])
        set_name = cmds.sets(name="hlibObjectSetTestSet", empty=True)
        self.created.append(set_name)
        self.set = Node(set_name)

    def tearDown(self):
        for node in reversed(self.created):
            if cmds.objExists(node):
                cmds.delete(node)

    def test_node_resolves_to_object_set_wrapper(self):
        self.assertIsInstance(self.set, ObjectSet)

    def test_members_empty_by_default(self):
        self.assertEqual(self.set.getMembers(), [])

    def test_add_and_members_returns_node_wrappers(self):
        result = self.set.addMembers(self.a, self.b)
        self.assertIs(result, self.set)
        members = self.set.getMembers()
        self.assertEqual({member.getName() for member in members}, {self.a.getName(), self.b.getName()})
        self.assertTrue(all(isinstance(member, Node) for member in members))

    def test_remove_drops_a_member(self):
        self.set.addMembers(self.a, self.b)
        result = self.set.removeMembers(self.a)
        self.assertIs(result, self.set)
        self.assertEqual([member.getName() for member in self.set.getMembers()], [self.b.getName()])

    def test_is_member(self):
        self.assertFalse(self.set.isMember(self.a))
        self.set.addMembers(self.a)
        self.assertTrue(self.set.isMember(self.a))
        self.assertTrue(self.set.isMember(self.a.getFullName()))
        self.assertFalse(self.set.isMember(self.b))

    def test_add_accepts_component_strings(self):
        cube_transform = cmds.polyCube(name="hlibObjectSetCube", constructionHistory=False)[0]
        self.created.append(cube_transform)
        component = cube_transform + ".vtx[0:2]"

        self.set.addMembers(component)
        members = self.set.getMembers()
        self.assertIn(component, members)
        self.assertTrue(self.set.isMember(component))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
