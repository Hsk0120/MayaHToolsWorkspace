"""名前空間・選択・matchTransform の通常経路と、om2 へ置き換えた読み取りを cmds と突き合わせる。

- Namespace.create/setCurrent/rename/move/remove は cmds.namespace で操作し、Undo 1 回で戻せる。
  3.0.0 で fast 引数は外した(``docs/mlib-api-design.md`` の「fast を持たない書き込み」)。
- Selection.select / mlib.select は cmds.select と同じ選択になる。
- Transform.matchTransform は cmds.matchTransform のままで、Undo 1 回で戻る。
- 選択・ドリブンキーの存在確認(MSelectionList.add)は cmds.objExists と同じ結果。
- Lambert/StandardSurface の基底は registry._inherited_node_types の継承列で選ぶ。
"""

import inspect
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common.namespace import Namespace
from mlib.common.selection import Selection
from support.specCase import NamespaceCase


class _CommonCase(NamespaceCase):
    PREFIX = "mlibSpecCommonEdits_"

    def setUp(self):
        super().setUp()
        self.current = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.relative = cmds.namespace(query=True, relativeNames=True)
        self.selection = cmds.ls(selection=True, long=True)
        cmds.select(clear=True)

    def tearDown(self):
        cmds.namespace(relativeNames=self.relative)
        cmds.namespace(set=self.current if cmds.namespace(exists=self.current) else ":")
        if self.selection:
            cmds.select(self.selection, replace=True)
        else:
            cmds.select(clear=True)
        super().tearDown()

    def namespaces(self, root):
        """root 配下の名前空間を root からの相対名で返す。"""
        names = cmds.namespaceInfo(root, listOnlyNamespaces=True, recurse=True, absoluteName=True) or []
        return sorted(name[len(root):] for name in names)

    def nodes(self, root):
        """root 配下のノードを root からの相対名で返す。"""
        names = cmds.namespaceInfo(root, listOnlyDependencyNodes=True, recurse=True, absoluteName=True) or []
        return sorted(name[len(root):] for name in names)


class FastArgumentRemovedTest(unittest.TestCase):

    def test_no_fast_argument(self):
        """3.0.0 で fast を外した書込みは、シグネチャに fast を持たない。"""
        from mlib.nodes import Joint, SkinCluster, Transform
        from mlib.plugs import Plug

        targets = [mlib.duplicate, mlib.select, Selection.select, Namespace.create, Namespace.setCurrent,
                   Namespace.rename, Namespace.move, Namespace.remove, Plug.setMuted, Plug.mute, Plug.unmute,
                   Transform.matchTransform, SkinCluster.removeInfluence, SkinCluster.removeUnusedInfluences,
                   Joint.removeInfluence]
        for target in targets:
            with self.subTest(target=target.__qualname__):
                self.assertNotIn("fast", inspect.signature(target).parameters)


