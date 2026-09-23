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
        self.created.extend([self.a.name(), self.b.name()])
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
        self.assertEqual(self.set.members(), [])

    def test_add_and_members_returns_node_wrappers(self):
        result = self.set.add(self.a, self.b)
        self.assertIs(result, self.set)
        members = self.set.members()
        self.assertEqual({member.name() for member in members}, {self.a.name(), self.b.name()})
        self.assertTrue(all(isinstance(member, Node) for member in members))

    def test_remove_drops_a_member(self):
        self.set.add(self.a, self.b)
        result = self.set.remove(self.a)
        self.assertIs(result, self.set)
        self.assertEqual([member.name() for member in self.set.members()], [self.b.name()])

    def test_is_member(self):
        self.assertFalse(self.set.is_member(self.a))
        self.set.add(self.a)
        self.assertTrue(self.set.is_member(self.a))
        self.assertTrue(self.set.is_member(self.a.full_name))
        self.assertFalse(self.set.is_member(self.b))

    def test_add_accepts_component_strings(self):
        cube_transform = cmds.polyCube(name="hlibObjectSetCube", constructionHistory=False)[0]
        self.created.append(cube_transform)
        component = cube_transform + ".vtx[0:2]"

        self.set.add(component)
        members = self.set.members()
        self.assertIn(component, members)
        self.assertTrue(self.set.is_member(component))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
