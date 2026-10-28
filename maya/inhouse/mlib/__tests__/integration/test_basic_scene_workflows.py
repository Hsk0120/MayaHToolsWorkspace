"""ノード取得・Plug編集・Transform・削除を組み合わせた操作を検証する。"""

import unittest
import uuid

import maya.cmds as cmds

import mlib
from mlib.decorator import undoChunk, undoTransaction


class BasicSceneWorkflowsTest(unittest.TestCase):
    """小さなDGとDAGを組み、Undo後も値・接続・保持参照を確認する。"""

    def setUp(self):
        self.namespace = ":basicWorkflows_" + uuid.uuid4().hex
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

    def make(self, kind="transform", parent=None):
        """Mayaコマンドで試験用ノードを作り、mlibの参照を取得する。"""
        flags = {"parent": parent.getFullName()} if parent is not None else {}
        return mlib.getNode(cmds.createNode(kind, name=self.namespace + ":node#", skipSelect=True, **flags))

    def assertConnected(self, source, destination):
        """mlibの接続照会と独立したcmdsで接続の有無を判定する。"""
        self.assertTrue(cmds.isConnected(source.getFullName(), destination.getFullName()))

    def test_utility_graph_delete_undo_redo_restores_edges_and_evaluation(self):
        """中間ノードを削除し、Undoで上下流の接続とDG評価を回復する。"""
        driver, utility, driven = self.make(), self.make("multiplyDivide"), self.make()
        source, input_plug = driver.getPlug("tx"), utility.getPlug("input1X")
        output, destination = utility.getPlug("outputX"), driven.getPlug("ty")
        source.set(3)
        utility.getPlug("input2X").set(2)
        input_plug.connect(source)
        destination.connect(output)
        self.assertEqual(cmds.getAttr(destination.getFullName()), 6)
        cmds.flushUndo()
        utility.delete()
        self.assertFalse(utility.isValid())
        self.assertFalse(input_plug.isValid())
        self.assertIsNone(destination.getSource())
        cmds.undo()
        self.assertTrue(utility.isValid() and input_plug.isValid() and output.isValid())
        self.assertConnected(source, input_plug)
        self.assertConnected(output, destination)
        self.assertEqual(cmds.getAttr(destination.getFullName()), 6)
        cmds.redo()
        self.assertFalse(utility.isValid())
        cmds.undo()
        source.set(5)
        self.assertEqual(cmds.getAttr(destination.getFullName()), 10)

    def test_attribute_creation_connection_transform_and_delete_share_one_undo(self):
        """アトリビュート追加・接続・TRS更新・削除を一つの操作として戻す。"""
        driver, driven, temporary = self.make(), self.make(), self.make()
        temporary_name = temporary.getFullName()
        cmds.flushUndo()
        with undoChunk("basicSceneWorkflow"):
            amount = driver.addAttr("amount", type="double", defaultValue=2)
            amount.set(8)
            driven.getPlug("tx").connect(amount)
            driven.setRotate((10, 20, 30), unit="deg")
            temporary.delete()
        self.assertEqual(cmds.getAttr(driven.getFullName() + ".tx"), 8)
        self.assertFalse(temporary.isValid())
        cmds.undo()
        self.assertFalse(cmds.attributeQuery("amount", node=driver.getFullName(), exists=True))
        self.assertEqual(cmds.getAttr(driven.getFullName() + ".t"), [(0, 0, 0)])
        self.assertEqual(cmds.getAttr(driven.getFullName() + ".r"), [(0, 0, 0)])
        self.assertTrue(cmds.objExists(temporary_name))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        cmds.redo()
        self.assertTrue(amount.isValid())
        self.assertConnected(amount, driven.getPlug("tx"))
        self.assertEqual(cmds.getAttr(driven.getFullName() + ".tx"), 8)
        self.assertFalse(temporary.isValid())

    def test_transaction_exception_restores_attributes_connections_and_transform(self):
        """例外時のトランザクション巻戻しで、追加と接続と移動を元へ戻す。"""
        driver, driven, temporary = self.make(), self.make(), self.make()
        cmds.flushUndo()
        driver.getPlug("ty").set(11)
        with self.assertRaisesRegex(ValueError, "workflow failure"):
            with undoTransaction("basicSceneRollback"):
                amount = driver.addAttr("amount", type="double")
                amount.set(9)
                driven.getPlug("tx").connect(amount)
                driven.setTranslate((0, 7, 8), at=1, safe=True)
                temporary.delete()
                raise ValueError("workflow failure")
        self.assertFalse(cmds.attributeQuery("amount", node=driver.getFullName(), exists=True))
        self.assertIsNone(driven.getPlug("tx").getSource())
        self.assertEqual(cmds.getAttr(driven.getFullName() + ".t"), [(0, 0, 0)])
        self.assertTrue(temporary.isValid())
        self.assertEqual(driver.getPlug("ty").get(), 11)
        cmds.undo()
        self.assertEqual(driver.getPlug("ty").get(), 0)

    def test_plain_chunk_exception_keeps_partial_work_until_explicit_undo(self):
        """通常のチャンクは例外で自動巻戻しせず、先行変更を一度のUndoで戻す。"""
        driver, driven = self.make(), self.make()
        cmds.setAttr(driven.getFullName() + ".ty", lock=True)
        cmds.flushUndo()
        with self.assertRaises(RuntimeError):
            with undoChunk("basicScenePartial"):
                amount = driver.addAttr("amount", type="double")
                amount.set(4)
                driven.getPlug("tx").connect(amount)
                driven.getPlug("ty").set(5)
        self.assertEqual(cmds.getAttr(driven.getFullName() + ".tx"), 4)
        self.assertTrue(cmds.getAttr(driven.getFullName() + ".ty", lock=True))
        cmds.undo()
        self.assertFalse(cmds.attributeQuery("amount", node=driver.getFullName(), exists=True))
        self.assertIsNone(driven.getPlug("tx").getSource())
        self.assertEqual(cmds.getAttr(driven.getFullName() + ".tx"), 0)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_delete_connected_dynamic_attribute_and_undo_restores_reference(self):
        """接続中の追加アトリビュートだけを削除し、Undoで値と保持参照を復元する。"""
        driver, driven = self.make(), self.make()
        source = driver.addAttr("amount", type="double", defaultValue=3)
        destination = driven.addAttr("amount", type="double")
        source.set(7)
        destination.connect(source)
        cmds.flushUndo()
        self.assertIsNone(destination.delete())
        self.assertFalse(destination.isValid())
        self.assertTrue(driver.isValid() and driven.isValid() and source.isValid())
        cmds.undo()
        self.assertTrue(destination.isValid())
        self.assertConnected(source, destination)
        self.assertEqual(cmds.getAttr(destination.getFullName()), 7)
        cmds.redo()
        self.assertFalse(destination.isValid())

    def test_sparse_array_removal_then_owner_delete_restore_separate_undo_steps(self):
        """疎配列の接続要素削除と所有ノード削除を、別々にUndo/redoする。"""
        driver, owner = self.make("network"), self.make("network")
        source = driver.addAttr("amount", type="double")
        array = owner.addAttr("values", type="double", multi=True)
        source.set(12)
        array[3].set(2)
        array[40].connect(source)
        cmds.flushUndo()
        array.removeElement(40)
        owner.delete()
        self.assertFalse(owner.isValid())
        cmds.undo()
        self.assertTrue(owner.isValid())
        self.assertEqual(array.getIndices(), [3])
        cmds.undo()
        self.assertEqual(array.getIndices(), [3, 40])
        self.assertEqual(array[3].get(), 2)
        self.assertConnected(source, array[40])
        self.assertEqual(array[40].get(), 12)
        cmds.redo()
        self.assertEqual(array.getIndices(), [3])
        cmds.redo()
        self.assertFalse(owner.isValid())
        self.assertTrue(driver.isValid())

    def test_safe_transform_edit_under_parent_keeps_driver_and_undo_boundary(self):
        """親変更後のsafe移動が接続軸を保ち、通常/fastそれぞれのUndo境界を維持する。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                parent, driver, child = self.make(), self.make(), self.make()
                cmds.setAttr(parent.getFullName() + ".t", 10, 20, 30)
                driver.getPlug("ty").set(12)
                child.getPlug("ty").connect(driver.getPlug("ty"))
                cmds.flushUndo()
                child.setParent(parent, relative=True, fast=fast)
                child.setTranslate((4, 5, 6), at=1, safe=True, fast=fast)
                self.assertEqual(cmds.getAttr(child.getFullName() + ".t"), [(4, 12, 6)])
                self.assertEqual(cmds.xform(child.getFullName(), query=True, translation=True, worldSpace=True),
                                 [14, 32, 36])
                self.assertConnected(driver.getPlug("ty"), child.getPlug("ty"))
                if fast:
                    self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
                else:
                    cmds.undo()
                    self.assertEqual(cmds.getAttr(child.getFullName() + ".t"), [(0, 12, 0)])
                    self.assertEqual(child.getParent().mnode(), parent.mnode())
                    cmds.undo()
                    self.assertIsNone(child.getParent())
                    self.assertConnected(driver.getPlug("ty"), child.getPlug("ty"))

    def test_safe_batch_delete_preserves_connected_subtree_and_restores_other_nodes(self):
        """safe削除で接続を持つ子孫を保護し、孤立ノードだけをUndoで戻す。"""
        root = self.make()
        child = self.make(parent=root)
        receiver, isolated = self.make("network"), self.make()
        input_plug = receiver.addAttr("input", type="message")
        input_plug.connect(child.getPlug("message"))
        cmds.flushUndo()
        with undoChunk("basicSceneSafeDelete"):
            for node in (root, isolated):
                node.delete(safe=True)
        self.assertTrue(root.isValid() and child.isValid() and receiver.isValid())
        self.assertFalse(isolated.isValid())
        self.assertConnected(child.getPlug("message"), input_plug)
        cmds.undo()
        self.assertTrue(isolated.isValid())
        self.assertConnected(child.getPlug("message"), input_plug)
        cmds.redo()
        self.assertFalse(isolated.isValid())
        self.assertTrue(root.isValid() and child.isValid())

    def test_renamed_reparented_connected_node_survives_delete_undo_cycles(self):
        """名前と親を変えた保持参照で削除を繰り返し、接続と評価を復元する。"""
        driver, driven, parent = self.make(), self.make(), self.make()
        source, destination = driver.getPlug("tx"), driven.getPlug("tz")
        source.set(9)
        destination.connect(source)
        cmds.rename(driven.getFullName(), self.namespace + ":renamed")
        driven.setParent(parent, relative=True)
        name = driven.getFullName()
        cmds.flushUndo()
        driven.delete()
        for _ in range(3):
            self.assertFalse(driven.isValid() or destination.isValid())
            cmds.undo()
            self.assertEqual(driven.getFullName(), name)
            self.assertConnected(source, destination)
            self.assertEqual(destination.get(), 9)
            cmds.redo()

    def test_ui_unit_changes_do_not_change_connected_distance_evaluation(self):
        """距離Plugの接続と親子移動を、cm/m/mm表示へ切り替えて照合する。"""
        driver, parent = self.make(), self.make()
        child = self.make(parent=parent)
        driver.getPlug("tx").set(100)
        parent.getPlug("tx").set(200)
        child.getPlug("tx").connect(driver.getPlug("tx"))
        for unit, expected_ui in (("cm", 300), ("m", 3), ("mm", 3000)):
            with self.subTest(unit=unit):
                cmds.currentUnit(linear=unit)
                self.assertEqual(child.getPlug("tx").get(), 100)
                self.assertAlmostEqual(cmds.xform(child.getFullName(), query=True,
                                                worldSpace=True, translation=True)[0], expected_ui)
                self.assertAlmostEqual(child.getTranslate(worldSpace=True, at=4).x, 300)
                self.assertConnected(driver.getPlug("tx"), child.getPlug("tx"))


if __name__ == "__main__":
    unittest.main()