class NamespaceTest(_CommonCase):

    def test_create_nested_and_existing(self):
        """多段の作成は親ごと作り、既存なら同じ名前を返す。relativeNames の設定によらず絶対名。"""
        for relative in (False, True):
            with self.subTest(relativeNames=relative):
                root = ":" + self.ns + ":" + ("rel" if relative else "abs")
                cmds.namespace(add=root.rsplit(":", 1)[-1], parent=":" + self.ns)
                cmds.namespace(set=":" + self.ns)
                cmds.namespace(relativeNames=relative)
                try:
                    created = Namespace.create("a:b", parent=root)
                    again = Namespace.create("a:b", parent=root)
                finally:
                    cmds.namespace(relativeNames=False)
                    cmds.namespace(set=":")
                self.assertEqual(created.name, root + ":a:b")
                self.assertEqual(again, created)
                self.assertEqual(self.namespaces(root), [":a", ":a:b"])

    def test_create_undo_once(self):
        """Undo 1 回で、作った親ごと消える。"""
        root = ":" + self.ns
        cmds.flushUndo()
        Namespace.create("x:y", parent=root)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibNamespaceCreate")
        cmds.undo()
        self.assertFalse(cmds.namespace(exists=root + ":x"))

    def test_create_sanitized_name(self):
        """Maya が不正文字を置き換える名前は、置き換え後の名前を作って返す(既存なら番号付き)。"""
        root = ":" + self.ns
        for name in ("1bad", "a-b", "a#", "1bad"):
            with self.subTest(name=name):
                actual = Namespace.create(name, parent=root)
                self.assertTrue(actual.exists())
        self.assertIn(":bad1", self.namespaces(root))

    def test_set_current(self):
        """setCurrent は切り替えて自身を返し、存在しない名前空間は RuntimeError。"""
        target = Namespace.create("cur", parent=":" + self.ns)
        self.assertIs(target.setCurrent(), target)
        self.assertEqual(cmds.namespaceInfo(currentNamespace=True, absoluteName=True), target.name)
        cmds.namespace(set=":")
        with self.assertRaises(RuntimeError):
            Namespace(":" + self.ns + ":missing").setCurrent()

    def build(self, root):
        """名前が衝突する A・B を root の下に作る。"""
        for name in ("A", "B", "A:C", "B:C"):
            cmds.namespace(add=name.rsplit(":", 1)[-1], parent=root + (":" + name.rsplit(":", 1)[0] if ":" in name else ""))
        for name in ("A:n1", "A:n2", "A:C:n1", "B:n1", "B:n2", "B:n21", "B:C:n1"):
            cmds.createNode("transform", name=root + ":" + name, skipSelect=True)

    def test_rename_move_remove_match_cmds(self):
        """rename・move・remove は保持名を更新し、cmds.namespace で同じ操作をした結果と同じになる。"""
        mlib_root, cmds_root = ":" + self.ns + ":viaMlib", ":" + self.ns + ":viaCmds"
        for root in (mlib_root, cmds_root):
            cmds.namespace(add=root.rsplit(":", 1)[-1], parent=":" + self.ns)
            self.build(root)
        renamed = Namespace(mlib_root + ":A").rename("R")
        self.assertEqual(renamed.name, mlib_root + ":R")
        moved = renamed.move(mlib_root + ":B")
        self.assertEqual(moved.name, mlib_root + ":B:R")
        destination = moved.remove(mlib_root + ":B")
        self.assertEqual(destination, Namespace(mlib_root + ":B"))
        # cmds.namespace の rename/move に相当する手順(作成・内容の移動・元の削除)。
        cmds.namespace(add="R", parent=cmds_root)
        cmds.namespace(moveNamespace=(cmds_root + ":A", cmds_root + ":R"), force=True)
        cmds.namespace(removeNamespace=cmds_root + ":A")
        cmds.namespace(add="R", parent=cmds_root + ":B")
        cmds.namespace(moveNamespace=(cmds_root + ":R", cmds_root + ":B:R"), force=True)
        cmds.namespace(removeNamespace=cmds_root + ":R")
        cmds.namespace(moveNamespace=(cmds_root + ":B:R", cmds_root + ":B"), force=True)
        cmds.namespace(removeNamespace=cmds_root + ":B:R")
        self.assertEqual(self.namespaces(mlib_root), self.namespaces(cmds_root))
        self.assertEqual(self.nodes(mlib_root), self.nodes(cmds_root))

    def test_remove_into_child_fails_without_change(self):
        """自身の子への移動は RuntimeError。"""
        root = ":" + self.ns
        self.build(root)
        with self.assertRaises(RuntimeError):
            Namespace(root + ":A").remove(root + ":A:C")
        self.assertTrue(cmds.namespace(exists=root + ":A"))


class SelectTest(_CommonCase):

    def setUp(self):
        super().setUp()
        self.cube = cmds.polyCube(name=self.name("cube"))[0]
        self.sphere = cmds.polySphere(name=self.name("sphere"))[0]
        self.curve = cmds.curve(name=self.name("curve"), degree=1, point=[(0, 0, 0), (1, 0, 0), (2, 0, 0)])
        self.set = cmds.sets(self.cube, self.sphere, name=self.name("set"))
        cmds.select(clear=True)

    def state(self):
        return cmds.ls(selection=True), cmds.ls(orderedSelection=True)

    def n(self, text):
        return self.ns + ":" + text

    def test_errors_match(self):
        """存在しない名前は ValueError で、選択を変えない。"""
        cmds.select(self.sphere)
        with self.assertRaises(ValueError):
            mlib.select([self.cube, self.n("missing")])
        self.assertEqual(cmds.ls(selection=True), [self.sphere])

    def test_normal_undo_once(self):
        """Undo 1 回で元の選択に戻る。"""
        cmds.select(self.sphere)
        mlib.select([self.cube + ".vtx[1]", self.curve])
        cmds.undo()
        self.assertEqual(cmds.ls(selection=True), [self.sphere])

    def test_selection_select(self):
        """Selection.select の各 mode は、cmds.select(noExpand=True) と同じ選択になる。"""
        names = [self.cube + ".vtx[3]", self.sphere, self.cube + ".vtx[1]", self.cube + ".vtx[2]", self.set]
        selection = Selection(names)
        base = [self.curve, self.cube + ".vtx[2]"]
        for mode, flag in (("replace", "replace"), ("add", "add"), ("remove", "deselect")):
            with self.subTest(mode=mode):
                cmds.select(base)
                cmds.select([item.getFullName() for item in selection], noExpand=True, **{flag: True})
                expected = self.state()
                cmds.select(base)
                self.assertIs(selection.select(mode), selection)
                self.assertEqual(self.state(), expected)
        cmds.select(self.curve)
        Selection().select()
        self.assertEqual(cmds.ls(selection=True), [])

    def test_exists_matches_obj_exists(self):
        """選択の存在確認(core.object._exists)は cmds.objExists と同じ結果になる。"""
        from mlib.core.object import _exists

        shape = cmds.listRelatives(self.cube, shapes=True, fullPath=True)[0]
        curve_shape = cmds.listRelatives(self.curve, shapes=True, fullPath=True)[0]
        node = cmds.ls(self.make(), long=True)[0]
        cmds.addAttr(node, longName="arr", multi=True)
        cmds.setAttr(node + ".arr[2]", 1)
        names = [shape + ".vtx[7]", shape + ".vtx[100]", shape + ".e[11]", shape + ".f[6]", shape + ".map[400]",
                 curve_shape + ".cv[2]", curve_shape + ".cv[50]", node + ".tx", node + ".nope", node + ".arr[2]",
                 node + ".arr[5]", node + ".worldMatrix[3]", node, node + "|nope", "|" + self.ns + ":missing"]
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(_exists(name), cmds.objExists(name))


