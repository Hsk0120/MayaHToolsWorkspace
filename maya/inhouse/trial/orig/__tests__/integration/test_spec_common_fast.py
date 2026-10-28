"""名前空間・選択・matchTransform の fast と、om2 へ置き換えた読み取りを cmds と突き合わせる(2.1.0 担当B)。

- Namespace.create/setCurrent/rename/move/remove(fast=True) は om2.MNamespace で操作し、cmds.namespace を
  呼ばず Undo に記録しない。結果の名前(衝突時の改名を含む)は通常経路と同じ。Maya が不正文字を置き換える
  名前は cmds と om2 で置換結果が異なるため、fast では変更前に NotImplementedError。
- Selection.select / mlib.select(fast=True) は MGlobal.setActiveSelectionList で反映し、選択の並び・
  コンポーネントのまとめ方が cmds.select と同じ。展開系のフラグ・toggle 等は変更前に NotImplementedError。
- Transform.matchTransform(fast=True) は position・pivots だけに対応し、cmds.matchTransform と同じ結果。
- 選択・ドリブンキーの存在確認(MSelectionList.add)は cmds.objExists と同じ結果。
- Lambert/StandardSurface の基底は registry._inherited_node_types の継承列で選ぶ。
"""

import itertools
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common.namespace import Namespace
from mlib.common.selection import Selection
from support.specCase import NamespaceCase


def _forbid(*names):
    """指定した cmds の関数を呼ぶと失敗させる。"""
    stack = ExitStack()
    for name in names:
        stack.enter_context(patch.object(cmds, name, side_effect=AssertionError(name)))
    return stack


class _FastCase(NamespaceCase):
    PREFIX = "mlibSpecCommonFast_"

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

    def sentinel(self):
        """Undo キューに 1 件積み、その名前を返す。"""
        cmds.setAttr(self.make() + ".tx", 1)
        return cmds.undoInfo(query=True, undoName=True)

    def namespaces(self, root):
        """root 配下の名前空間を root からの相対名で返す。"""
        names = cmds.namespaceInfo(root, listOnlyNamespaces=True, recurse=True, absoluteName=True) or []
        return sorted(name[len(root):] for name in names)

    def nodes(self, root):
        """root 配下のノードを root からの相対名で返す。"""
        names = cmds.namespaceInfo(root, listOnlyDependencyNodes=True, recurse=True, absoluteName=True) or []
        return sorted(name[len(root):] for name in names)


