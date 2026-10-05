"""内部責務の移動後も保存形式・部分失敗・型登録の契約を維持する。"""
import sys
import unittest
from unittest.mock import patch

import maya.cmds as cmds
import hlib


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
        from hlib.events import Deferred
        add_module = importlib.import_module("hlib.cmds.addAttr")
        deferred_module = importlib.import_module("hlib.cmds.executeDeferred")
        node = hlib.createNode("transform")
        with patch.object(add_module, "addAttr", side_effect=AssertionError("reverse dependency")):
            plug = node.addAttr("referenceCheck", attributeType="double", defaultValue=3)
        self.assertEqual(plug.get(), 3)
        cmds.undo()
        self.assertFalse(cmds.attributeQuery("referenceCheck", node=node.fullName(), exists=True))
        callback = lambda: None
        with patch.object(deferred_module, "executeDeferred", side_effect=AssertionError("reverse dependency")), \
                patch.object(maya.utils, "executeDeferred") as enqueue:
            Deferred.call(callback, 3, value=4)
            enqueue.assert_called_once_with(callback, 3, value=4)

    def test_general_input_expansion_does_not_reenter_node_resolution(self):
        """一度きりの反復入力とPlug列を、Nodesの解決入口へ戻らず名前にする。"""
        from hlib.nodes.node import Nodes
        node = hlib.createNode("transform")
        plug = node.plug("tx")
        with patch.object(Nodes, "_resolve_inputs", side_effect=AssertionError("input cycle")):
            self.assertEqual(hlib.Object._input_names(x for x in [[plug]]), [plug.fullName()])
            with self.assertRaises(TypeError):
                hlib.Object._input_names([node, node.fullName()])

    def test_snapshot_base_kind_and_serialized_shape(self):
        """基底Snapshotのkindによる適用と既存JSON構造を維持する。"""
        from hlib.json.snapshots import Snapshot
        node = hlib.createNode("transform")
        node.plug("tx").set(3)
        saved = hlib.json.capture([node], kind="attributes", attributes=["translateX"])
        data = saved.toData()
        self.assertEqual(set(data), {"kind", "records", "units", "version"})
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["records"][0]["attributes"],
                         [{"name": "translateX", "type": "doubleLinear", "value": 3.0}])
        generic = Snapshot(**data)
        node.plug("tx").set(7)
        generic.apply()
        self.assertEqual(node.plug("tx").get(), 3)
        cmds.undo()
        self.assertEqual(node.plug("tx").get(), 7)
        self.assertEqual(hlib.json.loads(hlib.json.dumps(saved)).toData(), data)

    def test_snapshot_partial_failure_and_undo(self):
        """全件検証後の実行失敗は先行変更を残し、一回のUndoで戻せる。"""
        from hlib.json import snapshots
        node = hlib.createNode("transform")
        saved = hlib.json.capture([node], kind="attributes", attributes=["translateX", "translateY"])
        node.plug("tx").set(3)
        node.plug("ty").set(4)
        original = snapshots._set_attribute

        def fail_second(name, attr):
            """二番目の更新時点でMayaの実行失敗を模擬する。"""
            if attr["name"] == "translateY":
                raise RuntimeError("second write failed")
            return original(name, attr)

        with patch.object(snapshots, "_set_attribute", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "second write"):
                saved.apply()
        self.assertEqual(node.plug("tx").get(), 0)
        self.assertEqual(node.plug("ty").get(), 4)
        cmds.undo()
        self.assertEqual(node.plug("tx").get(), 3)
        self.assertEqual(node.plug("ty").get(), 4)

    def test_influence_single_multiple_and_scene_changes(self):
        """単数・複数検索が改名・除去後にも同じ物理番号を返す。"""
        joints = [cmds.createNode("joint") for _ in range(3)]
        mesh = cmds.polyCube(ch=False)[0]
        skin = hlib.getNode(cmds.skinCluster(joints, mesh, tsb=True)[0])
        joints[0] = cmds.rename(joints[0], "renamedInfluence")
        queries = [joints[2], joints[0], joints[2], "notAnInfluence"]
        self.assertEqual([skin._jnt_index(x) for x in queries],
                         skin._influence_indices(queries, skin.fn.influenceObjects()))
        cmds.skinCluster(skin.fullName(), edit=True, removeInfluence=joints[1])
        self.assertIsNone(skin._jnt_index(joints[1]))
        self.assertEqual(skin._jnt_index(joints[2]), 1)
        cmds.undo()
        self.assertEqual(skin._jnt_index(joints[2]), 2)

    def test_numeric_read_write_and_units(self):
        """数値型の共有定義が通常更新・fast更新・単位規則を変えない。"""
        node = hlib.createNode("transform")
        for kind, value in (("bool", True), ("byte", 12), ("char", 3), ("short", -2),
                            ("long", 53), ("float", 1.25), ("double", 2.5)):
            name = "value_" + kind
            cmds.addAttr(node.fullName(), longName=name, attributeType=kind)
            plug = node.plug(name)
            plug.set(value)
            normal = plug.get()
            plug.set(0, fast=True)
            plug.set(value, fast=True)
            self.assertEqual(plug.get(), normal)
            self.assertEqual(plug.dataType(), kind)
        cmds.currentUnit(linear="m", angle="rad")
        node.plug("tx").set(2, fast=True)
        self.assertAlmostEqual(node.plug("tx").get(), 2)
        # 角度のget/setはUI単位によらずrad。
        node.plug("rx").set(1, fast=True)
        import math
        self.assertAlmostEqual(node.plug("rx").get(), 1.0)

    def test_reload_rebuilds_registry_and_caches(self):
        """新しい基底・型登録・型情報で再取得でき、独自登録を残さない。"""
        from hlib._core import typeHierarchy
        old_registry = hlib.nodes.Node._registry
        old_registry.register("temporaryRefactorType", hlib.nodes.Node)
        typeHierarchy._INHERITED_TYPES_CACHE["temporaryRefactorType"] = ("temporaryRefactorType",)
        name = cmds.createNode("transform")
        for _ in range(2):
            hlib.reload()
            node = hlib.getNode(name)
            self.assertIs(type(node), hlib.nodes.Transform)
            self.assertIs(type(node.plug("tx")), hlib.plugs.DoubleLinearPlug)
            self.assertIsNot(hlib.nodes.Node._registry, old_registry)
            self.assertIsNone(hlib.nodes.Node._registry.lookup("temporaryRefactorType"))
            from hlib._core import typeHierarchy
            self.assertNotIn("temporaryRefactorType", typeHierarchy._INHERITED_TYPES_CACHE)
            node.plug("tx").set(9, fast=True)
            self.assertEqual(node.plug("tx").get(), 9)
            self.assertIs(hlib.getNode, hlib.cmds.getNode)

    def test_calculation_validation_before_target_resolution(self):
        """不正入力で接続先解決や更新を開始しない。"""
        node = hlib.createNode("addDoubleLinear")
        node.setInput(1, 5)
        with patch.object(type(node), "inputPlug", side_effect=AssertionError("target resolved")):
            with self.assertRaises(ValueError):
                node.setInput(1, float("nan"))
            with self.assertRaises(TypeError):
                node.connectInput(1, object())
        self.assertEqual(node.getInput(1), 5)

    def test_calculation_shared_edit_modes(self):
        """共通化後も戻り値・Undo・fast・接続元の入力形式を維持する。"""
        node = hlib.createNode("addDoubleLinear")
        source = hlib.createNode("addDoubleLinear")
        node.setInput(1, 2)
        self.assertIs(node.setInput(1, 7), node)
        cmds.undo()
        self.assertEqual(node.getInput(1), 2)
        cmds.redo()
        self.assertEqual(node.getInput(1), 7)
        cmds.flushUndo()
        self.assertIs(node.setInput(1, 9, fast=True), node)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertEqual(node.getInput(1), 9)
        for value in (source.outputPlug(), source.outputPlug().fullName(), source.outputPlug().mplug()):
            self.assertIs(node.connectInput(1, value), node)
            self.assertTrue(source.outputPlug().isConnectedTo(node.inputPlug(1)))
            cmds.undo()
            self.assertFalse(source.outputPlug().isConnectedTo(node.inputPlug(1)))

    def test_deferred_entrypoints_share_validation(self):
        """どちらの入口も同じ引数で一度だけMayaへ予約する。"""
        import maya.utils
        from hlib.events import Deferred
        callback = lambda value: value
        for entry in (hlib.executeDeferred, Deferred.call):
            with patch.object(maya.utils, "executeDeferred") as enqueue:
                self.assertIsNone(entry(callback, 1, flag=True))
                enqueue.assert_called_once_with(callback, 1, flag=True)
                with self.assertRaises(TypeError):
                    entry("print('not callable')")
                self.assertEqual(enqueue.call_count, 1)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
