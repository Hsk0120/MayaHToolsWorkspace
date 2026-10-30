"""5.0.0で変えた編集の案内・一括適用・Undo の表示名の約束を固定する。

対象: 位置・回転・マトリクスの ``space=``/``ws=`` と成分を分けた指定の案内、ロック・接続された成分の案内、
DrivenKey.setKey の既存の入力の案内、getChildren(type=)、resetAttrs/setAttrFlags の Plug 指定、
複数形の一括の書込み(Undo 1回・fast)、Undo の表示名(``mlib setTranslate <対象>``)。
"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common.drivenKey import DrivenKey
from mlib.decorator import undoChunk
from mlib.nodes import Joints, Node, Nodes
from support.specCase import NamespaceCase


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecGuidance_"


class ArgumentHintTest(_SpecCase):
    """よくある引数の誤りの案内。"""

    def test_space_keywords_suggest_world_space(self):
        node = Node(self.make())
        calls = (("setTranslate", ((1, 2, 3),)), ("getTranslate", ()), ("setRotate", ((1, 2, 3),)),
                 ("getRotate", ()), ("setMatrix", (node.getMatrix(),)), ("getMatrix", ()))
        for method, args in calls:
            for keyword, value in (("space", "world"), ("ws", True)):
                with self.subTest(method=method, keyword=keyword):
                    self.flushUndo()
                    with self.assertRaisesRegex(TypeError, r"unexpected keyword argument '{}'; use worldSpace=True"
                                                .format(keyword)):
                        getattr(node, method)(*args, **{keyword: value})
                    self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_spread_components_suggest_a_sequence(self):
        node = Node(self.make())
        for method in ("setTranslate", "setRotate", "setScale"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(TypeError, r"pass a sequence: {0}\(\(x, y, z\)\)".format(method)):
                    getattr(node, method)(1, 2, 3)
        self.assertEqual(cmds.getAttr(str(node) + ".t")[0], (0.0, 0.0, 0.0))

    def test_locked_or_connected_child_is_named(self):
        name = self.make()
        node = Node(name)
        cmds.setAttr(name + ".ty", lock=True)
        with self.assertRaisesRegex(RuntimeError, r"{}\.translateY is locked; .*safe=True".format(name)):
            node.setTranslate((1, 2, 3))
        node.setTranslate((1, 2, 3), safe=True)
        self.assertEqual(cmds.getAttr(name + ".t")[0], (1.0, 0.0, 3.0))
        source = self.make("plusMinusAverage", "pma")
        cmds.connectAttr(source + ".output1D", name + ".rz")
        with self.assertRaisesRegex(RuntimeError, r"rotateZ is connected from {}\.output1D".format(source)):
            node.setRotate((10, 20, 30))

    def test_driven_key_existing_input_is_explained(self):
        driver = Node(self.make(text="driver"))
        driven = Node(self.make(text="driven"))
        source = self.make("plusMinusAverage", "pma")
        cmds.connectAttr(source + ".output1D", str(driven) + ".tx")
        key = DrivenKey(driver.getPlug("tx"), driven.getPlug("tx"))
        with self.assertRaisesRegex(RuntimeError, r"already has an input from {}\.output1D .*blendWeighted"
                                    .format(source)):
            key.setKey(0, 1)


class ChildrenTypeTest(_SpecCase):
    """getChildren(type=)。"""

    def test_type_filter_matches_list_relatives(self):
        root = self.make("joint", "root")
        child = self.make("joint", "child", parent=root)
        group = self.make("transform", "grp", parent=child)
        leaf = self.make("joint", "leaf", parent=group)
        shape = self.make("mesh", "rootShape", parent=self.make("transform", "geo", parent=root))
        node = Node(root)
        for flags, kind in (({}, "joint"), ({"allDescendents": True}, "joint"),
                            ({"allDescendents": True}, "transform"), ({"allDescendents": True}, "mesh")):
            with self.subTest(flags=flags, type=kind):
                expected = cmds.listRelatives(root, type=kind, fullPath=True, **flags) or []
                actual = [item.getFullName() for item in node.getChildren(type=kind, **flags)]
                self.assertEqual(sorted(actual), sorted(expected))
        # 探索は型で絞らず、結果だけを絞る(型の違う grp の下の leaf も見つかる)。深さ優先の順。
        self.assertEqual([item.getNodeName() for item in node.getChildren(type=["joint", "mesh"],
                                                                          allDescendents=True)],
                         [self.name("child"), self.name("leaf"), self.name("rootShape")])
        self.assertEqual(Node(shape).getNodeName(), self.name("rootShape"))
        self.assertEqual(Node(group).getChildren(type="joint"), [Node(leaf)])
        with self.assertRaises(TypeError):
            node.getChildren(type=1)
        with self.assertRaises(ValueError):
            node.getChildren(type="")


class PlugArgumentTest(_SpecCase):
    """resetAttrs・setAttrFlags の Plug 指定。"""

    def test_set_attr_flags_accepts_plugs(self):
        node = Node(self.make())
        self.flushUndo()
        self.assertIs(node.setAttrFlags([node.tx, "ty", node.getPlug("rotateX")], locked=True), node)
        for attribute in ("tx", "ty", "rx"):
            self.assertTrue(cmds.getAttr(str(node) + "." + attribute, lock=True))
        self.assertUndoesInOneStep(lambda: self.assertFalse(cmds.getAttr(str(node) + ".tx", lock=True)),
                                   lambda: self.assertTrue(cmds.getAttr(str(node) + ".tx", lock=True)))
        other = Node(self.make())
        with self.assertRaisesRegex(ValueError, "does not belong to"):
            node.setAttrFlags(other.tx, locked=True)
        with self.assertRaises(TypeError):
            node.setAttrFlags([1], locked=True)


class BulkWriteTest(_SpecCase):
    """複数形の一括の書込み。"""

    def test_bulk_writes_match_singular_and_undo_once(self):
        names = [self.make(text="n{}".format(index)) for index in range(3)]
        nodes = Nodes(names)
        cases = (
            (lambda: nodes.setAttrFlags(["tx"], locked=True), lambda name: cmds.getAttr(name + ".tx", lock=True)),
            (lambda: nodes.setLocked(True), lambda name: cmds.lockNode(name, query=True, lock=True)[0]),
            (lambda: nodes.setVisibility(False), lambda name: not cmds.getAttr(name + ".v")),
            (lambda: nodes.hide(), lambda name: not cmds.getAttr(name + ".v")),
            (lambda: nodes.setColor(17), lambda name: cmds.getAttr(name + ".overrideColor") == 17),
        )
        for action, check in cases:
            with self.subTest(action=action):
                self.flushUndo()
                result = action()
                self.assertIs(result, nodes)
                self.assertUndoesInOneStep(lambda: self.assertFalse(any(check(name) for name in names)),
                                           lambda: self.assertTrue(all(check(name) for name in names)))

    def test_bulk_fast_and_reset(self):
        names = [self.make(text="f{}".format(index)) for index in range(2)]
        for name in names:
            cmds.setAttr(name + ".tx", 4)
        nodes = Nodes(names)
        self.flushUndo()
        plugs = nodes.resetAttrs(["tx"], fast=True)
        self.assertEqual(len(plugs), 2)
        self.assertEqual([cmds.getAttr(name + ".tx") for name in names], [0.0, 0.0])
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        with self.assertRaises(TypeError):
            nodes.setLocked(True, fast=1)

    def test_set_parent_and_joints(self):
        group = self.make(text="grp")
        names = [self.make(text="p{}".format(index)) for index in range(2)]
        Nodes(names).setParent(group)
        self.assertEqual(sorted(cmds.listRelatives(group, children=True)), sorted(names))
        joints = Joints([self.make("joint", "j0"), self.make("joint", "j1")])
        self.flushUndo()
        self.assertIs(joints.setRadius(3.0), joints)
        self.assertEqual([joint.getRadius() for joint in joints], [3.0, 3.0])
        self.assertTrue(cmds.undoInfo(query=True, undoName=True).startswith("mlib setRadius"))
        cmds.undo()
        self.assertEqual([joint.getRadius() for joint in joints], [1.0, 1.0])

    def test_unsupported_items_are_rejected_before_writing(self):
        dg = self.make("multiplyDivide", "md")
        transform = self.make(text="dag")
        with self.assertRaisesRegex(TypeError, r"requires every item to support setVisibility"):
            Nodes([transform, dg]).setVisibility(False)
        self.assertTrue(cmds.getAttr(transform + ".v"))


class UndoNameTest(_SpecCase):
    """Undo の表示名。"""

    def test_names_show_method_and_target(self):
        name = self.make(text="L_arm_CTRL")
        node = Node(name)
        cases = ((lambda: node.setTranslate((1, 2, 3)), "mlib setTranslate " + node.getName()),
                 (lambda: node.getPlug("rx").set(10), "mlib set {}.rotateX".format(node.getName())),
                 (lambda: node.setAttrFlags("tx", keyable=False), "mlib setAttrFlags " + node.getName()),
                 (lambda: mlib.createNode("transform", name=self.name("made")), "mlib createNode transform"))
        for action, expected in cases:
            with self.subTest(expected=expected):
                action()
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), expected)

    def test_user_chunk_names_are_kept(self):
        node = Node(self.make())
        with undoChunk("mlibMyToolStep"):
            node.setTranslate((1, 0, 0))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibMyToolStep")
        with undoChunk("my tool"):
            node.setTranslate((2, 0, 0))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "my tool")

        @undoChunk("mlibDecorated")
        def edit():
            node.setTranslate((3, 0, 0))

        edit()
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibDecorated")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
