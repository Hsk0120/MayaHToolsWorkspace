"""5.0.0で変えたノード型・作成の約束を固定する。

対象: Maya 2026の改名(multDoubleLinear→multDL・addDoubleLinear→addDL)の両方の名前を全版で使えること
(createNode・ls の type/exactType/excludeType・isType・ラッパークラスの選択。getType はその版の名前)、
この版に無い型の作成の案内、joint の下へ作った joint の inverseScale の自動接続(通常は Undo 1回・fast)。
"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import AddDL, AddDoubleLinear, MultDL, MultDoubleLinear, Node
from support.specCase import NamespaceCase

#: (2025以前の名前, 2026以降の名前, クラス)
RENAMED = (("multDoubleLinear", "multDL", MultDoubleLinear), ("addDoubleLinear", "addDL", AddDoubleLinear))


def _version():
    """Mayaのメジャー版番号。"""
    return int(cmds.about(majorVersion=True))


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecNodeTypes_"


class RenamedTypeTest(_SpecCase):
    """改名された型の両方の名前。"""

    def test_alias_classes_are_the_same_object(self):
        self.assertIs(MultDL, MultDoubleLinear)
        self.assertIs(AddDL, AddDoubleLinear)
        self.assertIs(mlib.nodes.Node._registry.wrapper_class("multDL"), MultDoubleLinear)
        self.assertIs(mlib.nodes.Node._registry.wrapper_class("addDoubleLinear"), AddDoubleLinear)

    def test_create_with_either_name_on_this_version(self):
        for legacy, modern, cls in RENAMED:
            real = modern if _version() >= 2026 else legacy
            for type_name in (legacy, modern):
                for fast in (False, True):
                    with self.subTest(type=type_name, fast=fast):
                        node = mlib.createNode(type_name, name=self.name(type_name + "#"), fast=fast)
                        self.assertIs(type(node), cls)
                        self.assertEqual(node.getType(), real)
                        self.assertEqual(cmds.nodeType(str(node)), real)
                        self.assertTrue(node.isType(legacy))
                        self.assertTrue(node.isType(modern))
                        self.assertIs(type(Node(str(node))), cls)

    def test_create_undoes_once(self):
        self.flushUndo()
        node = mlib.createNode("multDL", name=self.name("undo"))
        name = node.getFullName()
        self.assertUndoesInOneStep(lambda: self.assertFalse(cmds.objExists(name)),
                                   lambda: self.assertTrue(cmds.objExists(name)))

    def test_ls_type_flags_accept_both_names(self):
        made = [mlib.createNode(legacy, name=self.name(legacy)) for legacy, _modern, _cls in RENAMED]
        pattern = self.ns + ":*"
        for legacy, modern, _cls in RENAMED:
            expected = [node for node in made if node.isType(legacy)]
            for type_name in (legacy, modern):
                with self.subTest(type=type_name):
                    self.assertEqual(mlib.ls(pattern, type=type_name), expected)
                    self.assertEqual(mlib.ls(pattern, exactType=[type_name]), expected)
                    # excludeType の結果の意味はMayaに従う(版の名前で cmds.ls と同じ結果になる)。
                    real = modern if _version() >= 2026 else legacy
                    self.assertEqual([node.getName() for node in mlib.ls(pattern, excludeType=type_name)],
                                     cmds.ls(pattern, excludeType=real))

    def test_cmds_parity_of_the_real_name(self):
        for legacy, modern, _cls in RENAMED:
            real = modern if _version() >= 2026 else legacy
            node = mlib.createNode(legacy, name=self.name("parity#"))
            self.assertIn(node.getName(), cmds.ls(self.ns + ":*", type=real))


class UnavailableTypeTest(_SpecCase):
    """この版に無い型の作成。"""

    def test_message_says_not_available_in_this_version(self):
        for fast in (False, True):
            with self.subTest(fast=fast):
                before = set(cmds.ls())
                with self.assertRaisesRegex(RuntimeError, r"not available in this Maya version"):
                    mlib.createNode("mlibNoSuchNodeTypeX", name=self.name("unknown"), fast=fast)
                self.assertEqual(set(cmds.ls()), before)

    def test_known_newer_type_names_the_first_version(self):
        if _version() >= 2024:
            self.assertEqual(mlib.createNode("parentMatrix", name=self.name("pm")).getType(), "parentMatrix")
            return
        with self.assertRaisesRegex(RuntimeError, r"parentMatrix \(not available in this Maya version \d+; "
                                                  r"it requires Maya 2024 or later\)"):
            mlib.createNode("parentMatrix", name=self.name("pm"))


class JointInverseScaleTest(_SpecCase):
    """joint の下へ作った joint の inverseScale(cmds.joint と同じ)。"""

    def test_connects_like_cmds_joint(self):
        root = mlib.createNode("joint", name=self.name("root"))
        for fast in (False, True):
            with self.subTest(fast=fast):
                child = mlib.createNode("joint", name=self.name("child#"), parent=root, fast=fast)
                self.assertEqual(child.getPlug("inverseScale").getSource(skipConversionNodes=True), root.getPlug("scale"))
        cmds.select(root.getFullName())
        reference = cmds.joint(name=self.name("cmdsChild"))
        self.assertEqual(cmds.listConnections(reference + ".inverseScale", plugs=True),
                         [root.getNodeName() + ".scale"])

    def test_undo_once_removes_node_and_connection(self):
        root = mlib.createNode("joint", name=self.name("root"))
        self.flushUndo()
        child = mlib.createNode("joint", name=self.name("child"), parent=root)
        name = child.getFullName()
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlib createNode joint")
        self.assertUndoesInOneStep(
            lambda: (self.assertFalse(cmds.objExists(name)),
                     self.assertEqual(cmds.listConnections(root.getFullName() + ".scale") or [], [])),
            lambda: self.assertTrue(cmds.objExists(name)))

    def test_other_parents_are_not_connected(self):
        group = mlib.createNode("transform", name=self.name("grp"))
        joint = mlib.createNode("joint", name=self.name("underGroup"), parent=group)
        self.assertIsNone(joint.getPlug("inverseScale").getSource(skipConversionNodes=True))
        transform = mlib.createNode("transform", name=self.name("underJoint"), parent=joint)
        self.assertEqual(cmds.listConnections(joint.getFullName() + ".scale") or [], [])
        self.assertTrue(transform.isValid())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