class NamespaceFastTest(_FastCase):

    def roots(self):
        """通常経路用と fast 経路用の、同じ構成の親名前空間を返す。"""
        result = []
        for label in ("normal", "fast"):
            cmds.namespace(add=label, parent=":" + self.ns)
            result.append(":" + self.ns + ":" + label)
        return result

    def test_create_matches_normal(self):
        """多段の作成と relativeNames の各設定で、fast は通常と同じ名前を返し cmds を呼ばない。"""
        for relative in (False, True):
            with self.subTest(relativeNames=relative):
                suffix = "Rel" if relative else "Abs"
                normal_root, fast_root = [":" + self.ns + ":" + label + suffix for label in ("normal", "fast")]
                for root in (normal_root, fast_root):
                    cmds.namespace(add=root.rsplit(":", 1)[-1], parent=":" + self.ns)
                cmds.namespace(set=":" + self.ns)
                cmds.namespace(relativeNames=relative)
                try:
                    expected = Namespace.create("a:b", parent=normal_root)
                    undo_name = self.sentinel()
                    with _forbid("namespace", "namespaceInfo", "undoInfo"):
                        actual = Namespace.create("a:b", parent=fast_root, fast=True)
                        again = Namespace.create("a:b", parent=fast_root, fast=True)
                    self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
                finally:
                    cmds.namespace(relativeNames=False)
                    cmds.namespace(set=":")
                self.assertEqual(actual.name[len(fast_root):], expected.name[len(normal_root):])
                self.assertEqual(actual.name, fast_root + ":a:b")
                self.assertEqual(again, actual)
                self.assertEqual(self.namespaces(fast_root), self.namespaces(normal_root))

    def test_create_undo_once(self):
        """通常経路は Undo 1 回で、作った親ごと消える。"""
        root = ":" + self.ns
        cmds.flushUndo()
        Namespace.create("x:y", parent=root)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibNamespaceCreate")
        cmds.undo()
        self.assertFalse(cmds.namespace(exists=root + ":x"))

    def test_create_sanitized_name(self):
        """Maya が不正文字を置き換える名前は、通常・fast とも同じ名前を作って返す(既存なら番号付き)。"""
        normal_root, fast_root = self.roots()
        for name in ("1bad", "a-b", "a#", "1bad"):
            with self.subTest(name=name):
                expected = Namespace.create(name, parent=normal_root)
                with _forbid("namespace", "namespaceInfo"):
                    actual = Namespace.create(name, parent=fast_root, fast=True)
                self.assertEqual(actual.name[len(fast_root):], expected.name[len(normal_root):])
                self.assertTrue(actual.exists())
        self.assertEqual(self.namespaces(fast_root), self.namespaces(normal_root))
        self.assertIn(":bad1", self.namespaces(fast_root))

    def test_create_non_ascii_not_implemented(self):
        """ASCII 以外は om2 へ渡す文字コード変換で cmds と異なる名前になるため、fast は作成前に拒否する。"""
        root = ":" + self.ns
        with self.assertRaises(NotImplementedError):
            Namespace.create("ok:äx", parent=root, fast=True)
        self.assertFalse(cmds.namespace(exists=root + ":ok"))
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            Namespace.create("z", parent=root, fast=1)

    def test_set_current(self):
        """setCurrent(fast=True) は cmds を呼ばずに切り替え、存在しない名前空間は RuntimeError。"""
        target = Namespace.create("cur", parent=":" + self.ns)
        undo_name = self.sentinel()
        with _forbid("namespace", "undoInfo"):
            self.assertIs(target.setCurrent(fast=True), target)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        self.assertEqual(cmds.namespaceInfo(currentNamespace=True, absoluteName=True), target.name)
        cmds.namespace(set=":")
        with self.assertRaises(RuntimeError):
            Namespace(":" + self.ns + ":missing").setCurrent(fast=True)

    def build(self, root):
        """名前が衝突する A・B を root の下に作る。"""
        for name in ("A", "B", "A:C", "B:C"):
            cmds.namespace(add=name.rsplit(":", 1)[-1], parent=root + (":" + name.rsplit(":", 1)[0] if ":" in name else ""))
        for name in ("A:n1", "A:n2", "A:C:n1", "B:n1", "B:n2", "B:n21", "B:C:n1"):
            cmds.createNode("transform", name=root + ":" + name, skipSelect=True)

    def test_rename_move_remove_match_normal(self):
        """rename・move・remove(衝突する名前の改名を含む)は通常と同じ結果になる。"""
        normal_root, fast_root = self.roots()
        for root in (normal_root, fast_root):
            self.build(root)
        Namespace(normal_root + ":A").rename("R")
        Namespace(normal_root + ":R").move(normal_root + ":B")
        Namespace(normal_root + ":B:R").remove(normal_root + ":B")
        undo_name = self.sentinel()
        with _forbid("namespace", "namespaceInfo", "undoInfo"):
            renamed = Namespace(fast_root + ":A").rename("R", fast=True)
            self.assertEqual(renamed.name, fast_root + ":R")
            moved = renamed.move(fast_root + ":B", fast=True)
            self.assertEqual(moved.name, fast_root + ":B:R")
            destination = moved.remove(fast_root + ":B", fast=True)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        self.assertEqual(destination, Namespace(fast_root + ":B"))
        self.assertEqual(self.namespaces(fast_root), self.namespaces(normal_root))
        self.assertEqual(self.nodes(fast_root), self.nodes(normal_root))

    def test_remove_into_child_fails_without_change(self):
        """自身の子への移動は通常・fast とも RuntimeError。"""
        root = ":" + self.ns
        self.build(root)
        for fast in (False, True):
            with self.subTest(fast=fast), self.assertRaises(RuntimeError):
                Namespace(root + ":A").remove(root + ":A:C", fast=fast)
        self.assertTrue(cmds.namespace(exists=root + ":A"))

    def test_rename_non_ascii_not_implemented(self):
        """fast の rename は ASCII 以外の名前を変更前に拒否する。"""
        root = ":" + self.ns
        self.build(root)
        with self.assertRaises(NotImplementedError):
            Namespace(root + ":A").rename("äx", fast=True)
        self.assertTrue(cmds.namespace(exists=root + ":A"))
        self.assertEqual(self.namespaces(root), [":A", ":A:C", ":B", ":B:C"])


