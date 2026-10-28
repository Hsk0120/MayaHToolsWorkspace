"""Transformの空間・単位・親子変更と失敗時の状態を検証する。"""

import unittest
import uuid

import maya.cmds as cmds

import mlib


class TransformBasicsTest(unittest.TestCase):
    """同じ入力をMayaコマンドへ適用した結果と比較する。"""

    def setUp(self):
        self.namespace = ":transformBasics_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg")

    def tearDown(self):
        for name in cmds.ls(self.namespace + ":*", long=True) or []:
            if cmds.objExists(name):
                cmds.lockNode(name, lock=False)
        if cmds.namespace(exists=self.namespace):
            cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.currentUnit(linear=self.units[0], angle=self.units[1])
        cmds.undoInfo(state=self.undo_state)

    def make(self, parent=None, kind="transform"):
        """選択を変更せずTransformを作る。"""
        flags = {"parent": parent.getFullName()} if parent is not None else {}
        return mlib.getNode(cmds.createNode(kind, name=self.namespace + ":node#", skipSelect=True, **flags))

    def matrix(self, node, world=False):
        """cmdsから16成分を取得し、mlibの取得結果へ依存せず比較する。"""
        return cmds.xform(node.getFullName(), query=True, matrix=True, worldSpace=world)

    def assertValuesAlmostEqual(self, actual, expected):
        """XYZやマトリクスを同じ許容誤差で比較する。"""
        self.assertEqual(len(actual), len(expected))
        for index, (value, reference) in enumerate(zip(actual, expected)):
            self.assertAlmostEqual(value, reference, places=6, msg="component {}".format(index))

    def test_local_translation_uses_cm_despite_ui_unit_and_preserves_offsets(self):
        """m表示でもcmでtranslateを設定し、回転・スケール・ピボットを保つ。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                node = self.make()
                name = node.getFullName()
                offsets = {"r": (20, -30, 40), "s": (2, 3, 4), "sh": (.1, .2, .3),
                           "rp": (1, 2, 3), "rpt": (4, 5, 6), "sp": (-1, -2, -3)}
                for attr, value in offsets.items():
                    cmds.setAttr(name + "." + attr, *value)
                cmds.currentUnit(linear="m")
                before = {attr: cmds.getAttr(name + "." + attr) for attr in offsets}
                self.assertIs(node.setTranslate((100, -200, 300), at=1, fast=fast), node)
                self.assertValuesAlmostEqual(cmds.getAttr(name + ".t")[0], (1, -2, 3))
                self.assertEqual({attr: cmds.getAttr(name + "." + attr) for attr in offsets}, before)
                self.assertValuesAlmostEqual(tuple(node.getTranslate(at=1)), (100, -200, 300))
                cmds.currentUnit(linear="cm")

    def test_world_origin_translation_under_rotated_scaled_parent(self):
        """非一様スケールを持つ親の下でも、指定ワールド原点へ移動する。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                parent = self.make()
                cmds.setAttr(parent.getFullName() + ".t", 8, -3, 9)
                cmds.setAttr(parent.getFullName() + ".r", 20, 35, -15)
                cmds.setAttr(parent.getFullName() + ".s", 2, 3, 4)
                node = self.make(parent)
                cmds.setAttr(node.getFullName() + ".r", 11, 22, 33)
                cmds.setAttr(node.getFullName() + ".rp", 1, 2, 3)
                rotation = cmds.getAttr(node.getFullName() + ".r")
                self.assertIs(node.setTranslate((30, -20, 10), worldSpace=True, at=4, fast=fast), node)
                self.assertValuesAlmostEqual(self.matrix(node, world=True)[12:15], (30, -20, 10))
                self.assertEqual(cmds.getAttr(node.getFullName() + ".r"), rotation)

    def test_rotation_matches_cmds_for_all_rotate_orders(self):
        """6種のrotateOrderとrotateAxisを含め、角度入力をcmdsと比較する。"""
        for fast in (False, True):
            for order in range(6):
                with self.subTest(fast=fast, order=order):
                    node, reference = self.make(), self.make()
                    for item in (node, reference):
                        name = item.getFullName()
                        cmds.setAttr(name + ".ro", order)
                        cmds.setAttr(name + ".ra", 7, -13, 19)
                        cmds.setAttr(name + ".t", 3, 4, 5)
                        cmds.setAttr(name + ".s", 2, 3, 4)
                        cmds.setAttr(name + ".rp", 1, -2, 3)
                    # setRotateの入力はrotateチャンネルではなく、rotateAxis込みの姿勢。
                    cmds.setAttr(reference.getFullName() + ".ra", 0, 0, 0)
                    cmds.setAttr(reference.getFullName() + ".r", 35, -50, 80)
                    self.assertIs(node.setRotate((35, -50, 80), unit="deg", fast=fast), node)
                    self.assertValuesAlmostEqual(self.matrix(node)[:12], self.matrix(reference)[:12])
                    self.assertEqual(cmds.getAttr(node.getFullName() + ".ra"), [(7, -13, 19)])
                    self.assertEqual(cmds.getAttr(node.getFullName() + ".t"), [(3, 4, 5)])
                    self.assertEqual(cmds.getAttr(node.getFullName() + ".s"), [(2, 3, 4)])
                    self.assertEqual(cmds.getAttr(node.getFullName() + ".rp"), [(1, -2, 3)])

    def test_scale_preserves_signed_channels_and_other_transform_values(self):
        """負スケールの指定値を保ち、回転・移動・シアーには書き込まない。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                node, reference = self.make(), self.make()
                for item in (node, reference):
                    name = item.getFullName()
                    cmds.setAttr(name + ".t", 3, -4, 5)
                    cmds.setAttr(name + ".r", 15, 30, 45)
                    cmds.setAttr(name + ".sh", .1, .2, -.3)
                    cmds.setAttr(name + ".sp", 2, 1, -3)
                cmds.setAttr(reference.getFullName() + ".s", -2, 3, -4)
                self.assertIs(node.setScale((-2, 3, -4), fast=fast), node)
                self.assertEqual(cmds.getAttr(node.getFullName() + ".s"), [(-2, 3, -4)])
                self.assertValuesAlmostEqual(self.matrix(node), self.matrix(reference))

    def test_world_matrix_matches_cmds_with_nonuniform_parent(self):
        """ワールドマトリクスを親の非一様スケール込みで往復する。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                parent = self.make()
                cmds.setAttr(parent.getFullName() + ".t", 5, -7, 9)
                cmds.setAttr(parent.getFullName() + ".r", 10, 25, -35)
                cmds.setAttr(parent.getFullName() + ".s", 2, 3, 4)
                node, reference = self.make(parent), self.make()
                cmds.setAttr(reference.getFullName() + ".t", 30, -20, 10)
                cmds.setAttr(reference.getFullName() + ".r", -15, 40, 65)
                cmds.setAttr(reference.getFullName() + ".s", 1.2, 2.3, 3.4)
                cmds.setAttr(reference.getFullName() + ".sh", .1, -.2, .3)
                target = self.matrix(reference, world=True)
                self.assertIs(node.setMatrix(target, ws=True, fast=fast), node)
                self.assertValuesAlmostEqual(self.matrix(node, world=True), target)

    def test_matrix_update_is_one_undo_step_for_all_trs_and_shear(self):
        """複数チャンネルを変更するsetMatrixを一度のUndo/redoで戻す。"""
        node, reference = self.make(), self.make()
        cmds.setAttr(node.getFullName() + ".t", 1, 2, 3)
        cmds.setAttr(reference.getFullName() + ".t", 6, 7, 8)
        cmds.setAttr(reference.getFullName() + ".r", 20, 35, 50)
        cmds.setAttr(reference.getFullName() + ".s", 2, 3, 4)
        cmds.setAttr(reference.getFullName() + ".sh", .1, .2, .3)
        before, target = self.matrix(node), self.matrix(reference)
        cmds.flushUndo()
        node.setMatrix(target)
        self.assertValuesAlmostEqual(self.matrix(node), target)
        cmds.undo()
        self.assertValuesAlmostEqual(self.matrix(node), before)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        cmds.redo()
        self.assertValuesAlmostEqual(self.matrix(node), target)

    def test_fast_matrix_update_keeps_existing_undo_entry(self):
        """fastのマトリクス変更は別ノードの通常Undoを消費しない。"""
        node, marker, reference = self.make(), self.make(), self.make()
        cmds.setAttr(reference.getFullName() + ".t", 4, 5, 6)
        cmds.setAttr(reference.getFullName() + ".r", 10, 20, 30)
        target = self.matrix(reference)
        cmds.flushUndo()
        marker.setTranslate((7, 8, 9), at=1)
        entry = cmds.undoInfo(query=True, undoName=True)
        node.setMatrix(target, fast=True)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), entry)
        self.assertTrue(cmds.undoInfo(query=True, state=True))
        cmds.undo()
        self.assertValuesAlmostEqual(self.matrix(node), target)
        self.assertEqual(cmds.getAttr(marker.getFullName() + ".t"), [(0, 0, 0)])

    def test_calculated_world_translation_is_independent_and_does_not_write(self):
        """ロック中でもget=Trueは親空間への計算だけを行い、返すlistは独立する。"""
        parent = self.make()
        cmds.setAttr(parent.getFullName() + ".t", 10, 20, 30)
        cmds.setAttr(parent.getFullName() + ".s", 2, 3, 4)
        node = self.make(parent)
        cmds.setAttr(node.getFullName() + ".tx", lock=True)
        before = self.matrix(node)
        cmds.flushUndo()
        planned = node.setTranslate((14, 29, 46), ws=True, at=1, safe=True, get=True)
        self.assertIsInstance(planned, list)
        self.assertValuesAlmostEqual(planned, (2, 3, 4))
        planned[0] = 999
        self.assertEqual(self.matrix(node), before)
        self.assertTrue(cmds.getAttr(node.getFullName() + ".tx", lock=True))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_reparent_preserves_world_or_local_matrix_as_requested(self):
        """親変更の既定はワールド、relative=Trueはローカルを保持する。"""
        for fast in (False, True):
            for relative in (False, True):
                with self.subTest(fast=fast, relative=relative):
                    old_parent, new_parent = self.make(), self.make()
                    for parent, position in ((old_parent, (5, 7, 9)), (new_parent, (-4, 2, 8))):
                        cmds.setAttr(parent.getFullName() + ".t", *position)
                        cmds.setAttr(parent.getFullName() + ".r", 10, 20, 30)
                        cmds.setAttr(parent.getFullName() + ".s", 2, 3, 4)
                    node = self.make(old_parent)
                    cmds.setAttr(node.getFullName() + ".t", 1, 2, 3)
                    cmds.setAttr(node.getFullName() + ".r", -15, 25, 35)
                    before = self.matrix(node, world=not relative)
                    held = node.getPlug("ty")
                    self.assertIs(node.setParent(new_parent, relative=relative, fast=fast), node)
                    self.assertEqual(node.getParent().mnode(), new_parent.mnode())
                    self.assertTrue(held.isValid())
                    self.assertValuesAlmostEqual(self.matrix(node, world=not relative), before)

    def test_reparent_undo_redo_rebinds_held_node_and_plug(self):
        """保持中のNode/Plugが親変更とUndo/redo後の完全パスへ追従する。"""
        old_parent, new_parent = self.make(), self.make()
        node = self.make(old_parent)
        held = node.getPlug("tx")
        cmds.setAttr(node.getFullName() + ".tx", 6)
        original = node.getFullName()
        cmds.flushUndo()
        node.setParent(new_parent, relative=True)
        changed = node.getFullName()
        self.assertNotEqual(original, changed)
        cmds.undo()
        self.assertEqual(node.getFullName(), original)
        self.assertEqual(held.get(), 6)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        cmds.redo()
        self.assertEqual(node.getFullName(), changed)
        self.assertEqual(held.get(), 6)

    def test_same_parent_and_world_root_are_noops(self):
        """同じ親と既にワールド直下の指定は、Undoへ空の更新を追加しない。"""
        for fast in (False, True):
            parent = self.make()
            child = self.make(parent)
            cmds.flushUndo()
            self.assertIs(child.setParent(parent, fast=fast), child)
            self.assertIs(parent.setParent(None, fast=fast), parent)
            self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_cycle_rejection_preserves_hierarchy_and_transforms(self):
        """子孫を親に指定しても階層とワールドマトリクスを壊さない。"""
        for fast in (False, True):
            root = self.make()
            child = self.make(root)
            leaf = self.make(child)
            cmds.setAttr(root.getFullName() + ".t", 1, 2, 3)
            paths = [node.getFullName() for node in (root, child, leaf)]
            matrices = [self.matrix(node, world=True) for node in (root, child, leaf)]
            with self.assertRaises(RuntimeError):
                root.setParent(leaf, fast=fast)
            self.assertEqual([node.getFullName() for node in (root, child, leaf)], paths)
            self.assertEqual([self.matrix(node, world=True) for node in (root, child, leaf)], matrices)

    def test_singular_parent_matrix_rejection_does_not_write_channels(self):
        """反転できない親の下へのワールド指定は、変更前にValueErrorとなる。"""
        # scale=0はMayaが微小値へ補正するため、実際に特異な親OPMを使う。
        singular = (0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
        for fast in (False, True):
            parent = self.make()
            cmds.setAttr(parent.getFullName() + ".offsetParentMatrix", *singular, type="matrix")
            node, reference = self.make(parent), self.make()
            self.assertTrue(node.mpath().exclusiveMatrix().isSingular())
            cmds.setAttr(node.getFullName() + ".t", 1, 2, 3)
            before = self.matrix(node)
            cmds.flushUndo()
            for flags in ({}, {"safe": True}, {"get": True}, {"safe": True, "get": True}):
                with self.subTest(fast=fast, flags=flags):
                    with self.assertRaises(ValueError):
                        node.setMatrix(self.matrix(reference), ws=True, fast=fast, **flags)
                    self.assertEqual(self.matrix(node), before)
                    self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_tiny_but_invertible_parent_is_not_rejected(self):
        """小さい行列式だけで拒否せず、OpenMayaが反転できる親を受け付ける。"""
        for fast in (False, True):
            parent = self.make()
            tiny = (1e-13, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
            cmds.setAttr(parent.getFullName() + ".offsetParentMatrix", *tiny, type="matrix")
            node, reference = self.make(parent), self.make()
            cmds.setAttr(reference.getFullName() + ".t", 3, 4, 5)
            target = self.matrix(reference)
            self.assertIs(node.setMatrix(target, ws=True, fast=fast), node)
            self.assertValuesAlmostEqual(self.matrix(node, world=True), target)

    def test_flag_conflicts_and_invalid_fast_do_not_record_changes(self):
        """長短フラグの競合と不正なfastは、更新とUndo記録より前に拒否する。"""
        node = self.make()
        before = self.matrix(node)
        calls = ((node.setTranslate, (1, 2, 3)), (node.setRotate, (.1, .2, .3)),
                 (node.setScale, (2, 3, 4)), (node.setMatrix, before))
        cmds.flushUndo()
        for method, value in calls:
            with self.subTest(method=method.__name__):
                with self.assertRaises(TypeError):
                    method(value, worldSpace=False, ws=False)
                with self.assertRaises(TypeError):
                    method(value, fast=1)
                self.assertEqual(self.matrix(node), before)
                self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_fast_parenting_unsupported_cases_reject_before_update(self):
        """Jointとadd=Trueのfast親変更は、接続や階層を変えずに拒否する。"""
        parent, node, joint = self.make(), self.make(), self.make(kind="joint")
        for item, flags in ((joint, {}), (node, {"add": True})):
            with self.subTest(kind=type(item).__name__, flags=flags):
                before = item.getFullName()
                with self.assertRaises(NotImplementedError):
                    item.setParent(parent, fast=True, **flags)
                self.assertEqual(item.getFullName(), before)
                self.assertIsNone(item.getParent())


if __name__ == "__main__":
    unittest.main()
