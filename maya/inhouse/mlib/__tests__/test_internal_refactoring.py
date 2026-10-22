"""内部責務の移動後も保存形式・部分失敗・型登録の契約を維持する。"""
import sys
import unittest
from unittest.mock import patch

import maya.cmds as cmds
import mlib


class InternalRefactoringTest(unittest.TestCase):
    """公開入口から内部再構成の境界条件を検証する。"""

    def setUp(self):
        """専用シーンと既定単位を用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")

    def test_class_operations_do_not_call_command_entries(self):
        """公開コマンドを差し替えてもクラスの追加・予約操作を実行できる。"""
        import importlib
        import maya.utils
        from mlib.common import Deferred
        add_module = importlib.import_module("mlib.cmds.addAttr")
        deferred_module = importlib.import_module("mlib.cmds.executeDeferred")
        node = mlib.createNode("transform")
        with patch.object(add_module, "addAttr", side_effect=AssertionError("reverse dependency")):
            plug = node.addAttr("referenceCheck", attributeType="double", defaultValue=3)
        self.assertEqual(plug.get(), 3)
        cmds.undo()
        self.assertFalse(cmds.attributeQuery("referenceCheck", node=node.getFullName(), exists=True))
        callback = lambda: None
        with patch.object(deferred_module, "executeDeferred", side_effect=AssertionError("reverse dependency")), \
                patch.object(maya.utils, "executeDeferred") as enqueue:
            Deferred.call(callback, 3, value=4)
            enqueue.assert_called_once_with(callback, 3, value=4)

    def test_general_input_expansion_does_not_reenter_node_resolution(self):
        """一度きりの反復入力とPlug列を、Nodesの解決入口へ戻らず名前にする。"""
        from mlib.nodes.node import Nodes
        node = mlib.createNode("transform")
        plug = node.getPlug("tx")
        with patch.object(Nodes, "_resolve_inputs", side_effect=AssertionError("input cycle")):
            self.assertEqual(mlib._core.object.Object._input_names(x for x in [[plug]]), [plug.getFullName()])
            with self.assertRaises(TypeError):
                mlib._core.object.Object._input_names([node, node.getFullName()])

    def test_snapshot_base_kind_and_serialized_shape(self):
        """基底Snapshotのkindによる適用と既存JSON構造を維持する。"""
        from mlib.json.snapshots import Snapshot
        node = mlib.createNode("transform")
        node.getPlug("tx").set(3)
        saved = mlib.json.capture([node], kind="attributes", attributes=["translateX"])
        data = saved.asData()
        self.assertEqual(set(data), {"kind", "records", "units", "version"})
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["records"][0]["attributes"],
                         [{"name": "translateX", "type": "doubleLinear", "value": 3.0}])
        generic = Snapshot(**data)
        node.getPlug("tx").set(7)
        generic.apply()
        self.assertEqual(node.getPlug("tx").get(), 3)
        cmds.undo()
        self.assertEqual(node.getPlug("tx").get(), 7)
        self.assertEqual(mlib.json.loads(mlib.json.dumps(saved)).asData(), data)

    def test_snapshot_partial_failure_and_undo(self):
        """全件検証後の実行失敗は先行変更を残し、一回のUndoで戻せる。"""
        from mlib.json import snapshots
        node = mlib.createNode("transform")
        saved = mlib.json.capture([node], kind="attributes", attributes=["translateX", "translateY"])
        node.getPlug("tx").set(3)
        node.getPlug("ty").set(4)
        original = snapshots._set_attribute

        def fail_second(name, attr):
            """二番目の更新時点でMayaの実行失敗を模擬する。"""
            if attr["name"] == "translateY":
                raise RuntimeError("second write failed")
            return original(name, attr)

        with patch.object(snapshots, "_set_attribute", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "second write"):
                saved.apply()
        self.assertEqual(node.getPlug("tx").get(), 0)
        self.assertEqual(node.getPlug("ty").get(), 4)
        cmds.undo()
        self.assertEqual(node.getPlug("tx").get(), 3)
        self.assertEqual(node.getPlug("ty").get(), 4)

    def test_influence_single_multiple_and_scene_changes(self):
        """単数・複数検索が改名・除去後にも同じ物理番号を返す。"""
        joints = [cmds.createNode("joint") for _ in range(3)]
        mesh = cmds.polyCube(ch=False)[0]
        skin = mlib.getNode(cmds.skinCluster(joints, mesh, tsb=True)[0])
        joints[0] = cmds.rename(joints[0], "renamedInfluence")
        queries = [joints[2], joints[0], joints[2], "notAnInfluence"]
        self.assertEqual([skin._jnt_index(x) for x in queries],
                         skin._influence_indices(queries, skin.fn.influenceObjects()))
        cmds.skinCluster(skin.getFullName(), edit=True, removeInfluence=joints[1])
        self.assertIsNone(skin._jnt_index(joints[1]))
        self.assertEqual(skin._jnt_index(joints[2]), 1)
        cmds.undo()
        self.assertEqual(skin._jnt_index(joints[2]), 2)

    def test_numeric_read_write_and_units(self):
        """数値型の共有定義が通常更新・fast更新・単位規則を変えない。"""
        node = mlib.createNode("transform")
        for kind, value in (("bool", True), ("byte", 12), ("char", 3), ("short", -2),
                            ("long", 53), ("float", 1.25), ("double", 2.5)):
            name = "value_" + kind
            cmds.addAttr(node.getFullName(), longName=name, attributeType=kind)
            plug = node.getPlug(name)
            plug.set(value)
            normal = plug.get()
            plug.set(0, fast=True)
            plug.set(value, fast=True)
            self.assertEqual(plug.get(), normal)
            self.assertEqual(plug.getDataType(), kind)
        cmds.currentUnit(linear="m", angle="rad")
        node.getPlug("tx").set(2, fast=True)
        self.assertAlmostEqual(node.getPlug("tx").get(), 2)
        # 角度のget/setはUI単位によらずrad。
        node.getPlug("rx").set(1, fast=True)
        import math
        self.assertAlmostEqual(node.getPlug("rx").get(), 1.0)

    def test_reload_rebuilds_registry_and_caches(self):
        """新しい基底・型登録・型情報で再取得でき、独自登録を残さない。"""
        from mlib._core import typeHierarchy
        old_registry = mlib.nodes.Node._registry
        old_registry.register("temporaryRefactorType", mlib.nodes.Node)
        typeHierarchy._INHERITED_TYPES_CACHE["temporaryRefactorType"] = ("temporaryRefactorType",)
        name = cmds.createNode("transform")
        for _ in range(2):
            mlib.reload()
            node = mlib.getNode(name)
            self.assertIs(type(node), mlib.nodes.Transform)
            self.assertIs(type(node.getPlug("tx")), mlib.plugs.DoubleLinearPlug)
            self.assertIsNot(mlib.nodes.Node._registry, old_registry)
            self.assertIsNone(mlib.nodes.Node._registry.lookup("temporaryRefactorType"))
            from mlib._core import typeHierarchy
            self.assertNotIn("temporaryRefactorType", typeHierarchy._INHERITED_TYPES_CACHE)
            node.getPlug("tx").set(9, fast=True)
            self.assertEqual(node.getPlug("tx").get(), 9)
            self.assertIs(mlib.getNode, mlib.cmds.getNode)

    def test_calculation_validation_before_target_resolution(self):
        """不正入力で接続先解決や更新を開始しない。"""
        node = mlib.createNode("addDoubleLinear")
        node.setInput(1, 5)
        with patch.object(type(node), "getInputPlug", side_effect=AssertionError("target resolved")):
            with self.assertRaises(ValueError):
                node.setInput(1, float("nan"))
            with self.assertRaises(TypeError):
                node.connectInput(1, object())
        self.assertEqual(node.getInputPlug(1).get(), 5)

    def test_calculation_shared_edit_modes(self):
        """共通化後も戻り値・Undo・fast・接続元の入力形式を維持する。"""
        node = mlib.createNode("addDoubleLinear")
        source = mlib.createNode("addDoubleLinear")
        node.setInput(1, 2)
        self.assertIs(node.setInput(1, 7), node)
        cmds.undo()
        self.assertEqual(node.getInputPlug(1).get(), 2)
        cmds.redo()
        self.assertEqual(node.getInputPlug(1).get(), 7)
        cmds.flushUndo()
        self.assertIs(node.setInput(1, 9, fast=True), node)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertEqual(node.getInputPlug(1).get(), 9)
        for value in (source.getPlug('output'), source.getPlug('output').getFullName(), source.getPlug('output').mplug()):
            self.assertIs(node.connectInput(1, value), node)
            self.assertTrue(source.getPlug('output').isConnectedTo(node.getInputPlug(1)))
            cmds.undo()
            self.assertFalse(source.getPlug('output').isConnectedTo(node.getInputPlug(1)))

    def test_deferred_entrypoints_share_validation(self):
        """どちらの入口も同じ引数で一度だけMayaへ予約する。"""
        import maya.utils
        from mlib.common import Deferred
        callback = lambda value: value
        for entry in (mlib.executeDeferred, Deferred.call):
            with patch.object(maya.utils, "executeDeferred") as enqueue:
                self.assertIsNone(entry(callback, 1, flag=True))
                enqueue.assert_called_once_with(callback, 1, flag=True)
                with self.assertRaises(TypeError):
                    entry("print('not callable')")
                self.assertEqual(enqueue.call_count, 1)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