class SelectFastTest(_FastCase):

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

    def cases(self):
        cube, sphere, curve = self.n("cube"), self.n("sphere"), self.n("curve")
        return [
            [cube + ".vtx[3]", sphere, cube + ".vtx[1]", cube + ".vtx[2]", curve + ".cv[1]", cube],
            [cube, sphere, cube],
            [cube + ".vtx[1]", sphere, cube + ".vtx[1]"],
            [cube + ".vtx[1]", cube + ".e[1]", cube + ".vtx[2]"],
            [cube + ".vtx[5]", cube + ".vtx[1]", cube + ".vtx[3]"],
            [cube + ".vtx[1:3]", cube + ".vtx[2:5]"],
            [cube + ".tx", cube + ".tx", cube],
            [cube, cube + ".vtx[1]", cube + ".f[2]", cube + ".map[1]"],
            [self.n("cube*")],
            [cube + ".vtx[*]"],
            [],
        ]

    def test_select_matches_cmds(self):
        """replace・add・addFirst・deselect で、選択の並びとまとめ方が cmds.select と同じ。"""
        cube, sphere, curve = self.n("cube"), self.n("sphere"), self.n("curve")
        base = [cube + ".vtx[3]", sphere, cube + ".vtx[1]"]
        rows = [(names, {}) for names in self.cases()]
        rows += [
            ([curve, cube + ".vtx[2]", cube + ".vtx[4]"], {"add": True}),
            ([sphere, cube + ".vtx[1]"], {"add": True}),
            ([cube + ".vtx[1]", sphere], {"deselect": True}),
            ([cube + ".vtx[1:3]"], {"deselect": True}),
            ([curve, cube + ".vtx[2]"], {"addFirst": True}),
            ([self.set], {"noExpand": True}),
            ([sphere], {"replace": True, "add": False}),
        ]
        for names, flags in rows:
            with self.subTest(names=names, flags=flags):
                cmds.select(base)
                cmds.select(names, **flags)
                expected = self.state()
                cmds.select(base)
                undo_name = cmds.undoInfo(query=True, undoName=True)
                with _forbid("select", "undoInfo"):
                    self.assertIsNone(mlib.select(names, fast=True, **flags))
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
                self.assertEqual(self.state(), expected)

    def test_clear_and_none(self):
        """対象なしの clear は選択を外し、フラグなしは何も変えない。"""
        cmds.select(self.cube)
        mlib.select(fast=True)
        self.assertEqual(cmds.ls(selection=True), [self.cube])
        mlib.select(clear=True, fast=True)
        self.assertEqual(cmds.ls(selection=True), [])

    def test_not_implemented_before_change(self):
        """展開・toggle・複数の選択方法・noExpand なしのセットは、選択を変えずに拒否する。"""
        rows = [
            ([self.cube], {"hierarchy": True}),
            ([self.cube], {"toggle": True}),
            ([self.cube], {"add": True, "deselect": True}),
            ([self.cube], {"clear": True}),
            ([self.cube], {"symmetry": True}),
            ([self.cube, self.set], {}),
            (None, {"allDagObjects": True}),
            (None, {"add": True}),
        ]
        for nodes, flags in rows:
            with self.subTest(nodes=nodes, flags=flags):
                cmds.select(self.sphere)
                with self.assertRaises(NotImplementedError):
                    mlib.select(nodes, fast=True, **flags)
                self.assertEqual(cmds.ls(selection=True), [self.sphere])
        # False のフラグは指定しないのと同じ。
        mlib.select([self.cube], hierarchy=False, fast=True)
        self.assertEqual(cmds.ls(selection=True), [self.cube])

    def test_errors_match(self):
        """存在しない名前は通常・fast とも ValueError、fast の型は bool だけ。"""
        cmds.select(self.sphere)
        for fast in (False, True):
            with self.subTest(fast=fast), self.assertRaises(ValueError):
                mlib.select([self.cube, self.n("missing")], fast=fast)
            self.assertEqual(cmds.ls(selection=True), [self.sphere])
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            mlib.select(self.cube, fast=1)

    def test_normal_undo_once(self):
        """通常経路は Undo 1 回で元の選択に戻る。"""
        cmds.select(self.sphere)
        mlib.select([self.cube + ".vtx[1]", self.curve])
        cmds.undo()
        self.assertEqual(cmds.ls(selection=True), [self.sphere])

    def test_selection_select(self):
        """Selection.select の各 mode で、fast は通常と同じ選択になり cmds を呼ばない。"""
        selection = Selection([self.cube + ".vtx[3]", self.sphere, self.cube + ".vtx[1]", self.cube + ".vtx[2]",
                               self.set])
        base = [self.curve, self.cube + ".vtx[2]"]
        for mode in ("replace", "add", "remove"):
            with self.subTest(mode=mode):
                cmds.select(base)
                selection.select(mode)
                expected = self.state()
                cmds.select(base)
                undo_name = cmds.undoInfo(query=True, undoName=True)
                with _forbid("select", "undoInfo", "objExists"):
                    self.assertIs(selection.select(mode, fast=True), selection)
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
                self.assertEqual(self.state(), expected)
        cmds.select(self.curve)
        Selection().select(fast=True)
        self.assertEqual(cmds.ls(selection=True), [])
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            selection.select(fast="yes")

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