class MatchTransformTest(_CommonCase):

    def scene(self):
        parent = self.make(text="P#")
        cmds.xform(parent, translation=(1, 2, 3), rotation=(10, 20, 30), scale=(1.5, 2, 0.5))
        other = self.make(text="Q#")
        cmds.xform(other, translation=(-2, 1, 4), rotation=(-40, 15, 60), scale=(0.7, 1.3, 1.1))
        source = self.make("transform", "S#", parent=parent)
        target = self.make("transform", "T#", parent=other)
        cmds.xform(source, translation=(0.3, -1, 2), rotation=(5, 70, -20), scale=(1, 2, 3))
        cmds.xform(target, translation=(3, 1, -1), rotation=(45, -30, 80), scale=(2, 0.5, 1.5))
        return source, target

    def snapshot(self, node):
        return (cmds.xform(node, query=True, worldSpace=True, matrix=True)
                + cmds.xform(node, query=True, worldSpace=True, rotatePivot=True)
                + cmds.xform(node, query=True, worldSpace=True, scalePivot=True))

    def test_all_false_is_noop(self):
        """全フラグ False は何も変更しない。"""
        source, target = self.scene()
        before = self.snapshot(source)
        mlib.getNode(source).matchTransform(target, position=False, rotation=False, scale=False)
        self.assertEqual(self.snapshot(source), before)

    def test_rejects_non_transform(self):
        """合わせ先が Transform でなければ TypeError。"""
        source, _ = self.scene()
        with self.assertRaises(TypeError):
            mlib.getNode(source).matchTransform(self.make("network", "dg#"))

    def test_normal_undo_once(self):
        """cmds.matchTransform と同じ結果で、Undo 1 回で戻る。"""
        source, target = self.scene()
        before = self.snapshot(source)
        cmds.flushUndo()
        mlib.getNode(source).matchTransform(target, pivots=True)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibTransformMatchTransform")
        result = self.snapshot(source)
        cmds.undo()
        self.assertSequenceAlmostEqual(self.snapshot(source), before)
        cmds.matchTransform(source, target, position=True, rotation=True, scale=True, pivots=True)
        self.assertSequenceAlmostEqual(result, self.snapshot(source), places=6)


class SurfaceBaseTest(unittest.TestCase):

    def test_base_follows_inherited_types(self):
        """Lambert・StandardSurface の基底は Maya の継承列に paintableShadingDependNode があるかで決まる。"""
        from mlib.nodes import Lambert, StandardSurface
        from mlib.nodes.paintableShadingDependNode import PaintableShadingDependNode
        from mlib.nodes.shadingDependNode import ShadingDependNode

        for cls, type_name in ((Lambert, "lambert"), (StandardSurface, "standardSurface")):
            with self.subTest(type_name=type_name):
                inherited = cmds.nodeType(type_name, isTypeName=True, inherited=True)
                base = PaintableShadingDependNode if "paintableShadingDependNode" in inherited else ShadingDependNode
                self.assertIs(cls.__bases__[0], base)


if __name__ == "__main__":
    unittest.main()