class MatchTransformFastTest(_FastCase):

    def scene(self, source_kind, target_kind, parent_transform):
        parent = self.make(text="P#")
        if parent_transform:
            cmds.xform(parent, translation=(1, 2, 3), rotation=(10, 20, 30), scale=(1.5, 2, 0.5))
        other = self.make(text="Q#")
        cmds.xform(other, translation=(-2, 1, 4), rotation=(-40, 15, 60), scale=(0.7, 1.3, 1.1))
        source = self.make(source_kind, "S#", parent=parent)
        target = self.make(target_kind, "T#", parent=other)
        cmds.xform(source, translation=(0.3, -1, 2), rotation=(5, 70, -20), scale=(1, 2, 3))
        cmds.xform(target, translation=(3, 1, -1), rotation=(45, -30, 80), scale=(2, 0.5, 1.5))
        if source_kind == "joint":
            cmds.setAttr(source + ".jointOrient", 10, 20, 30)
        else:
            cmds.xform(source, rotatePivot=(0.5, 0.2, -0.3), scalePivot=(0.1, -0.4, 0.6), objectSpace=True)
        if target_kind == "joint":
            cmds.setAttr(target + ".jointOrient", -15, 5, 40)
        else:
            cmds.xform(target, rotatePivot=(-0.2, 0.7, 0.4), scalePivot=(0.3, 0.3, -0.2), objectSpace=True)
        return source, target

    def snapshot(self, node):
        return (cmds.xform(node, query=True, worldSpace=True, matrix=True)
                + cmds.xform(node, query=True, worldSpace=True, rotatePivot=True)
                + cmds.xform(node, query=True, worldSpace=True, scalePivot=True))

    def test_fast_matches_cmds(self):
        """position・pivots の組合せ × 親の変換の有無 × transform/joint で、cmds.matchTransform と同じ結果。"""
        kinds = list(itertools.product(("transform", "joint"), repeat=2))
        for (source_kind, target_kind), parent_transform, (position, pivots) in itertools.product(
                kinds, (False, True), ((True, False), (False, True), (True, True))):
            with self.subTest(source=source_kind, target=target_kind, parent=parent_transform,
                              position=position, pivots=pivots):
                source, target = self.scene(source_kind, target_kind, parent_transform)
                cmds.matchTransform(source, target, position=position, rotation=False, scale=False, pivots=pivots)
                expected = self.snapshot(source)
                source, target = self.scene(source_kind, target_kind, parent_transform)
                undo_name = cmds.undoInfo(query=True, undoName=True)
                node = mlib.getNode(source)
                with _forbid("matchTransform", "xform", "setAttr", "undoInfo"):
                    self.assertIs(node.matchTransform(target, position=position, rotation=False, scale=False,
                                                      pivots=pivots, fast=True), node)
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
                self.assertSequenceAlmostEqual(self.snapshot(source), expected, places=6)

    def test_all_false_is_noop(self):
        """全フラグ False は通常・fast とも何も変更しない(cmds.matchTransform は呼ばない)。"""
        source, target = self.scene("transform", "transform", True)
        before = self.snapshot(source)
        node = mlib.getNode(source)
        for fast in (False, True):
            with _forbid("matchTransform"):
                node.matchTransform(target, position=False, rotation=False, scale=False, fast=fast)
            self.assertEqual(self.snapshot(source), before)

    def test_rotation_scale_not_implemented(self):
        """rotation・scale は fast で変更前に NotImplementedError(既定の True も含む)。"""
        source, target = self.scene("transform", "transform", True)
        before = self.snapshot(source)
        node = mlib.getNode(source)
        for flags in ({}, {"rotation": True, "scale": False}, {"rotation": False, "scale": True}):
            with self.subTest(flags=flags), self.assertRaises(NotImplementedError):
                node.matchTransform(target, fast=True, **flags)
        self.assertEqual(self.snapshot(source), before)
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            node.matchTransform(target, fast=None)
        with self.assertRaises(TypeError):
            node.matchTransform(self.make("network", "dg#"), rotation=False, scale=False, fast=True)

    def test_fast_locked_channel(self):
        """fast で動かす translate がロックされていれば RuntimeError。"""
        source, target = self.scene("transform", "transform", False)
        cmds.setAttr(source + ".tx", lock=True)
        with self.assertRaises(RuntimeError):
            mlib.getNode(source).matchTransform(target, rotation=False, scale=False, fast=True)

    def test_normal_undo_once(self):
        """通常経路は cmds.matchTransform のままで、Undo 1 回で戻る。"""
        source, target = self.scene("transform", "transform", True)
        before = self.snapshot(source)
        cmds.flushUndo()
        mlib.getNode(source).matchTransform(target, pivots=True)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibTransformMatch")
        cmds.undo()
        self.assertSequenceAlmostEqual(self.snapshot(source), before)


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
